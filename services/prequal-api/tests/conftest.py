"""Pytest fixtures for prequal-api tests."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add app directory to path
app_dir = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_dir))


@pytest.fixture()
def mock_db_session():
    """Mock database session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    session.query = MagicMock()
    return session


@pytest.fixture()
def mock_encryption_service():
    """Mock encryption service."""
    service = MagicMock()
    service.encrypt.return_value = b"encrypted_data"
    service.decrypt.return_value = "ABCDE1234F"
    return service


@pytest.fixture()
def valid_application_data():
    """Valid application request data."""
    return {
        "pan_number": "ABCDE1234F",
        "first_name": "Rajesh",
        "last_name": "Kumar",
        "date_of_birth": "1990-01-15",
        "email": "rajesh.kumar@example.com",
        "phone_number": "9876543210",
        "requested_amount": 500000.00,
    }
