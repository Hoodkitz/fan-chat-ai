"""Stats endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timedelta
from apps.api.schemas.persona import StatsResponse
from apps.db.session import get_session
from apps.db.models import ChatMessage as ChatMessageModel

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/auto-respond")
async def get_auto_respond_stats(session: AsyncSession = Depends(get_session)):
    """Get auto-respond statistics."""
    stmt = select(ChatMessageModel).where(ChatMessageModel.is_automated == True)
    result = await session.execute(stmt)
    automated = result.scalars().all()
    
    total = len(automated)
    today = [m for m in automated if m.timestamp.date() == datetime.utcnow().date()]
    
    return {
        "total_automated": total,
        "today": len(today),
        "responses": [
            {"fan_id": str(m.fan_id), "timestamp": m.timestamp, "platform": m.platform}
            for m in automated[:100]
        ]
    }


@router.get("/engagement/{tenant_id}")
async def get_engagement(tenant_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get engagement stats."""
    # Get fan count
    stmt = select(ChatMessageModel.fan_id).distinct().where(ChatMessageModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    fans = result.scalars().all()
    
    return {
        "tenant_id": str(tenant_id),
        "active_fans": len(fans),
        "last_7_days_messages": 0,  # stub
        "response_rate": 0.85,  # stub
    }
