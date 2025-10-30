"""CIBIL score calculation logic for credit service.

This module implements deterministic CIBIL score simulation based on:
- Test PAN mappings for predictable testing
- Income-based adjustments
- Loan type considerations
- Seeded random variation for determinism
"""
import hashlib
import random
from typing import Dict, Any
from uuid import UUID


class CibilService:
    """Service for calculating CIBIL credit scores."""

    # Test PAN mappings for predictable testing
    TEST_PAN_SCORES = {
        "ABCDE1234F": 790,  # Good credit score
        "FGHIJ5678K": 610,  # Below threshold score
    }

    @classmethod
    def calculate_score(cls, application_data: Dict[str, Any]) -> int:
        """Calculate CIBIL score for a loan application.

        Uses deterministic seeded random to ensure reprocessing the same
        application produces the same score (critical for idempotency).

        Args:
            application_data: Dict containing:
                - application_id (str/UUID): For seeding random
                - pan_number (str): PAN card number (decrypted)
                - monthly_income_inr (float): Monthly income
                - loan_amount_inr (float): Requested loan amount
                - loan_type (str): PERSONAL, HOME, or AUTO

        Returns:
            int: CIBIL score between 300-900

        Business Rules:
            1. Check test PAN mappings first
            2. Base score: 650
            3. Income adjustments:
               - High income (>75000): +40
               - Low income (<30000): -20
            4. Loan type adjustments:
               - PERSONAL: -10 (higher risk)
               - HOME: +10 (lower risk)
               - AUTO: 0 (neutral)
            5. Add random variation (-5 to +5) using seeded random
            6. Cap between 300-900
        """
        pan_number = application_data.get("pan_number", "")

        # Check test PAN mappings first
        if pan_number in cls.TEST_PAN_SCORES:
            return cls.TEST_PAN_SCORES[pan_number]

        # Start with base score
        score = 650

        # Income-based adjustments
        monthly_income = float(application_data.get("monthly_income_inr", 0))
        if monthly_income > 75000:
            score += 40
        elif monthly_income < 30000:
            score -= 20

        # Loan type adjustments
        loan_type = application_data.get("loan_type", "").upper()
        if loan_type == "PERSONAL":
            score -= 10
        elif loan_type == "HOME":
            score += 10
        # AUTO is neutral (no adjustment)

        # Add deterministic random variation using application_id as seed
        # This ensures the same application_id always produces the same score
        application_id = str(application_data.get("application_id", ""))
        seed = cls._generate_seed(application_id)
        random.seed(seed)
        variation = random.randint(-5, 5)
        score += variation

        # Cap between 300-900 (CIBIL score range)
        score = max(300, min(900, score))

        return score

    @staticmethod
    def _generate_seed(application_id: str) -> int:
        """Generate a deterministic seed from application_id.

        Uses SHA-256 hash to convert UUID to integer seed for random.

        Args:
            application_id: Application UUID as string

        Returns:
            int: Deterministic seed value
        """
        # Hash the application_id and take first 8 bytes as integer
        hash_bytes = hashlib.sha256(application_id.encode()).digest()[:8]
        seed = int.from_bytes(hash_bytes, byteorder="big")
        return seed

    @classmethod
    def get_credit_report(cls, application_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate complete credit report for an application.

        Args:
            application_data: Application details

        Returns:
            Dict containing:
                - application_id
                - pan_number (encrypted for Kafka)
                - cibil_score
                - credit_report_generated_at (timestamp)
        """
        from datetime import datetime

        cibil_score = cls.calculate_score(application_data)

        return {
            "application_id": str(application_data.get("application_id")),
            "pan_number": application_data.get("pan_number"),  # Will be re-encrypted for Kafka
            "applicant_name": application_data.get("applicant_name"),
            "cibil_score": cibil_score,
            "credit_report_generated_at": datetime.utcnow().isoformat(),
        }
