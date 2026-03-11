"""CRUD helpers for conversation persistence"""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from db.models import ConversationSession, Turn

logger = logging.getLogger(__name__)


def get_or_create_session(db: Session, session_id: str) -> ConversationSession:
    session = db.query(ConversationSession).filter_by(id=session_id).first()
    if not session:
        session = ConversationSession(id=session_id)
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info("Created new session: %s", session_id)
    return session


def get_session_turns(db: Session, session_id: str) -> List[Turn]:
    return db.query(Turn).filter_by(session_id=session_id).order_by(Turn.id).all()


def save_turn(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    frame_path: Optional[str] = None,
    stt_latency_ms: Optional[int] = None,
    llm_first_token_ms: Optional[int] = None,
    tts_first_audio_ms: Optional[int] = None,
) -> Turn:
    turn = Turn(
        session_id=session_id,
        role=role,
        content=content,
        frame_path=frame_path,
        stt_latency_ms=stt_latency_ms,
        llm_first_token_ms=llm_first_token_ms,
        tts_first_audio_ms=tts_first_audio_ms,
    )
    db.add(turn)

    # Auto-set session title from first user turn
    if role == "user":
        session = db.query(ConversationSession).filter_by(id=session_id).first()
        if session and not session.title:
            session.title = content[:60] + ("..." if len(content) > 60 else "")

    db.commit()
    db.refresh(turn)
    return turn


def list_sessions(db: Session) -> List[ConversationSession]:
    return db.query(ConversationSession).order_by(ConversationSession.updated_at.desc()).all()


def delete_session(db: Session, session_id: str) -> bool:
    session = db.query(ConversationSession).filter_by(id=session_id).first()
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True
