"""Pydantic models for API request/response validation.

This module defines the data models for:
- Application creation request
- Application creation response
- Application status response
- Error responses
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

# Constants
MIN_AGE = 18
MAX_AGE = 100


class ApplicationStatus(str, Enum):
    """Application status enum."""

    PENDING = "PENDING"
    PRE_APPROVED = "PRE_APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ErrorCode(str, Enum):
    """Error code enum for standardized error responses."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE_PAN = "DUPLICATE_PAN"
    DATABASE_ERROR = "DATABASE_ERROR"
    KAFKA_ERROR = "KAFKA_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    ENCRYPTION_ERROR = "ENCRYPTION_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


class ApplicationCreateRequest(BaseModel):
    """Request model for creating a loan application.

    All fields are required. PAN will be encrypted before storage.
    """

    pan_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="10-character PAN (e.g., ABCDE1234F)",
        json_schema_extra={"example": "ABCDE1234F"},
    )
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Applicant's first name",
        json_schema_extra={"example": "Rajesh"},
    )
    last_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Applicant's last name",
        json_schema_extra={"example": "Kumar"},
    )
    date_of_birth: date = Field(
        ...,
        description="Applicant's date of birth (YYYY-MM-DD)",
        json_schema_extra={"example": "1985-06-15"},
    )
    email: EmailStr = Field(
        ...,
        description="Applicant's email address",
        json_schema_extra={"example": "rajesh.kumar@example.com"},
    )
    phone_number: str = Field(
        ...,
        min_length=10,
        max_length=15,
        description="Applicant's phone number",
        json_schema_extra={"example": "9876543210"},
    )
    requested_amount: Decimal = Field(
        ...,
        gt=0,
        le=10000000,  # Max 1 crore
        decimal_places=2,
        description="Requested loan amount in INR",
        json_schema_extra={"example": 500000.00},
    )

    @field_validator("pan_number")
    @classmethod
    def validate_pan_format(cls, v: str) -> str:
        """Validate PAN format: AAAAA9999A.

        Format:
        - First 5 characters: Uppercase letters
        - Next 4 characters: Digits
        - Last character: Uppercase letter
        """
        if not v.isalnum():
            raise ValueError("PAN must contain only alphanumeric characters")

        if not v[:5].isalpha() or not v[:5].isupper():
            raise ValueError("First 5 characters must be uppercase letters")

        if not v[5:9].isdigit():
            raise ValueError("Characters 6-9 must be digits")

        if not v[9].isalpha() or not v[9].isupper():
            raise ValueError("Last character must be an uppercase letter")

        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validate phone number contains only digits."""
        if not v.isdigit():
            raise ValueError("Phone number must contain only digits")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_age(cls, v: date) -> date:
        """Validate applicant is at least 18 years old."""
        today = datetime.now(tz=timezone.utc).date()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))

        if age < MIN_AGE:
            raise ValueError("Applicant must be at least 18 years old")

        if age > MAX_AGE:
            raise ValueError("Invalid date of birth")

        return v

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "pan_number": "ABCDE1234F",
                "first_name": "Rajesh",
                "last_name": "Kumar",
                "date_of_birth": "1985-06-15",
                "email": "rajesh.kumar@example.com",
                "phone_number": "9876543210",
                "requested_amount": 500000.00,
            }
        }


class ApplicationCreateResponse(BaseModel):
    """Response model for successful application creation.

    Returns 202 Accepted with application_id.
    """

    application_id: UUID = Field(..., description="Unique identifier for the application")
    status: ApplicationStatus = Field(
        ..., description="Current application status (always PENDING)"
    )
    message: str = Field(
        ...,
        description="Human-readable message",
        json_schema_extra={"example": "Application submitted successfully and is being processed"},
    )
    created_at: datetime = Field(..., description="Timestamp of application creation")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "PENDING",
                "message": "Application submitted successfully and is being processed",
                "created_at": "2024-01-15T10:30:00Z",
            }
        }


class ApplicationStatusResponse(BaseModel):
    """Response model for application status query.

    PAN is masked for security (XXXXX1234F).
    """

    application_id: UUID = Field(..., description="Unique identifier for the application")
    status: ApplicationStatus = Field(..., description="Current application status")
    pan_number_masked: str = Field(
        ...,
        description="Masked PAN showing only last 4 characters",
        json_schema_extra={"example": "XXXXX1234F"},
    )
    first_name: str = Field(..., description="Applicant's first name")
    last_name: str = Field(..., description="Applicant's last name")
    requested_amount: Decimal = Field(..., description="Requested loan amount")

    # Credit information (populated after credit-service processing)
    credit_score: Optional[int] = Field(None, description="CIBIL credit score (300-900)")
    annual_income: Optional[Decimal] = Field(None, description="Annual income in INR")
    existing_loans_count: Optional[int] = Field(None, description="Number of existing loans")

    # Decision information (populated after decision-service processing)
    decision_reason: Optional[str] = Field(None, description="Reason for approval/rejection")
    max_approved_amount: Optional[Decimal] = Field(
        None, description="Maximum approved amount (if PRE_APPROVED)"
    )

    created_at: datetime = Field(..., description="Timestamp of application creation")
    updated_at: datetime = Field(..., description="Timestamp of last update")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "PRE_APPROVED",
                "pan_number_masked": "XXXXX1234F",
                "first_name": "Rajesh",
                "last_name": "Kumar",
                "requested_amount": 500000.00,
                "credit_score": 750,
                "annual_income": 1200000.00,
                "existing_loans_count": 1,
                "decision_reason": "Good credit score and sufficient income",
                "max_approved_amount": 600000.00,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:31:00Z",
            }
        }


class ErrorResponse(BaseModel):
    """Standardized error response model."""

    error_code: ErrorCode = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Additional error details (for debugging)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "error_code": "DUPLICATE_PAN",
                "message": "An application with this PAN already exists",
                "detail": "PAN hash collision detected",
                "timestamp": "2024-01-15T10:30:00Z",
            }
        }


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Service health status")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Health check timestamp"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {"example": {"status": "healthy", "timestamp": "2024-01-15T10:30:00Z"}}


class ReadinessResponse(BaseModel):
    """Readiness check response model."""

    ready: bool = Field(..., description="Whether service is ready to accept traffic")
    database: str = Field(..., description="Database connection status")
    kafka: str = Field(..., description="Kafka connection status")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Readiness check timestamp"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "ready": True,
                "database": "connected",
                "kafka": "connected",
                "timestamp": "2024-01-15T10:30:00Z",
            }
        }
