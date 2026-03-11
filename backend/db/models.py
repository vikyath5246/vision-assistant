"""SQLAlchemy ORM models for conversation persistence"""
import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db.database import Base


class ConversationSession(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)           # UUID from client
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    title = Column(String, nullable=True)           # Auto-set from first user turn

    turns = relationship("Turn", back_populates="session", cascade="all, delete-orphan", order_by="Turn.id")


class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    role = Column(String, nullable=False)           # "user" or "assistant"
    content = Column(Text, nullable=False)
    frame_path = Column(String, nullable=True)      # Relative path to JPEG on disk

    # Performance metrics (Tier 2 observability)
    stt_latency_ms = Column(Integer, nullable=True)
    llm_first_token_ms = Column(Integer, nullable=True)
    tts_first_audio_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("ConversationSession", back_populates="turns")
