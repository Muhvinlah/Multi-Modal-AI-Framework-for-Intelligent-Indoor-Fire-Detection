# chatbot_service/config.py
# ==============================================================================
# Tujuan : Konfigurasi terpusat chatbot service, terisolasi dari dashboard
# ==============================================================================
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatbotConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === vLLM server (OpenAI-compat endpoint) ===
    vllm_base_url: str = "http://localhost:8002/v1"
    vllm_api_key: str = "EMPTY"
    chatbot_model_name: str = "qwen-k3"

    # === Generation params ===
    # vLLM max-model-len = 4096. System prompt alone ≈ 750t; with RAG+history input
    # can reach 2700t, leaving only ~1300t for output. Dynamic cap in llm_engine.py
    # enforces input+output <= model_max_context automatically.
    model_max_context: int = 4096
    max_tokens_short: int = 256
    max_tokens_medium: int = 600
    max_tokens_long: int = 900
    temperature: float = 0.4
    top_p: float = 0.9
    presence_penalty: float = 0.3
    request_timeout: float = 90.0

    # === Callback ke dashboard untuk real-time data ===
    dashboard_base_url: str = "http://localhost:8000"
    dashboard_api_key: str = ""
    dashboard_timeout: float = 5.0

    # === RAG ===
    chroma_db_path: str = "./chroma_db_native"
    chroma_collection: str = "k3_knowledge"
    embedding_model_name: str = "intfloat/multilingual-e5-base"
    reranker_model_name: str = ""
    rag_bm25_weight: float = 0.4
    rag_dense_weight: float = 0.6
    rag_top_k_retrieve: int = 10
    rag_top_k_final: int = 3
    rag_context_max_chars: int = 800
    bm25_index_path: str = "models/bm25_index.pkl"

    # === Service ===
    host: str = "0.0.0.0"
    chatbot_port: int = 8001

    # Convenience aliases agar kode lain tidak perlu diubah
    @property
    def model_name(self) -> str:
        return self.chatbot_model_name

    @property
    def chromadb_path(self) -> str:
        return self.chroma_db_path

    @property
    def chromadb_collection(self) -> str:
        return self.chroma_collection

    @property
    def port(self) -> int:
        return self.chatbot_port


cfg = ChatbotConfig()
