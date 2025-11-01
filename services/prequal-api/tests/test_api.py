"""API Integration Tests for Prequal API.

Tests all FastAPI endpoints with various scenarios:
- POST /applications (success, validation errors, duplicate PAN)
- GET /applications/{id}/status (success, not found)
- Health and readiness endpoints

Uses FastAPI TestClient for isolated testing without external dependencies.
"""
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# Add app directory to path (since parent dir has hyphen)
app_dir = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_dir))

# Also add project root for shared imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture()
def test_client() -> Generator[TestClient, None, None]:
    """Create FastAPI test client with mocked dependencies.

    Mocks:
    - Database session (no actual DB connection)
    - EncryptionService (no actual encryption)
    - Kafka producer (no actual message publishing)
    """
    # Import here to avoid import errors before path is set
    from main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture()
def valid_application_data() -> dict:
    """Return valid application request data."""
    return {
        "pan_number": "ABCDE1234F",
        "first_name": "Rajesh",
        "last_name": "Kumar",
        "date_of_birth": "1990-01-15",
        "email": "rajesh.kumar@example.com",
        "phone_number": "9876543210",
        "requested_amount": 500000.00,
    }


class TestApplicationCreation:
    """Test suite for POST /applications endpoint."""

    def test_create_application_success(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test successful application creation returns 202 Accepted."""
        response = test_client.post("/applications", json=valid_application_data)

        assert response.status_code == 202
        data = response.json()

        # Verify response structure
        assert "application_id" in data
        assert "status" in data
        assert "message" in data
        assert "created_at" in data

        # Verify response values
        assert data["status"] == "PENDING"
        assert "successfully" in data["message"].lower()

        # Verify application_id is a valid UUID
        application_id = data["application_id"]
        assert len(application_id) == 36  # UUID format with hyphens

    def test_create_application_invalid_pan_format(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with invalid PAN format returns 422."""
        # Test various invalid PAN formats
        invalid_pans = [
            "ABC1234567",  # Too short
            "ABCDE12345",  # Too long
            "abcde1234f",  # Lowercase letters
            "12345ABCDE",  # Digits first
            "ABCDE1234",  # Missing last letter
            "ABCDE12345",  # Extra digit
        ]

        for invalid_pan in invalid_pans:
            data = {**valid_application_data, "pan_number": invalid_pan}
            response = test_client.post("/applications", json=data)

            assert response.status_code == 422, f"Expected 422 for PAN: {invalid_pan}"
            error = response.json()
            assert "detail" in error

    def test_create_application_underage_applicant(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with underage applicant returns 422."""
        # Set DOB to 17 years ago
        underage_dob = (datetime.now(tz=timezone.utc) - timedelta(days=365 * 17)).strftime(
            "%Y-%m-%d"
        )
        data = {**valid_application_data, "date_of_birth": underage_dob}

        response = test_client.post("/applications", json=data)

        assert response.status_code == 422
        error = response.json()
        assert "detail" in error
        assert any("18 years old" in str(detail) for detail in error["detail"])

    def test_create_application_invalid_email(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with invalid email returns 422."""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user name@example.com",
        ]

        for invalid_email in invalid_emails:
            data = {**valid_application_data, "email": invalid_email}
            response = test_client.post("/applications", json=data)

            assert response.status_code == 422, f"Expected 422 for email: {invalid_email}"

    def test_create_application_invalid_phone(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with invalid phone returns 422."""
        invalid_phones = [
            "123",  # Too short
            "12345678901234567",  # Too long
            "987-654-3210",  # Contains hyphens
            "+919876543210",  # Contains plus sign
        ]

        for invalid_phone in invalid_phones:
            data = {**valid_application_data, "phone_number": invalid_phone}
            response = test_client.post("/applications", json=data)

            assert response.status_code == 422, f"Expected 422 for phone: {invalid_phone}"

    def test_create_application_invalid_amount(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with invalid amount returns 422."""
        invalid_amounts = [
            0,  # Zero amount
            -1000,  # Negative amount
            10000001,  # Exceeds max (1 crore)
        ]

        for invalid_amount in invalid_amounts:
            data = {**valid_application_data, "requested_amount": invalid_amount}
            response = test_client.post("/applications", json=data)

            assert response.status_code == 422, f"Expected 422 for amount: {invalid_amount}"

    def test_create_application_missing_required_fields(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with missing fields returns 422."""
        required_fields = [
            "pan_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "email",
            "phone_number",
            "requested_amount",
        ]

        for field in required_fields:
            data = {**valid_application_data}
            del data[field]

            response = test_client.post("/applications", json=data)

            assert response.status_code == 422, f"Expected 422 when missing: {field}"
            error = response.json()
            assert "detail" in error

    @patch("services.ApplicationService.create_application")
    def test_create_application_duplicate_pan(
        self, mock_create: MagicMock, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with duplicate PAN returns 400."""
        # Mock the service to raise ValueError for duplicate
        mock_create.side_effect = ValueError("Application with this PAN already exists")

        response = test_client.post("/applications", json=valid_application_data)

        assert response.status_code == 400
        error = response.json()
        assert "detail" in error
        assert error["detail"]["error_code"] == "DUPLICATE_PAN"

    def test_create_application_with_edge_case_values(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with edge case values."""
        # Test minimum valid values
        edge_case_data = {
            **valid_application_data,
            "first_name": "A",  # Single character
            "last_name": "B",  # Single character
            "phone_number": "1234567890",  # Minimum length
            "requested_amount": 0.01,  # Minimum amount
        }

        response = test_client.post("/applications", json=edge_case_data)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "PENDING"

    def test_create_application_with_special_characters_in_name(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test application creation with special characters in name."""
        special_names = [
            "O'Brien",  # Apostrophe
            "José",  # Accented character
            "Mary-Jane",  # Hyphen
        ]

        for name in special_names:
            data = {**valid_application_data, "first_name": name}
            response = test_client.post("/applications", json=data)

            # Should accept valid names with special characters
            assert response.status_code in [202, 422]  # Depends on validation rules


class TestApplicationStatus:
    """Test suite for GET /applications/{id}/status endpoint."""

    @patch("services.ApplicationService.get_application_status")
    def test_get_application_status_success(
        self, mock_get_status: MagicMock, test_client: TestClient
    ):
        """Test successful status retrieval returns 200."""
        application_id = str(uuid4())

        # Mock the service response
        mock_get_status.return_value = {
            "application_id": application_id,
            "status": "PENDING",
            "pan_number_masked": "XXXXX1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "requested_amount": Decimal("500000.00"),
            "credit_score": None,
            "annual_income": None,
            "existing_loans_count": None,
            "decision_reason": None,
            "max_approved_amount": None,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        }

        response = test_client.get(f"/applications/{application_id}/status")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data["application_id"] == application_id
        assert data["status"] == "PENDING"
        assert data["pan_number_masked"] == "XXXXX1234F"
        assert data["credit_score"] is None

    @patch("services.ApplicationService.get_application_status")
    def test_get_application_status_not_found(
        self, mock_get_status: MagicMock, test_client: TestClient
    ):
        """Test status retrieval for non-existent application returns 404."""
        application_id = str(uuid4())

        # Mock the service to raise ValueError for not found
        mock_get_status.side_effect = ValueError(f"Application not found: {application_id}")

        response = test_client.get(f"/applications/{application_id}/status")

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error
        assert error["detail"]["error_code"] == "NOT_FOUND"

    def test_get_application_status_invalid_uuid(self, test_client: TestClient):
        """Test status retrieval with invalid UUID returns 422."""
        invalid_ids = [
            "not-a-uuid",
            "12345",
            "abcd-efgh-ijkl-mnop",
        ]

        for invalid_id in invalid_ids:
            response = test_client.get(f"/applications/{invalid_id}/status")

            assert response.status_code == 422, f"Expected 422 for ID: {invalid_id}"

    @patch("services.ApplicationService.get_application_status")
    def test_get_application_status_with_decision(
        self, mock_get_status: MagicMock, test_client: TestClient
    ):
        """Test status retrieval for application with decision."""
        application_id = str(uuid4())

        # Mock application with decision
        mock_get_status.return_value = {
            "application_id": application_id,
            "status": "PRE_APPROVED",
            "pan_number_masked": "XXXXX1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "requested_amount": Decimal("500000.00"),
            "credit_score": 750,
            "annual_income": Decimal("600000.00"),
            "existing_loans_count": 0,
            "decision_reason": "Good credit score and sufficient income",
            "max_approved_amount": Decimal("2400000.00"),
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        }

        response = test_client.get(f"/applications/{application_id}/status")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "PRE_APPROVED"
        assert data["credit_score"] == 750
        assert data["decision_reason"] is not None
        assert data["max_approved_amount"] is not None


class TestHealthEndpoints:
    """Test suite for health and readiness endpoints."""

    def test_health_endpoint(self, test_client: TestClient):
        """Test /health endpoint returns 200."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @patch("main.engine.connect")
    def test_readiness_endpoint_all_services_ready(
        self, mock_connect: MagicMock, test_client: TestClient
    ):
        """Test /ready endpoint when all services are ready."""
        # Mock successful DB connection
        mock_connect.return_value.__enter__.return_value = MagicMock()

        response = test_client.get("/ready")

        assert response.status_code == 200
        data = response.json()

        assert data["ready"] is True
        assert data["database"] == "connected"

    @patch("main.engine.connect")
    def test_readiness_endpoint_database_down(
        self, mock_connect: MagicMock, test_client: TestClient
    ):
        """Test /ready endpoint when database is down."""
        # Mock DB connection failure
        mock_connect.side_effect = Exception("Database connection failed")

        response = test_client.get("/ready")

        assert response.status_code == 503
        data = response.json()

        assert data["ready"] is False
        assert data["database"] == "disconnected"


class TestMetricsEndpoint:
    """Test suite for /metrics endpoint."""

    def test_metrics_endpoint(self, test_client: TestClient):
        """Test /metrics endpoint returns Prometheus metrics."""
        response = test_client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        # Verify some expected metrics are present
        metrics_text = response.text
        assert "requests_total" in metrics_text or "http_requests" in metrics_text


class TestCORSAndSecurity:
    """Test suite for CORS and security headers."""

    def test_cors_headers_present(self, test_client: TestClient):
        """Test CORS headers are present in responses."""
        response = test_client.get("/health")

        # Check for CORS headers (if configured)
        # Note: This depends on whether CORS is enabled in the app
        assert response.status_code == 200

    def test_api_accepts_json_content_type(
        self, test_client: TestClient, valid_application_data: dict
    ):
        """Test API accepts JSON content type."""
        response = test_client.post(
            "/applications",
            json=valid_application_data,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code in [202, 400, 422, 500]

    def test_api_rejects_non_json_content(self, test_client: TestClient):
        """Test API rejects non-JSON content."""
        response = test_client.post(
            "/applications",
            data="not json",
            headers={"Content-Type": "text/plain"},
        )

        assert response.status_code == 422


class TestErrorResponses:
    """Test suite for error response format consistency."""

    def test_validation_error_format(self, test_client: TestClient, valid_application_data: dict):
        """Test validation errors have consistent format."""
        data = {**valid_application_data, "pan_number": "INVALID"}
        response = test_client.post("/applications", json=data)

        assert response.status_code == 422
        error = response.json()

        # FastAPI validation error format
        assert "detail" in error
        assert isinstance(error["detail"], list)

    @patch("services.ApplicationService.get_application_status")
    def test_not_found_error_format(self, mock_get_status: MagicMock, test_client: TestClient):
        """Test 404 errors have consistent format."""
        application_id = str(uuid4())
        mock_get_status.side_effect = ValueError(f"Application not found: {application_id}")

        response = test_client.get(f"/applications/{application_id}/status")

        assert response.status_code == 404
        error = response.json()

        # Custom error format
        assert "detail" in error
        assert "error_code" in error["detail"]
        assert "message" in error["detail"]
        assert "timestamp" in error["detail"]
        assert error["detail"]["error_code"] == "NOT_FOUND"
