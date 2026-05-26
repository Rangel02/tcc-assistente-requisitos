from datetime import datetime
from typing import Optional, Any, Dict
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class InterviewSession(SQLModel, table=True):
    session_id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    answers_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    briefing_md: Optional[str] = None
