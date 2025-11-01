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
    return base64.b64encode(key).decode("ascii")


if __name__ == "__main__":
    key = generate_encryption_key()
    print("Generated AES-256 Encryption Key:")
    print(f"ENCRYPTION_KEY={key}")
    print("\nAdd this to your .env files:")
    print("  services/prequal-api/.env")
    print("  services/credit-service/.env")
    print("  services/decision-service/.env")
