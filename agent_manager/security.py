"""Fernet encryption / decryption helpers."""

from cryptography.fernet import Fernet

from .config import settings

if not settings.FERNET_KEY:
    raise ValueError("FERNET_KEY environment variable is not set")

fernet = Fernet(settings.FERNET_KEY)


def encrypt(data: str) -> str:
    if not data:
        return None
    return fernet.encrypt(data.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return None
    return fernet.decrypt(token.encode()).decode()
