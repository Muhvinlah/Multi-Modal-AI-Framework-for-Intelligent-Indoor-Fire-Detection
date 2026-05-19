# ==============================================================================
# Tujuan       : Unified wrapper untuk LLM API call (Gemini/Claude/OpenAI)
#                Centralize provider logic biar script lain nggak duplicate
# Usage        : from scripts.llm_client import LLMClient
#                client = LLMClient(provider="gemini")
#                result = client.generate_json(prompt, max_tokens=2000)
# ==============================================================================

import os
import re
import json
import time
from typing import Optional, Any
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """Unified LLM client. Auto-detect provider dari env, atau set manual."""
    
    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or os.getenv("LLM_PROVIDER", "gemini")
        self._init_client()
    
    def _init_client(self):
        if self.provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "❌ GEMINI_API_KEY belum di-set di .env\n"
                    "   Get free key: https://aistudio.google.com/app/apikey"
                )
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError("Run: pip install google-generativeai")
            
            genai.configure(api_key=api_key)
            # Gemini 2.5 Flash — fastest free tier model
            self._model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "max_output_tokens": 2500,
                },
            )
            print(f"[LLM] Initialized Gemini 2.5 Flash (free tier)")
        
        elif self.provider == "claude":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("❌ ANTHROPIC_API_KEY belum di-set di .env")
            try:
                import anthropic
            except ImportError:
                raise ImportError("Run: pip install anthropic")
            
            self._client = anthropic.Anthropic(api_key=api_key)
            # Use latest Haiku model
            self._model_name = "claude-haiku-4-5"
            print(f"[LLM] Initialized Claude Haiku 4.5")
        
        elif self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("❌ OPENAI_API_KEY belum di-set di .env")
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("Run: pip install openai")
            
            self._client = OpenAI(api_key=api_key)
            self._model_name = "gpt-4o-mini"
            print(f"[LLM] Initialized GPT-4o-mini")
        
        else:
            raise ValueError(f"Provider '{self.provider}' tidak supported. Use: gemini/claude/openai")
    
    def _strip_markdown_fence(self, text: str) -> str:
        """Strip ```json...``` fences kalau ada."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()
    
    def generate_text(self, prompt: str, max_tokens: int = 2000) -> str:
        """Generate raw text response. Provider-agnostic."""
        if self.provider == "gemini":
            response = self._model.generate_content(prompt)
            return response.text.strip()
        
        elif self.provider == "claude":
            response = self._client.messages.create(
                model=self._model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        
        elif self.provider == "openai":
            response = self._client.chat.completions.create(
                model=self._model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
    
    def generate_json(self, prompt: str, max_tokens: int = 2000, retries: int = 2) -> Any:
        """Generate JSON response with parsing + retry on failure."""
        last_error = None
        for attempt in range(retries + 1):
            try:
                text = self.generate_text(prompt, max_tokens)
                text = self._strip_markdown_fence(text)
                return json.loads(text)
            except json.JSONDecodeError as e:
                last_error = e
                if attempt < retries:
                    time.sleep(2)
                    continue
        # Final fail — return empty list (graceful degradation)
        print(f"  ⚠️ JSON parse failed after {retries+1} attempts: {last_error}")
        return []
    
    def rate_limit_sleep(self):
        """Sleep sesuai rate limit provider."""
        if self.provider == "claude":
            time.sleep(4)        # Free tier: 15 req/menit → 4 detik gap aman
        else:
            time.sleep(1)        # Paid tier: 1 detik cukup