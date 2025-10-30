"""Decision engine logic for loan prequalification.

This module implements the business rules for approving or rejecting
loan applications based on CIBIL score and income-to-loan ratio.
"""
from typing import Dict, Any, Tuple
from enum import Enum


class DecisionStatus(Enum):
    """Loan application decision statuses."""
    PRE_APPROVED = "PRE_APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DecisionService:
    """Service for making loan prequalification decisions."""

    # Business rule thresholds
    MINIMUM_CIBIL_SCORE = 650
    LOAN_TERM_MONTHS = 48  # 4-year loan term for income ratio calculation

    @classmethod
    def evaluate(
        cls,
        application_data: Dict[str, Any],
        cibil_score: int
    ) -> Tuple[DecisionStatus, str]:
        """Evaluate loan application and make decision.

        Business Rules:
        1. If CIBIL score < 650 → REJECTED
        2. If CIBIL score >= 650 AND monthly_income > (loan_amount / 48) → PRE_APPROVED
        3. If CIBIL score >= 650 AND monthly_income <= (loan_amount / 48) → MANUAL_REVIEW

        Args:
            application_data: Application details containing:
                - monthly_income_inr: Monthly income
                - loan_amount_inr: Requested loan amount
            cibil_score: CIBIL credit score (300-900)

        Returns:
            Tuple of (DecisionStatus, reason: str)
        """
        monthly_income = float(application_data.get("monthly_income_inr", 0))
        loan_amount = float(application_data.get("loan_amount_inr", 0))

        # Rule 1: Check CIBIL score threshold
        if cibil_score < cls.MINIMUM_CIBIL_SCORE:
            reason = (
                f"CIBIL score {cibil_score} is below minimum threshold of "
                f"{cls.MINIMUM_CIBIL_SCORE}"
            )
            return DecisionStatus.REJECTED, reason

        # Calculate required monthly income for loan approval
        # Formula: loan_amount / 48 months (4-year term)
        required_monthly_income = loan_amount / cls.LOAN_TERM_MONTHS

        # Rule 2: Good credit score AND sufficient income → PRE_APPROVED
        if monthly_income > required_monthly_income:
            reason = (
                f"CIBIL score {cibil_score} meets threshold and "
                f"monthly income ₹{monthly_income:,.2f} exceeds required "
                f"₹{required_monthly_income:,.2f} for ₹{loan_amount:,.2f} loan"
            )
            return DecisionStatus.PRE_APPROVED, reason

        # Rule 3: Good credit score BUT insufficient income → MANUAL_REVIEW
        reason = (
            f"CIBIL score {cibil_score} meets threshold but "
            f"monthly income ₹{monthly_income:,.2f} does not exceed required "
            f"₹{required_monthly_income:,.2f} for ₹{loan_amount:,.2f} loan. "
            f"Requires manual review."
        )
        return DecisionStatus.MANUAL_REVIEW, reason

    @classmethod
    def calculate_max_approved_amount(
        cls,
        monthly_income: float,
        cibil_score: int
    ) -> float:
        """Calculate maximum loan amount that can be approved.

        Uses same formula: monthly_income * 48 months

        Args:
            monthly_income: Monthly income in INR
            cibil_score: CIBIL credit score

        Returns:
            float: Maximum approved loan amount (0 if rejected)
        """
        if cibil_score < cls.MINIMUM_CIBIL_SCORE:
            return 0.0

        # Maximum loan = monthly income * 48 months
        max_amount = monthly_income * cls.LOAN_TERM_MONTHS

        return max_amount

    @classmethod
    def make_decision(
        cls,
        application_data: Dict[str, Any],
        cibil_score: int
    ) -> Dict[str, Any]:
        """Make complete decision including status and max approved amount.

        Args:
            application_data: Application details
            cibil_score: CIBIL credit score

        Returns:
            Dict containing:
                - application_id
                - status: PRE_APPROVED, REJECTED, or MANUAL_REVIEW
                - decision_reason: Explanation of decision
                - cibil_score: Credit score used
                - max_approved_amount: Maximum loan amount (if applicable)
        """
        decision_status, decision_reason = cls.evaluate(application_data, cibil_score)

        monthly_income = float(application_data.get("monthly_income_inr", 0))
        max_approved = cls.calculate_max_approved_amount(monthly_income, cibil_score)

        return {
            "application_id": application_data.get("application_id"),
            "status": decision_status.value,
            "decision_reason": decision_reason,
            "cibil_score": cibil_score,
            "max_approved_amount": max_approved if decision_status != DecisionStatus.REJECTED else None,
        }
