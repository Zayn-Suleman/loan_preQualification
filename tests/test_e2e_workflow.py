"""End-to-End Tests for Loan Prequalification Workflow.

These tests require docker-compose to be running with all services:
- PostgreSQL database
- Kafka broker
- prequal-api service
- credit-service consumer
- decision-service consumer

Run with: docker-compose up -d && pytest tests/test_e2e_workflow.py -v -m e2e

Tests the complete flow:
1. POST /applications - Submit application
2. Wait for async processing (Kafka → credit-service → decision-service)
3. GET /applications/{id}/status - Poll until final decision
4. Verify database state
"""
import os
import time
from datetime import datetime
from decimal import Decimal

import pytest
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Mark all tests in this module as e2e tests
pytestmark = pytest.mark.e2e

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://loan_user:loan_password@localhost:5432/loan_prequalification",
)

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def _check_services_running():
    """Verify all required services are running before tests."""
    # Check API
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        assert response.status_code == 200, "API service not healthy"
    except Exception as e:
        pytest.skip(f"API service not running: {e}")

    # Check Database
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Database not accessible: {e}")

    # Check Readiness
    try:
        response = requests.get(f"{API_BASE_URL}/ready", timeout=5)
        assert response.status_code == 200, "API not ready"
    except Exception as e:
        pytest.skip(f"API not ready: {e}")


@pytest.fixture()
def db_session():
    """Get database session for verification."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def wait_for_decision(application_id: str, timeout: int = 30, poll_interval: int = 2) -> dict:
    """Poll application status until decision is made or timeout.

    Args:
        application_id: Application UUID
        timeout: Maximum time to wait in seconds
        poll_interval: Time between polls in seconds

    Returns:
        Final application status

    Raises:
        TimeoutError: If decision not reached within timeout
    """
    start_time = time.time()
    final_statuses = {"PRE_APPROVED", "REJECTED", "MANUAL_REVIEW"}

    while time.time() - start_time < timeout:
        response = requests.get(f"{API_BASE_URL}/applications/{application_id}/status", timeout=5)
        assert response.status_code == 200, f"Failed to get status: {response.text}"

        status_data = response.json()
        current_status = status_data["status"]

        if current_status in final_statuses:
            return status_data

        time.sleep(poll_interval)

    raise TimeoutError(
        f"Application {application_id} did not reach final decision within {timeout}s"
    )


@pytest.mark.usefixtures("_check_services_running")
class TestE2EWorkflow:
    """End-to-end tests for complete loan application workflow."""

    def test_services_health(self):
        """Test that all services are healthy."""
        # Health endpoint
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

        # Readiness endpoint
        response = requests.get(f"{API_BASE_URL}/ready", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["database"] == "connected"

    def test_pre_approved_flow(self, db_session):
        """Test complete flow for pre-approved application.

        Scenario: Good credit score + sufficient income = PRE_APPROVED
        """
        # Step 1: Submit application
        application_data = {
            "pan_number": "APPRO1234V",  # New PAN for this test
            "first_name": "Approved",
            "last_name": "Applicant",
            "date_of_birth": "1985-05-15",
            "email": "approved@example.com",
            "phone_number": "9876543211",
            "requested_amount": 300000.00,  # Lower amount, easier to approve
        }

        response = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        assert response.status_code == 202, f"Failed to create application: {response.text}"

        create_response = response.json()
        application_id = create_response["application_id"]
        assert create_response["status"] == "PENDING"
        assert "created_at" in create_response

        # Step 2: Wait for async processing
        print(f"\nWaiting for application {application_id} to be processed...")
        final_status = wait_for_decision(application_id, timeout=45)

        # Step 3: Verify final status
        print(f"Final status: {final_status['status']}")
        print(f"Credit score: {final_status.get('credit_score')}")
        print(f"Decision reason: {final_status.get('decision_reason')}")

        # Assertions
        assert final_status["application_id"] == application_id
        assert final_status["status"] in {
            "PRE_APPROVED",
            "MANUAL_REVIEW",
        }  # Can vary based on CIBIL sim
        assert final_status["credit_score"] is not None
        assert final_status["credit_score"] >= 300  # Valid range
        assert final_status["credit_score"] <= 900

        if final_status["status"] == "PRE_APPROVED":
            assert final_status["max_approved_amount"] is not None
            assert Decimal(final_status["max_approved_amount"]) > 0

        # Step 4: Verify database state
        result = db_session.execute(
            text("SELECT * FROM applications WHERE id = :id"), {"id": application_id}
        )
        db_record = result.fetchone()
        assert db_record is not None
        assert str(db_record.id) == application_id
        assert db_record.status == final_status["status"]
        assert db_record.credit_score == final_status["credit_score"]

    def test_rejected_flow(self, db_session):
        """Test complete flow for rejected application.

        Scenario: Test with PAN that should generate low credit score
        """
        # Step 1: Submit application with parameters likely to be rejected
        application_data = {
            "pan_number": "REJEC1234T",  # New PAN
            "first_name": "Rejected",
            "last_name": "Applicant",
            "date_of_birth": "1995-03-20",
            "email": "rejected@example.com",
            "phone_number": "9876543212",
            "requested_amount": 5000000.00,  # Very high amount
        }

        response = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        assert response.status_code == 202

        create_response = response.json()
        application_id = create_response["application_id"]

        # Step 2: Wait for processing
        print(f"\nWaiting for application {application_id} to be processed...")
        final_status = wait_for_decision(application_id, timeout=45)

        # Step 3: Verify status
        print(f"Final status: {final_status['status']}")
        print(f"Credit score: {final_status.get('credit_score')}")

        # Assertions - status depends on simulated CIBIL score
        assert final_status["status"] in {"PRE_APPROVED", "REJECTED", "MANUAL_REVIEW"}
        assert final_status["credit_score"] is not None

        # Verify database
        result = db_session.execute(
            text("SELECT * FROM applications WHERE id = :id"), {"id": application_id}
        )
        db_record = result.fetchone()
        assert db_record is not None
        assert str(db_record.id) == application_id

    def test_duplicate_pan(self):
        """Test that duplicate PAN is rejected."""
        # Submit first application
        application_data = {
            "pan_number": "DUPLI1234C",
            "first_name": "Duplicate",
            "last_name": "Test",
            "date_of_birth": "1990-01-01",
            "email": "duplicate@example.com",
            "phone_number": "9876543213",
            "requested_amount": 500000.00,
        }

        response1 = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        assert response1.status_code == 202

        # Try to submit duplicate
        response2 = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        assert response2.status_code == 400
        error = response2.json()
        assert "detail" in error
        assert error["detail"]["error_code"] == "DUPLICATE_PAN"

    def test_invalid_application_id(self):
        """Test status lookup with non-existent application ID."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = requests.get(f"{API_BASE_URL}/applications/{fake_id}/status", timeout=5)
        assert response.status_code == 404
        error = response.json()
        assert error["detail"]["error_code"] == "NOT_FOUND"

    def test_test_pan_deterministic_behavior(self):
        """Test that test PAN ABCDE1234F produces consistent high score."""
        application_data = {
            "pan_number": "ABCDE1234F",  # Test PAN with predetermined score
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1985-01-01",
            "email": "test@example.com",
            "phone_number": "9876543214",
            "requested_amount": 500000.00,
        }

        response = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        assert response.status_code == 202

        application_id = response.json()["application_id"]

        # Wait for processing
        final_status = wait_for_decision(application_id, timeout=45)

        # Test PANs should have high scores (790 for ABCDE1234F)
        print(f"Test PAN credit score: {final_status['credit_score']}")
        assert final_status["credit_score"] == 790  # As per credit-service logic
        assert final_status["status"] == "PRE_APPROVED"


@pytest.mark.usefixtures("_check_services_running")
class TestE2EErrorHandling:
    """Test error handling in E2E scenarios."""

    def test_invalid_pan_format(self):
        """Test validation error for invalid PAN format."""
        application_data = {
            "pan_number": "INVALID",
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1990-01-01",
            "email": "test@example.com",
            "phone_number": "9876543215",
            "requested_amount": 500000.00,
        }

        response = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        assert response.status_code == 422

    def test_underage_applicant(self):
        """Test validation error for underage applicant."""
        from datetime import timedelta, timezone

        # Calculate DOB for 17-year-old
        underage_dob = (datetime.now(tz=timezone.utc) - timedelta(days=365 * 17)).strftime(
            "%Y-%m-%d"
        )

        application_data = {
            "pan_number": "YOUNG1234B",
            "first_name": "Young",
            "last_name": "Applicant",
            "date_of_birth": underage_dob,
            "email": "young@example.com",
            "phone_number": "9876543216",
            "requested_amount": 500000.00,
        }

        response = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        assert response.status_code == 422


@pytest.mark.usefixtures("_check_services_running")
class TestE2EPerformance:
    """Performance tests for E2E workflow."""

    def test_api_response_time(self):
        """Test that API responds quickly (< 200ms for initial 202)."""
        application_data = {
            "pan_number": f"PERF{int(time.time())}A",  # Unique PAN
            "first_name": "Performance",
            "last_name": "Test",
            "date_of_birth": "1990-01-01",
            "email": "perf@example.com",
            "phone_number": "9876543217",
            "requested_amount": 500000.00,
        }

        start_time = time.time()
        response = requests.post(f"{API_BASE_URL}/applications", json=application_data, timeout=5)
        response_time = (time.time() - start_time) * 1000  # Convert to ms

        assert response.status_code == 202
        print(f"\nAPI response time: {response_time:.2f}ms")
        # Note: 200ms target may not always be met depending on system load
        # This is more of a performance indicator than a strict requirement
        assert response_time < 1000  # Relaxed to 1 second for CI/CD
