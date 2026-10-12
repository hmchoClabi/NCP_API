from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class KeyEncryptionProvider(Protocol):
    @property
    def reference(self) -> str: ...

    def wrap_key(self, key: bytes, context: bytes) -> tuple[bytes, bytes]: ...

    def unwrap_key(self, encrypted_key: bytes, nonce: bytes, context: bytes) -> bytes: ...


class LocalKeyEncryptionProvider:
    def __init__(self, key_file: str | Path):
        self.path = Path(key_file)
        self._key = self._load_key(self.path)

    @property
    def reference(self) -> str:
        return "secret-file://credential-master-key"

    def wrap_key(self, key: bytes, context: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return AESGCM(self._key).encrypt(nonce, key, context), nonce

    def unwrap_key(self, encrypted_key: bytes, nonce: bytes, context: bytes) -> bytes:
        return AESGCM(self._key).decrypt(nonce, encrypted_key, context)

    @staticmethod
    def _load_key(path: Path) -> bytes:
        if not path.is_file():
            raise RuntimeError("Credential master key file was not found.")
        encoded = path.read_text(encoding="ascii").strip()
        try:
            key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Credential master key file is invalid.") from exc
        if len(key) != 32:
            raise RuntimeError("Credential master key must decode to 32 bytes.")
        return key


@dataclass(frozen=True)
class EncryptedCredential:
    encrypted_dek: bytes
    dek_nonce: bytes
    ciphertext: bytes
    credential_nonce: bytes
    access_key_hint: str
    key_reference: str


class CredentialCipher:
    def __init__(self, provider: KeyEncryptionProvider):
        self.provider = provider

    def encrypt(self, account_id: str, access_key: str, secret_key: str) -> EncryptedCredential:
        access_key = access_key.strip()
        secret_key = secret_key.strip()
        if not access_key or not secret_key:
            raise ValueError("Access Key and Secret Key are required.")
        context = account_id.encode("utf-8")
        dek = os.urandom(32)
        credential_nonce = os.urandom(12)
        plaintext = json.dumps(
            {"access_key": access_key, "secret_key": secret_key},
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = AESGCM(dek).encrypt(credential_nonce, plaintext, context)
        encrypted_dek, dek_nonce = self.provider.wrap_key(dek, context)
        return EncryptedCredential(
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            ciphertext=ciphertext,
            credential_nonce=credential_nonce,
            access_key_hint=f"***{access_key[-4:]}",
            key_reference=self.provider.reference,
        )

    def decrypt(
        self,
        account_id: str,
        encrypted_dek: bytes,
        dek_nonce: bytes,
        ciphertext: bytes,
        credential_nonce: bytes,
    ) -> dict[str, str]:
        context = account_id.encode("utf-8")
        dek = self.provider.unwrap_key(encrypted_dek, dek_nonce, context)
        plaintext = AESGCM(dek).decrypt(credential_nonce, ciphertext, context)
        result = json.loads(plaintext)
        if not result.get("access_key") or not result.get("secret_key"):
            raise RuntimeError("Decrypted credential payload is invalid.")
        return result
