"""Encryption utilities for API keys and tokens."""

import hashlib

from cryptography.fernet import Fernet


def hash_api_key(raw_key: str) -> str:
    """Return SHA-256 hex digest of *raw_key* (one-way)."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def encrypt_value(plaintext: str, key: str) -> str:
    """Fernet-encrypt *plaintext* using *key*. Returns URL-safe base64 ciphertext."""
    f = Fernet(key.encode("utf-8"))
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str, key: str) -> str:
    """Fernet-decrypt *ciphertext* using *key*. Returns plaintext."""
    f = Fernet(key.encode("utf-8"))
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
