# chatbot_service/llm_engine.py
# ==============================================================================
# Tujuan : Thin wrapper untuk vLLM OpenAI-compat endpoint
#          Bener-bener stateless — vLLM sendiri yang handle batching & cache
# ==============================================================================
import asyncio
from typing import List, Dict, Optional, AsyncIterator
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


def _safe_max_tokens(messages: List[Dict[str, str]], requested: int) -> int:
    """Cap max_tokens so that estimated input + output stays within context window."""
    # Rough token estimate: 3 chars ≈ 1 token for mixed Indonesian/English text,
    # plus ~5 special tokens per message turn for role markers.
    estimated_input = sum(len(m.get("content") or "") for m in messages) // 3
    estimated_input += len(messages) * 5
    headroom = cfg.model_max_context - estimated_input - 50  # 50-token safety margin
    return max(64, min(requested, headroom))


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
    max_tokens = _safe_max_tokens(messages, max_tokens)
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


async def generate_stream(
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: Optional[float] = None,
) -> AsyncIterator[str]:
    """Streaming generate — yields tokens as they arrive from vLLM."""
    client = get_client()
    max_tokens = _safe_max_tokens(messages, max_tokens)
    stream = await client.chat.completions.create(
        model=cfg.model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature if temperature is not None else cfg.temperature,
        top_p=cfg.top_p,
        presence_penalty=cfg.presence_penalty,
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content.replace('\x00', '')
            if token:
                yield token