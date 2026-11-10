"""Field-level encryption for sensitive fan data (Fernet / AES-128-CBC + HMAC)."""
from cryptography.fernet import Fernet
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import settings

_f = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else _f.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        return None if value is None else _f.decrypt(value.encode()).decode()
