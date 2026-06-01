# chatbot_service/chat_tools.py
# ==============================================================================
# Tujuan : Tool dispatcher — fetch real-time data dari Dashboard service
#          Pakai httpx async, ada retry + timeout. Kalau dashboard down,
#          tool gagal gracefully (bot fallback ke knowledge umum)
# ==============================================================================
import json
import re
from typing import Dict, Optional
import httpx
from chatbot_service.config import cfg

_http: Optional[httpx.AsyncClient] = None

def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            base_url=cfg.dashboard_base_url,
            timeout=cfg.dashboard_timeout,
            headers={"X-Internal-Token": cfg.dashboard_api_key} if cfg.dashboard_api_key else {},
        )
    return _http


TOOLS_SCHEMA = [
    {
        "name": "get_sensor_now",
        "endpoint": "/api/internal/sensor-snapshot",
        "params": {"camera_id": "string?"},
    },
    {
        "name": "get_camera_list",
        "endpoint": "/api/internal/camera-list",
        "params": {},
    },
    {
        "name": "query_lstm_history",
        "endpoint": "/api/internal/lstm-history",
        "params": {"camera_id": "string", "minutes": "int"},
    },
    {
        "name": "query_alert_history",
        "endpoint": "/api/internal/alert-history",
        "params": {"limit": "int"},
    },
    {
        "name": "generate_report",
        "endpoint": "/api/internal/generate-report",
        "params": {"report_type": "string (sensor|incident)", "camera_id": "string?", "minutes": "int?", "limit": "int?"},
    },
]


def get_tools_prompt() -> str:
    tool_lines = []
    for t in TOOLS_SCHEMA:
        params = ", ".join(f"{k}={v}" for k, v in t["params"].items()) or "(no args)"
        tool_lines.append(f"  - {t['name']}({params})")
    tools_str = "\n".join(tool_lines)
    return (
        "TOOL SELECTOR — ATURAN MUTLAK:\n"
        "Balas dengan TEPAT SATU baris berikut. Tidak boleh ada teks lain.\n"
        "Tidak ada penjelasan. Tidak ada laporan. Hanya satu baris ini:\n\n"
        'TOOL_CALL: {"tool":"<nama_tool>","args":{...}}\n\n'
        f"Tool tersedia:\n{tools_str}\n\n"
        "CATATAN generate_report: tool ini mengambil semua data secara INTERNAL — "
        "jangan panggil query_alert_history atau tool lain sebelumnya."
    )


def parse_tool_call(text: str) -> Optional[Dict]:
    """Extract the last valid TOOL_CALL from text using balanced-brace matching.

    Uses balanced-brace scanning instead of greedy regex so multiple TOOL_CALL
    blocks in one response are all parsed; the last valid one is returned
    (models tend to put their 'final' intent last).
    """
    last_valid: Optional[Dict] = None
    for m in re.finditer(r'TOOL_CALL:\s*\{', text):
        start = m.end() - 1  # position of opening '{'
        depth = 0
        for i, ch in enumerate(text[start:]):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start: start + i + 1])
                        if 'tool' in data and 'args' in data:
                            last_valid = data
                    except json.JSONDecodeError:
                        pass
                    break
    return last_valid


async def dispatch(tool_name: str, args: Dict) -> Dict:
    """Call dashboard endpoint. Return dict dengan 'ok' flag."""
    schema = next((t for t in TOOLS_SCHEMA if t["name"] == tool_name), None)
    if not schema:
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}

    try:
        resp = await _client().get(schema["endpoint"], params=args)
        resp.raise_for_status()
        return {"ok": True, "data": resp.json()}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Dashboard timeout — service mungkin sibuk"}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Dashboard error: {e}"}


def format_tool_result(tool_name: str, result: Dict) -> str:
    if not result.get("ok"):
        return f"[Tool {tool_name} gagal: {result.get('error')}. Jawab dari pengetahuan umum.]"
    return f"[Tool {tool_name} hasil]: {json.dumps(result['data'], ensure_ascii=False)}"