# chatbot_service/llm_engine.py
# ==============================================================================
# Tujuan : Thin wrapper untuk vLLM OpenAI-compat endpoint
#          Bener-bener stateless — vLLM sendiri yang handle batching & cache
# ==============================================================================
import asyncio
from typing import List, Dict, Optional
from openai import AsyncOpenAI, APIError, APITimeoutError
from chatbot_service.config import cfg

# Async client — reuse koneksi, hindari overhead per-request
_client: Optional[AsyncOpenAI] = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=cfg.vllm_base_url,
            api_key=cfg.vllm_api_key,
            timeout=cfg.request_timeout,
        )
    return _client


async def health_check() -> bool:
    """Ping vLLM. Dipanggil sama /health endpoint chatbot service."""
    try:
        client = get_client()
        # vLLM expose /v1/models — light & cheap
        await client.models.list()
        return True
    except Exception as e:
        print(f"[LLM] Health check failed: {e}")
        return False


async def generate(
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: Optional[float] = None,
    stop: Optional[List[str]] = None,
) -> str:
    """Generate completion. messages = list of {role, content}.

    Raises:
        APITimeoutError, APIError — caller WAJIB tangani.
    """
    client = get_client()
    try:
        resp = await client.chat.completions.create(
            model=cfg.model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature if temperature is not None else cfg.temperature,
            top_p=cfg.top_p,
            presence_penalty=cfg.presence_penalty,
            stop=stop,
            stream=False,
        )
        content = (resp.choices[0].message.content or "").replace('\x00', '').strip()
        if not content:
            raise ValueError("Model returned empty/null response — model mungkin BASE bukan Instruct")
        return content
    except APITimeoutError:
        raise
    except APIError as e:
        print(f"[LLM] vLLM API error: {e}")
        raise