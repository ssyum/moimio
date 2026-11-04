import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.email import send_minor_form_email
from app.main import app
from app.models.event import Event, EventStatus
from app.models.minor_form import MinorFormSubmission, MinorFormTemplate
from app.models.participant import Participant, RegistrationStatus
from app.models.user import User, UserRole
from app.services.minor_form_service import age_on_date, digest_upload_token


def _admin() -> User:
    return User(
        id=uuid.uuid4(),
        email="minor-forms@test.local",
        hashed_password="test-hash",
        full_name="Test Admin",
        role=UserRole.SUPER_ADMIN,
    )


@pytest.mark.parametrize(
    ("dob", "event_date", "expected"),
    [
        (date(2008, 11, 5), date(2026, 11, 4), 17),
        (date(2008, 11, 4), date(2026, 11, 4), 18),
        (date(2008, 2, 29), date(2026, 2, 28), 17),
        (date(2008, 2, 29), date(2026, 3, 1), 18),
        (None, date(2026, 11, 4), None),
        (date(2027, 1, 1), date(2026, 11, 4), None),
    ],
)
def test_age_is_calculated_on_event_start(dob, event_date, expected):
    assert age_on_date(dob, event_date) == expected


@pytest.mark.asyncio
async def test_minor_form_email_attaches_template_and_creates_private_link(
    client, db, monkeypatch
):
    event = Event(
        name="Gathering",
        start_date=date(2026, 11, 4),
        status=EventStatus.OPEN,
    )
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        date_of_birth=date(2010, 5, 1),
        registration_status=RegistrationStatus.CONFIRMED,
        preferred_language="en",
    )
    template = MinorFormTemplate(
        event_id=event.id,
        storage_key=f"{'a' * 32}.pdf",
        filename="consent.pdf",
    )
    db.add_all([participant, template])
    await db.commit()
    sent = {}
    monkeypatch.setattr(
        "app.api.minor_forms.read_pdf",
        lambda key: b"%PDF-1.7 sample",
    )

    def fake_send(**kwargs):
        sent.update(kwargs)
        return True

    monkeypatch.setattr("app.api.minor_forms.send_minor_form_email", fake_send)
    app.dependency_overrides[get_current_user] = _admin
    try:
        response = await client.post(
            f"/api/events/{event.id}/participants/{participant.id}/minor-form-email"
        )
        assert response.status_code == 200
        assert response.json()["sent"] is True
        assert sent["to_email"] == participant.email
        assert sent["attachment_name"] == "consent.pdf"
        assert sent["attachment_content"].startswith(b"%PDF-")
        assert "/minor-form-upload/" in sent["upload_link"]
        token = sent["upload_link"].rsplit("/", 1)[-1]
        submission = await db.get(MinorFormSubmission, participant.id)
        assert submission.token_digest == digest_upload_token(token)
        assert submission.token_expires_at > datetime.now(timezone.utc)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_adult_cannot_be_sent_minor_form_email(client, db, monkeypatch):
    event = Event(
        name="Gathering",
        start_date=date(2026, 11, 4),
        status=EventStatus.OPEN,
    )
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        date_of_birth=date(2008, 11, 4),
        registration_status=RegistrationStatus.CONFIRMED,
    )
    db.add(participant)
    await db.commit()
    monkeypatch.setattr(
        "app.api.minor_forms.send_minor_form_email",
        lambda **kwargs: pytest.fail("Adults must not receive the minor form email"),
    )
    app.dependency_overrides[get_current_user] = _admin
    try:
        response = await client.post(
            f"/api/events/{event.id}/participants/{participant.id}/minor-form-email"
        )
        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "errors.minor_form.not_applicable"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_cancelled_participant_cannot_be_sent_minor_form_email(client, db):
    event = Event(
        name="Gathering",
        start_date=date(2026, 11, 4),
        status=EventStatus.OPEN,
    )
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        date_of_birth=date(2010, 5, 1),
        registration_status=RegistrationStatus.CANCELLED,
    )
    db.add(participant)
    await db.commit()
    app.dependency_overrides[get_current_user] = _admin
    try:
        response = await client.post(
            f"/api/events/{event.id}/participants/{participant.id}/minor-form-email"
        )
        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "errors.minor_form.participant_cancelled"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_can_upload_download_and_delete_private_forms(
    client, db, monkeypatch
):
    event = Event(name="Gathering", start_date=date(2026, 11, 4))
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        date_of_birth=date(2010, 5, 1),
        registration_status=RegistrationStatus.CONFIRMED,
    )
    db.add(participant)
    await db.flush()
    db.add(
        MinorFormSubmission(
            participant_id=participant.id,
            storage_key=f"{'f' * 32}.pdf",
            filename="signed.pdf",
            uploaded_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    deleted = []
    monkeypatch.setattr(
        "app.api.minor_forms.write_pdf",
        lambda content: f"{'a' * 32}.pdf",
    )
    monkeypatch.setattr(
        "app.api.minor_forms.read_pdf",
        lambda key: b"%PDF-1.7 private",
    )
    monkeypatch.setattr("app.api.minor_forms.delete_pdf", deleted.append)
    app.dependency_overrides[get_current_user] = _admin
    try:
        invalid = await client.post(
            f"/api/events/{event.id}/minor-form-template",
            files={"file": ("not-a-pdf.txt", b"not a PDF", "text/plain")},
        )
        assert invalid.status_code == 422
        uploaded = await client.post(
            f"/api/events/{event.id}/minor-form-template",
            files={"file": ("blank.pdf", b"%PDF-1.7 blank", "application/pdf")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json() == {"available": True, "filename": "blank.pdf"}
        template = await client.get(f"/api/events/{event.id}/minor-form-template")
        assert template.json() == {"available": True, "filename": "blank.pdf"}

        submissions = await client.get(
            f"/api/events/{event.id}/minor-form-submissions"
        )
        assert submissions.json()["submissions"][0]["participant_id"] == str(
            participant.id
        )
        download = await client.get(
            f"/api/events/{event.id}/participants/{participant.id}/minor-form-submission"
        )
        assert download.status_code == 200
        assert download.content == b"%PDF-1.7 private"
        assert download.headers["content-type"] == "application/pdf"

        removed = await client.delete(
            f"/api/events/{event.id}/participants/{participant.id}/minor-form-submission"
        )
        assert removed.status_code == 204
        assert deleted == [f"{'f' * 32}.pdf"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_public_upload_replaces_previous_pdf(client, db, monkeypatch):
    event = Event(name="Gathering", start_date=date(2026, 11, 4))
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        date_of_birth=date(2010, 5, 1),
        registration_status=RegistrationStatus.CONFIRMED,
    )
    db.add(participant)
    await db.flush()
    token = "private-link-token"
    submission = MinorFormSubmission(
        participant_id=participant.id,
        storage_key=f"{'b' * 32}.pdf",
        filename="old.pdf",
        uploaded_at=datetime.now(timezone.utc),
        token_digest=digest_upload_token(token),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(submission)
    await db.commit()
    written = iter([f"{'c' * 32}.pdf", f"{'d' * 32}.pdf"])
    deleted = []
    monkeypatch.setattr(
        "app.api.minor_forms.write_pdf",
        lambda content: next(written),
    )
    monkeypatch.setattr("app.api.minor_forms.delete_pdf", deleted.append)
    try:
        invalid = await client.post(
            f"/api/public/minor-form-upload/{token}",
            files={"file": ("signed.pdf", b"not a PDF", "application/pdf")},
        )
        assert invalid.status_code == 422
        for expected_key in (f"{'c' * 32}.pdf", f"{'d' * 32}.pdf"):
            response = await client.post(
                f"/api/public/minor-form-upload/{token}",
                files={"file": ("signed.pdf", b"%PDF-1.7 signed", "application/pdf")},
            )
            assert response.status_code == 200
            assert response.json() == {"uploaded": True}
            await db.refresh(submission)
            assert submission.storage_key == expected_key
            assert submission.filename == "signed.pdf"
        assert deleted == [f"{'b' * 32}.pdf", f"{'c' * 32}.pdf"]
    finally:
        await db.delete(submission)
        await db.delete(participant)
        await db.delete(event)
        await db.commit()


@pytest.mark.asyncio
async def test_expired_upload_link_is_rejected(client, db):
    event = Event(name="Gathering", start_date=date(2026, 11, 4))
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        date_of_birth=date(2010, 5, 1),
        registration_status=RegistrationStatus.CONFIRMED,
    )
    db.add(participant)
    await db.flush()
    token = "expired-private-link"
    db.add(
        MinorFormSubmission(
            participant_id=participant.id,
            token_digest=digest_upload_token(token),
            token_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db.commit()
    response = await client.get(f"/api/public/minor-form-upload/{token}")
    assert response.status_code == 410
    assert response.json()["detail"]["key"] == "errors.minor_form.link_expired"


@pytest.mark.asyncio
async def test_removing_participant_deletes_the_private_submission(
    client, db, monkeypatch
):
    event = Event(name="Gathering", start_date=date(2026, 11, 4))
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        date_of_birth=date(2010, 5, 1),
        registration_status=RegistrationStatus.CONFIRMED,
    )
    db.add(participant)
    await db.flush()
    submission = MinorFormSubmission(
        participant_id=participant.id,
        storage_key=f"{'e' * 32}.pdf",
        filename="signed.pdf",
    )
    db.add(submission)
    await db.commit()
    deleted = []
    monkeypatch.setattr("app.api.participants.delete_pdf", deleted.append)
    monkeypatch.setattr(
        "app.api.participants.send_registration_cancellation_email",
        lambda **kwargs: True,
    )
    app.dependency_overrides[get_current_user] = _admin
    try:
        response = await client.delete(f"/api/participants/{participant.id}")
        assert response.status_code == 200
        assert deleted == [f"{'e' * 32}.pdf"]
        remaining = await db.scalar(
            select(MinorFormSubmission).where(
                MinorFormSubmission.participant_id == participant.id
            )
        )
        assert remaining is None
        await db.refresh(participant)
        assert participant.deleted_at is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_minor_form_email_renders_upload_link_and_pdf_attachment(monkeypatch):
    sent = {}

    def fake_send(to_email, subject, html_body, text_body=None, attachments=None):
        sent.update(subject=subject, html=html_body, text=text_body, attachments=attachments)
        return True

    monkeypatch.setattr("app.core.email.send_email", fake_send)
    assert send_minor_form_email(
        "sam@example.org",
        "Sam",
        "Gathering 2026",
        "https://example.org/minor-form-upload/secret-token",
        "consent.pdf",
        b"%PDF-1.7 form",
        email_strings={
            "minor_form_subject": "Consent for {event}",
            "minor_form_hi": "Hi {name}",
            "minor_form_body": "Upload here: {upload_link}",
            "minor_form_closing": "Thanks",
        },
    )
    assert sent["subject"] == "Consent for Gathering 2026"
    assert 'href="https://example.org/minor-form-upload/secret-token"' in sent["html"]
    assert sent["attachments"] == [
        ("consent.pdf", b"%PDF-1.7 form", "application/pdf")
    ]
