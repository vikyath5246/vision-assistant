"""REST endpoints for session management and conversation history"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db import crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions")


class TurnResponse(BaseModel):
    id: int
    role: str
    content: str
    frame_path: Optional[str]
    stt_latency_ms: Optional[int]
    llm_first_token_ms: Optional[int]
    tts_first_audio_ms: Optional[int]
    created_at: str

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    turn_count: int

    class Config:
        from_attributes = True


@router.get("", response_model=List[SessionResponse])
def list_sessions(db: Session = Depends(get_db)):
    sessions = crud.list_sessions(db)
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at.isoformat() if s.created_at else "",
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
            turn_count=len(s.turns)
        )
        for s in sessions
    ]


@router.get("/{session_id}/turns", response_model=List[TurnResponse])
def get_session_turns(session_id: str, db: Session = Depends(get_db)):
    from db.models import ConversationSession
    turns = crud.get_session_turns(db, session_id)
    if not turns:
        session = db.query(ConversationSession).filter_by(id=session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    return [
        TurnResponse(
            id=t.id,
            role=t.role,
            content=t.content,
            frame_path=t.frame_path,
            stt_latency_ms=t.stt_latency_ms,
            llm_first_token_ms=t.llm_first_token_ms,
            tts_first_audio_ms=t.tts_first_audio_ms,
            created_at=t.created_at.isoformat() if t.created_at else ""
        )
        for t in turns
    ]


@router.delete("/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    deleted = crud.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}
