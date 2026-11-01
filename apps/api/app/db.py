import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now():
    return datetime.now(timezone.utc).isoformat()

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String, default='admin')
    totp: Mapped[str | None] = mapped_column(String, nullable=True)

class Session(Base):
    __tablename__ = 'sessions'
    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    expires: Mapped[str] = mapped_column(String)

class Record(Base):
    __tablename__ = 'records'
    __table_args__ = (UniqueConstraint('org', 'kind', 'external_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    external_id: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[str] = mapped_column(String, default=now)

engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///./bankguard.db'), hide_parameters=True)
DB = sessionmaker(engine, expire_on_commit=False)

def database():
    with DB() as db:
        yield db
