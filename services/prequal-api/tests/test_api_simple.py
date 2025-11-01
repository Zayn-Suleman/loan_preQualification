"""Simplified API Integration Tests for Prequal API.

Tests API endpoints using mock data without requiring full app initialization.
This is a temporary simplified version to demonstrate test structure.

For full integration tests with real DB/Kafka, see test_integration.py (TODO).
"""
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

# Add app directory to path (to avoid hyphenated directory import issues)
app_dir = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_dir))


class TestApplicationValidation:
    """Test Pydantic model validation logic."""

    def test_valid_pan_format(self):
        """Test PAN validation accepts valid formats."""
        from models import ApplicationCreateRequest

        # This should not raise
        valid_pans = ["ABCDE1234F", "ZYXWV9876K"]

        for pan in valid_pans:
            try:
                request = ApplicationCreateRequest(
                    pan_number=pan,
                    first_name="Test",
                    last_name="User",
                    date_of_birth=date(1990, 1, 1),
                    email="test@example.com",
                    phone_number="9876543210",
                    requested_amount=500000.00,
                )
                assert request.pan_number == pan
            except Exception as e:
                pytest.fail(f"Valid PAN {pan} failed validation: {e}")

    def test_invalid_pan_format(self):
        """Test PAN validation rejects invalid formats."""
        from models import ApplicationCreateRequest
        from pydantic import ValidationError

        invalid_pans = [
            "ABC1234567",  # Wrong format
            "abcde1234f",  # Lowercase
            "12345ABCDE",  # Numbers first
        ]

        for invalid_pan in invalid_pans:
            with pytest.raises(ValidationError):
                ApplicationCreateRequest(
                    pan_number=invalid_pan,
                    first_name="Test",
                    last_name="User",
                    date_of_birth=date(1990, 1, 1),
                    email="test@example.com",
                    phone_number="9876543210",
                    requested_amount=500000.00,
                )

    def test_underage_validation(self):
        """Test age validation rejects underage applicants."""
        from datetime import datetime, timedelta, timezone

        from models import ApplicationCreateRequest
        from pydantic import ValidationError

        # Create DOB for 17-year-old
        underage_dob = datetime.now(tz=timezone.utc).date() - timedelta(days=365 * 17)

        with pytest.raises(ValidationError) as exc_info:
            ApplicationCreateRequest(
                pan_number="ABCDE1234F",
                first_name="Young",
                last_name="Person",
                date_of_birth=underage_dob,
                email="young@example.com",
                phone_number="9876543210",
                requested_amount=100000.00,
            )

        # Check error message
        assert "18 years old" in str(exc_info.value)

    def test_invalid_email(self):
        """Test email validation."""
        from models import ApplicationCreateRequest
        from pydantic import ValidationError

        invalid_emails = ["not-an-email", "@example.com", "user@"]

        for invalid_email in invalid_emails:
            with pytest.raises(ValidationError):
                ApplicationCreateRequest(
                    pan_number="ABCDE1234F",
                    first_name="Test",
                    last_name="User",
                    date_of_birth=date(1990, 1, 1),
                    email=invalid_email,
                    phone_number="9876543210",
                    requested_amount=500000.00,
                )

    def test_invalid_phone_number(self):
        """Test phone number validation."""
        from models import ApplicationCreateRequest
        from pydantic import ValidationError

        # Phone with non-digits should fail
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(
                pan_number="ABCDE1234F",
                first_name="Test",
                last_name="User",
                date_of_birth=date(1990, 1, 1),
                email="test@example.com",
                phone_number="987-654-3210",  # Contains hyphens
                requested_amount=500000.00,
            )

    def test_invalid_amount(self):
        """Test amount validation."""
        from models import ApplicationCreateRequest
        from pydantic import ValidationError

        # Zero amount should fail
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(
                pan_number="ABCDE1234F",
                first_name="Test",
                last_name="User",
                date_of_birth=date(1990, 1, 1),
                email="test@example.com",
                phone_number="9876543210",
                requested_amount=0,
            )

        # Negative amount should fail
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(
                pan_number="ABCDE1234F",
                first_name="Test",
                last_name="User",
                date_of_birth=date(1990, 1, 1),
                email="test@example.com",
                phone_number="9876543210",
                requested_amount=-1000,
            )

    def test_missing_required_fields(self):
        """Test validation fails when required fields are missing."""
        from models import ApplicationCreateRequest
        from pydantic import ValidationError

        # Missing pan_number
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(
                first_name="Test",
                last_name="User",
                date_of_birth=date(1990, 1, 1),
                email="test@example.com",
                phone_number="9876543210",
                requested_amount=500000.00,
            )


class TestApplicationStatusResponse:
    """Test ApplicationStatusResponse model."""

    def test_status_response_creation(self):
        """Test creating a status response."""
        from datetime import datetime, timezone
        from decimal import Decimal

        from models import ApplicationStatusResponse

        response = ApplicationStatusResponse(
            application_id=uuid4(),
            status="PENDING",
            pan_number_masked="XXXXX1234F",
            first_name="Rajesh",
            last_name="Kumar",
            requested_amount=Decimal("500000.00"),
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )

        assert response.status == "PENDING"
        assert response.pan_number_masked == "XXXXX1234F"
        assert response.credit_score is None  # Optional field


class TestErrorCodeEnum:
    """Test ErrorCode enum."""

    def test_error_codes_exist(self):
        """Test that all expected error codes exist."""
        from models import ErrorCode

        expected_codes = [
            "VALIDATION_ERROR",
            "DUPLICATE_PAN",
            "NOT_FOUND",
            "INTERNAL_ERROR",
        ]

        for code in expected_codes:
            assert hasattr(ErrorCode, code), f"Missing error code: {code}"


# Note: Full API endpoint tests with FastAPI TestClient require:
# 1. Mocking database session
# 2. Mocking EncryptionService
# 3. Mocking Kafka producer
# 4. Proper app initialization with test dependencies
#
# These will be added in test_api_full.py once infrastructure mocking is set up.
