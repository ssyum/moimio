"""Private blank forms and completed minor-consent form submissions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MinorFormTemplate(Base):
    __tablename__ = "minor_form_templates"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MinorFormSubmission(Base):
    __tablename__ = "minor_form_submissions"

    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    storage_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    token_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
