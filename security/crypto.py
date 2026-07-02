"""
Modul Kriptografi — Proteksi data sensitif at-rest.
Menggunakan Fernet (AES-128-CBC) dengan key yang diturunkan dari ENCRYPTION_KEY.
Mendukung key rotation melalui MultiFernet.
"""
import os
import base64
import hashlib
from cryptography.fernet import Fernet, MultiFernet
from loguru import logger

class CryptoManager:
    def __init__(self):
        secret = os.environ.get("ENCRYPTION_KEY")
        
        # Enforce strong key requirement
        if not secret:
            raise RuntimeError(
                "ENCRYPTION_KEY tidak ditemukan di environment. "
                "Jalankan scripts/rotate_secrets.py untuk generate."
            )
        
        if len(secret) < 32:
            raise ValueError("ENCRYPTION_KEY terlalu pendek — minimal 32 karakter untuk keamanan.")

        # Primary key derivation
        primary_key = self._derive_key(secret)
        
        # MultiFernet support for future rotation
        self.fernet = MultiFernet([Fernet(primary_key)])
        logger.debug("CryptoManager initialized with MultiFernet (Strict Mode)")

    def _derive_key(self, secret: str) -> bytes:
        """
        Turunkan key Fernet (32 bytes base64) dari secret.
        Known limitation: Static salt means same secret + same salt = same key across installs.
        """
        key = hashlib.pbkdf2_hmac(
            'sha256',
            secret.encode(),
            b'rav-spy-salt-v1',
            iterations=100_000
        )
        return base64.urlsafe_b64encode(key)

    def encrypt(self, data: str) -> str:
        """Enkripsi string ke string base64."""
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Dekripsi string base64 ke string original."""
        return self.fernet.decrypt(encrypted_data.encode()).decode()

# Singleton instance - Choice A (Strict Fail-Closed)
# Any failure here will (and should) cause the application to fail to import/start.
crypto = CryptoManager()
