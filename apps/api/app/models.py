"""Operational tables supplement the domain records retained from v0.1."""
from sqlalchemy import String, Text, JSON, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, now
import uuid


def uid():
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[str] = mapped_column(String, default=now)


class Credential(Base):
    __tablename__ = 'integration_credentials'
    __table_args__ = (UniqueConstraint('org', 'provider'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String)
    ciphertext: Mapped[str] = mapped_column(Text)
    updated: Mapped[str] = mapped_column(String, default=now)


class Job(Base):
    __tablename__ = 'source_sync_jobs'
    __table_args__ = (UniqueConstraint('org', 'source', 'window'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String)
    window: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default='queued')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    updated: Mapped[str] = mapped_column(String, default=now)


class Attachment(Base):
    __tablename__ = 'investigation_attachments'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org: Mapped[str] = mapped_column(String, index=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    media_type: Mapped[str] = mapped_column(String)
    ciphertext: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String)
    created: Mapped[str] = mapped_column(String, default=now)
