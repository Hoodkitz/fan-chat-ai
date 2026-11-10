"""Chat management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from apps.api.schemas.persona import ChatMessageCreate, ChatMessageResponse
from apps.db.session import get_session
from apps.db.models import ChatMessage as ChatMessageModel

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("/reply")
async def reply(req: ChatMessageCreate, session: AsyncSession = Depends(get_session)):
    """Send a reply."""
    db_msg = ChatMessageModel(
        id=UUID(req.tenant_id.hex + "_" + datetime.utcnow().strftime("%Y%m%d%H%M%S")),
        tenant_id=req.tenant_id,
        fan_id=req.fan_id,
        platform=req.platform,
        role=req.role,
        content=req.content,
        timestamp=datetime.utcnow(),
        is_automated=req.is_automated or False,
    )
    session.add(db_msg)
    await session.commit()
    return {"status": "sent", "message_id": str(db_msg.id)}


@router.get("/history/{tenant_id}")
async def chat_history(tenant_id: UUID, limit: int = 50, session: AsyncSession = Depends(get_session)):
    """Get all chat history for a tenant."""
    stmt = select(ChatMessageModel).where(ChatMessageModel.tenant_id == tenant_id).order_by(ChatMessageModel.timestamp.desc()).limit(limit)
    result = await session.execute(stmt)
    messages = result.scalars().all()
    return {"tenant_id": str(tenant_id), "messages": [
        {"id": str(m.id), "fan_id": str(m.fan_id), "platform": m.platform, "role": m.role,
         "content": m.content, "timestamp": m.timestamp, "is_automated": m.is_automated}
        for m in messages
    ]}
