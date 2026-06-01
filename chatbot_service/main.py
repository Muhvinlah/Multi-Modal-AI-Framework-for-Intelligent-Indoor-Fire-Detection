# chatbot_service/main.py
# ==============================================================================
# Tujuan : Entry point chatbot service (FastAPI, port 8001)
#          STATELESS — bisa di-restart kapanpun tanpa pengaruh dashboard
# ==============================================================================
import uuid
import json
import traceback
from contextlib import asynccontextmanager
from typing import List, Dict, Optional

import openai
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from chatbot_service.config import cfg
from chatbot_service.llm_engine import generate, generate_stream, health_check
from chatbot_service.prompt_builder import build_messages
from chatbot_service.intent_router import classify_intent, smalltalk_response, out_of_domain_response
from chatbot_service.rag_engine import load_rag_engine, retrieve
from chatbot_service.chat_tools import (
    get_tools_prompt, parse_tool_call, dispatch, format_tool_result,
)
from chatbot_service.conversation import build_effective_history


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print(f"Chatbot Service starting on :{cfg.port}")
    print(f"  vLLM endpoint : {cfg.vllm_base_url}")
    print(f"  Model         : {cfg.model_name}")
    print("=" * 50)

    # Ping vLLM — kalau gagal, service tetap jalan (degraded)
    try:
        ok = await health_check()
        print(f"[Startup] vLLM reachable: {ok}")
    except Exception as e:
        print(f"[Startup] vLLM not reachable: {e} — service jalan degraded")

    # Load RAG — fail-soft per komponen
    try:
        load_rag_engine()
    except Exception as e:
        print(f"[Startup] RAG load failed: {e} — service tetap jalan tanpa RAG")

    yield
    print("[Shutdown] Chatbot service stopped")


app = FastAPI(title="Chatbot Service - K3 Fire Detection", lifespan=lifespan)


# === Pydantic models ===

class SensorContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    camera_id: Optional[str] = None
    mq2: float = 0.0
    mq4: float = 0.0
    mq5: float = 0.0
    mq7: float = 0.0
    mq135: float = 0.0
    temperature: float = 0.0
    humidity: float = 0.0
    flame_detected: bool = False
    lstm_score: Optional[float] = None


class ChatRequest(BaseModel):
    pertanyaan: str = Field(..., min_length=1, max_length=2000)
    history: Optional[List[Dict[str, str]]] = None
    sensor_context: Optional[SensorContext] = None


class ChatResponse(BaseModel):
    message_id: str
    reply: str
    intent: str
    tool_used: Optional[str] = None
    context_used: Optional[str] = None
    report_url: Optional[str] = None
    report_filename: Optional[str] = None


# === Health endpoint ===

@app.get("/health")
async def health():
    llm_ok = await health_check()
    return {
        "status": "ok" if llm_ok else "degraded",
        "llm": llm_ok,
        "service": "chatbot",
    }


# === Helpers ===

def _build_sensor_block(ctx: SensorContext) -> str:
    parts = [
        f"Camera: {ctx.camera_id or 'unknown'}",
        f"Suhu: {ctx.temperature}C | Kelembapan: {ctx.humidity}%",
        f"MQ-2: {ctx.mq2} | MQ-4: {ctx.mq4} | MQ-5: {ctx.mq5}",
        f"MQ-7 (CO): {ctx.mq7} | MQ-135: {ctx.mq135}",
        f"Flame: {'TERDETEKSI' if ctx.flame_detected else 'tidak ada'}",
    ]
    if ctx.lstm_score is not None:
        level = "ANOMALI TINGGI" if ctx.lstm_score >= 0.5 else "normal"
        parts.append(f"LSTM Anomaly: {ctx.lstm_score:.2f} ({level})")
    return " | ".join(parts)


def _llm_error(e: Exception) -> HTTPException:
    """Map openai exceptions ke HTTP status yang sesuai."""
    if isinstance(e, openai.APITimeoutError):
        return HTTPException(504, "LLM terlalu lama merespons — coba lagi.")
    if isinstance(e, openai.APIError) and getattr(e, "status_code", 0) >= 500:
        return HTTPException(503, "LLM sedang tidak tersedia.")
    if isinstance(e, openai.APIError):
        return HTTPException(502, f"LLM error: {e}")
    return HTTPException(500, f"Internal error: {e}")


# === Main chat endpoint ===

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    pertanyaan = req.pertanyaan.strip()
    has_sensor = req.sensor_context is not None

    # 1. Intent classification
    intent = classify_intent(pertanyaan, has_sensor_context=has_sensor)

    # 2. Fast-path: no LLM call for smalltalk or out-of-domain
    if intent == "smalltalk":
        return ChatResponse(
            message_id=uuid.uuid4().hex[:16],
            reply=smalltalk_response(pertanyaan),
            intent=intent,
        )
    if intent == "out_of_domain":
        return ChatResponse(
            message_id=uuid.uuid4().hex[:16],
            reply=out_of_domain_response(),
            intent=intent,
        )

    # 3. Sensor block
    sensor_block = _build_sensor_block(req.sensor_context) if has_sensor else ""

    # 4. RAG retrieve
    rag_context = ""
    if intent in ("rag_query", "system_meta"):
        try:
            rag_result = retrieve(pertanyaan, req.sensor_context)
            rag_context = rag_result.get("context", "")
        except Exception as e:
            print(f"[Chat] RAG error: {e}")

    # 5. Build conversation history
    effective_history = build_effective_history(req.history or [])

    # 6. Tool-calling first pass
    tool_result_text = ""
    tool_used = None
    report_url = None
    report_filename = None

    if intent == "tool_needed":
        # Minimal first-pass: only the tool selector prompt + sensor data.
        # Deliberately skips the K3 assistant instructions so the model cannot
        # generate a full formatted response — it should output only one TOOL_CALL line.
        sys_tool = get_tools_prompt()
        if sensor_block:
            sys_tool += f"\n\nData sensor saat ini: {sensor_block}"
        first_pass_msgs = [
            {"role": "system", "content": sys_tool},
            {"role": "user", "content": pertanyaan},
        ]
        try:
            first_pass = await generate(first_pass_msgs, max_tokens=150)
        except Exception as e:
            traceback.print_exc()
            raise _llm_error(e)

        tool_call = parse_tool_call(first_pass)
        if tool_call:
            tool_used = tool_call["tool"]
            result = await dispatch(tool_call["tool"], tool_call["args"])
            tool_result_text = format_tool_result(tool_call["tool"], result)
            if tool_used == "generate_report" and result.get("ok"):
                data = result.get("data", {})
                if data.get("ok"):
                    report_url = data.get("download_url")
                    report_filename = data.get("filename")
        else:
            # Model chose not to call a tool — escalate to full RAG answer
            intent = "rag_query"

    # 7. Final generation
    messages, max_tok = build_messages(
        pertanyaan, rag_context, sensor_block, tool_result_text,
        effective_history, intent,
    )
    try:
        reply = await generate(messages, max_tokens=max_tok)
    except Exception as e:
        traceback.print_exc()
        raise _llm_error(e)

    return ChatResponse(
        message_id=uuid.uuid4().hex[:16],
        reply=reply,
        intent=intent,
        tool_used=tool_used,
        context_used=rag_context[:500] or None,
        report_url=report_url,
        report_filename=report_filename,
    )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming version of /api/chat. Client reads text/event-stream tokens."""
    pertanyaan = req.pertanyaan.strip()
    has_sensor = req.sensor_context is not None
    msg_id = uuid.uuid4().hex[:16]

    async def event_stream():
        intent = classify_intent(pertanyaan, has_sensor_context=has_sensor)

        # Fast paths — single SSE event
        if intent == "smalltalk":
            reply = smalltalk_response(pertanyaan)
            yield f"data: {json.dumps({'token': reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'message_id': msg_id, 'intent': intent})}\n\n"
            return
        if intent == "out_of_domain":
            reply = out_of_domain_response()
            yield f"data: {json.dumps({'token': reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'message_id': msg_id, 'intent': intent})}\n\n"
            return

        sensor_block = _build_sensor_block(req.sensor_context) if has_sensor else ""

        rag_context = ""
        if intent in ("rag_query", "system_meta"):
            try:
                rag_result = retrieve(pertanyaan, req.sensor_context)
                rag_context = rag_result.get("context", "")
            except Exception as e:
                print(f"[Stream] RAG error: {e}")

        effective_history = build_effective_history(req.history or [])

        tool_result_text = ""
        tool_used = None
        report_url = None
        report_filename = None

        if intent == "tool_needed":
            sys_tool = get_tools_prompt()
            if sensor_block:
                sys_tool += f"\n\nData sensor saat ini: {sensor_block}"
            first_pass_msgs = [
                {"role": "system", "content": sys_tool},
                {"role": "user", "content": pertanyaan},
            ]
            try:
                first_pass = await generate(first_pass_msgs, max_tokens=150)
            except Exception as e:
                traceback.print_exc()
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                return

            tool_call = parse_tool_call(first_pass)
            if tool_call:
                tool_used = tool_call["tool"]
                result = await dispatch(tool_call["tool"], tool_call["args"])
                tool_result_text = format_tool_result(tool_call["tool"], result)
                if tool_used == "generate_report" and result.get("ok"):
                    data = result.get("data", {})
                    if data.get("ok"):
                        report_url = data.get("download_url")
                        report_filename = data.get("filename")
            else:
                # Model chose not to call a tool — fall through to full RAG generation
                intent = "rag_query"

        messages, max_tok = build_messages(
            pertanyaan, rag_context, sensor_block, tool_result_text,
            effective_history, intent,
        )
        try:
            async for token in generate_stream(messages, max_tokens=max_tok):
                yield f"data: {json.dumps({'token': token})}\n\n"
            done_payload = {
                'done': True, 'message_id': msg_id, 'intent': intent,
                'tool_used': tool_used, 'context_used': rag_context[:500] or None,
            }
            if report_url:
                done_payload['report_url'] = report_url
                done_payload['report_filename'] = report_filename
            yield f"data: {json.dumps(done_payload)}\n\n"
        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot_service.main:app", host=cfg.host, port=cfg.port, reload=False)
