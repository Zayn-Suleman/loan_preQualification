"""
EncryptionService for PAN data protection.

Implements AES-256-GCM authenticated encryption as specified in tech-design.md v2.0.
Provides methods for:
- Encrypting PAN for database storage
- Decrypting PAN when needed (audit logged)
- Hashing PAN for duplicate detection without decryption
- Base64 encoding/decoding for Kafka message transport
"""
import base64
import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptionService:
    """
    Service for encrypting/decrypting PAN numbers using AES-256-GCM.

    Uses authenticated encryption with associated data (AEAD) for security.
    Random nonce (96-bit) ensures same plaintext encrypts to different ciphertext.

    Attributes:
        _cipher: AESGCM cipher instance with 256-bit key
    """

    def __init__(self, encryption_key: str):
        """
        Initialize encryption service with base64-encoded key.

        Args:
            encryption_key: Base64-encoded 32-byte (256-bit) encryption key

        Raises:
            ValueError: If key is not exactly 32 bytes after base64 decoding
        """
        try:
            key_bytes = base64.b64decode(encryption_key)
        except Exception as e:
            raise ValueError(f"Invalid base64 encryption key: {e}")

        if len(key_bytes) != 32:
            raise ValueError(
                f"Encryption key must be 32 bytes (256 bits), got {len(key_bytes)} bytes"
            )

        self._cipher = AESGCM(key_bytes)

    def encrypt_pan(self, pan_plaintext: str) -> bytes:
        """
        Encrypt PAN using AES-256-GCM.

        Generates random 96-bit nonce for each encryption, ensuring same plaintext
        produces different ciphertext. Nonce is prepended to ciphertext.

        Args:
            pan_plaintext: Plaintext PAN number

        Returns:
            Encrypted PAN as bytes (nonce + ciphertext + auth_tag)
        """
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        plaintext_bytes = pan_plaintext.encode("utf-8")

        # Encrypt and authenticate (no additional associated data)
        ciphertext = self._cipher.encrypt(nonce, plaintext_bytes, None)

        # Prepend nonce to ciphertext for later decryption
        return nonce + ciphertext

    def decrypt_pan(self, pan_encrypted: bytes) -> str:
        """
        Decrypt PAN using AES-256-GCM.

        Extracts nonce from encrypted data and decrypts ciphertext.
        Authentication tag is verified automatically by AESGCM.

        Args:
            pan_encrypted: Encrypted PAN (nonce + ciphertext + auth_tag)

        Returns:
            Decrypted PAN as string

        Raises:
            cryptography.exceptions.InvalidTag: If authentication fails (tampered data)
        """
        # Extract nonce (first 12 bytes)
        nonce = pan_encrypted[:12]
        ciphertext = pan_encrypted[12:]

        # Decrypt and verify authentication tag
        plaintext_bytes = self._cipher.decrypt(nonce, ciphertext, None)

        return plaintext_bytes.decode("utf-8")

    def hash_pan(self, pan_plaintext: str) -> str:
        """
        Generate SHA-256 hash of PAN for duplicate detection.

        Hash is deterministic (same input → same output) and one-way.
        Allows duplicate checking without decrypting stored PANs.

        Args:
            pan_plaintext: Plaintext PAN number

        Returns:
            Hexadecimal SHA-256 hash (64 characters)
        """
        pan_bytes = pan_plaintext.encode("utf-8")
        hash_bytes = hashlib.sha256(pan_bytes).digest()
        return hash_bytes.hex()

    def encrypt_pan_for_kafka(self, pan_plaintext: str) -> str:
        """
        Encrypt PAN and encode as base64 for Kafka message transport.

        Kafka messages contain base64-encoded encrypted PAN instead of plaintext.
        This maintains end-to-end encryption as specified in tech-design v2.0.

        Args:
            pan_plaintext: Plaintext PAN number

        Returns:
            Base64-encoded encrypted PAN
        """
        encrypted_bytes = self.encrypt_pan(pan_plaintext)
        return base64.b64encode(encrypted_bytes).decode("ascii")

    def decrypt_pan_from_kafka(self, pan_encrypted_base64: str) -> str:
        """
        Decrypt base64-encoded PAN from Kafka message.

        Args:
            pan_encrypted_base64: Base64-encoded encrypted PAN

        Returns:
            Decrypted PAN as string
        """
        encrypted_bytes = base64.b64decode(pan_encrypted_base64)
        return self.decrypt_pan(encrypted_bytes)
