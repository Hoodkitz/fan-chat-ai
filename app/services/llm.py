"""LLM adapters: fake (tests), gemini, anthropic (Claude), openai (any OpenAI-compatible API, e.g. OpenRouter).

Every provider raises LLMError on failure; callers turn that into an escalation instead of a 500.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings


class LLMError(RuntimeError):
    """The language model could not produce a draft (outage, quota, bad key, empty answer)."""


class LLM:
    def draft(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


def _post(url: str, headers: dict, payload: dict, retries: int = 2) -> dict:
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code in (429, 500, 502, 503, 529):
                last = LLMError(f"LLM busy (HTTP {r.status_code})")
                continue
            if r.status_code >= 400:
                raise LLMError(f"LLM request rejected (HTTP {r.status_code})")
            return r.json()
        except httpx.HTTPError as e:
            last = LLMError(f"LLM unreachable ({e.__class__.__name__})")
    raise last or LLMError("LLM request failed")


def _key(env_value: str, file_path: str) -> str:
    if env_value:
        return env_value
    try:
        return Path(file_path).read_text().strip()
    except OSError:
        raise LLMError("LLM API key missing")


class FakeLLM(LLM):
    def draft(self, prompt: str) -> str:
        last = ""
        if "NACHRICHT DES FANS:" in prompt:
            lines = [ln for ln in prompt.rsplit("NACHRICHT DES FANS:", 1)[-1].splitlines()
                     if ln.strip() and not ln.strip().startswith("<")]
            last = lines[0].strip()[:60] if lines else ""
        return f"Danke dir für deine Nachricht 😊 ({last})"


class GeminiLLM(LLM):
    def draft(self, prompt: str) -> str:
        data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
                     {"x-goog-api-key": _key(settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_FILE)},
                     {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.7}})
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError):
            raise LLMError("LLM returned no text (possibly blocked by the provider's safety filter)")


class AnthropicLLM(LLM):
    def draft(self, prompt: str) -> str:
        data = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": _key(settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_API_KEY_FILE),
                      "anthropic-version": "2023-06-01"},
                     {"model": settings.ANTHROPIC_MODEL, "max_tokens": 600,
                      "messages": [{"role": "user", "content": prompt}]})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        if not text:
            raise LLMError("LLM returned no text")
        return text


class OpenAICompatibleLLM(LLM):
    def draft(self, prompt: str) -> str:
        data = _post(f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                     {"Authorization": f"Bearer {_key(settings.OPENAI_API_KEY, settings.OPENAI_API_KEY_FILE)}"},
                     {"model": settings.OPENAI_MODEL, "temperature": 0.7,
                      "messages": [{"role": "user", "content": prompt}]})
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text:
            raise LLMError("LLM returned no text")
        return text


PROVIDERS = {"fake": FakeLLM, "gemini": GeminiLLM, "anthropic": AnthropicLLM, "openai": OpenAICompatibleLLM}


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        try:
            _llm = PROVIDERS[settings.LLM_PROVIDER]()
        except KeyError:
            raise LLMError(f"unknown LLM_PROVIDER {settings.LLM_PROVIDER!r}")
    return _llm


def set_llm(llm: LLM) -> None:
    global _llm
    _llm = llm
