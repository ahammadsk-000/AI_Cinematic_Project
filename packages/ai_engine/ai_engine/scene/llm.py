"""LLM provider abstraction.

Per the locked stack decision, every LLM call goes through this layer so Ollama,
vLLM, an OpenAI-compatible server, etc. can be swapped via config without touching
call sites. Ollama is the default and requires no API key.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import httpx

from ai_engine.config import EngineConfig
from ai_engine.utils.logging import get_logger
from ai_engine.utils.retry import retry

log = get_logger("llm")

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


@runtime_checkable
class LLMClient(Protocol):
    """Minimal chat-completion contract. json_mode requests strict JSON output."""

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str: ...


class OllamaClient:
    """Default. Talks to a local Ollama server (llama3 / mistral / qwen)."""

    def __init__(self, host: str, model: str) -> None:
        self.host = host.rstrip("/")
        self.model = model

    @retry(attempts=3, backoff=1.5, exceptions=(httpx.HTTPError,))
    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.8},
        }
        if json_mode:
            payload["format"] = "json"  # Ollama enforces a valid JSON object
        log.debug("ollama chat model=%s json=%s", self.model, json_mode)
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(f"{self.host}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


class OpenAICompatibleClient:
    """Fallback for any OpenAI-compatible endpoint (vLLM, LM Studio, OpenAI, ...)."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.getenv("CINEFORGE_LLM_API_KEY", "not-needed")

    @retry(attempts=3, backoff=1.5, exceptions=(httpx.HTTPError,))
    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.8,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


def build_llm_client(cfg: EngineConfig) -> LLMClient:
    """Factory honoring cfg.llm_provider. Defaults to Ollama."""
    if cfg.llm_provider == "openai_compatible":
        base = os.getenv("CINEFORGE_LLM_BASE_URL", "http://localhost:8000/v1")
        return OpenAICompatibleClient(base, cfg.llm_model)
    return OllamaClient(cfg.ollama_host, cfg.llm_model)
