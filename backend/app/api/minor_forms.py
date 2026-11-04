"""Private PDF workflow for participant minor-consent forms."""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
import unicodedata
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_event_admin, ensure_event_writable, get_current_user
from app.core.database import get_db
from app.core.email import send_minor_form_email
from app.core.logging import get_logger
from app.core.urls import get_app_base_url
from app.models.event import Event
from app.models.minor_form import MinorFormSubmission, MinorFormTemplate
from app.models.participant import Participant, RegistrationStatus
from app.models.user import User
from app.services.event_service import get_event_by_id
from app.services.minor_form_service import (
    age_on_date,
    create_upload_token,
    digest_upload_token,
)
from app.services.minor_form_storage import delete_pdf, read_pdf, write_pdf
from app.services.workspace_settings_service import get_email_templates

logger = get_logger(__name__)
router = APIRouter(tags=["minor_forms"])

MAX_PDF_BYTES = 10 * 1024 * 1024
_SAFE_FILENAME_CHARS = re.compile(r"[^\w .()\-]", re.UNICODE)


def _filename(raw: str | None) -> str:
    value = Path((raw or "").replace("\\", "/")).name
    value = "".join(char for char in value if unicodedata.category(char) != "Cc")
    value = _SAFE_FILENAME_CHARS.sub("_", value).strip(" .")
    if not value.lower().endswith(".pdf"):
        value = f"{Path(value).stem or 'consent-form'}.pdf"
    return value[:255]


async def _read_pdf(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"key": "errors.minor_form.file_too_large"},
        )
    if not content.startswith(b"%PDF-") or not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "errors.minor_form.pdf_only"},
        )
    return content, _filename(file.filename)


def _pdf_response(content: bytes, filename: str) -> Response:
    safe_name = _filename(filename)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _get_upload_record(
    db: AsyncSession, token: str
) -> tuple[MinorFormSubmission, Participant, Event]:
    digest = digest_upload_token(token)
    row = (
        await db.execute(
            select(MinorFormSubmission, Participant, Event)
            .join(Participant, Participant.id == MinorFormSubmission.participant_id)
            .join(Event, Event.id == Participant.event_id)
            .where(
                MinorFormSubmission.token_digest == digest,
                Participant.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "errors.minor_form.link_invalid"},
        )
    submission, participant, event = row
    if (
        submission.token_expires_at is None
        or submission.token_expires_at <= datetime.now(timezone.utc)
        or participant.registration_status == RegistrationStatus.CANCELLED
        or age_on_date(participant.date_of_birth, event.start_date) is None
        or age_on_date(participant.date_of_birth, event.start_date) >= 18
    ):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"key": "errors.minor_form.link_expired"},
        )
    return submission, participant, event


@router.get("/api/events/{event_id}/minor-form-template")
async def get_minor_form_template(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    template = await db.get(MinorFormTemplate, event_id)
    return {
        "available": template is not None,
        "filename": template.filename if template else None,
    }


@router.post("/api/events/{event_id}/minor-form-template")
async def upload_minor_form_template(
    event_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    await ensure_event_writable(db, event_id, current_user)
    content, filename = await _read_pdf(file)
    storage_key = write_pdf(content)
    template = await db.get(MinorFormTemplate, event_id)
    previous_key = template.storage_key if template else None
    if template is None:
        template = MinorFormTemplate(event_id=event_id, storage_key=storage_key, filename=filename)
        db.add(template)
    else:
        template.storage_key = storage_key
        template.filename = filename
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        delete_pdf(storage_key)
        raise
    if previous_key:
        delete_pdf(previous_key)
    return {"available": True, "filename": filename}


@router.delete("/api/events/{event_id}/minor-form-template", status_code=204)
async def delete_minor_form_template(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    await ensure_event_writable(db, event_id, current_user)
    template = await db.get(MinorFormTemplate, event_id)
    if template is None:
        return Response(status_code=204)
    storage_key = template.storage_key
    await db.delete(template)
    await db.commit()
    delete_pdf(storage_key)
    return Response(status_code=204)


@router.post(
    "/api/events/{event_id}/participants/{participant_id}/minor-form-email"
)
async def send_minor_form(
    event_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    await ensure_event_writable(db, event_id, current_user)
    participant = await db.scalar(
        select(Participant).where(
            Participant.id == participant_id,
            Participant.event_id == event_id,
            Participant.deleted_at.is_(None),
        )
    )
    if participant is None:
        raise HTTPException(status_code=404, detail={"key": "errors.participant.not_found"})
    if participant.registration_status == RegistrationStatus.CANCELLED:
        raise HTTPException(
            status_code=409,
            detail={"key": "errors.minor_form.participant_cancelled"},
        )
    if age_on_date(participant.date_of_birth, event.start_date) is None or age_on_date(
        participant.date_of_birth, event.start_date
    ) >= 18:
        raise HTTPException(
            status_code=409,
            detail={"key": "errors.minor_form.not_applicable"},
        )
    template = await db.get(MinorFormTemplate, event_id)
    if template is None:
        raise HTTPException(
            status_code=409,
            detail={"key": "errors.minor_form.template_missing"},
        )
    try:
        attachment = read_pdf(template.storage_key)
    except FileNotFoundError as exc:
        logger.exception("minor_form_template_file_missing", event_id=str(event_id))
        raise HTTPException(
            status_code=500,
            detail={"key": "errors.minor_form.template_unavailable"},
        ) from exc

    token, digest, expires_at = create_upload_token()
    submission = await db.get(MinorFormSubmission, participant_id)
    if submission is None:
        submission = MinorFormSubmission(participant_id=participant_id)
        db.add(submission)
    submission.token_digest = digest
    submission.token_expires_at = expires_at
    upload_link = f"{get_app_base_url(request)}/minor-form-upload/{token}"
    lang = participant.preferred_language or "en"
    sent = send_minor_form_email(
        to_email=participant.email,
        first_name=participant.first_name,
        event_name=event.name,
        upload_link=upload_link,
        attachment_name=template.filename,
        attachment_content=attachment,
        lang=lang,
        email_strings=(await get_email_templates(db)).get(lang),
    )
    if not sent:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"key": "errors.email.delivery_failed"},
        )
    await db.commit()
    logger.info(
        "minor_form_email_sent",
        participant_id=str(participant_id),
        event_id=str(event_id),
        sent_by=str(current_user.id),
    )
    return {"sent": True, "expires_at": expires_at.isoformat()}


@router.get("/api/events/{event_id}/minor-form-submissions")
async def list_minor_form_submissions(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    rows = (
        await db.execute(
            select(MinorFormSubmission, Participant)
            .join(Participant, Participant.id == MinorFormSubmission.participant_id)
            .where(
                Participant.event_id == event_id,
                Participant.deleted_at.is_(None),
                MinorFormSubmission.storage_key.is_not(None),
            )
            .order_by(MinorFormSubmission.uploaded_at.desc())
        )
    ).all()
    return {
        "submissions": [
            {
                "participant_id": str(participant.id),
                "first_name": participant.first_name,
                "last_name": participant.last_name,
                "filename": submission.filename,
                "uploaded_at": submission.uploaded_at.isoformat(),
            }
            for submission, participant in rows
        ]
    }


@router.get(
    "/api/events/{event_id}/participants/{participant_id}/minor-form-submission"
)
async def download_minor_form_submission(
    event_id: uuid.UUID,
    participant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    row = (
        await db.execute(
            select(MinorFormSubmission)
            .join(Participant, Participant.id == MinorFormSubmission.participant_id)
            .where(
                Participant.id == participant_id,
                Participant.event_id == event_id,
                Participant.deleted_at.is_(None),
                MinorFormSubmission.storage_key.is_not(None),
            )
        )
    ).scalar_one_or_none()
    if row is None or not row.storage_key or not row.filename:
        raise HTTPException(status_code=404, detail={"key": "errors.minor_form.submission_not_found"})
    try:
        content = read_pdf(row.storage_key)
    except FileNotFoundError as exc:
        logger.exception(
            "minor_form_submission_file_missing",
            participant_id=str(participant_id),
            event_id=str(event_id),
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "errors.minor_form.submission_unavailable"},
        ) from exc
    return _pdf_response(content, row.filename)


@router.delete(
    "/api/events/{event_id}/participants/{participant_id}/minor-form-submission",
    status_code=204,
)
async def delete_minor_form_submission(
    event_id: uuid.UUID,
    participant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    await ensure_event_writable(db, event_id, current_user)
    row = await db.get(MinorFormSubmission, participant_id)
    if row is None:
        return Response(status_code=204)
    participant = await db.get(Participant, participant_id)
    if participant is None or participant.event_id != event_id:
        raise HTTPException(status_code=404, detail={"key": "errors.participant.not_found"})
    storage_key = row.storage_key
    await db.delete(row)
    await db.commit()
    if storage_key:
        delete_pdf(storage_key)
    return Response(status_code=204)


@router.get("/api/public/minor-form-upload/{token}")
async def get_public_minor_form_upload(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    submission, participant, event = await _get_upload_record(db, token)
    return {
        "participant_name": f"{participant.first_name} {participant.last_name}",
        "event_name": event.name,
        "uploaded": submission.storage_key is not None,
        "expires_at": submission.token_expires_at.isoformat(),
    }


@router.post("/api/public/minor-form-upload/{token}")
async def upload_public_minor_form(
    token: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    submission, _, _ = await _get_upload_record(db, token)
    content, filename = await _read_pdf(file)
    storage_key = write_pdf(content)
    previous_key = submission.storage_key
    submission.storage_key = storage_key
    submission.filename = filename
    submission.uploaded_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        delete_pdf(storage_key)
        raise
    if previous_key:
        delete_pdf(previous_key)
    logger.info(
        "minor_form_submitted",
        participant_id=str(submission.participant_id),
    )
    return {"uploaded": True}
