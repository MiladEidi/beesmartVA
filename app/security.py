from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CryptoService:
    def __init__(self, key: str | None = None) -> None:
        settings = get_settings()
        self._fernet = Fernet((key or settings.encryption_key).encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            return None
