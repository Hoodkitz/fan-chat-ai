"""Chat API endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatMessageRequest(BaseModel):
    tenant_id: UUID
    fan_id: UUID
    platform: str
    content: str


@router.post("/chat/send")
async def send_message(req: ChatMessageRequest):
    return {"message_id": str(UUID(int=1)), "status": "sent"}


@router.get("/chat/history/{fan_id}")
async def chat_history(fan_id: UUID, limit: int = 50):
    return {"fan_id": str(fan_id), "messages": []}


@router.post("/chat/auto-respond/{fan_id}")
async def auto_respond(fan_id: UUID):
    return {"fan_id": str(fan_id), "response": "AI generated response", "is_automated": True}


@router.get("/chat/persona/{tenant_id}")
async def get_persona(tenant_id: UUID):
    return {"tenant_id": str(tenant_id), "persona": "", "writing_style": "", "boundaries": []}
