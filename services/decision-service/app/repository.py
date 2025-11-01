"""Repository for updating application status with optimistic locking.

This module implements the data access layer with support for:
- Optimistic locking using version column
- Retry logic for concurrent update conflicts
- Transactional updates
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class OptimisticLockError(Exception):
    """Exception raised when optimistic lock fails (version mismatch)."""


class ApplicationRepository:
    """Repository for application data access with optimistic locking."""

    def __init__(self, db: Session):
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_application_by_id(self, application_id: str) -> Optional[Dict[str, Any]]:
        """Fetch application by ID.

        Args:
            application_id: Application UUID

        Returns:
            Dict with application data or None if not found
        """
        result = self.db.execute(
            text(
                """
                SELECT
                    application_id,
                    first_name,
                    last_name,
                    requested_amount,
                    annual_income,
                    status,
                    credit_score,
                    version,
                    created_at,
                    updated_at
                FROM applications
                WHERE application_id = :app_id
            """
            ),
            {"app_id": application_id},
        )

        row = result.fetchone()
        if not row:
            return None

        return {
            "application_id": str(row[0]),
            "first_name": row[1],
            "last_name": row[2],
            "requested_amount": float(row[3]) if row[3] else 0,
            "annual_income": float(row[4]) if row[4] else 0,
            "status": row[5],
            "credit_score": row[6],
            "version": row[7],
            "created_at": row[8],
            "updated_at": row[9],
        }

    def update_status_with_version(
        self,
        application_id: str,
        status: str,
        cibil_score: int,
        decision_reason: str,
        max_approved_amount: Optional[float],
        expected_version: int,
    ) -> bool:
        """Update application status with optimistic locking.

        Uses the version column to ensure no concurrent updates occurred.
        If version mismatch, returns False indicating conflict.

        Args:
            application_id: Application UUID
            status: New status (PRE_APPROVED, REJECTED, MANUAL_REVIEW)
            cibil_score: CIBIL credit score
            decision_reason: Explanation of decision
            max_approved_amount: Maximum approved loan amount
            expected_version: Expected current version (for optimistic lock)

        Returns:
            bool: True if update successful, False if version conflict

        Raises:
            OptimisticLockError: If version conflict detected
        """
        try:
            result = self.db.execute(
                text(
                    """
                    UPDATE applications
                    SET
                        status = :status,
                        credit_score = :cibil_score,
                        decision_reason = :decision_reason,
                        max_approved_amount = :max_approved_amount,
                        version = version + 1,
                        updated_at = :updated_at
                    WHERE
                        application_id = :app_id
                        AND version = :expected_version
                """
                ),
                {
                    "app_id": application_id,
                    "status": status,
                    "cibil_score": cibil_score,
                    "decision_reason": decision_reason,
                    "max_approved_amount": max_approved_amount,
                    "expected_version": expected_version,
                    "updated_at": datetime.now(tz=timezone.utc),
                },
            )

            rows_affected = result.rowcount

            if rows_affected == 0:
                # No rows updated - version conflict
                logger.warning(
                    f"Optimistic lock conflict for application {application_id}. "
                    f"Expected version: {expected_version}"
                )
                raise OptimisticLockError(f"Version conflict for application {application_id}")

            logger.info(
                f"Updated application {application_id} to status {status} "
                f"(version {expected_version} -> {expected_version + 1})"
            )
            return True

        except OptimisticLockError:
            raise
        except Exception as e:
            logger.error(f"Error updating application status: {e}", exc_info=True)
            raise

    def update_with_retry(
        self,
        application_id: str,
        status: str,
        cibil_score: int,
        decision_reason: str,
        max_approved_amount: Optional[float],
        max_retries: int = 3,
    ) -> bool:
        """Update application with automatic retry on version conflicts.

        Implements optimistic locking with retry logic:
        1. Read current application and version
        2. Attempt update with expected version
        3. If conflict, re-read and retry (up to max_retries)

        Args:
            application_id: Application UUID
            status: New status
            cibil_score: CIBIL credit score
            decision_reason: Decision explanation
            max_approved_amount: Maximum approved amount
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            bool: True if update successful

        Raises:
            OptimisticLockError: If max retries exceeded
            ValueError: If application not found
        """
        for attempt in range(max_retries):
            try:
                # Read current application and version
                application = self.get_application_by_id(application_id)

                if not application:
                    raise ValueError(f"Application {application_id} not found")

                current_version = application["version"]

                logger.debug(
                    f"Update attempt {attempt + 1}/{max_retries} for application "
                    f"{application_id}, version {current_version}"
                )

                # Attempt update with current version
                self.update_status_with_version(
                    application_id=application_id,
                    status=status,
                    cibil_score=cibil_score,
                    decision_reason=decision_reason,
                    max_approved_amount=max_approved_amount,
                    expected_version=current_version,
                )

                # Success!
                logger.info(
                    f"Successfully updated application {application_id} "
                    f"on attempt {attempt + 1}"
                )
                return True

            except OptimisticLockError:
                if attempt < max_retries - 1:
                    logger.info(f"Optimistic lock conflict on attempt {attempt + 1}, retrying...")
                    continue
                logger.error(
                    f"Max retries ({max_retries}) exceeded for application " f"{application_id}"
                )
                raise

        return False
