# chatbot_service/config.py
# ==============================================================================
# Tujuan : Konfigurasi terpusat chatbot service, terisolasi dari dashboard
# ==============================================================================
import os
from pydantic import BaseModel


class ChatbotConfig(BaseModel):
    # === vLLM server (OpenAI-compat endpoint) ===
    vllm_base_url: str = os.getenv("VLLM_BASE_URL", "http://localhost:8002/v1")
    vllm_api_key: str = os.getenv("VLLM_API_KEY", "EMPTY")
    model_name: str = os.getenv("CHATBOT_MODEL_NAME", "qwen-k3")

    # === Generation params ===
    # vLLM max-model-len = 4096. Typical input ≈ 900-1200t, leaving 2800-3200t for output.
    max_tokens_short: int = 256
    max_tokens_medium: int = 900
    max_tokens_long: int = 1400
    temperature: float = 0.4
    top_p: float = 0.9
    presence_penalty: float = 0.3
    request_timeout: float = 90.0

    # === Callback ke dashboard untuk real-time data ===
    dashboard_base_url: str = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000")
    dashboard_api_key: str = os.getenv("DASHBOARD_API_KEY", "")
    dashboard_timeout: float = 5.0

    # === RAG (Sprint 2) ===
    chromadb_path: str = os.getenv("CHROMA_DB_PATH", "./chroma_db_native")
    chromadb_collection: str = os.getenv("CHROMA_COLLECTION", "k3_knowledge")
    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base"
    )
    reranker_model_name: str = os.getenv("RERANKER_MODEL_NAME", "")
    rag_bm25_weight: float = float(os.getenv("RAG_BM25_WEIGHT", "0.4"))
    rag_dense_weight: float = float(os.getenv("RAG_DENSE_WEIGHT", "0.6"))
    rag_top_k_retrieve: int = int(os.getenv("RAG_TOP_K_RETRIEVE", "10"))
    rag_top_k_final: int = int(os.getenv("RAG_TOP_K_FINAL", "3"))
    rag_context_max_chars: int = int(os.getenv("RAG_CONTEXT_MAX_CHARS", "800"))
    bm25_index_path: str = os.getenv("BM25_INDEX_PATH", "models/bm25_index.pkl")

    # === Service ===
    host: str = "0.0.0.0"
    port: int = int(os.getenv("CHATBOT_PORT", "8001"))


cfg = ChatbotConfig()
