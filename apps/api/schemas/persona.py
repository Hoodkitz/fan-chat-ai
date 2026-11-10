"""Pydantic schemas for Fan Chat AI."""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from enum import Enum
from apps.core.models import Platform, ModelProfile, FanProfile


class PersonaSet(BaseModel):
    tenant_id: UUID
    persona: str
    writing_style: str
    boundaries: list[str] = Field(default_factory=list)
    prices: dict = Field(default_factory=dict)
    auto_responder_enabled: bool = False
    escalation_threshold: str = "complex"


class PersonaResponse(BaseModel):
    tenant_id: UUID
    persona: str | None = None
    writing_style: str | None = None
    boundaries: list[str] = []
    prices: dict = Field(default_factory=dict)
    auto_responder_enabled: bool = False
    escalation_threshold: str = "complex"
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class FanProfileCreate(BaseModel):
    tenant_id: UUID
    platform: Platform
    platform_user_id: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1, max_length=255)
    preferences: dict = Field(default_factory=dict)
    purchase_history: list[dict] = Field(default_factory=list)
    last_contact: datetime | None = None
    birthday: str | None = None
    timezone: str = "UTC"


class FanProfileUpdate(BaseModel):
    platform: Platform | None = None
    platform_user_id: str | None = None
    username: str | None = None
    preferences: dict | None = None
    purchase_history: list[dict] | None = None
    last_contact: datetime | None = None
    birthday: str | None = None
    timezone: str | None = None


class FanProfileResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    platform: str
    platform_user_id: str
    username: str
    preferences: dict
    purchase_history: list[dict]
    last_contact: datetime | None
    birthday: str | None
    timezone: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageCreate(BaseModel):
    fan_id: UUID
    tenant_id: UUID
    platform: str
    role: str = "fan"
    content: str
    is_automated: bool = False
    model_response: str | None = None


class ChatMessageResponse(BaseModel):
    message_id: str
    fan_id: str
    platform: str
    role: str
    content: str
    timestamp: datetime
    is_automated: bool


class ChatAutoRespond(BaseModel):
    fan_id: UUID
    tenant_id: UUID
    content: str


class ChatIngest(ChatMessageCreate):
    fan_username: str


class StatsResponse(BaseModel):
    total_automated: int
    today: int
    responses: list[dict]
    active_fans: int
    response_rate: float
