import base64
import os
import tempfile
import unittest
from pathlib import Path

from webapp.security import (
    CredentialCipher,
    LocalKeyEncryptionProvider,
    hash_password,
    verify_password,
)


class WebSecurityTests(unittest.TestCase):
    def test_password_hash_does_not_store_plaintext(self):
        password = "correct horse battery staple"
        password_hash = hash_password(password)

        self.assertNotIn(password, password_hash)
        self.assertTrue(verify_password(password_hash, password))
        self.assertFalse(verify_password(password_hash, "wrong password"))

    def test_envelope_encryption_round_trip_and_account_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "master.key"
            key_path.write_text(
                base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
                encoding="ascii",
            )
            cipher = CredentialCipher(LocalKeyEncryptionProvider(key_path))
            encrypted = cipher.encrypt("account-1", "ACCESS-1234", "SECRET-5678")
            plaintext = cipher.decrypt(
                "account-1",
                encrypted.encrypted_dek,
                encrypted.dek_nonce,
                encrypted.ciphertext,
                encrypted.credential_nonce,
            )

            self.assertEqual(plaintext["access_key"], "ACCESS-1234")
            self.assertEqual(plaintext["secret_key"], "SECRET-5678")
            self.assertNotIn(b"SECRET-5678", encrypted.ciphertext)
            with self.assertRaises(Exception):  # noqa: B017 - 기존 계정 바인딩 불일치 시 복호화 거부 검증을 유지합니다.
                cipher.decrypt(
                    "another-account",
                    encrypted.encrypted_dek,
                    encrypted.dek_nonce,
                    encrypted.ciphertext,
                    encrypted.credential_nonce,
                )


if __name__ == "__main__":
    unittest.main()
