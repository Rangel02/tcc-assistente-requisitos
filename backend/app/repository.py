from datetime import datetime
from typing import Dict, List
from sqlmodel import select
from .db import get_session
from .models import InterviewSession

def upsert_session(session_id: str, answers_json: Dict | None, briefing_md: str | None = None):
    with get_session() as s:
        obj = s.get(InterviewSession, session_id)
        now = datetime.utcnow()
        if obj is None:
            obj = InterviewSession(
                session_id=session_id,
                created_at=now,
                updated_at=now,
                answers_json=answers_json,
                briefing_md=briefing_md,
            )
            s.add(obj)
        else:
            obj.updated_at = now
            if answers_json is not None:
                obj.answers_json = answers_json
            if briefing_md is not None:
                obj.briefing_md = briefing_md
        s.commit()

def list_sessions(limit: int = 20) -> List[InterviewSession]:
    with get_session() as s:
        stmt = select(InterviewSession).order_by(InterviewSession.updated_at.desc()).limit(limit)
        return list(s.exec(stmt))

def get_session_by_id(session_id: str) -> InterviewSession | None:
    with get_session() as s:
        return s.get(InterviewSession, session_id)
