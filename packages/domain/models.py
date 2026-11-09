"""Domain models for Fan Chat AI SaaS."""
from enum import Enum
from datetime import datetime
from typing import Optional, List
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


class FanProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    platform: Platform
    platform_user_id: str
    username: str
    preferences: dict = {}
    purchase_history: list = []
    last_contact: Optional[datetime] = None
    birthday: Optional[str] = None


class ModelProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    persona: str
    writing_style: str
    boundaries: list = []
    prices: dict = {}
    auto_responder_enabled: bool = False


class ChatMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    fan_id: UUID
    platform: Platform
    role: str  # "fan" or "model"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_automated: bool = False
