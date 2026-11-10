"""Persona management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from apps.api.schemas.persona import (
    PersonaSet, PersonaResponse, FanProfileCreate, FanProfileResponse,
    ChatAutoRespond, ChatMessageCreate, ChatMessageResponse
)
from apps.db.session import get_session
from apps.db.models import (
    ModelProfile as ModelProfileModel, FanProfile as FanProfileModel,
    ChatMessage as ChatMessageModel
)

router = APIRouter(prefix="/persona", tags=["persona"])


@router.post("/set")
async def set_persona(req: PersonaSet, session: AsyncSession = Depends(get_session)):
    stmt = select(ModelProfileModel).where(ModelProfileModel.tenant_id == req.tenant_id)
    existing = (await session.execute(stmt)).scalars().first()
    if existing:
        for field, value in req.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        existing.updated_at = datetime.utcnow()
        await session.commit()
    else:
        from apps.db.models import Tenant
        tenant = (await session.execute(select(Tenant).where(Tenant.id == req.tenant_id))).scalars().first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        db = ModelProfileModel(
            id=UUID(req.tenant_id.hex + "_model_"),
            tenant_id=req.tenant_id,
            persona=req.persona,
            writing_style=req.writing_style,
            boundaries=req.boundaries,
            prices=req.prices,
            auto_responder_enabled=req.auto_responder_enabled,
            escalation_threshold=req.escalation_threshold,
        )
        session.add(db)
        await session.commit()
    return {"status": "set", "tenant_id": str(req.tenant_id)}


@router.get("/{tenant_id}")
async def get_persona(tenant_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(ModelProfileModel).where(ModelProfileModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    profile = result.scalars().first()
    if not profile:
        return {"tenant_id": str(tenant_id), "persona": None, "auto_responder_enabled": False}
    return profile


@router.post("/auto-respond/{tenant_id}/{fan_id}")
async def auto_respond(tenant_id: UUID, fan_id: UUID, message: str, session: AsyncSession = Depends(get_session)):
    # Get persona
    stmt = select(ModelProfileModel).where(ModelProfileModel.tenant_id == tenant_id)
    profile = (await session.execute(stmt)).scalars().first()
    if not profile:
        return {"response": "Ich bin gerade nicht verfügbar.", "is_automated": True}
    
    if not profile.auto_responder_enabled:
        return {"response": "Auto-Responder ist deaktiviert.", "is_automated": False}
    
    # Generate response
    response = _generate_ai_response(profile, message)
    
    # Save to chat history
    db_msg = ChatMessageModel(
        id=UUID(str(tenant_id) + "_" + str(fan_id) + "_" + datetime.utcnow().strftime("%Y%m%d%H%M%S")),
        tenant_id=tenant_id,
        fan_id=fan_id,
        platform="unknown",
        role="model",
        content=response,
        timestamp=datetime.utcnow(),
        is_automated=True,
        model_response=response,
    )
    session.add(db_msg)
    await session.commit()
    
    return {"response": response, "is_automated": True}


def _generate_ai_response(profile, message: str) -> str:
    """Generate a response based on persona and message."""
    style = profile.writing_style.lower()
    persona = profile.persona.lower()
    
    # Simple template-based response with persona adaptation
    if "friendly" in style or "friendship" in persona:
        response = f"Hallo! Danke für deine Nachricht. Ich habe dich gesehen. 😊"
    elif "casual" in style:
        response = f"Hey {message.split()[0]}! Wie geht's?"
    else:
        response = f"Danke für deine Nachricht. Ich werde mich umgehend bei dir melden."
    
    # Add personalization based on preferences
    prefs = profile.preferences
    if prefs:
        if "emoji" in prefs and prefs["emoji"]:
            response += " 😊"
        if "shorten" in style:
            response = response[:200] + "..."
    
    return response


@router.post("/fan")
async def create_fan(req: FanProfileCreate, session: AsyncSession = Depends(get_session)):
    # Validate tenant
    from apps.db.models import Tenant
    tenant = (await session.execute(select(Tenant).where(Tenant.id == req.tenant_id))).scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    db_fan = FanProfileModel(
        id=UUID(req.tenant_id.hex + "_fan_" + datetime.utcnow().strftime("%Y%m%d%H%M%S")),
        tenant_id=req.tenant_id,
        platform=req.platform,
        platform_user_id=req.platform_user_id,
        username=req.username,
        preferences=req.preferences or {},
        purchase_history=req.purchase_history or [],
        last_contact=req.last_contact,
        birthday=req.birthday,
        timezone=req.timezone,
    )
    session.add(db_fan)
    await session.commit()
    return db_fan


@router.get("/fan/{fan_id}")
async def get_fan(fan_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(FanProfileModel).where(FanProfileModel.id == fan_id)
    result = await session.execute(stmt)
    fan = result.scalars().first()
    if not fan:
        raise HTTPException(status_code=404, detail="Fan not found")
    return fan


@router.get("/fan/history/{fan_id}")
async def get_chat_history(fan_id: UUID, limit: int = 50, session: AsyncSession = Depends(get_session)):
    stmt = select(ChatMessageModel).where(ChatMessageModel.fan_id == fan_id).order_by(ChatMessageModel.timestamp.desc()).limit(limit)
    result = await session.execute(stmt)
    messages = result.scalars().all()
    return {"fan_id": str(fan_id), "messages": [
        {"id": str(m.id), "platform": m.platform, "role": m.role, "content": m.content, 
         "timestamp": m.timestamp, "is_automated": m.is_automated} for m in messages
    ]}


@router.get("/chat/{tenant_id}/{platform}")
async def get_platform_chat(tenant_id: UUID, platform: str, limit: int = 50, session: AsyncSession = Depends(get_session)):
    """Get chat history for a specific platform."""
    stmt = select(ChatMessageModel).where(ChatMessageModel.tenant_id == tenant_id, ChatMessageModel.platform == platform).order_by(ChatMessageModel.timestamp.desc()).limit(limit)
    result = await session.execute(stmt)
    messages = result.scalars().all()
    return {"platform": platform, "messages": [
        {"id": str(m.id), "fan_id": str(m.fan_id), "role": m.role, "content": m.content,
         "timestamp": m.timestamp, "is_automated": m.is_automated} for m in messages
    ]}


@router.post("/reply")
async def send_reply(req: ChatMessageCreate, session: AsyncSession = Depends(get_session)):
    """Send a reply message."""
    db_msg = ChatMessageModel(
        id=UUID(req.tenant_id.hex + "_" + datetime.utcnow().strftime("%Y%m%d%H%M%S")),
        tenant_id=req.tenant_id,
        fan_id=req.fan_id,
        platform=req.platform,
        role="model",
        content=req.content,
        timestamp=datetime.utcnow(),
        is_automated=req.is_automated or False,
    )
    session.add(db_msg)
    await session.commit()
    return {"status": "sent", "message_id": str(db_msg.id)}
