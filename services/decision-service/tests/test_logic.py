"""Unit tests for decision engine logic.

Tests the DecisionService class to ensure:
- Business rules are applied correctly
- CIBIL score thresholds work
- Income ratio calculations are accurate
- All three decision outcomes work (PRE_APPROVED, REJECTED, MANUAL_REVIEW)
- Edge cases are handled
"""
import pytest
from uuid import uuid4

import sys
from pathlib import Path

# Add parent directories to path
service_root = Path(__file__).parent.parent
sys.path.insert(0, str(service_root))

from app.logic import DecisionService, DecisionStatus


class TestDecisionService:
    """Test suite for DecisionService."""

    def test_rejected_low_cibil_score(self):
        """Test that CIBIL score < 650 results in REJECTED."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 100000,  # High income doesn't matter
            "loan_amount_inr": 500000,
        }
        cibil_score = 600  # Below threshold

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        assert status == DecisionStatus.REJECTED
        assert "below minimum threshold" in reason.lower()
        assert "600" in reason
        assert "650" in reason

    def test_rejected_exactly_649_cibil(self):
        """Test that CIBIL score of exactly 649 is rejected."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 50000,
            "loan_amount_inr": 500000,
        }
        cibil_score = 649

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        assert status == DecisionStatus.REJECTED

    def test_pre_approved_good_cibil_sufficient_income(self):
        """Test PRE_APPROVED: CIBIL >= 650 AND income > (loan / 48)."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 50000,  # 50k per month
            "loan_amount_inr": 2000000,    # 20 lakh loan
        }
        # Required monthly income = 2000000 / 48 = 41,666.67
        # 50,000 > 41,666.67 → PRE_APPROVED
        cibil_score = 750

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        assert status == DecisionStatus.PRE_APPROVED
        assert "pre_approved" in status.value.lower()
        assert "750" in reason

    def test_pre_approved_exactly_650_cibil(self):
        """Test that CIBIL score of exactly 650 can be pre-approved."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 30000,
            "loan_amount_inr": 1000000,  # Required: 1000000/48 = 20,833.33
        }
        cibil_score = 650  # Exactly at threshold

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        assert status == DecisionStatus.PRE_APPROVED

    def test_manual_review_good_cibil_insufficient_income(self):
        """Test MANUAL_REVIEW: CIBIL >= 650 BUT income <= (loan / 48)."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 40000,  # 40k per month
            "loan_amount_inr": 2000000,   # 20 lakh loan
        }
        # Required monthly income = 2000000 / 48 = 41,666.67
        # 40,000 < 41,666.67 → MANUAL_REVIEW
        cibil_score = 700

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        assert status == DecisionStatus.MANUAL_REVIEW
        assert "manual review" in reason.lower()
        assert "700" in reason

    def test_manual_review_exactly_equal_income(self):
        """Test MANUAL_REVIEW when income exactly equals required amount."""
        # Edge case: income == loan/48 (not greater than)
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 20833.00,
            "loan_amount_inr": 1000000.00,  # 1000000 / 48 = 20833.33...
        }
        cibil_score = 680

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        # Should be MANUAL_REVIEW (income 20833 < required 20833.33)
        assert status == DecisionStatus.MANUAL_REVIEW

    def test_income_ratio_calculation(self):
        """Test that income ratio is calculated correctly (loan / 48)."""
        # 48-month loan term
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 25000,
            "loan_amount_inr": 1200000,  # 12 lakh
        }
        # Required income = 1200000 / 48 = 25,000 exactly
        cibil_score = 700

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        # 25000 is NOT > 25000, so MANUAL_REVIEW
        assert status == DecisionStatus.MANUAL_REVIEW

    def test_calculate_max_approved_amount_approved(self):
        """Test max approved amount for good credit."""
        monthly_income = 50000
        cibil_score = 750

        max_amount = DecisionService.calculate_max_approved_amount(
            monthly_income, cibil_score
        )

        # Max = 50000 * 48 = 2,400,000
        assert max_amount == 2400000.0

    def test_calculate_max_approved_amount_rejected(self):
        """Test max approved amount for rejected (below threshold)."""
        monthly_income = 50000
        cibil_score = 600  # Below 650

        max_amount = DecisionService.calculate_max_approved_amount(
            monthly_income, cibil_score
        )

        # Should return 0 for rejected
        assert max_amount == 0.0

    def test_make_decision_pre_approved(self):
        """Test complete decision for PRE_APPROVED case."""
        application_data = {
            "application_id": "test-app-123",
            "monthly_income_inr": 80000,
            "loan_amount_inr": 3000000,  # Required: 3000000/48 = 62,500
        }
        cibil_score = 780

        decision = DecisionService.make_decision(application_data, cibil_score)

        assert decision["application_id"] == "test-app-123"
        assert decision["status"] == "PRE_APPROVED"
        assert decision["cibil_score"] == 780
        assert decision["decision_reason"] is not None
        assert decision["max_approved_amount"] == 80000 * 48

    def test_make_decision_rejected(self):
        """Test complete decision for REJECTED case."""
        application_data = {
            "application_id": "test-app-456",
            "monthly_income_inr": 30000,
            "loan_amount_inr": 500000,
        }
        cibil_score = 620  # Below 650

        decision = DecisionService.make_decision(application_data, cibil_score)

        assert decision["application_id"] == "test-app-456"
        assert decision["status"] == "REJECTED"
        assert decision["cibil_score"] == 620
        assert decision["max_approved_amount"] is None  # None for rejected

    def test_make_decision_manual_review(self):
        """Test complete decision for MANUAL_REVIEW case."""
        application_data = {
            "application_id": "test-app-789",
            "monthly_income_inr": 35000,
            "loan_amount_inr": 2000000,  # Required: 2000000/48 = 41,666.67
        }
        cibil_score = 710

        decision = DecisionService.make_decision(application_data, cibil_score)

        assert decision["application_id"] == "test-app-789"
        assert decision["status"] == "MANUAL_REVIEW"
        assert decision["cibil_score"] == 710
        assert decision["max_approved_amount"] == 35000 * 48

    def test_high_income_high_loan_pre_approved(self):
        """Test high-value loan with sufficient income."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 200000,  # 2 lakh per month
            "loan_amount_inr": 8000000,    # 80 lakh loan
        }
        # Required: 8000000 / 48 = 166,666.67
        # 200,000 > 166,666.67 → PRE_APPROVED
        cibil_score = 850

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        assert status == DecisionStatus.PRE_APPROVED

    def test_low_income_small_loan_pre_approved(self):
        """Test small loan with low income can still be approved."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 25000,
            "loan_amount_inr": 500000,  # Required: 500000/48 = 10,416.67
        }
        cibil_score = 680

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        assert status == DecisionStatus.PRE_APPROVED

    def test_missing_income_defaults_to_zero(self):
        """Test handling of missing income (edge case)."""
        application_data = {
            "application_id": str(uuid4()),
            # Missing monthly_income_inr
            "loan_amount_inr": 1000000,
        }
        cibil_score = 750

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        # With 0 income, should be MANUAL_REVIEW (0 < required income)
        assert status == DecisionStatus.MANUAL_REVIEW

    def test_missing_loan_amount_defaults_to_zero(self):
        """Test handling of missing loan amount (edge case)."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 50000,
            # Missing loan_amount_inr
        }
        cibil_score = 750

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        # With 0 loan amount, required income = 0
        # 50000 > 0 → PRE_APPROVED
        assert status == DecisionStatus.PRE_APPROVED

    def test_decision_status_enum_values(self):
        """Test that enum values are correct."""
        assert DecisionStatus.PRE_APPROVED.value == "PRE_APPROVED"
        assert DecisionStatus.REJECTED.value == "REJECTED"
        assert DecisionStatus.MANUAL_REVIEW.value == "MANUAL_REVIEW"

    def test_decision_reason_contains_key_info(self):
        """Test that decision reasons contain important information."""
        application_data = {
            "application_id": str(uuid4()),
            "monthly_income_inr": 45000,
            "loan_amount_inr": 1800000,
        }
        cibil_score = 720

        status, reason = DecisionService.evaluate(application_data, cibil_score)

        # Reason should contain CIBIL score
        assert "720" in reason
        # Reason should mention income amounts
        assert "45" in reason or "45000" in reason
        # Reason should be descriptive
        assert len(reason) > 50  # Reasonably detailed explanation
