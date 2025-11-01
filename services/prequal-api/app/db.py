"""Database models for loan prequalification system.

This module defines the SQLAlchemy ORM models for:
- applications: Loan applications with encrypted PAN
- audit_log: PAN access audit trail
- processed_messages: Idempotency tracking for Kafka consumers
- outbox_events: Transactional outbox for reliable message publishing
"""
from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class Application(Base):
    """Loan application with encrypted PAN data.

    Implements:
    - Optimistic locking (version column)
    - PAN encryption (pan_number_encrypted as LargeBinary)
    - Duplicate detection (pan_number_hash with unique index)
    - Status tracking with timestamps
    """

    __tablename__ = "applications"

    # Primary key
    application_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Encrypted PAN (binary data: nonce + ciphertext)
    pan_number_encrypted = Column(LargeBinary, nullable=False)
    pan_number_hash = Column(String(64), nullable=False)  # SHA-256 hex digest

    # Personal information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(TIMESTAMP, nullable=False)
    email = Column(String(255), nullable=False)
    phone_number = Column(String(15), nullable=False)

    # Loan details
    requested_amount = Column(Numeric(10, 2), nullable=False)

    # Status tracking
    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        comment="PENDING | PRE_APPROVED | REJECTED | MANUAL_REVIEW",
    )

    # Credit information (populated by credit-service)
    credit_score = Column(Integer, nullable=True)
    annual_income = Column(Numeric(12, 2), nullable=True)
    existing_loans_count = Column(Integer, nullable=True)

    # Decision metadata (populated by decision-service)
    decision_reason = Column(Text, nullable=True)
    max_approved_amount = Column(Numeric(10, 2), nullable=True)

    # Optimistic locking
    version = Column(Integer, nullable=False, default=1)

    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    audit_logs = relationship(
        "AuditLog", back_populates="application", cascade="all, delete-orphan"
    )

    # Indexes defined at class level
    __table_args__ = (
        Index("idx_applications_pan_hash", "pan_number_hash", unique=True),
        Index("idx_applications_status", "status"),
        Index("idx_applications_email", "email"),
        Index("idx_applications_created_at", "created_at"),
    )


class AuditLog(Base):
    """Audit trail for PAN access.

    Tracks every access to decrypted PAN data for compliance.
    """

    __tablename__ = "audit_log"

    # Primary key
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Foreign key to application
    application_id = Column(
        UUID(as_uuid=True), ForeignKey("applications.application_id"), nullable=False
    )

    # Audit metadata
    service_name = Column(
        String(50), nullable=False, comment="prequal-api | credit-service | decision-service"
    )
    operation = Column(String(50), nullable=False, comment="ENCRYPT | DECRYPT | MASK")
    user_id = Column(String(100), nullable=True, comment="For future user authentication")

    # Timestamp
    accessed_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Relationships
    application = relationship("Application", back_populates="audit_logs")

    # Indexes
    __table_args__ = (
        Index("idx_audit_log_application_id", "application_id"),
        Index("idx_audit_log_accessed_at", "accessed_at"),
        Index("idx_audit_log_service_name", "service_name"),
    )


class ProcessedMessage(Base):
    """Idempotency tracking for Kafka consumers.

    Prevents duplicate processing by storing message_id from Kafka headers.
    """

    __tablename__ = "processed_messages"

    # Primary key
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Idempotency key
    message_id = Column(String(255), nullable=False, unique=True)

    # Kafka metadata
    topic_name = Column(String(100), nullable=False)
    partition_num = Column(Integer, nullable=True)
    offset_num = Column(BigInteger, nullable=True)

    # Processing metadata
    consumer_group = Column(String(100), nullable=False)
    processed_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_processed_messages_message_id", "message_id", unique=True),
        Index("idx_processed_messages_topic", "topic_name"),
        Index("idx_processed_messages_processed_at", "processed_at"),
    )


class OutboxEvent(Base):
    """Transactional outbox for reliable Kafka message publishing.

    Ensures message publishing is part of the same database transaction
    as the business logic, preventing message loss.
    """

    __tablename__ = "outbox_events"

    # Primary key
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Event identification
    aggregate_id = Column(UUID(as_uuid=True), nullable=False, comment="application_id")
    event_type = Column(
        String(100),
        nullable=False,
        comment="APPLICATION_SUBMITTED | CREDIT_REPORT_GENERATED",
    )

    # Event payload (JSON)
    payload = Column(JSONB, nullable=False, comment="Full Kafka message payload")

    # Kafka routing
    topic_name = Column(String(100), nullable=False)
    partition_key = Column(String(255), nullable=True, comment="For consistent partitioning")

    # Publishing status
    published = Column(Boolean, nullable=False, default=False)
    published_at = Column(TIMESTAMP, nullable=True)
    error_message = Column(Text, nullable=True, comment="Last error if publishing failed")
    retry_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_outbox_events_published", "published", "created_at"),
        Index("idx_outbox_events_aggregate_id", "aggregate_id"),
        Index("idx_outbox_events_event_type", "event_type"),
    )
