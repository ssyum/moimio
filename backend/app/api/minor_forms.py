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
from app.models.minor_form import (
    MinorFormSubmission,
    MinorFormSubmissionFile,
    MinorFormTemplate,
)
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
MAX_TEMPLATE_BYTES = 18 * 1024 * 1024
MAX_SUBMISSION_FILES = 2
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
    templates = (
        await db.scalars(
            select(MinorFormTemplate)
            .where(MinorFormTemplate.event_id == event_id)
            .order_by(MinorFormTemplate.filename, MinorFormTemplate.storage_key)
        )
    ).all()
    return {
        "available": bool(templates),
        "files": [
            {"storage_key": template.storage_key, "filename": template.filename}
            for template in templates
        ],
    }


@router.post("/api/events/{event_id}/minor-form-template")
async def upload_minor_form_template(
    event_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    await ensure_event_writable(db, event_id, current_user)
    if not files:
        raise HTTPException(
            status_code=422,
            detail={"key": "errors.minor_form.pdf_only"},
        )

    uploaded: list[tuple[str, str]] = []
    try:
        existing_templates = (
            await db.scalars(
                select(MinorFormTemplate).where(
                    MinorFormTemplate.event_id == event_id
                )
            )
        ).all()
        try:
            existing_size = sum(
                len(read_pdf(template.storage_key)) for template in existing_templates
            )
        except FileNotFoundError as exc:
            logger.exception(
                "minor_form_template_file_missing",
                event_id=str(event_id),
            )
            raise HTTPException(
                status_code=500,
                detail={"key": "errors.minor_form.template_unavailable"},
            ) from exc
        content_total = existing_size
        for file in files:
            content, filename = await _read_pdf(file)
            content_total += len(content)
            if content_total > MAX_TEMPLATE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={"key": "errors.minor_form.total_too_large"},
                )
            storage_key = write_pdf(content)
            uploaded.append((storage_key, filename))

        db.add_all(
            [
                MinorFormTemplate(
                    event_id=event_id,
                    storage_key=storage_key,
                    filename=filename,
                )
                for storage_key, filename in uploaded
            ]
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        for storage_key, _ in uploaded:
            delete_pdf(storage_key)
        raise
    except SQLAlchemyError:
        await db.rollback()
        for storage_key, _ in uploaded:
            delete_pdf(storage_key)
        raise
    except OSError as exc:
        await db.rollback()
        for storage_key, _ in uploaded:
            delete_pdf(storage_key)
        logger.exception("minor_form_template_storage_failed", event_id=str(event_id))
        raise HTTPException(
            status_code=500,
            detail={"key": "errors.minor_form.template_unavailable"},
        ) from exc
    return {
        "available": True,
        "files": [
            {"storage_key": storage_key, "filename": filename}
            for storage_key, filename in uploaded
        ],
    }


@router.delete(
    "/api/events/{event_id}/minor-form-template/{storage_key}",
    status_code=204,
)
async def delete_minor_form_template(
    event_id: uuid.UUID,
    storage_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    await ensure_event_writable(db, event_id, current_user)
    template = await db.scalar(
        select(MinorFormTemplate).where(
            MinorFormTemplate.event_id == event_id,
            MinorFormTemplate.storage_key == storage_key,
        )
    )
    if template is None:
        return Response(status_code=204)
    await db.delete(template)
    await db.commit()
    try:
        delete_pdf(storage_key)
    except OSError as exc:
        logger.exception(
            "minor_form_template_cleanup_failed",
            event_id=str(event_id),
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "errors.minor_form.cleanup_failed"},
        ) from exc
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
    templates = (
        await db.scalars(
            select(MinorFormTemplate)
            .where(MinorFormTemplate.event_id == event_id)
            .order_by(MinorFormTemplate.filename, MinorFormTemplate.storage_key)
        )
    ).all()
    if not templates:
        raise HTTPException(
            status_code=409,
            detail={"key": "errors.minor_form.template_missing"},
        )
    attachments = []
    try:
        total_size = 0
        for template in templates:
            content = read_pdf(template.storage_key)
            total_size += len(content)
            if total_size > MAX_TEMPLATE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={"key": "errors.minor_form.total_too_large"},
                )
            attachments.append((template.filename, content, "application/pdf"))
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
        attachments=attachments,
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
            select(MinorFormSubmissionFile, Participant)
            .join(
                Participant,
                Participant.id == MinorFormSubmissionFile.participant_id,
            )
            .where(
                Participant.event_id == event_id,
                Participant.deleted_at.is_(None),
            )
            .order_by(
                MinorFormSubmissionFile.uploaded_at.desc(),
                MinorFormSubmissionFile.filename,
            )
        )
    ).all()
    submissions: dict[uuid.UUID, dict] = {}
    for submitted_file, participant in rows:
        submission = submissions.setdefault(
            participant.id,
            {
                "participant_id": str(participant.id),
                "first_name": participant.first_name,
                "last_name": participant.last_name,
                "files": [],
            },
        )
        submission["files"].append(
            {
                "storage_key": submitted_file.storage_key,
                "filename": submitted_file.filename,
                "uploaded_at": (
                    submitted_file.uploaded_at.isoformat()
                    if submitted_file.uploaded_at
                    else None
                ),
            }
        )
    return {
        "submissions": list(submissions.values())
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
    submitted_file = (
        await db.execute(
            select(MinorFormSubmissionFile)
            .join(
                Participant,
                Participant.id == MinorFormSubmissionFile.participant_id,
            )
            .where(
                Participant.id == participant_id,
                Participant.event_id == event_id,
                Participant.deleted_at.is_(None),
            )
            .order_by(MinorFormSubmissionFile.uploaded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if submitted_file is None:
        raise HTTPException(status_code=404, detail={"key": "errors.minor_form.submission_not_found"})
    try:
        content = read_pdf(submitted_file.storage_key)
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
    return _pdf_response(content, submitted_file.filename)


@router.get(
    "/api/events/{event_id}/participants/{participant_id}/minor-form-submissions/{storage_key}"
)
async def download_minor_form_submission_file(
    event_id: uuid.UUID,
    participant_id: uuid.UUID,
    storage_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    submitted_file = await db.scalar(
        select(MinorFormSubmissionFile)
        .join(
            Participant,
            Participant.id == MinorFormSubmissionFile.participant_id,
        )
        .where(
            Participant.id == participant_id,
            Participant.event_id == event_id,
            Participant.deleted_at.is_(None),
            MinorFormSubmissionFile.storage_key == storage_key,
        )
    )
    if submitted_file is None:
        raise HTTPException(
            status_code=404,
            detail={"key": "errors.minor_form.submission_not_found"},
        )
    try:
        content = read_pdf(submitted_file.storage_key)
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
    return _pdf_response(content, submitted_file.filename)


@router.delete(
    "/api/events/{event_id}/participants/{participant_id}/minor-form-submissions/{storage_key}",
    status_code=204,
)
async def delete_minor_form_submission_file(
    event_id: uuid.UUID,
    participant_id: uuid.UUID,
    storage_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await get_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"key": "errors.event.not_found"})
    await ensure_event_admin(db, event_id, current_user)
    await ensure_event_writable(db, event_id, current_user)
    submitted_file = await db.scalar(
        select(MinorFormSubmissionFile)
        .join(
            Participant,
            Participant.id == MinorFormSubmissionFile.participant_id,
        )
        .where(
            Participant.id == participant_id,
            Participant.event_id == event_id,
            MinorFormSubmissionFile.storage_key == storage_key,
        )
    )
    if submitted_file is None:
        return Response(status_code=204)
    await db.delete(submitted_file)
    await db.commit()
    try:
        delete_pdf(storage_key)
    except OSError as exc:
        logger.exception(
            "minor_form_submission_cleanup_failed",
            participant_id=str(participant_id),
            event_id=str(event_id),
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "errors.minor_form.cleanup_failed"},
        ) from exc
    return Response(status_code=204)


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
    participant = await db.get(Participant, participant_id)
    if participant is None or participant.event_id != event_id:
        raise HTTPException(status_code=404, detail={"key": "errors.participant.not_found"})
    submitted_files = (
        await db.scalars(
            select(MinorFormSubmissionFile).where(
                MinorFormSubmissionFile.participant_id == participant_id
            )
        )
    ).all()
    storage_keys = [file.storage_key for file in submitted_files]
    for submitted_file in submitted_files:
        await db.delete(submitted_file)
    if row is not None:
        await db.delete(row)
    await db.commit()
    for storage_key in storage_keys:
        delete_pdf(storage_key)
    return Response(status_code=204)


@router.get("/api/public/minor-form-upload/{token}")
async def get_public_minor_form_upload(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    submission, participant, event = await _get_upload_record(db, token)
    submitted_files = (
        await db.scalars(
            select(MinorFormSubmissionFile)
            .where(
                MinorFormSubmissionFile.participant_id == participant.id
            )
            .order_by(MinorFormSubmissionFile.filename)
        )
    ).all()
    return {
        "participant_name": f"{participant.first_name} {participant.last_name}",
        "event_name": event.name,
        "uploaded": bool(submitted_files),
        "files": [file.filename for file in submitted_files],
        "expires_at": submission.token_expires_at.isoformat(),
    }


@router.post("/api/public/minor-form-upload/{token}")
async def upload_public_minor_form(
    token: str,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    submission, _, _ = await _get_upload_record(db, token)
    if len(files) != MAX_SUBMISSION_FILES:
        raise HTTPException(
            status_code=422,
            detail={"key": "errors.minor_form.submission_file_count"},
        )

    uploaded: list[MinorFormSubmissionFile] = []
    try:
        content_total = 0
        for file in files:
            content, filename = await _read_pdf(file)
            content_total += len(content)
            if content_total > MAX_TEMPLATE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={"key": "errors.minor_form.total_too_large"},
                )
            uploaded.append(
                MinorFormSubmissionFile(
                    participant_id=submission.participant_id,
                    storage_key=write_pdf(content),
                    filename=filename,
                    uploaded_at=datetime.now(timezone.utc),
                )
            )
        previous_files = (
            await db.scalars(
                select(MinorFormSubmissionFile).where(
                    MinorFormSubmissionFile.participant_id
                    == submission.participant_id
                )
            )
        ).all()
        previous_keys = [previous.storage_key for previous in previous_files]
        for previous in previous_files:
            await db.delete(previous)
        db.add_all(uploaded)
        await db.commit()
    except HTTPException:
        await db.rollback()
        for submitted_file in uploaded:
            delete_pdf(submitted_file.storage_key)
        raise
    except SQLAlchemyError:
        await db.rollback()
        for submitted_file in uploaded:
            delete_pdf(submitted_file.storage_key)
        raise
    except OSError as exc:
        await db.rollback()
        for submitted_file in uploaded:
            delete_pdf(submitted_file.storage_key)
        logger.exception(
            "minor_form_submission_storage_failed",
            participant_id=str(submission.participant_id),
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "errors.minor_form.submission_unavailable"},
        ) from exc
    for storage_key in previous_keys:
        delete_pdf(storage_key)
    logger.info(
        "minor_form_submitted",
        participant_id=str(submission.participant_id),
    )
    return {"uploaded": True, "files": [file.filename for file in uploaded]}
