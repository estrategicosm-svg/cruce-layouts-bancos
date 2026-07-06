from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, String, Integer
from datetime import datetime

class Base(DeclarativeBase):
    pass

class AuditableMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=True, default="SYSTEM")
    processing_run_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    workflow_event_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
