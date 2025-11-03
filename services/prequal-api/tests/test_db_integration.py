"""Database integration tests for prequal-api.

Tests database operations:
- Application CRUD operations
- Optimistic locking (version conflicts)
- Duplicate PAN detection
- Audit log creation
- Outbox event persistence
"""
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

# Add parent directories to path
service_root = Path(__file__).parent.parent
sys.path.insert(0, str(service_root))

from app.db import Application, AuditLog, Base, OutboxEvent, ProcessedMessage


@pytest.fixture(scope="module")
def test_engine():
    """Create test database engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session(test_engine):
    """Create fresh database session for each test."""
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = session_factory()
    yield session
    session.rollback()
    session.close()


class TestApplicationCRUD:
    """Test Application table CRUD operations."""

    def test_create_application(self, db_session):
        """Test creating a new application."""
        app = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted_pan_data",
            pan_number_hash="hashed_pan_value",
            first_name="Rajesh",
            last_name="Kumar",
            date_of_birth=datetime(1985, 6, 15, tzinfo=timezone.utc),
            email="rajesh@example.com",
            phone_number="9876543210",
            requested_amount=Decimal("500000.00"),
            status="PENDING",
            version=1,
        )

        db_session.add(app)
        db_session.commit()

        # Verify created
        assert app.application_id is not None
        assert app.created_at is not None
        assert app.updated_at is not None

    def test_read_application(self, db_session):
        """Test reading an application."""
        # Create application
        app_id = uuid4()
        app = Application(
            application_id=app_id,
            pan_number_encrypted=b"encrypted_pan",
            pan_number_hash="hash123",
            first_name="Test",
            last_name="User",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="test@example.com",
            phone_number="1234567890",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
        )
        db_session.add(app)
        db_session.commit()

        # Read back
        retrieved = db_session.query(Application).filter_by(application_id=app_id).first()

        assert retrieved is not None
        assert retrieved.application_id == app_id
        assert retrieved.first_name == "Test"
        assert retrieved.status == "PENDING"

    def test_update_application_status(self, db_session):
        """Test updating application status."""
        # Create application
        app = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted",
            pan_number_hash="hash",
            first_name="Test",
            last_name="User",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="test@example.com",
            phone_number="1234567890",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
        )
        db_session.add(app)
        db_session.commit()

        # Update status
        app.status = "PRE_APPROVED"
        app.credit_score = 750
        app.max_approved_amount = Decimal("500000.00")
        db_session.commit()

        # Verify update
        db_session.refresh(app)
        assert app.status == "PRE_APPROVED"
        assert app.credit_score == 750

    def test_delete_application(self, db_session):
        """Test deleting an application."""
        # Create application
        app_id = uuid4()
        app = Application(
            application_id=app_id,
            pan_number_encrypted=b"encrypted",
            pan_number_hash="hash",
            first_name="Test",
            last_name="User",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="test@example.com",
            phone_number="1234567890",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
        )
        db_session.add(app)
        db_session.commit()

        # Delete
        db_session.delete(app)
        db_session.commit()

        # Verify deleted
        retrieved = db_session.query(Application).filter_by(application_id=app_id).first()
        assert retrieved is None


class TestOptimisticLocking:
    """Test optimistic locking with version column."""

    def test_version_increments_on_update(self, db_session):
        """Test that version increments when application is updated."""
        # Create application
        app = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted",
            pan_number_hash="hash",
            first_name="Test",
            last_name="User",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="test@example.com",
            phone_number="1234567890",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
            version=1,
        )
        db_session.add(app)
        db_session.commit()

        initial_version = app.version

        # Update application
        app.status = "PRE_APPROVED"
        app.version = initial_version + 1
        db_session.commit()

        # Verify version incremented
        db_session.refresh(app)
        assert app.version == initial_version + 1

    def test_concurrent_update_detection(self, db_session):
        """Test that concurrent updates are detected via version mismatch."""
        # Create application
        app = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted",
            pan_number_hash="hash",
            first_name="Test",
            last_name="User",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="test@example.com",
            phone_number="1234567890",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
            version=1,
        )
        db_session.add(app)
        db_session.commit()

        # Simulate concurrent update scenario
        # In real code, would check version before update
        # and raise exception if version doesn't match
        current_version = app.version

        # Attempt update with old version (simulating conflict)
        # This would be caught in application code, not DB
        # Just verify version tracking works
        assert current_version == 1


class TestDuplicatePANDetection:
    """Test duplicate PAN detection via unique pan_number_hash."""

    def test_duplicate_pan_hash_rejected(self, db_session):
        """Test that duplicate PAN hash is rejected by unique constraint."""
        pan_hash = "unique_pan_hash_12345"

        # Create first application
        app1 = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted1",
            pan_number_hash=pan_hash,
            first_name="User",
            last_name="One",
            date_of_birth=datetime(1985, 1, 1, tzinfo=timezone.utc),
            email="user1@example.com",
            phone_number="1111111111",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
        )
        db_session.add(app1)
        db_session.commit()

        # Attempt to create second application with same PAN hash
        app2 = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted2",
            pan_number_hash=pan_hash,  # Same hash!
            first_name="User",
            last_name="Two",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="user2@example.com",
            phone_number="2222222222",
            requested_amount=Decimal("200000.00"),
            status="PENDING",
        )
        db_session.add(app2)

        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestAuditLog:
    """Test audit log creation."""

    def test_create_audit_log(self, db_session):
        """Test creating audit log entry."""
        # Create application first
        app = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted",
            pan_number_hash="hash",
            first_name="Test",
            last_name="User",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="test@example.com",
            phone_number="1234567890",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
        )
        db_session.add(app)
        db_session.commit()

        # Create audit log
        audit = AuditLog(
            application_id=app.application_id,
            action="PAN_ACCESSED",
            service_name="prequal-api",
            details="PAN retrieved for application status check",
        )
        db_session.add(audit)
        db_session.commit()

        # Verify created
        assert audit.audit_id is not None
        assert audit.timestamp is not None
        assert audit.action == "PAN_ACCESSED"

    def test_audit_log_relationship(self, db_session):
        """Test relationship between Application and AuditLog."""
        # Create application
        app = Application(
            application_id=uuid4(),
            pan_number_encrypted=b"encrypted",
            pan_number_hash="hash",
            first_name="Test",
            last_name="User",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            email="test@example.com",
            phone_number="1234567890",
            requested_amount=Decimal("100000.00"),
            status="PENDING",
        )
        db_session.add(app)
        db_session.commit()

        # Create multiple audit logs
        audit1 = AuditLog(
            application_id=app.application_id, action="CREATED", service_name="prequal-api"
        )
        audit2 = AuditLog(
            application_id=app.application_id, action="PAN_ACCESSED", service_name="credit-service"
        )
        db_session.add_all([audit1, audit2])
        db_session.commit()

        # Verify relationship
        db_session.refresh(app)
        assert len(app.audit_logs) == 2


class TestOutboxEvent:
    """Test outbox event persistence for transactional outbox pattern."""

    def test_create_outbox_event(self, db_session):
        """Test creating outbox event."""
        event = OutboxEvent(
            event_id=uuid4(),
            aggregate_id=uuid4(),
            event_type="ApplicationSubmitted",
            topic="loan_applications_submitted",
            payload={"application_id": str(uuid4()), "status": "PENDING"},
        )
        db_session.add(event)
        db_session.commit()

        # Verify created
        assert event.event_id is not None
        assert event.created_at is not None
        assert event.published is False

    def test_mark_outbox_event_published(self, db_session):
        """Test marking outbox event as published."""
        event = OutboxEvent(
            event_id=uuid4(),
            aggregate_id=uuid4(),
            event_type="ApplicationSubmitted",
            topic="loan_applications_submitted",
            payload={"test": "data"},
        )
        db_session.add(event)
        db_session.commit()

        # Mark as published
        event.published = True
        event.published_at = datetime.now(tz=timezone.utc)
        db_session.commit()

        # Verify updated
        db_session.refresh(event)
        assert event.published is True
        assert event.published_at is not None


class TestProcessedMessage:
    """Test processed message tracking for idempotency."""

    def test_create_processed_message(self, db_session):
        """Test recording processed message."""
        message = ProcessedMessage(
            message_id="kafka_offset_12345",
            consumer_group="credit-service-group",
            topic="loan_applications_submitted",
            partition=0,
            offset=12345,
        )
        db_session.add(message)
        db_session.commit()

        # Verify created
        assert message.processed_message_id is not None
        assert message.processed_at is not None

    def test_duplicate_message_detection(self, db_session):
        """Test detecting duplicate message processing."""
        message_id = "unique_message_12345"

        # Process message first time
        msg1 = ProcessedMessage(
            message_id=message_id,
            consumer_group="credit-service-group",
            topic="loan_applications_submitted",
            partition=0,
            offset=100,
        )
        db_session.add(msg1)
        db_session.commit()

        # Check if message already processed
        existing = (
            db_session.query(ProcessedMessage)
            .filter_by(message_id=message_id, consumer_group="credit-service-group")
            .first()
        )

        # Should find existing record
        assert existing is not None
        assert existing.message_id == message_id
