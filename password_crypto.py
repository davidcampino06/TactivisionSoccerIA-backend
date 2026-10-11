"""RSA-OAEP (SHA-256) encryption of passwords between the browser and the backend.

The browser encrypts the password with the public key (GET /api/auth/public-key), so the request
body never shows it in plain text (DevTools -> Network). Only the backend, holding the private key,
can decrypt it; it then validates the rules and stores a bcrypt hash. HTTPS still protects the transport.

Encrypted values are sent as ``rsa:<base64 ciphertext>``.
"""

from __future__ import annotations

import base64
import binascii
import logging
import threading

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from config import settings
from errors import AppError

logger = logging.getLogger("tactivision.crypto")

ENCRYPTED_PREFIX = "rsa:"
KEY_SIZE = 2048
_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)

_lock = threading.Lock()
_private_key: rsa.RSAPrivateKey | None = None


def _load_private_key() -> rsa.RSAPrivateKey:
    global _private_key
    with _lock:
        if _private_key is None:
            pem = settings.rsa_private_key
            if pem:
                key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
                if not isinstance(key, rsa.RSAPrivateKey):
                    raise ValueError("RSA_PRIVATE_KEY must be an RSA private key.")
                _private_key = key
            else:
                logger.warning("RSA_PRIVATE_KEY is not set: using a temporary key (it changes on every restart).")
                _private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
        return _private_key


def public_key_spki_base64() -> str:
    """Public key as base64 DER (SubjectPublicKeyInfo), the format WebCrypto imports as 'spki'."""
    der = _load_private_key().public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base64.b64encode(der).decode("ascii")


def encrypt_for_tests(plain_text: str) -> str:
    """Encrypt like the browser does. Used by the automated tests."""
    ciphertext = _load_private_key().public_key().encrypt(plain_text.encode("utf-8"), _OAEP)
    return ENCRYPTED_PREFIX + base64.b64encode(ciphertext).decode("ascii")


def reveal_password(value: str) -> str:
    """Return the plain password from an ``rsa:`` value.

    Plain text is accepted only when REQUIRE_ENCRYPTED_PASSWORDS is off (local development, tests, /docs).
    """
    if not value.startswith(ENCRYPTED_PREFIX):
        if settings.require_encrypted_passwords:
            raise AppError(400, "PASSWORD_NOT_ENCRYPTED", "Passwords must be sent encrypted with the public key.")
        return value
    try:
        ciphertext = base64.b64decode(value[len(ENCRYPTED_PREFIX):], validate=True)
        return _load_private_key().decrypt(ciphertext, _OAEP).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError) as error:
        raise AppError(400, "PASSWORD_DECRYPTION_FAILED",
                       "The password could not be decrypted. Reload the page and try again.") from error
