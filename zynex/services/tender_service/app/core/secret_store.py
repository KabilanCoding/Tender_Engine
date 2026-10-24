"""Encrypt API keys before they are saved in the database (Settings page secrets).

The key is derived from SECRET_KEY, so a database dump alone does not reveal the keys. If SECRET_KEY is
changed the saved keys can no longer be read and must be entered again (they then read as "not set").
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)
_PREFIX = "enc:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plain: str) -> str:
    return _PREFIX + _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(stored: str) -> str:
    """The original text, or '' when it cannot be read (wrong SECRET_KEY, damaged value)."""
    if not stored:
        return ""
    if not isinstance(stored, str) or not stored.startswith(_PREFIX):
        return ""     # never treat an unencrypted value as a key
    try:
        return _fernet().decrypt(stored[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning("A saved API key could not be decrypted (SECRET_KEY changed?); enter it again on the Settings page")
        return ""
