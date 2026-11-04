"""Private PDF storage for event minor-consent forms."""

import os
import re
import uuid
from pathlib import Path

from app.core.config import get_settings

_STORAGE_KEY = re.compile(r"^[0-9a-f]{32}\.pdf$")


def _directory() -> Path:
    directory = Path(get_settings().private_upload_dir).resolve() / "minor-forms"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    return directory


def write_pdf(content: bytes) -> str:
    key = f"{uuid.uuid4().hex}.pdf"
    path = _directory() / key
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(content)
    return key


def read_pdf(key: str) -> bytes:
    if not _STORAGE_KEY.fullmatch(key):
        raise ValueError("invalid private PDF storage key")
    return (_directory() / key).read_bytes()


def delete_pdf(key: str) -> None:
    if not _STORAGE_KEY.fullmatch(key):
        raise ValueError("invalid private PDF storage key")
    path = _directory() / key
    try:
        path.unlink()
    except FileNotFoundError:
        return
