#!/usr/bin/env python3
"""
Generate a secure encryption key for PAN data.

Usage:
    python scripts/generate_encryption_key.py
"""
import base64
import os


def generate_encryption_key():
    """Generate a 32-byte (256-bit) key for AES-256-GCM encryption."""
    key = os.urandom(32)
    encoded_key = base64.b64encode(key).decode('ascii')
    return encoded_key


if __name__ == "__main__":
    key = generate_encryption_key()
    print("Generated AES-256 Encryption Key:")
    print(f"ENCRYPTION_KEY={key}")
    print("\nAdd this to your .env files:")
    print(f"  services/prequal-api/.env")
    print(f"  services/credit-service/.env")
    print(f"  services/decision-service/.env")
