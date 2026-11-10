"""SQLAlchemy models."""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, JSON, Text, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default="NOW()")
    is_active = Column(Boolean, default=True)
    fan_profiles = relationship("FanProfile", back_populates="tenant")
    model_profiles = relationship("ModelProfile", back_populates="tenant")


class FanProfile(Base):
    __tablename__ = "fan_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    platform = Column(String(50), nullable=False)
    platform_user_id = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    preferences = Column(JSON, default=dict)
    purchase_history = Column(JSON, default=list)
    last_contact = Column(DateTime, nullable=True)
    birthday = Column(String(50), nullable=True)
    timezone = Column(String(50), default="UTC")
    created_at = Column(DateTime, server_default="NOW()")
    tenant = relationship("Tenant", back_populates="fan_profiles")


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    persona = Column(String(255), nullable=False)
    writing_style = Column(String(255), nullable=False)
    boundaries = Column(JSON, default=list)
    prices = Column(JSON, default=dict)
    auto_responder_enabled = Column(Boolean, default=False)
    escalation_threshold = Column(String(100), default="complex")
    created_at = Column(DateTime, server_default="NOW()")
    tenant = relationship("Tenant", back_populates="model_profiles")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    fan_id = Column(UUID(as_uuid=True), ForeignKey("fan_profiles.id"), nullable=False)
    platform = Column(String(50), nullable=False)
    role = Column(String(50), default="fan")
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    is_automated = Column(Boolean, default=False)
    model_response = Column(Text, nullable=True)
    fan = relationship("FanProfile")
    tenant = relationship("Tenant")
    __table_args__ = ({"extend_existing": True})


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    fan_id = Column(UUID(as_uuid=True), ForeignKey("fan_profiles.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default="NOW()")
    fan = relationship("FanProfile")
    tenant = relationship("Tenant")
