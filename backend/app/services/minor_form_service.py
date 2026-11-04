"""Age checks and bearer-link validation for minor consent forms."""

from datetime import date, datetime, timedelta, timezone
import hashlib
import secrets


UPLOAD_TOKEN_TTL_DAYS = 30


def age_on_date(date_of_birth: date | None, event_date: date | None) -> int | None:
    if date_of_birth is None or event_date is None or date_of_birth > event_date:
        return None
    return event_date.year - date_of_birth.year - (
        (event_date.month, event_date.day) < (date_of_birth.month, date_of_birth.day)
    )


def create_upload_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
        days=UPLOAD_TOKEN_TTL_DAYS
    )
    return token, digest, expires_at


def digest_upload_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
