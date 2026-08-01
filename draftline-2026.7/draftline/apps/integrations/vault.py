"""Credential envelope encryption.

Local Fernet implementation for development. Production swaps in GcpKmsEncryptor
without changing Connection call sites.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Protocol

from cryptography.fernet import Fernet
from django.conf import settings


class CredentialEncryptor(Protocol):
    def encrypt(self, plaintext: dict) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> dict: ...


class FernetEncryptor:
    """Derives a Fernet key from CREDENTIAL_ENCRYPTION_KEY or SECRET_KEY."""

    def __init__(self, secret: str | None = None) -> None:
        material = (secret or getattr(settings, "CREDENTIAL_ENCRYPTION_KEY", None) or settings.SECRET_KEY).encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: dict) -> bytes:
        payload = json.dumps(plaintext, separators=(",", ":"), sort_keys=True).encode()
        return self._fernet.encrypt(payload)

    def decrypt(self, ciphertext: bytes) -> dict:
        raw = self._fernet.decrypt(ciphertext)
        return json.loads(raw.decode())


class GcpKmsEncryptor:
    """Stub for Cloud KMS envelope encryption. Not used until GCP is wired."""

    def __init__(self, key_name: str | None = None) -> None:
        self.key_name = key_name or getattr(settings, "CREDENTIAL_KMS_KEY_NAME", "")
        raise NotImplementedError(
            "GcpKmsEncryptor requires google-cloud-kms and CREDENTIAL_KMS_KEY_NAME. "
            "Use FernetEncryptor locally."
        )

    def encrypt(self, plaintext: dict) -> bytes:
        raise NotImplementedError

    def decrypt(self, ciphertext: bytes) -> dict:
        raise NotImplementedError


def get_encryptor() -> CredentialEncryptor:
    backend = getattr(settings, "CREDENTIAL_ENCRYPTOR", "fernet")
    if backend == "kms":
        return GcpKmsEncryptor()
    return FernetEncryptor()
