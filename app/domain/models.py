"""Data model. Every table is tenant-scoped (one tenant = one model/creator account or agency)."""
import enum
import uuid

from sqlalchemy import (BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.crypto import EncryptedText
from app.core.db import Base


class Role(str, enum.Enum):
    OWNER = "owner"          # the creator / agency owner
    ASSISTANT = "assistant"  # may review drafts, may not approve sending unless allowed
    VIEWER = "viewer"


class DraftStatus(str, enum.Enum):
    PENDING = "pending"      # waiting for the creator's decision
    APPROVED = "approved"    # approved, ready to send (always with AI disclosure)
    REJECTED = "rejected"
    SENT = "sent"
    ESCALATED = "escalated"  # needs a personal reply, no AI text


def _id():
    return uuid.uuid4()


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=_id)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=_id)
    email = Column(String(320), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    token_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=_id)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default=Role.OWNER.value)


class CreatorProfile(Base):
    """Model-Datenbank: persona, tone, boundaries, prices."""
    __tablename__ = "creator_profiles"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    display_name = Column(String(120), nullable=False)
    persona = Column(EncryptedText, nullable=True)          # personality, interests
    boundaries = Column(JSONB, nullable=False, default=list)  # topics the AI must never engage in
    prices = Column(JSONB, nullable=False, default=dict)      # e.g. {"custom_video": 50}
    escalation_keywords = Column(JSONB, nullable=False, default=list)
    high_value_threshold = Column(Numeric(10, 2), nullable=False, default=100)
    style = Column(JSONB, nullable=True)                      # learned writing style
    auto_outreach_days = Column(Integer, nullable=False, default=14)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Fan(Base):
    """Fan-Datenbank (one record per fan and portal)."""
    __tablename__ = "fans"
    __table_args__ = (UniqueConstraint("tenant_id", "portal", "portal_user_id"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=_id)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    portal = Column(String(40), nullable=False)
    portal_user_id = Column(String(200), nullable=False)
    nickname = Column(String(120), nullable=True)
    real_name = Column(EncryptedText, nullable=True)
    preferences = Column(EncryptedText, nullable=True)
    notes = Column(EncryptedText, nullable=True)
    birthday = Column(Date, nullable=True)
    total_spent = Column(Numeric(12, 2), nullable=False, default=0)
    last_contact_at = Column(DateTime(timezone=True), nullable=True)
    do_not_contact = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(UUID(as_uuid=True), primary_key=True, default=_id)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    fan_id = Column(UUID(as_uuid=True), ForeignKey("fans.id", ondelete="CASCADE"), nullable=False, index=True)
    item = Column(String(200), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    """Chat history (imported from portals or recorded when sent)."""
    __tablename__ = "messages"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    fan_id = Column(UUID(as_uuid=True), ForeignKey("fans.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # in (from fan) | out (from creator)
    body = Column(EncryptedText, nullable=False)
    ai_assisted = Column(Boolean, nullable=False, default=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class Draft(Base):
    """AI-written reply proposal. Never leaves the system without an explicit approval."""
    __tablename__ = "drafts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=_id)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    fan_id = Column(UUID(as_uuid=True), ForeignKey("fans.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="reply")  # reply | outreach
    reason = Column(String(200), nullable=True)
    body = Column(EncryptedText, nullable=True)
    status = Column(String(20), nullable=False, default=DraftStatus.PENDING.value)
    escalation_reason = Column(String(300), nullable=True)
    decided_by = Column(UUID(as_uuid=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(80), nullable=False)
    target = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


TENANT_TABLES = ["creator_profiles", "fans", "purchases", "messages", "drafts", "audit_log"]
