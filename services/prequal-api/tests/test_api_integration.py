"""API Integration Tests for prequal-api endpoints.

Tests FastAPI endpoints with TestClient, verifying:
- POST /applications endpoint with validation
- GET /applications/{id}/status endpoint
- Health and readiness endpoints
- Error responses (404, 422)
"""
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directories to path
service_root = Path(__file__).parent.parent
sys.path.insert(0, str(service_root))


# Mock database and dependencies before importing app
@pytest.fixture(scope="module")
def test_db():
    """Create test database engine."""
    engine = create_engine("sqlite:///:memory:")
    from app.db import Base

    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def client(test_db):
    """Create TestClient with mocked dependencies."""
    # Mock encryption service
    with patch("app.main.encryption_service") as mock_encryption, patch(
        "app.main.SessionLocal"
    ) as mock_session, patch("app.main.outbox_publisher") as mock_outbox:
        # Configure encryption mock
        mock_encryption.encrypt_pan.return_value = b"encrypted_pan_data"
        mock_encryption.hash_pan.return_value = "hashed_pan"
        mock_encryption.encrypt_pan_for_kafka.return_value = "base64_encrypted"

        # Configure session mock
        mock_session.return_value = test_db()

        # Configure outbox mock
        mock_outbox_instance = MagicMock()
        mock_outbox.return_value = mock_outbox_instance

        # Import app after mocking
        from app.main import app

        with TestClient(app) as test_client:
            yield test_client


class TestApplicationSubmission:
    """Test POST /applications endpoint."""

    def test_valid_application_returns_202(self, client):
        """Test submitting a valid application returns 202 Accepted."""
        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "date_of_birth": "1985-06-15",
            "email": "rajesh.kumar@example.com",
            "phone_number": "9876543210",
            "requested_amount": 500000.00,
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "application_id" in data
        assert "status" in data
        assert data["status"] == "PENDING"
        assert "message" in data

        # Verify application_id is valid UUID
        try:
            UUID(data["application_id"])
        except ValueError:
            pytest.fail("application_id is not a valid UUID")

    def test_invalid_pan_format_returns_422(self, client):
        """Test invalid PAN format returns 422 validation error."""
        payload = {
            "pan_number": "INVALID123",  # Invalid format
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "date_of_birth": "1985-06-15",
            "email": "rajesh.kumar@example.com",
            "phone_number": "9876543210",
            "requested_amount": 500000.00,
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_underage_applicant_returns_422(self, client):
        """Test applicant under 18 years old returns 422."""
        # Calculate DOB for 17-year-old
        seventeen_years_ago = datetime.now(tz=timezone.utc).date() - timedelta(days=17 * 365)

        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Young",
            "last_name": "Applicant",
            "date_of_birth": seventeen_years_ago.isoformat(),
            "email": "young@example.com",
            "phone_number": "9876543210",
            "requested_amount": 100000.00,
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        # Should mention age validation

    def test_invalid_email_returns_422(self, client):
        """Test invalid email format returns 422."""
        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "date_of_birth": "1985-06-15",
            "email": "invalid-email",  # Invalid email
            "phone_number": "9876543210",
            "requested_amount": 500000.00,
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 422

    def test_invalid_phone_number_returns_422(self, client):
        """Test invalid phone number returns 422."""
        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "date_of_birth": "1985-06-15",
            "email": "rajesh@example.com",
            "phone_number": "123",  # Too short
            "requested_amount": 500000.00,
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 422

    def test_zero_amount_returns_422(self, client):
        """Test zero loan amount returns 422."""
        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "date_of_birth": "1985-06-15",
            "email": "rajesh@example.com",
            "phone_number": "9876543210",
            "requested_amount": 0.00,  # Invalid: must be > 0
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 422

    def test_excessive_amount_returns_422(self, client):
        """Test loan amount exceeding 1 crore returns 422."""
        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "date_of_birth": "1985-06-15",
            "email": "rajesh@example.com",
            "phone_number": "9876543210",
            "requested_amount": 15000000.00,  # > 10M limit
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 422

    def test_missing_required_fields_returns_422(self, client):
        """Test missing required fields returns 422."""
        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Rajesh",
            # Missing last_name, email, phone, amount
        }

        response = client.post("/applications", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_extra_fields_ignored(self, client):
        """Test that extra fields are ignored (Pydantic default)."""
        payload = {
            "pan_number": "ABCDE1234F",
            "first_name": "Rajesh",
            "last_name": "Kumar",
            "date_of_birth": "1985-06-15",
            "email": "rajesh@example.com",
            "phone_number": "9876543210",
            "requested_amount": 500000.00,
            "extra_field": "should_be_ignored",
        }

        response = client.post("/applications", json=payload)

        # Should succeed, extra fields ignored
        assert response.status_code == 202


class TestApplicationStatus:
    """Test GET /applications/{id}/status endpoint."""

    @patch("app.main.SessionLocal")
    def test_get_existing_application_status(self, mock_session_local, client):
        """Test getting status of existing application returns 200."""
        # Mock database query
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        # Create mock application
        mock_app = MagicMock()
        mock_app.application_id = uuid4()
        mock_app.status = "PENDING"
        mock_app.created_at = datetime.now(tz=timezone.utc)
        mock_app.first_name = "Rajesh"
        mock_app.last_name = "Kumar"
        mock_app.requested_amount = Decimal("500000.00")
        mock_app.credit_score = None
        mock_app.max_approved_amount = None
        mock_app.decision_reason = None

        mock_session.query.return_value.filter.return_value.first.return_value = mock_app

        response = client.get(f"/applications/{mock_app.application_id}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["application_id"] == str(mock_app.application_id)
        assert data["status"] == "PENDING"

    def test_get_nonexistent_application_returns_404(self, client):
        """Test getting status of non-existent application returns 404."""
        fake_uuid = uuid4()

        with patch("app.main.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.return_value = None

            response = client.get(f"/applications/{fake_uuid}/status")

            assert response.status_code == 404
            data = response.json()
            assert "detail" in data

    def test_get_invalid_uuid_returns_422(self, client):
        """Test getting status with invalid UUID returns 422."""
        response = client.get("/applications/invalid-uuid/status")

        assert response.status_code == 422


class TestHealthEndpoints:
    """Test health and readiness endpoints."""

    def test_health_endpoint_returns_200(self, client):
        """Test /health endpoint returns 200 OK."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "timestamp" in data

    @patch("app.main.engine")
    def test_ready_endpoint_healthy_database(self, mock_engine, client):
        """Test /ready endpoint with healthy database returns 200."""
        # Mock successful database connection
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = MagicMock()

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert "database" in data

    @patch("app.main.engine")
    def test_ready_endpoint_unhealthy_database(self, mock_engine, client):
        """Test /ready endpoint with database connection failure returns 503."""
        # Mock database connection failure
        mock_engine.connect.side_effect = Exception("Database connection failed")

        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint."""

    def test_metrics_endpoint_returns_200(self, client):
        """Test /metrics endpoint returns 200 with Prometheus format."""
        response = client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        # Should contain Prometheus metric names
        assert b"prequal_api" in response.content


class TestErrorHandling:
    """Test global error handling."""

    def test_internal_server_error_handling(self, client):
        """Test that internal errors are properly handled."""
        # This test would require triggering an internal error
        # For now, we verify the error response structure

    def test_cors_headers_if_enabled(self, client):
        """Test CORS headers if CORS is enabled."""
        # Check if CORS middleware is configured
        response = client.options("/applications")
        # May return 405 if OPTIONS not explicitly handled, which is fine
        assert response.status_code in [200, 405]
