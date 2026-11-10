"""Persona management endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import UUID

router = APIRouter(prefix="/api/v1", tags=["persona"])
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        from packages.storage.persona_engine import PersonaEngine
        _engine = PersonaEngine()
    return _engine


class PersonaSet(BaseModel):
    tenant_id: UUID
    persona: str
    writing_style: str
    boundaries: List[str] = []
    prices: Dict = {}
    auto_responder_enabled: bool = False


@router.post("/persona/set")
async def set_persona(req: PersonaSet):
    engine = get_engine()
    engine.set_persona(str(req.tenant_id), req.persona, req.writing_style, req.boundaries, req.prices)
    return {"status": "set", "tenant_id": str(req.tenant_id)}


@router.get("/persona/{tenant_id}")
async def get_persona(tenant_id: UUID):
    engine = get_engine()
    return engine.get_persona(str(tenant_id))


@router.post("/persona/auto-respond/{tenant_id}/{fan_id}")
async def auto_respond(tenant_id: UUID, fan_id: UUID, message: str):
    engine = get_engine()
    if not engine.should_auto_respond(str(tenant_id)):
        return {"status": "disabled"}
    response = engine.generate_response(str(tenant_id), str(fan_id), message)
    return {"response": response, "is_automated": True}
