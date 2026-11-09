"""Tests for domain models."""
from packages.domain.models import FanProfile, ModelProfile, ChatMessage, Platform
from uuid import uuid4


def test_fan_profile():
    fp = FanProfile(tenant_id=uuid4(), platform=Platform.TELEGRAM, platform_user_id="123", username="fan1")
    assert fp.platform == Platform.TELEGRAM


def test_model_profile():
    mp = ModelProfile(tenant_id=uuid4(), persona="friendly", writing_style="casual")
    assert mp.auto_responder_enabled is False


def test_chat_message():
    cm = ChatMessage(tenant_id=uuid4(), fan_id=uuid4(), platform=Platform.DISCORD, role="fan", content="hello")
    assert cm.is_automated is False
