"""
Tests for EncryptionService - TDD Red Phase.

Following tech-design.md v2.0 requirements:
- AES-256-GCM authenticated encryption
- PAN encryption/decryption
- SHA-256 hashing for lookups
- Base64 encoding for Kafka messages
"""
import base64
import pytest
from services.shared.encryption import EncryptionService


class TestEncryptionService:
    """Test suite for EncryptionService following TDD methodology."""

    @pytest.fixture
    def encryption_service(self):
        """Create EncryptionService with test key."""
        # 32-byte key for AES-256 (base64 encoded)
        test_key = base64.b64encode(b"test_encryption_key_32_bytes!").decode()
        return EncryptionService(encryption_key=test_key)

    def test_encrypt_pan_returns_bytes(self, encryption_service):
        """Test that encrypt_pan returns encrypted bytes."""
        pan = "ABCDE1234F"
        encrypted = encryption_service.encrypt_pan(pan)
        assert isinstance(encrypted, bytes)
        assert encrypted != pan.encode()  # Encrypted data should be different

    def test_decrypt_pan_returns_original_value(self, encryption_service):
        """Test that decrypt_pan returns original PAN."""
        pan = "ABCDE1234F"
        encrypted = encryption_service.encrypt_pan(pan)
        decrypted = encryption_service.decrypt_pan(encrypted)
        assert decrypted == pan

    def test_encrypt_different_pans_produce_different_ciphertexts(self, encryption_service):
        """Test that encrypting different PANs produces different ciphertexts."""
        pan1 = "ABCDE1234F"
        pan2 = "FGHIJ5678K"
        encrypted1 = encryption_service.encrypt_pan(pan1)
        encrypted2 = encryption_service.encrypt_pan(pan2)
        assert encrypted1 != encrypted2

    def test_encrypt_same_pan_twice_produces_different_ciphertexts(self, encryption_service):
        """Test that encrypting same PAN twice produces different ciphertexts (nonce)."""
        pan = "ABCDE1234F"
        encrypted1 = encryption_service.encrypt_pan(pan)
        encrypted2 = encryption_service.encrypt_pan(pan)
        # Due to random nonce, ciphertexts should be different
        assert encrypted1 != encrypted2
        # But both should decrypt to same value
        assert encryption_service.decrypt_pan(encrypted1) == pan
        assert encryption_service.decrypt_pan(encrypted2) == pan

    def test_hash_pan_returns_consistent_hash(self, encryption_service):
        """Test that hash_pan returns consistent SHA-256 hash."""
        pan = "ABCDE1234F"
        hash1 = encryption_service.hash_pan(pan)
        hash2 = encryption_service.hash_pan(pan)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest is 64 characters

    def test_hash_different_pans_produce_different_hashes(self, encryption_service):
        """Test that different PANs produce different hashes."""
        pan1 = "ABCDE1234F"
        pan2 = "FGHIJ5678K"
        hash1 = encryption_service.hash_pan(pan1)
        hash2 = encryption_service.hash_pan(pan2)
        assert hash1 != hash2

    def test_encrypt_pan_for_kafka_returns_base64_string(self, encryption_service):
        """Test that encrypt_pan_for_kafka returns base64 encoded string."""
        pan = "ABCDE1234F"
        encrypted_base64 = encryption_service.encrypt_pan_for_kafka(pan)
        assert isinstance(encrypted_base64, str)
        # Should be valid base64
        base64.b64decode(encrypted_base64)  # Should not raise exception

    def test_decrypt_pan_from_kafka_decrypts_base64_string(self, encryption_service):
        """Test that decrypt_pan_from_kafka decrypts base64 encoded string."""
        pan = "ABCDE1234F"
        encrypted_base64 = encryption_service.encrypt_pan_for_kafka(pan)
        decrypted = encryption_service.decrypt_pan_from_kafka(encrypted_base64)
        assert decrypted == pan

    def test_decrypt_invalid_data_raises_exception(self, encryption_service):
        """Test that decrypting invalid data raises exception."""
        with pytest.raises(Exception):  # Should raise decryption error
            encryption_service.decrypt_pan(b"invalid_encrypted_data")

    def test_invalid_key_length_raises_exception(self):
        """Test that invalid key length raises exception."""
        with pytest.raises(ValueError):
            EncryptionService(encryption_key="short_key")

    def test_empty_pan_encryption_decryption(self, encryption_service):
        """Test encryption/decryption of empty string."""
        pan = ""
        encrypted = encryption_service.encrypt_pan(pan)
        decrypted = encryption_service.decrypt_pan(encrypted)
        assert decrypted == pan

    def test_special_characters_in_pan(self, encryption_service):
        """Test encryption/decryption with special characters."""
        pan = "ABC@#1234F"
        encrypted = encryption_service.encrypt_pan(pan)
        decrypted = encryption_service.decrypt_pan(encrypted)
        assert decrypted == pan

    def test_unicode_characters_in_pan(self, encryption_service):
        """Test encryption/decryption with unicode characters."""
        pan = "ABCदे1234F"
        encrypted = encryption_service.encrypt_pan(pan)
        decrypted = encryption_service.decrypt_pan(encrypted)
        assert decrypted == pan
