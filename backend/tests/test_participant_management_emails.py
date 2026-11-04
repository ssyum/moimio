import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.api.deps import get_current_user
from app.main import app
from app.models.event import Event, EventStatus
from app.models.participant import Participant, RegistrationStatus
from app.models.user import User, UserRole


def _super_admin() -> User:
    return User(
        id=uuid.uuid4(),
        email="payment-reminders@test.local",
        hashed_password="test-hash",
        full_name="Test Admin",
        role=UserRole.SUPER_ADMIN,
    )


@pytest.mark.asyncio
async def test_payment_reminder_requires_more_than_three_calendar_days(
    client, db, monkeypatch
):
    event = Event(name="Gathering", timezone="UTC", status=EventStatus.OPEN)
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        registration_status=RegistrationStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        preferred_language="en",
    )
    db.add(participant)
    await db.commit()
    monkeypatch.setattr(
        "app.api.participants.send_payment_reminder_email",
        lambda **kwargs: pytest.fail("A reminder must not be sent before day four"),
    )
    app.dependency_overrides[get_current_user] = _super_admin
    try:
        response = await client.post(
            f"/api/events/{event.id}/participants/{participant.id}/payment-reminder"
        )
        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "errors.participant.reminder_not_due"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_payment_reminder_sends_current_day_count(client, db, monkeypatch):
    event = Event(name="Gathering", timezone="UTC", status=EventStatus.OPEN)
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        registration_status=RegistrationStatus.PENDING,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        preferred_language="en",
    )
    db.add(participant)
    await db.commit()
    sent = {}

    def fake_send(**kwargs):
        sent.update(kwargs)
        return True

    monkeypatch.setattr("app.api.participants.send_payment_reminder_email", fake_send)
    app.dependency_overrides[get_current_user] = _super_admin
    try:
        response = await client.post(
            f"/api/events/{event.id}/participants/{participant.id}/payment-reminder"
        )
        assert response.status_code == 200
        assert response.json()["sent"] is True
        assert response.json()["days_since_registration"] >= 4
        assert sent["to_email"] == "sam@example.org"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_final_confirmation_sends_to_confirmed_participant(client, db, monkeypatch):
    event = Event(name="Gathering", timezone="UTC", status=EventStatus.OPEN)
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        registration_status=RegistrationStatus.CONFIRMED,
        preferred_language="en",
    )
    db.add(participant)
    await db.commit()
    sent = {}

    def fake_send(**kwargs):
        sent.update(kwargs)
        return True

    monkeypatch.setattr(
        "app.api.participants.send_final_registration_confirmation_email",
        fake_send,
    )
    app.dependency_overrides[get_current_user] = _super_admin
    try:
        response = await client.post(
            f"/api/events/{event.id}/participants/{participant.id}/final-confirmation"
        )
        assert response.status_code == 200
        assert response.json() == {"sent": True}
        assert sent["to_email"] == "sam@example.org"
        assert sent["event_name"] == "Gathering"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_final_confirmation_rejects_pending_participant(client, db, monkeypatch):
    event = Event(name="Gathering", timezone="UTC", status=EventStatus.OPEN)
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        registration_status=RegistrationStatus.PENDING,
        preferred_language="en",
    )
    db.add(participant)
    await db.commit()
    monkeypatch.setattr(
        "app.api.participants.send_final_registration_confirmation_email",
        lambda **kwargs: pytest.fail("A final confirmation must only go to confirmed participants"),
    )
    app.dependency_overrides[get_current_user] = _super_admin
    try:
        response = await client.post(
            f"/api/events/{event.id}/participants/{participant.id}/final-confirmation"
        )
        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "errors.participant.final_confirmation_not_applicable"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_removing_participant_sends_cancellation_email_even_if_delivery_fails(
    client, db, monkeypatch
):
    event = Event(name="Gathering", timezone="UTC", status=EventStatus.OPEN)
    db.add(event)
    await db.flush()
    participant = Participant(
        event_id=event.id,
        first_name="Sam",
        last_name="Example",
        email="sam@example.org",
        registration_status=RegistrationStatus.CONFIRMED,
        preferred_language="en",
    )
    db.add(participant)
    await db.commit()
    monkeypatch.setattr(
        "app.api.participants.send_registration_cancellation_email",
        lambda **kwargs: False,
    )
    app.dependency_overrides[get_current_user] = _super_admin
    try:
        response = await client.delete(f"/api/participants/{participant.id}")
        assert response.status_code == 200
        assert response.json() == {"email_sent": False}
        await db.refresh(participant)
        assert participant.deleted_at is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
