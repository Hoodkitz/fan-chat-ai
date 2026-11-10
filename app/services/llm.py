"""LLM adapter. 'fake' is deterministic for tests; 'gemini' uses the Gemini API."""
from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings


class LLM:
    def draft(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class FakeLLM(LLM):
    def draft(self, prompt: str) -> str:
        last = prompt.rsplit("NACHRICHT DES FANS:", 1)[-1].strip().splitlines()[0][:60] if "NACHRICHT DES FANS:" in prompt else ""
        return f"Danke dir für deine Nachricht 😊 ({last})"


class GeminiLLM(LLM):
    def _key(self) -> str:
        return Path(settings.GEMINI_API_KEY_FILE).read_text().strip()

    def draft(self, prompt: str) -> str:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": self._key()}, timeout=60,
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.7}})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = FakeLLM() if settings.LLM_PROVIDER == "fake" else GeminiLLM()
    return _llm


def set_llm(llm: LLM) -> None:
    global _llm
    _llm = llm
