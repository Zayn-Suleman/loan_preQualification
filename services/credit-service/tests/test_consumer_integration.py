"""Integration tests for credit-service Kafka consumer.

Tests the consumer logic components:
- CIBIL score calculation with encryption
- Message serialization/deserialization
- PAN encryption/decryption flow
"""
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

# Add parent directories to path
service_root = Path(__file__).parent.parent
sys.path.insert(0, str(service_root))

from app.logic import CibilService  # noqa: E402

from services.shared.encryption import EncryptionService  # noqa: E402


class TestCreditServiceIntegration:
    """Test credit service integration with encryption."""

    def test_cibil_calculation_with_encryption_roundtrip(self):
        """Test CIBIL calculation with PAN encryption/decryption."""
        # Setup encryption service
        encryption_key = "test_encryption_key_32_bytes!!"
        encryption_service = EncryptionService(encryption_key)

        # Original PAN
        original_pan = "ABCDE1234F"

        # Encrypt PAN for Kafka (as prequal-api would do)
        encrypted_pan = encryption_service.encrypt_pan_for_kafka(original_pan)

        # Simulate receiving message with encrypted PAN
        application_data = {
            "application_id": str(uuid4()),
            "pan_number": encrypted_pan,  # Encrypted
            "applicant_name": "Rajesh Kumar",
            "monthly_income_inr": 80000.0,
            "loan_amount_inr": 500000.0,
            "loan_type": "PERSONAL",
        }

        # Decrypt PAN (as consumer would do)
        decrypted_pan = encryption_service.decrypt_pan_from_kafka(encrypted_pan)
        assert decrypted_pan == original_pan

        # Calculate CIBIL score with decrypted PAN
        application_data["pan_number"] = decrypted_pan
        credit_report = CibilService.get_credit_report(application_data)

        # Verify credit report
        assert credit_report["application_id"] == application_data["application_id"]
        assert credit_report["cibil_score"] == 790  # Test PAN ABCDE1234F → 790
        assert credit_report["pan_number"] == decrypted_pan
        assert "credit_report_generated_at" in credit_report

        # Re-encrypt PAN for output (as consumer would do)
        credit_report["pan_number"] = encryption_service.encrypt_pan_for_kafka(
            credit_report["pan_number"]
        )

        # Verify PAN is encrypted
        assert credit_report["pan_number"] != original_pan
        assert isinstance(credit_report["pan_number"], str)

    def test_poor_credit_score_with_encryption(self):
        """Test poor credit score calculation with encryption."""
        encryption_key = "test_encryption_key_32_bytes!!"
        encryption_service = EncryptionService(encryption_key)

        # Poor credit test PAN
        original_pan = "FGHIJ5678K"
        encrypted_pan = encryption_service.encrypt_pan_for_kafka(original_pan)

        application_data = {
            "application_id": str(uuid4()),
            "pan_number": encryption_service.decrypt_pan_from_kafka(encrypted_pan),
            "applicant_name": "Test User",
            "monthly_income_inr": 30000.0,
            "loan_amount_inr": 200000.0,
            "loan_type": "PERSONAL",
        }

        credit_report = CibilService.get_credit_report(application_data)

        # Verify poor credit score
        assert credit_report["cibil_score"] == 610  # Test PAN FGHIJ5678K → 610

    def test_deterministic_scoring_with_same_application_id(self):
        """Test that same application_id produces same CIBIL score."""
        encryption_key = "test_encryption_key_32_bytes!!"
        encryption_service = EncryptionService(encryption_key)

        original_pan = "XYZAB9999C"
        encrypted_pan = encryption_service.encrypt_pan_for_kafka(original_pan)
        decrypted_pan = encryption_service.decrypt_pan_from_kafka(encrypted_pan)

        # Fixed application_id for deterministic scoring
        fixed_app_id = str(uuid4())

        application_data = {
            "application_id": fixed_app_id,
            "pan_number": decrypted_pan,
            "applicant_name": "Test User",
            "monthly_income_inr": 50000.0,
            "loan_amount_inr": 300000.0,
            "loan_type": "HOME",
        }

        # Calculate score twice with same application_id
        report1 = CibilService.get_credit_report(application_data)
        report2 = CibilService.get_credit_report(application_data)

        # Verify deterministic scoring
        assert report1["cibil_score"] == report2["cibil_score"]

    def test_message_serialization_deserialization(self):
        """Test JSON message serialization/deserialization."""
        # Create credit report
        credit_report = {
            "application_id": str(uuid4()),
            "pan_number": "encrypted_base64_pan",
            "cibil_score": 750,
            "credit_report_generated_at": "2025-01-03T10:00:00Z",
        }

        # Serialize to JSON (as producer would do)
        json_bytes = json.dumps(credit_report).encode("utf-8")

        # Deserialize (as consumer would do)
        deserialized = json.loads(json_bytes)

        # Verify round-trip
        assert deserialized["application_id"] == credit_report["application_id"]
        assert deserialized["cibil_score"] == credit_report["cibil_score"]
        assert deserialized["pan_number"] == credit_report["pan_number"]

    def test_missing_fields_handling(self):
        """Test handling of message with missing optional fields."""
        encryption_key = "test_encryption_key_32_bytes!!"
        encryption_service = EncryptionService(encryption_key)

        original_pan = "ABCDE1234F"
        decrypted_pan = encryption_service.decrypt_pan_from_kafka(
            encryption_service.encrypt_pan_for_kafka(original_pan)
        )

        # Minimal application data
        application_data = {
            "application_id": str(uuid4()),
            "pan_number": decrypted_pan,
            # Missing other fields - should use defaults
        }

        # Should still calculate a score
        credit_report = CibilService.get_credit_report(application_data)

        assert "cibil_score" in credit_report
        assert credit_report["cibil_score"] >= 300
        assert credit_report["cibil_score"] <= 900

    def test_encryption_decryption_failure_handling(self):
        """Test handling of invalid encrypted data."""
        encryption_key = "test_encryption_key_32_bytes!!"
        encryption_service = EncryptionService(encryption_key)

        # Invalid base64 encrypted data
        invalid_encrypted = "not_valid_base64_encrypted_data"

        # Should raise exception (ValueError or similar from base64/cryptography)
        with pytest.raises((ValueError, Exception), match=".*"):
            encryption_service.decrypt_pan_from_kafka(invalid_encrypted)

    def test_multiple_pans_different_scores(self):
        """Test that different PANs produce different scores (unless test PANs)."""
        application_data_1 = {
            "application_id": str(uuid4()),
            "pan_number": "ABCDE1234F",  # Test PAN → 790
            "applicant_name": "User One",
            "monthly_income_inr": 50000.0,
            "loan_amount_inr": 300000.0,
            "loan_type": "PERSONAL",
        }

        application_data_2 = {
            "application_id": str(uuid4()),
            "pan_number": "FGHIJ5678K",  # Test PAN → 610
            "applicant_name": "User Two",
            "monthly_income_inr": 50000.0,
            "loan_amount_inr": 300000.0,
            "loan_type": "PERSONAL",
        }

        report1 = CibilService.get_credit_report(application_data_1)
        report2 = CibilService.get_credit_report(application_data_2)

        # Different test PANs should give different scores
        assert report1["cibil_score"] == 790
        assert report2["cibil_score"] == 610
        assert report1["cibil_score"] != report2["cibil_score"]
