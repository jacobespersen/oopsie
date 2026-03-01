"""Tests for oopsie.utils.encryption."""

import pytest
from cryptography.fernet import Fernet
from oopsie.utils.encryption import decrypt_value, encrypt_value, hash_api_key


class TestHashApiKey:
    def test_deterministic(self):
        assert hash_api_key("my-key") == hash_api_key("my-key")

    def test_different_keys_different_hashes(self):
        assert hash_api_key("key-a") != hash_api_key("key-b")

    def test_returns_64_char_hex(self):
        h = hash_api_key("anything")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestEncryptDecrypt:
    @pytest.fixture
    def fernet_key(self):
        return Fernet.generate_key().decode()

    def test_roundtrip(self, fernet_key):
        plaintext = "ghp_supersecrettoken123"
        ciphertext = encrypt_value(plaintext, fernet_key)
        assert ciphertext != plaintext
        assert decrypt_value(ciphertext, fernet_key) == plaintext

    def test_wrong_key_fails(self, fernet_key):
        ciphertext = encrypt_value("secret", fernet_key)
        other_key = Fernet.generate_key().decode()
        with pytest.raises(Exception):
            decrypt_value(ciphertext, other_key)

    def test_ciphertext_is_different_each_time(self, fernet_key):
        a = encrypt_value("same", fernet_key)
        b = encrypt_value("same", fernet_key)
        assert a != b  # Fernet uses a random IV
