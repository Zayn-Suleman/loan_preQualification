"""Unit tests for CIBIL score calculation logic.

Tests the CibilService class to ensure:
- Test PAN mappings work correctly
- Income-based adjustments are applied
- Loan type adjustments are correct
- Deterministic random seeding produces consistent results
- Score capping works (300-900 range)
"""
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directories to path
service_root = Path(__file__).parent.parent
sys.path.insert(0, str(service_root))

from app.logic import CibilService

# Test constants
EXPECTED_GOOD_SCORE = 790
EXPECTED_BAD_SCORE = 610
BASE_SCORE_LOWER = 645
BASE_SCORE_UPPER = 655
HIGH_INCOME_LOWER = 685
HIGH_INCOME_UPPER = 695
LOW_INCOME_LOWER = 625
LOW_INCOME_UPPER = 635
PERSONAL_LOAN_LOWER = 635
PERSONAL_LOAN_UPPER = 645
HOME_LOAN_LOWER = 655
HOME_LOAN_UPPER = 665
AUTO_LOAN_LOWER = 645
AUTO_LOAN_UPPER = 655
MIN_CIBIL = 300
MAX_CIBIL = 900


class TestCibilService:
    """Test suite for CibilService."""

    def test_test_pan_mapping_good_credit(self):
        """Test that test PAN ABCDE1234F returns 790."""
        application_data = {
            "application_id": str(uuid4()),
            "pan_number": "ABCDE1234F",
            "monthly_income_inr": 50000,
            "loan_amount_inr": 500000,
            "loan_type": "PERSONAL",
        }

        score = CibilService.calculate_score(application_data)
        assert score == EXPECTED_GOOD_SCORE, f"Expected 790 for test PAN ABCDE1234F, got {score}"

    def test_test_pan_mapping_below_threshold(self):
        """Test that test PAN FGHIJ5678K returns 610."""
        application_data = {
            "application_id": str(uuid4()),
            "pan_number": "FGHIJ5678K",
            "monthly_income_inr": 50000,
            "loan_amount_inr": 500000,
            "loan_type": "PERSONAL",
        }

        score = CibilService.calculate_score(application_data)
        assert score == EXPECTED_BAD_SCORE, f"Expected 610 for test PAN FGHIJ5678K, got {score}"

    def test_base_score_calculation(self):
        """Test base score calculation without adjustments."""
        # Use a fixed application_id to make random variation predictable
        application_id = "00000000-0000-0000-0000-000000000001"

        application_data = {
            "application_id": application_id,
            "pan_number": "ZZZZZ9999Z",  # Not a test PAN
            "monthly_income_inr": 50000,  # Between 30k-75k (no adjustment)
            "loan_amount_inr": 500000,
            "loan_type": "AUTO",  # Neutral adjustment
        }

        score = CibilService.calculate_score(application_data)

        # Base 650 + 0 (income) + 0 (loan type) + random(-5 to +5)
        assert 645 <= score <= BASE_SCORE_UPPER, f"Expected score between 645-655, got {score}"

    def test_high_income_adjustment(self):
        """Test that high income (>75000) adds +40 to score."""
        application_id = "00000000-0000-0000-0000-000000000002"

        application_data = {
            "application_id": application_id,
            "pan_number": "BBBBB8888B",
            "monthly_income_inr": 100000,  # High income
            "loan_amount_inr": 500000,
            "loan_type": "AUTO",
        }

        score = CibilService.calculate_score(application_data)

        # Base 650 + 40 (high income) + 0 (auto) + random(-5 to +5) = 685-695
        assert 685 <= score <= HIGH_INCOME_UPPER, f"Expected score between 685-695, got {score}"

    def test_low_income_adjustment(self):
        """Test that low income (<30000) subtracts -20 from score."""
        application_id = "00000000-0000-0000-0000-000000000003"

        application_data = {
            "application_id": application_id,
            "pan_number": "CCCCC7777C",
            "monthly_income_inr": 25000,  # Low income
            "loan_amount_inr": 200000,
            "loan_type": "AUTO",
        }

        score = CibilService.calculate_score(application_data)

        # Base 650 - 20 (low income) + 0 (auto) + random(-5 to +5) = 625-635
        assert 625 <= score <= LOW_INCOME_UPPER, f"Expected score between 625-635, got {score}"

    def test_personal_loan_adjustment(self):
        """Test that PERSONAL loan subtracts -10 from score."""
        application_id = "00000000-0000-0000-0000-000000000004"

        application_data = {
            "application_id": application_id,
            "pan_number": "DDDDD6666D",
            "monthly_income_inr": 50000,
            "loan_amount_inr": 300000,
            "loan_type": "PERSONAL",
        }

        score = CibilService.calculate_score(application_data)

        # Base 650 + 0 (income) - 10 (personal) + random(-5 to +5) = 635-645
        assert 635 <= score <= 645, f"Expected score between 635-645, got {score}"

    def test_home_loan_adjustment(self):
        """Test that HOME loan adds +10 to score."""
        application_id = "00000000-0000-0000-0000-000000000005"

        application_data = {
            "application_id": application_id,
            "pan_number": "EEEEE5555E",
            "monthly_income_inr": 50000,
            "loan_amount_inr": 5000000,
            "loan_type": "HOME",
        }

        score = CibilService.calculate_score(application_data)

        # Base 650 + 0 (income) + 10 (home) + random(-5 to +5) = 655-665
        assert 655 <= score <= 665, f"Expected score between 655-665, got {score}"

    def test_combined_high_income_personal_loan(self):
        """Test combined adjustments: high income + personal loan."""
        application_id = "00000000-0000-0000-0000-000000000006"

        application_data = {
            "application_id": application_id,
            "pan_number": "FFFFF4444F",
            "monthly_income_inr": 80000,  # High income (+40)
            "loan_amount_inr": 600000,
            "loan_type": "PERSONAL",  # Personal loan (-10)
        }

        score = CibilService.calculate_score(application_data)

        # Base 650 + 40 - 10 + random(-5 to +5) = 675-685
        assert 675 <= score <= 685, f"Expected score between 675-685, got {score}"

    def test_combined_low_income_home_loan(self):
        """Test combined adjustments: low income + home loan."""
        application_id = "00000000-0000-0000-0000-000000000007"

        application_data = {
            "application_id": application_id,
            "pan_number": "GGGGG3333G",
            "monthly_income_inr": 28000,  # Low income (-20)
            "loan_amount_inr": 3000000,
            "loan_type": "HOME",  # Home loan (+10)
        }

        score = CibilService.calculate_score(application_data)

        # Base 650 - 20 + 10 + random(-5 to +5) = 635-645
        assert 635 <= score <= 645, f"Expected score between 635-645, got {score}"

    def test_score_capping_lower_bound(self):
        """Test that score is capped at minimum 300."""
        application_id = "00000000-0000-0000-0000-000000000008"

        application_data = {
            "application_id": application_id,
            "pan_number": "HHHHH2222H",
            "monthly_income_inr": 15000,  # Very low income
            "loan_amount_inr": 100000,
            "loan_type": "PERSONAL",
        }

        score = CibilService.calculate_score(application_data)

        # Should never go below 300
        assert score >= MIN_CIBIL, f"Score {score} is below minimum 300"

    def test_score_capping_upper_bound(self):
        """Test that score is capped at maximum 900."""
        application_id = "00000000-0000-0000-0000-000000000009"

        application_data = {
            "application_id": application_id,
            "pan_number": "IIIII1111I",
            "monthly_income_inr": 500000,  # Very high income
            "loan_amount_inr": 10000000,
            "loan_type": "HOME",
        }

        score = CibilService.calculate_score(application_data)

        # Should never exceed 900
        assert score <= MAX_CIBIL, f"Score {score} exceeds maximum 900"

    def test_deterministic_seeding_same_application(self):
        """Test that same application_id always produces same score."""
        application_id = "12345678-1234-1234-1234-123456789abc"

        application_data = {
            "application_id": application_id,
            "pan_number": "JJJJJ0000J",
            "monthly_income_inr": 60000,
            "loan_amount_inr": 800000,
            "loan_type": "AUTO",
        }

        # Calculate score multiple times
        score1 = CibilService.calculate_score(application_data)
        score2 = CibilService.calculate_score(application_data)
        score3 = CibilService.calculate_score(application_data)

        # All should be identical (deterministic)
        assert score1 == score2 == score3, f"Scores not deterministic: {score1}, {score2}, {score3}"

    def test_different_applications_different_scores(self):
        """Test that different application_ids can produce different scores."""
        base_data = {
            "pan_number": "KKKKK9999K",
            "monthly_income_inr": 55000,
            "loan_amount_inr": 500000,
            "loan_type": "AUTO",
        }

        # Create 10 applications with different IDs
        scores = []
        for i in range(10):
            data = {**base_data, "application_id": f"00000000-0000-0000-0000-00000000000{i}"}
            scores.append(CibilService.calculate_score(data))

        # Should have some variation due to random seed
        unique_scores = set(scores)
        assert len(unique_scores) > 1, "All scores identical, random variation not working"

    def test_get_credit_report_structure(self):
        """Test that get_credit_report returns correct structure."""
        application_data = {
            "application_id": str(uuid4()),
            "pan_number": "ABCDE1234F",
            "applicant_name": "Test User",
            "monthly_income_inr": 50000,
            "loan_amount_inr": 500000,
            "loan_type": "PERSONAL",
        }

        credit_report = CibilService.get_credit_report(application_data)

        # Verify structure
        assert "application_id" in credit_report
        assert "pan_number" in credit_report
        assert "applicant_name" in credit_report
        assert "cibil_score" in credit_report
        assert "credit_report_generated_at" in credit_report

        # Verify types
        assert isinstance(credit_report["cibil_score"], int)
        assert 300 <= credit_report["cibil_score"] <= 900

    def test_missing_fields_handling(self):
        """Test that missing fields are handled gracefully."""
        application_data = {
            "application_id": str(uuid4()),
            # Missing: pan_number, monthly_income_inr, loan_type
        }

        # Should not raise exception
        score = CibilService.calculate_score(application_data)

        # Should return valid score
        assert 300 <= score <= 900

    def test_seed_generation_consistency(self):
        """Test that seed generation is consistent for same application_id."""
        application_id = "test-app-id-123"

        seed1 = CibilService._generate_seed(application_id)
        seed2 = CibilService._generate_seed(application_id)

        assert seed1 == seed2, "Seed generation is not deterministic"

    def test_seed_generation_uniqueness(self):
        """Test that different application_ids produce different seeds."""
        seed1 = CibilService._generate_seed("app-id-1")
        seed2 = CibilService._generate_seed("app-id-2")

        assert seed1 != seed2, "Different application_ids produced same seed"
