"""Fan management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from apps.api.schemas.persona import FanProfileCreate, FanProfileResponse, FanProfileUpdate
from apps.db.session import get_session
from apps.db.models import FanProfile as FanProfileModel, Tenant as TenantModel

router = APIRouter(prefix="/fans", tags=["fans"])


@router.post("")
async def create_fan(req: FanProfileCreate, session: AsyncSession = Depends(get_session)):
    tenant = (await session.execute(select(TenantModel).where(TenantModel.id == req.tenant_id))).scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    db = FanProfileModel(
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
    session.add(db)
    await session.commit()
    return db


@router.get("/{fan_id}")
async def get_fan(fan_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(FanProfileModel).where(FanProfileModel.id == fan_id)
    result = await session.execute(stmt)
    fan = result.scalars().first()
    if not fan:
        raise HTTPException(status_code=404, detail="Fan not found")
    return fan


@router.get("/tenant/{tenant_id}")
async def list_fans(tenant_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(FanProfileModel).where(FanProfileModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return [f for f in result.scalars().all()]


@router.put("/{fan_id}")
async def update_fan(fan_id: UUID, req: FanProfileUpdate, session: AsyncSession = Depends(get_session)):
    stmt = select(FanProfileModel).where(FanProfileModel.id == fan_id)
    fan = (await session.execute(stmt)).scalars().first()
    if not fan:
        raise HTTPException(status_code=404, detail="Fan not found")
    
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(fan, field, value)
    await session.commit()
    return {"status": "updated", "id": fan_id}


@router.delete("/{fan_id}")
async def delete_fan(fan_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(FanProfileModel).where(FanProfileModel.id == fan_id)
    fan = (await session.execute(stmt)).scalars().first()
    if not fan:
        raise HTTPException(status_code=404, detail="Fan not found")
    await session.delete(fan)
    await session.commit()
    return {"status": "deleted", "id": fan_id}
