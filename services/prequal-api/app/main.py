"""FastAPI application for loan prequalification service.

This module implements the REST API with:
- POST /applications - Submit loan application
- GET /applications/{id}/status - Check application status
- GET /health - Liveness probe
- GET /ready - Readiness probe
- GET /metrics - Prometheus metrics
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Add project root to path for imports
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from services.shared.encryption import EncryptionService
from .models import (
    ApplicationCreateRequest,
    ApplicationCreateResponse,
    ApplicationStatusResponse,
    ErrorCode,
    ErrorResponse,
    HealthResponse,
    ReadinessResponse,
)
from .services import ApplicationService


# Configuration
class Settings(BaseSettings):
    """Application settings from environment variables."""

    database_url: str = "postgresql://loan_user:loan_password@localhost:5432/loan_prequalification"
    encryption_key: str
    service_name: str = "prequal-api"
    log_level: str = "INFO"
    kafka_bootstrap_servers: Optional[str] = "localhost:9092"  # For future use

    class Config:
        """Pydantic config."""

        env_file = ".env"


# Global settings
settings = Settings()

# Database engine and session factory
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Encryption service
encryption_service = EncryptionService(settings.encryption_key)

# Prometheus metrics
REQUESTS_TOTAL = Counter(
    "prequal_api_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "prequal_api_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
)

APPLICATIONS_CREATED = Counter(
    "prequal_api_applications_created_total",
    "Total number of applications created",
)

APPLICATIONS_REJECTED = Counter(
    "prequal_api_applications_rejected_total",
    "Total number of applications rejected",
    ["reason"],
)


# Import OutboxPublisher
from .outbox_publisher import OutboxPublisher

# Global OutboxPublisher instance
outbox_publisher: Optional[OutboxPublisher] = None


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    global outbox_publisher

    # Startup
    print(f"Starting {settings.service_name}...")
    print(f"Database: {settings.database_url.split('@')[1]}")  # Hide password

    # Test database connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database connection successful")
    except Exception as e:
        print(f"WARNING: Database connection failed: {e}")

    # Start OutboxPublisher background task
    print("Starting OutboxPublisher...")
    outbox_publisher = OutboxPublisher(
        session_factory=SessionLocal,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers or "localhost:9092",
        poll_interval_ms=100,
        batch_size=10,
        max_retries=5,
    )

    # Start publisher in background
    import asyncio

    publisher_task = asyncio.create_task(outbox_publisher.start())
    print("OutboxPublisher started successfully")

    yield

    # Shutdown
    print(f"Shutting down {settings.service_name}...")

    # Stop OutboxPublisher
    if outbox_publisher:
        print("Stopping OutboxPublisher...")
        outbox_publisher.stop()
        await asyncio.sleep(0.5)  # Give time to finish current batch

    # Cancel publisher task
    if not publisher_task.done():
        publisher_task.cancel()
        try:
            await publisher_task
        except asyncio.CancelledError:
            pass

    engine.dispose()
    print("Shutdown complete")


# FastAPI app
app = FastAPI(
    title="Loan Prequalification API",
    description="Event-driven microservice for instant loan eligibility decisions",
    version="1.0.0",
    lifespan=lifespan,
)


# Dependency: Database session
def get_db() -> Session:
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Dependency: Application service
def get_application_service(db: Session) -> ApplicationService:
    """Get ApplicationService dependency."""
    return ApplicationService(db, encryption_service)


# === API Endpoints ===


@app.post(
    "/applications",
    response_model=ApplicationCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Application accepted for processing"},
        400: {
            "model": ErrorResponse,
            "description": "Validation error or duplicate PAN",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Applications"],
)
async def create_application(request: ApplicationCreateRequest) -> ApplicationCreateResponse:
    """Submit a new loan application.

    The application will be:
    1. Validated (PAN format, age, amount limits)
    2. Encrypted (PAN) and stored in database
    3. Published to Kafka for asynchronous processing

    Returns 202 Accepted with application_id.
    """
    db = next(get_db())
    service = get_application_service(db)

    try:
        # Record metrics
        with REQUEST_DURATION.labels(method="POST", endpoint="/applications").time():
            response = service.create_application(request)
            APPLICATIONS_CREATED.inc()
            REQUESTS_TOTAL.labels(
                method="POST", endpoint="/applications", status="202"
            ).inc()
            return response

    except ValueError as e:
        # Duplicate PAN or validation error
        APPLICATIONS_REJECTED.labels(reason="duplicate_pan").inc()
        REQUESTS_TOTAL.labels(
            method="POST", endpoint="/applications", status="400"
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": ErrorCode.DUPLICATE_PAN.value,
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        # Internal error
        REQUESTS_TOTAL.labels(
            method="POST", endpoint="/applications", status="500"
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": ErrorCode.INTERNAL_ERROR.value,
                "message": "Failed to create application",
                "detail": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@app.get(
    "/applications/{application_id}/status",
    response_model=ApplicationStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Application status retrieved"},
        404: {"model": ErrorResponse, "description": "Application not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Applications"],
)
async def get_application_status(application_id: UUID) -> ApplicationStatusResponse:
    """Get the status of a loan application.

    Returns:
    - Application status (PENDING, PRE_APPROVED, REJECTED, MANUAL_REVIEW)
    - Masked PAN (XXXXX1234F)
    - Credit information (if available)
    - Decision details (if available)
    """
    db = next(get_db())
    service = get_application_service(db)

    try:
        with REQUEST_DURATION.labels(
            method="GET", endpoint="/applications/{id}/status"
        ).time():
            response = service.get_application_status(application_id)
            REQUESTS_TOTAL.labels(
                method="GET", endpoint="/applications/{id}/status", status="200"
            ).inc()
            return response

    except ValueError as e:
        # Application not found
        REQUESTS_TOTAL.labels(
            method="GET", endpoint="/applications/{id}/status", status="404"
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": ErrorCode.NOT_FOUND.value,
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        REQUESTS_TOTAL.labels(
            method="GET", endpoint="/applications/{id}/status", status="500"
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": ErrorCode.INTERNAL_ERROR.value,
                "message": "Failed to retrieve application status",
                "detail": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
)
async def health_check() -> HealthResponse:
    """Liveness probe.

    Returns 200 if service is alive (for Kubernetes liveness probe).
    """
    return HealthResponse(status="healthy", timestamp=datetime.utcnow())


@app.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"},
    },
    tags=["Health"],
)
async def readiness_check() -> ReadinessResponse:
    """Readiness probe.

    Checks:
    - Database connectivity
    - (Future: Kafka connectivity)

    Returns 200 if ready, 503 if not ready (for Kubernetes readiness probe).
    """
    # Check database
    db_status = "disconnected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        pass

    # Check Kafka (placeholder for future implementation)
    kafka_status = "not_configured"

    ready = db_status == "connected"

    if not ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "ready": False,
                "database": db_status,
                "kafka": kafka_status,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    return ReadinessResponse(
        ready=True,
        database=db_status,
        kafka=kafka_status,
        timestamp=datetime.utcnow(),
    )


@app.get(
    "/metrics",
    response_class=PlainTextResponse,
    tags=["Observability"],
)
async def metrics() -> str:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    """
    return generate_latest().decode("utf-8")


@app.get(
    "/outbox/metrics",
    tags=["Observability"],
)
async def outbox_metrics():
    """OutboxPublisher metrics endpoint.

    Returns current metrics from the OutboxPublisher background process.
    """
    if outbox_publisher:
        return outbox_publisher.get_metrics()
    return {
        "error": "OutboxPublisher not initialized",
        "total_published": 0,
        "total_failed": 0,
        "circuit_breaker_state": "UNKNOWN",
        "running": False,
    }


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }
