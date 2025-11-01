"""Business logic services for loan prequalification.

This module implements the ApplicationService with:
- Transactional outbox pattern for reliable message publishing
- PAN encryption before database storage
- Duplicate detection via PAN hash
- Audit logging for PAN access
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from services.shared.encryption import EncryptionService

from .db import Application, AuditLog, OutboxEvent
from .models import (
    ApplicationCreateRequest,
    ApplicationCreateResponse,
    ApplicationStatus,
    ApplicationStatusResponse,
)

# Constants
PAN_LENGTH = 10


class ApplicationService:
    """Service layer for loan application business logic.

    Implements:
    - Transactional outbox pattern (DB write + outbox event in same transaction)
    - PAN encryption with AES-256-GCM
    - PAN masking for API responses
    - Audit logging for compliance
    """

    def __init__(self, db_session: Session, encryption_service: EncryptionService):
        """Initialize ApplicationService.

        Args:
            db_session: SQLAlchemy database session
            encryption_service: Service for PAN encryption/decryption
        """
        self.db = db_session
        self.encryption = encryption_service

    def create_application(self, request: ApplicationCreateRequest) -> ApplicationCreateResponse:
        """Create a new loan application with transactional outbox.

        Flow:
        1. Encrypt PAN and compute hash
        2. Check for duplicate PAN (via hash)
        3. Create Application record
        4. Create AuditLog record
        5. Create OutboxEvent record
        6. Commit transaction (all or nothing)

        Args:
            request: Validated application request

        Returns:
            ApplicationCreateResponse with application_id and status

        Raises:
            ValueError: If duplicate PAN detected
            Exception: On database or encryption errors
        """
        # Step 1: Encrypt PAN and compute hash
        pan_encrypted = self.encryption.encrypt_pan(request.pan_number)
        pan_hash = self.encryption.hash_pan(request.pan_number)

        # Step 2: Check for duplicate PAN
        existing_app = self.db.execute(
            select(Application).where(Application.pan_number_hash == pan_hash)
        ).scalar_one_or_none()

        if existing_app:
            raise ValueError(
                f"Duplicate PAN detected. Existing application: {existing_app.application_id}"
            )

        # Step 3: Create Application record
        application = Application(
            application_id=uuid4(),
            pan_number_encrypted=pan_encrypted,
            pan_number_hash=pan_hash,
            first_name=request.first_name,
            last_name=request.last_name,
            date_of_birth=datetime.combine(request.date_of_birth, datetime.min.time()),
            email=request.email,
            phone_number=request.phone_number,
            requested_amount=request.requested_amount,
            status=ApplicationStatus.PENDING.value,
            version=1,
        )
        self.db.add(application)

        # Step 4: Create AuditLog record
        audit_log = AuditLog(
            application_id=application.application_id,
            service_name="prequal-api",
            operation="ENCRYPT",
            user_id=None,  # For future authentication
        )
        self.db.add(audit_log)

        # Step 5: Create OutboxEvent for Kafka publishing
        # Encrypt PAN for Kafka (base64 encoded)
        pan_encrypted_b64 = self.encryption.encrypt_pan_for_kafka(request.pan_number)

        event_payload = {
            "application_id": str(application.application_id),
            "pan_number_encrypted": pan_encrypted_b64,
            "pan_number_hash": pan_hash,
            "first_name": request.first_name,
            "last_name": request.last_name,
            "date_of_birth": request.date_of_birth.isoformat(),
            "email": request.email,
            "phone_number": request.phone_number,
            "requested_amount": float(request.requested_amount),
            "status": ApplicationStatus.PENDING.value,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        outbox_event = OutboxEvent(
            aggregate_id=application.application_id,
            event_type="APPLICATION_SUBMITTED",
            payload=event_payload,
            topic_name="loan_applications_submitted",
            partition_key=str(application.application_id),
            published=False,
        )
        self.db.add(outbox_event)

        # Step 6: Commit transaction (all-or-nothing)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"Database integrity error: {str(e)}") from e
        except Exception as e:
            self.db.rollback()
            raise Exception(f"Failed to create application: {str(e)}") from e

        # Return response
        return ApplicationCreateResponse(
            application_id=application.application_id,
            status=ApplicationStatus.PENDING,
            message="Application submitted successfully and is being processed",
            created_at=application.created_at,
        )

    def get_application_status(self, application_id: UUID) -> ApplicationStatusResponse:
        """Get application status with masked PAN.

        Args:
            application_id: UUID of the application

        Returns:
            ApplicationStatusResponse with all application details

        Raises:
            ValueError: If application not found
        """
        # Query application
        application = self.db.execute(
            select(Application).where(Application.application_id == application_id)
        ).scalar_one_or_none()

        if not application:
            raise ValueError(f"Application not found: {application_id}")

        # Decrypt PAN and mask it
        pan_decrypted = self.encryption.decrypt_pan(application.pan_number_encrypted)
        pan_masked = self._mask_pan(pan_decrypted)

        # Create audit log for PAN access
        audit_log = AuditLog(
            application_id=application.application_id,
            service_name="prequal-api",
            operation="MASK",
            user_id=None,
        )
        self.db.add(audit_log)
        self.db.commit()

        # Build response
        return ApplicationStatusResponse(
            application_id=application.application_id,
            status=ApplicationStatus(application.status),
            pan_number_masked=pan_masked,
            first_name=application.first_name,
            last_name=application.last_name,
            requested_amount=application.requested_amount,
            credit_score=application.credit_score,
            annual_income=application.annual_income,
            existing_loans_count=application.existing_loans_count,
            decision_reason=application.decision_reason,
            max_approved_amount=application.max_approved_amount,
            created_at=application.created_at,
            updated_at=application.updated_at,
        )

    def _mask_pan(self, pan_plaintext: str) -> str:
        """Mask PAN showing only last 4 characters.

        Args:
            pan_plaintext: Decrypted PAN (e.g., "ABCDE1234F")

        Returns:
            Masked PAN (e.g., "XXXXX1234F")
        """
        if len(pan_plaintext) != PAN_LENGTH:
            raise ValueError("Invalid PAN length")
        return "XXXXX" + pan_plaintext[-5:]
