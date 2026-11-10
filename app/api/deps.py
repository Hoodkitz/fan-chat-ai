import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import new_session
from app.core.tokens import decode_token
from app.domain.models import Membership, User

bearer = HTTPBearer(auto_error=False)


@dataclass
class Ctx:
    user: User
    tenant_id: uuid.UUID
    role: str
    db: Session


def ctx(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if creds is None:
        raise HTTPException(401, "Nicht angemeldet")
    try:
        c = decode_token(creds.credentials)
        uid, tid = uuid.UUID(c["sub"]), uuid.UUID(c["tid"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Token ungültig")
    db = new_session(tid, uid)
    try:
        user = db.get(User, uid)
        if user is None or user.token_version != c.get("ver"):
            raise HTTPException(401, "Token widerrufen")
        m = db.query(Membership).filter(Membership.tenant_id == tid, Membership.user_id == uid).one_or_none()
        if m is None:
            raise HTTPException(403, "Kein Zugriff")
        yield Ctx(user, tid, m.role, db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def owner(c: Ctx = Depends(ctx)) -> Ctx:
    if c.role != "owner":
        raise HTTPException(403, "Nur die Creatorin selbst darf das")
    return c


def editor(c: Ctx = Depends(ctx)) -> Ctx:
    if c.role not in ("owner", "assistant"):
        raise HTTPException(403, "Keine Berechtigung")
    return c
