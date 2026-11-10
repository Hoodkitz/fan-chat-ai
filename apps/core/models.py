"""Domain models for Fan Chat AI."""
from enum import Enum
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Platform(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    TWITCH = "twitch"
    INSTAGRAM = "instagram"
    ONLYFANS = "onlyfans"
    FANSLY = "fansly"


class Tenant(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class FanProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    platform: Platform
    platform_user_id: str
    username: str
    preferences: dict = Field(default_factory=dict)
    purchase_history: list[dict] = Field(default_factory=list)
    last_contact: datetime | None = None
    birthday: str | None = None
    timezone: str = "UTC"


class ModelProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    persona: str
    writing_style: str
    boundaries: list[str] = Field(default_factory=list)
    prices: dict = Field(default_factory=dict)
    auto_responder_enabled: bool = False
    escalation_threshold: str = "complex"


class ChatMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    fan_id: UUID
    platform: Platform
    role: str = "fan"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_automated: bool = False
    model_response: str | None = None


class Feedback(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    fan_id: UUID
    rating: int = Field(ge=1, le=5)
    comment: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
