# ==============================================================================
# Tujuan       : Tool registry untuk chatbot — kasih bot kemampuan "action"
#                Pattern: bot generate JSON tool call → dispatcher eksekusi →
#                hasil diinjeksi balik ke context → bot generate final answer
# Caller       : app.chatbot
# Main Functions: get_tools_prompt(), dispatch_tool_call(), parse_tool_call()
# ==============================================================================

import json
import re
from typing import Dict, Optional
from datetime import datetime


# === Tool definitions ===
# Schema dipake buat inject ke system prompt, biar SLM tau tool apa yang available.
TOOLS_SCHEMA = [
    {
        "name": "get_sensor_now",
        "description": "Ambil snapshot sensor terkini untuk 1 kamera. Pakai kalau user nanya kondisi sensor saat ini.",
        "parameters": {
            "camera_id": "string (opsional, default: kamera aktif)"
        },
        "example_call": '{"tool":"get_sensor_now","args":{"camera_id":"cam1"}}',
    },
    {
        "name": "get_camera_list",
        "description": "List semua kamera yang aktif di sistem. Pakai kalau user nanya 'ada berapa kamera' atau 'kamera mana aja'.",
        "parameters": {},
        "example_call": '{"tool":"get_camera_list","args":{}}',
    },
    {
        "name": "query_lstm_history",
        "description": "Ambil tren anomaly score LSTM untuk N menit terakhir. Pakai kalau user nanya tren/pattern/perubahan.",
        "parameters": {
            "camera_id": "string",
            "minutes": "integer (1-60, default: 10)"
        },
        "example_call": '{"tool":"query_lstm_history","args":{"camera_id":"cam1","minutes":10}}',
    },
    {
        "name": "query_alert_history",
        "description": "List alert/notifikasi yang pernah ke-trigger. Pakai kalau user nanya 'kapan terakhir bahaya' atau 'history alert'.",
        "parameters": {
            "limit": "integer (default: 5, max: 20)"
        },
        "example_call": '{"tool":"query_alert_history","args":{"limit":5}}',
    },
]


def get_tools_prompt() -> str:
    """Generate prompt section yang ngenalin tools ke SLM."""
    lines = [
        "TOOLS YANG TERSEDIA:",
        "Kalau pertanyaan butuh data real-time (sensor sekarang, tren, history),",
        "balas dengan SATU baris JSON di format ini, JANGAN dijawab langsung:",
        'TOOL_CALL: {"tool":"<nama>","args":{...}}',
        "",
    ]
    for t in TOOLS_SCHEMA:
        lines.append(f"- {t['name']}: {t['description']}")
        if t["parameters"]:
            params_str = ", ".join(f"{k}={v}" for k, v in t["parameters"].items())
            lines.append(f"  Params: {params_str}")
        lines.append(f"  Contoh: TOOL_CALL: {t['example_call']}")
    lines.append("")
    lines.append("Kalau pertanyaan BUKAN butuh tool (pertanyaan K3 umum, prosedur, dll), jawab langsung pakai pengetahuan yang tersedia.")
    return "\n".join(lines)


def _extract_balanced_json(text: str, start: int) -> Optional[str]:
    """Ambil objek JSON lengkap mulai dari '{' di posisi `start`, hormati nested braces & string."""
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_tool_call(llm_response: str) -> Optional[Dict]:
    """Parse LLM output, deteksi tool call. Return dict {tool, args} atau None.

    Pakai balanced-brace scanner, bukan regex non-greedy — biar nested
    object di `args` (mis. {"args":{"camera_id":"cam1"}}) tetap ke-parse.
    """
    marker = re.search(r"TOOL_CALL\s*:\s*", llm_response, re.IGNORECASE)
    if not marker:
        return None
    brace_start = llm_response.find("{", marker.end())
    if brace_start == -1:
        return None
    json_str = _extract_balanced_json(llm_response, brace_start)
    if not json_str:
        return None
    try:
        parsed = json.loads(json_str)
        if "tool" not in parsed:
            return None
        return {
            "tool": parsed["tool"],
            "args": parsed.get("args", {}),
        }
    except json.JSONDecodeError:
        return None


# === Dispatchers ===
def _tool_get_sensor_now(args: Dict, fallback_ctx=None) -> Dict:
    """Get current sensor snapshot."""
    try:
        from app.sensor import get_latest_snapshot
        camera_id = args.get("camera_id") or (fallback_ctx.camera_id if fallback_ctx else None)
        snapshot = get_latest_snapshot(camera_id)
        if not snapshot:
            return {"error": f"Snapshot kamera {camera_id} tidak tersedia"}
        return {
            "camera_id": camera_id,
            "snapshot": snapshot,
            "ts": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": f"Failed get_sensor_now: {e}"}


def _tool_get_camera_list(args: Dict, **kwargs) -> Dict:
    """List active cameras."""
    try:
        from app.camera import get_camera_list
        cameras = get_camera_list()
        return {
            "count": len(cameras),
            "cameras": cameras,
        }
    except Exception as e:
        return {"error": f"Failed get_camera_list: {e}"}


def _tool_query_lstm_history(args: Dict, **kwargs) -> Dict:
    """Get LSTM score trend untuk N menit terakhir."""
    try:
        from app.lstm_anomaly import query_score_history
        camera_id = args.get("camera_id")
        minutes = int(args.get("minutes", 10))
        minutes = max(1, min(minutes, 60))

        history = query_score_history(camera_id, minutes)
        if not history:
            return {"error": f"Belum ada data history untuk {camera_id}"}

        scores = [h["score"] for h in history]
        return {
            "camera_id": camera_id,
            "minutes": minutes,
            "samples": len(scores),
            "avg_score": round(sum(scores) / len(scores), 4),
            "max_score": round(max(scores), 4),
            "min_score": round(min(scores), 4),
            "trend": "naik" if scores[-1] > scores[0] else "turun",
            "latest": round(scores[-1], 4),
        }
    except Exception as e:
        return {"error": f"Failed query_lstm_history: {e}"}


def _tool_query_alert_history(args: Dict, **kwargs) -> Dict:
    """Query recent alert history."""
    limit = min(int(args.get("limit", 5)), 20)
    try:
        from app.notification import get_recent_alerts
        alerts = get_recent_alerts(limit)
        return {
            "count": len(alerts),
            "alerts": alerts,
        }
    except (ImportError, AttributeError):
        return {
            "count": 0,
            "alerts": [],
            "note": "Alert history belum tersimpan persistent — fitur ini perlu DB",
        }
    except Exception as e:
        return {"error": f"Failed query_alert_history: {e}"}


_TOOL_REGISTRY = {
    "get_sensor_now": _tool_get_sensor_now,
    "get_camera_list": _tool_get_camera_list,
    "query_lstm_history": _tool_query_lstm_history,
    "query_alert_history": _tool_query_alert_history,
}


def dispatch_tool_call(tool_name: str, args: Dict, fallback_ctx=None) -> Dict:
    """Execute tool by name. Return result dict atau error dict."""
    if tool_name not in _TOOL_REGISTRY:
        return {"error": f"Tool '{tool_name}' nggak ada. Available: {list(_TOOL_REGISTRY.keys())}"}
    try:
        return _TOOL_REGISTRY[tool_name](args, fallback_ctx=fallback_ctx)
    except Exception as e:
        return {"error": f"Tool execution error: {e}"}


def format_tool_result(tool_name: str, result: Dict) -> str:
    """Format tool result jadi text untuk inject ke prompt LLM second-pass."""
    if "error" in result:
        return f"HASIL TOOL {tool_name}: ERROR — {result['error']}"
    return f"HASIL TOOL {tool_name}:\n{json.dumps(result, indent=2, ensure_ascii=False)}"
