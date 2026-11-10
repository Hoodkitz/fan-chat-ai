"""JWT access tokens. Role is re-read from the DB on every request."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

ISS = "fan-chat-ai"


def create_token(user_id, tenant_id, version: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"iss": ISS, "sub": str(user_id), "tid": str(tenant_id), "ver": version, "iat": now,
                       "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES), "jti": uuid.uuid4().hex},
                      settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], issuer=ISS,
                      options={"require": ["exp", "sub", "tid"]})
