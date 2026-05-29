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
]


def get_tools_prompt() -> str:
    lines = [
        "TOOLS YANG TERSEDIA (kalau butuh data real-time, balas SATU baris):",
        'TOOL_CALL: {"tool":"<nama>","args":{...}}',
        "",
    ]
    for t in TOOLS_SCHEMA:
        params = ", ".join(f"{k}={v}" for k, v in t["params"].items()) or "(no args)"
        lines.append(f"- {t['name']}({params})")
    return "\n".join(lines)


_TOOL_PATTERN = re.compile(r'TOOL_CALL:\s*(\{.*\})', re.DOTALL)

def parse_tool_call(text: str) -> Optional[Dict]:
    m = _TOOL_PATTERN.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        if "tool" in data and "args" in data:
            return data
    except json.JSONDecodeError:
        pass
    return None


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