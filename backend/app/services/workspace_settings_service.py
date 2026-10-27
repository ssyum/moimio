"""Helpers for the one-row `workspace_settings` table.

The public registration form reads the privacy notice URL; super admins
manage workspace-wide privacy and registration-email settings. Validation
lives here so API callers use the same rules.
"""

from string import Formatter
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EMAIL_STRINGS
from app.models.workspace_settings import SINGLETON_ID, WorkspaceSettings

# The longest URL the field accepts. Generous for a real notice page,
# small enough that nothing can be parked in the column.
PRIVACY_NOTICE_URL_MAX_LEN = 2048
EMAIL_TEMPLATE_LANGUAGES = tuple(EMAIL_STRINGS)
EMAIL_TEMPLATE_KEYS = (
    "confirm_subject",
    "confirm_preheader",
    "confirm_hi",
    "confirm_body",
    "confirm_button",
    "confirm_fallback_pre",
    "confirm_footer",
    "receipt_subject",
    "receipt_preheader",
    "receipt_hi",
    "receipt_body",
    "receipt_group_code_title",
    "receipt_group_code_hint",
    "receipt_closing",
)
EMAIL_TEMPLATE_VALUE_MAX_LEN = 2000
EMAIL_TEMPLATE_PLACEHOLDERS = {
    "confirm_subject": {"event"},
    "confirm_hi": {"name"},
    "confirm_body": {"event"},
    "receipt_subject": {"event"},
    "receipt_hi": {"name"},
    "receipt_body": {"event"},
}


class InvalidPrivacyNoticeUrl(ValueError):
    """The value is not an absolute http(s) URL."""


def normalise_privacy_notice_url(raw: str | None) -> str | None:
    """Return the URL to store, or None for "unset".

    Blank and whitespace-only mean unset, so clearing the box clears the
    setting. Anything else must be an absolute URL with an http or https
    scheme and a host: `example.org/privacy` is rejected rather than
    guessed at, because a link the form renders must not point somewhere
    the admin did not type.
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > PRIVACY_NOTICE_URL_MAX_LEN:
        raise InvalidPrivacyNoticeUrl("too long")
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise InvalidPrivacyNoticeUrl(str(exc)) from exc
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InvalidPrivacyNoticeUrl("not an absolute http(s) URL")
    # A host has to have something in it besides credentials or a port.
    if not parts.hostname:
        raise InvalidPrivacyNoticeUrl("no host")
    return value


async def get_workspace_settings(db: AsyncSession) -> WorkspaceSettings | None:
    """The row, or None if nothing has ever been saved."""
    return await db.get(WorkspaceSettings, SINGLETON_ID)


async def get_privacy_notice_url(db: AsyncSession) -> str | None:
    row = await get_workspace_settings(db)
    return row.privacy_notice_url if row else None


async def set_privacy_notice_url(db: AsyncSession, raw: str | None) -> WorkspaceSettings:
    """Validate, then store. Raises InvalidPrivacyNoticeUrl; commits nothing,
    the caller owns the transaction."""
    value = normalise_privacy_notice_url(raw)
    row = await get_workspace_settings(db)
    if row is None:
        row = WorkspaceSettings(id=SINGLETON_ID)
        db.add(row)
    row.privacy_notice_url = value
    await db.flush()
    return row


class InvalidEmailTemplates(ValueError):
    """The supplied transactional email templates are malformed."""


def normalise_email_templates(raw: dict) -> dict[str, dict[str, str]]:
    """Validate editable copy while retaining only supported languages/keys."""
    if not isinstance(raw, dict):
        raise InvalidEmailTemplates("templates must be an object")

    normalised: dict[str, dict[str, str]] = {}
    for language, values in raw.items():
        if language not in EMAIL_TEMPLATE_LANGUAGES or not isinstance(values, dict):
            raise InvalidEmailTemplates("unsupported language")
        if not set(values).issubset(EMAIL_TEMPLATE_KEYS):
            raise InvalidEmailTemplates("unsupported template field")
        normalised[language] = {}
        for key, value in values.items():
            if not isinstance(value, str) or len(value) > EMAIL_TEMPLATE_VALUE_MAX_LEN:
                raise InvalidEmailTemplates("invalid template value")
            if key.endswith("_subject") and ("\r" in value or "\n" in value):
                raise InvalidEmailTemplates("subject must be a single line")
            try:
                parts = Formatter().parse(value)
            except ValueError as exc:
                raise InvalidEmailTemplates("malformed placeholder") from exc
            placeholders = set()
            for _, field, format_spec, conversion in parts:
                if field is not None:
                    if format_spec or conversion:
                        raise InvalidEmailTemplates("unsupported placeholder format")
                    placeholders.add(field)
            if not placeholders.issubset(EMAIL_TEMPLATE_PLACEHOLDERS.get(key, set())):
                raise InvalidEmailTemplates("unsupported placeholder")
            normalised[language][key] = value
    return normalised


async def get_email_templates(db: AsyncSession) -> dict[str, dict[str, str]]:
    """Return all supported template strings, including saved overrides."""
    row = await get_workspace_settings(db)
    overrides = row.email_templates if row and row.email_templates else {}
    return {
        language: {
            **{key: values[key] for key in EMAIL_TEMPLATE_KEYS},
            **(overrides.get(language, {}) if isinstance(overrides, dict) else {}),
        }
        for language, values in EMAIL_STRINGS.items()
    }


async def set_email_templates(db: AsyncSession, raw: dict) -> WorkspaceSettings:
    """Validate and store the workspace-wide email copy without committing."""
    templates = normalise_email_templates(raw)
    row = await get_workspace_settings(db)
    if row is None:
        row = WorkspaceSettings(id=SINGLETON_ID)
        db.add(row)
    row.email_templates = templates
    await db.flush()
    return row
