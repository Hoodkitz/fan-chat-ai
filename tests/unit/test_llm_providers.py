"""Provider adapters (HTTP mocked) and graceful degradation when the model is down."""
import httpx
import pytest

from app.core.config import settings
from app.services import llm


class Resp:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


def test_anthropic_and_openai_parse(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers))
        if "anthropic" in url:
            return Resp(200, {"content": [{"type": "text", "text": " Hallo Süßer 😘 "}]})
        return Resp(200, {"choices": [{"message": {"content": "Hey du!"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.AnthropicLLM().draft("x") == "Hallo Süßer 😘"
    assert llm.OpenAICompatibleLLM().draft("x") == "Hey du!"
    assert calls[0][1]["anthropic-version"] and calls[1][1]["Authorization"] == "Bearer k"


def test_errors_become_llmerror(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp(503, {}))
    with pytest.raises(llm.LLMError):
        llm.OpenAICompatibleLLM().draft("x")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp(200, {"candidates": []}))
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "k")
    with pytest.raises(llm.LLMError):
        llm.GeminiLLM().draft("x")
