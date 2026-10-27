import uuid

import pytest

from app.api.deps import get_current_user
from app.core import email
from app.main import app
from app.models.user import User, UserRole
from app.services.workspace_settings_service import (
    EMAIL_TEMPLATE_KEYS,
    InvalidEmailTemplates,
    get_email_templates,
    normalise_email_templates,
    set_email_templates,
)

ADMIN = "/api/admin/workspace/email-templates"


def _user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{role.value}@email-templates.test",
        hashed_password="$2b$12$test.hash.placeholder.for.test.fixtures.only....",
        full_name="Test",
        role=role,
    )


def _as(role: UserRole):
    app.dependency_overrides[get_current_user] = lambda: _user(role)


def _anon():
    app.dependency_overrides.pop(get_current_user, None)


def test_email_template_validation_accepts_known_placeholders():
    assert normalise_email_templates({
        "en": {
            "receipt_subject": "You're registered for {event}",
            "receipt_hi": "Hi {name}",
        },
    }) == {
        "en": {
            "receipt_subject": "You're registered for {event}",
            "receipt_hi": "Hi {name}",
        },
    }


def test_all_builtin_email_translations_are_editable():
    editable = {
        language: {key: value for key, value in values.items() if key in EMAIL_TEMPLATE_KEYS}
        for language, values in email.EMAIL_STRINGS.items()
    }
    assert set(normalise_email_templates(editable)) == set(email.EMAIL_STRINGS)


@pytest.mark.parametrize("templates", [
    {"xx": {"receipt_body": "text"}},
    {"en": {"not_a_template": "text"}},
    {"en": {"receipt_body": "Hi {unknown}"}},
    {"en": {"receipt_body": "Hi {"}},
    {"en": {"receipt_subject": "Subject\nBcc: other@example.org"}},
    {"en": {"receipt_body": "x" * 2001}},
])
@pytest.mark.asyncio
def test_invalid_email_templates_are_rejected(templates):
    with pytest.raises(InvalidEmailTemplates):
        normalise_email_templates(templates)


@pytest.mark.asyncio
async def test_saved_templates_override_defaults_without_changing_other_languages(db):
    await set_email_templates(db, {"en": {"receipt_body": "Welcome to {event}!"}})
    await db.commit()

    templates = await get_email_templates(db)
    assert templates["en"]["receipt_body"] == "Welcome to {event}!"
    assert templates["de"]["receipt_body"]
    assert "powered_by" not in templates["en"]


@pytest.mark.asyncio
async def test_admin_can_save_templates_and_retrieve_effective_content(client, db):
    _as(UserRole.SUPER_ADMIN)
    try:
        response = await client.put(
            ADMIN,
            json={"templates": {"en": {"receipt_body": "Welcome to {event}!"}}},
        )
        assert response.status_code == 200
        assert response.json()["templates"]["en"]["receipt_body"] == "Welcome to {event}!"

        response = await client.get(ADMIN)
        assert response.status_code == 200
        assert response.json()["templates"]["en"]["receipt_body"] == "Welcome to {event}!"
        assert response.json()["templates"]["fr"]["receipt_body"]
    finally:
        _anon()


@pytest.mark.asyncio
async def test_only_super_admin_can_read_or_write_templates(client, db):
    _as(UserRole.STAFF)
    try:
        response = await client.get(ADMIN)
        assert response.status_code == 403
        response = await client.put(ADMIN, json={"templates": {}})
        assert response.status_code == 403
    finally:
        _anon()

    response = await client.put(ADMIN, json={"templates": {"en": {"receipt_body": "{invalid}"}}})
    assert response.status_code in (401, 403)


def test_registration_email_uses_custom_copy_and_escapes_editable_html(monkeypatch):
    sent = {}

    def fake_send(to_email, subject, html_body, text_body=None):
        sent.update(subject=subject, html=html_body, text=text_body)
        return True

    monkeypatch.setattr(email, "send_email", fake_send)

    email.send_registration_receipt(
        "person@example.org",
        "<script>alert(1)</script>",
        "Gathering <2026>",
        lang="en",
        email_strings={
            "receipt_subject": "Welcome to {event}",
            "receipt_hi": "Hi {name}",
            "receipt_body": "Thanks for joining {event}",
            "receipt_closing": "See you soon",
        },
    )

    assert sent["subject"] == "Welcome to Gathering <2026>"
    assert "Thanks for joining Gathering &lt;2026&gt;" in sent["html"]
    assert "<script>" not in sent["html"]
    assert "Welcome to Gathering <2026>" in sent["text"]


def test_confirmation_email_uses_custom_copy(monkeypatch):
    sent = {}

    def fake_send(to_email, subject, html_body, text_body=None):
        sent.update(subject=subject, html=html_body, text=text_body)
        return True

    monkeypatch.setattr(email, "send_email", fake_send)

    email.send_confirmation_email(
        "person@example.org",
        "Sam",
        "Gathering 2026",
        "https://example.org/confirm/token",
        lang="en",
        email_strings={
            "confirm_subject": "Please confirm for {event}",
            "confirm_hi": "Welcome {name}",
            "confirm_body": "Finish signing up for {event}",
            "confirm_button": "Continue",
            "confirm_footer": "Ignore this message",
        },
    )

    assert sent["subject"] == "Please confirm for Gathering 2026"
    assert "Finish signing up for Gathering 2026" in sent["html"]
    assert "Welcome Sam" in sent["text"]
