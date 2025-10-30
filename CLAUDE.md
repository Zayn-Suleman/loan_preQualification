# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Loan Prequalification Service** built as an event-driven microservices system for the Indian financial market. The system provides instant loan eligibility decisions through asynchronous processing.

**Architecture**: Three independent Python microservices communicating via Kafka:
- **prequal-api** (FastAPI): User-facing REST API for application submission and status checking
- **credit-service**: Kafka consumer that simulates CIBIL score calculation
- **decision-service**: Kafka consumer that applies business rules and makes prequalification decisions

**Core Flow**:
1. User submits application → API saves to PostgreSQL with `PENDING` status → publishes to Kafka
2. Credit service consumes message → simulates CIBIL score → publishes to Kafka
3. Decision service consumes message → applies business rules → updates DB with final decision

## Tech Stack

- **Language**: Python 3.10+
- **Framework**: FastAPI with Pydantic for validation
- **Build Tool**: Poetry
- **Database**: PostgreSQL
- **Message Broker**: Kafka
- **Testing**: Pytest with TestClient for API tests
- **Code Quality**: pre-commit hooks (Ruff for linting, Black for formatting)
- **Orchestration**: Docker Compose

## Development Commands

### Setup
```bash
# Install dependencies
poetry install

# Install pre-commit hooks
pre-commit install

# Start all services (Kafka, PostgreSQL, and microservices)
docker-compose up -d
```

### Testing
```bash
# Run all tests with coverage
make test

# Run specific test types
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only
pytest -m e2e              # End-to-end tests only

# Generate coverage report
pytest --cov=services --cov-report=html
```

### Code Quality
```bash
# Run linting
make lint
# or
ruff check .

# Format code
black .

# Run pre-commit hooks manually
pre-commit run --all-files
```

### Running Services
```bash
# Start entire stack
make run-local
# or
docker-compose up

# Rebuild services after code changes
docker-compose build

# View logs
docker-compose logs -f prequal-api
docker-compose logs -f credit-service
docker-compose logs -f decision-service
```

## Architecture Details

### Data Model (PostgreSQL)

The `applications` table is the single source of truth:
- `id` (UUID): Primary key
- `pan_number` (VARCHAR(10)): Indian PAN card number
- `applicant_name` (VARCHAR(255))
- `monthly_income_inr` (DECIMAL): Gross monthly income
- `loan_amount_inr` (DECIMAL): Requested loan amount
- `loan_type` (VARCHAR): PERSONAL, HOME, or AUTO
- `status` (VARCHAR): PENDING → PRE_APPROVED/REJECTED/MANUAL_REVIEW
- `cibil_score` (INTEGER): 300-900 range, populated by credit-service
- `created_at`, `updated_at` (TIMESTAMP)

### Kafka Topics

1. **loan_applications_submitted**: Published by prequal-api when application received
2. **credit_reports_generated**: Published by credit-service with CIBIL score

### Business Logic

**CIBIL Score Simulation** (credit-service):
- Test PANs: "ABCDE1234F" → 790, "FGHIJ5678K" → 610
- Default logic: Base 650, adjust for income/loan type, random variation, cap 300-900

**Decision Rules** (decision-service):
- CIBIL < 650 → REJECTED
- CIBIL ≥ 650 AND income > (loan_amount / 48) → PRE_APPROVED
- CIBIL ≥ 650 AND income ≤ (loan_amount / 48) → MANUAL_REVIEW

### API Endpoints (prequal-api)

**POST /applications**
- Accepts: `{pan_number, applicant_name, monthly_income_inr, loan_amount_inr, loan_type}`
- Returns: 202 Accepted with `{application_id, status: "PENDING"}`
- Validates input with Pydantic, saves to DB, publishes to Kafka

**GET /applications/{application_id}/status**
- Returns: 200 OK with `{application_id, status}`
- Status reflects current state from database

## Testing Requirements

- **Minimum coverage**: 85% overall
- **Business logic coverage**: 95%+ (CIBIL simulation, decision rules)
- **Test types required**:
  - Unit tests: Mock dependencies, test logic in isolation
  - API tests: Use FastAPI TestClient, verify status codes and responses
  - Integration tests: Test Kafka message flow and DB updates with docker-compose
  - E2E tests: Full workflow from POST to final status in DB

## Code Standards

- **Follow TDD**: Write failing tests first (Red), implement (Green), refactor (Blue)
- **Event-driven patterns**: Services must be loosely coupled, communicate only via Kafka
- **Pydantic models**: Use for all API I/O and Kafka message schemas
- **Exception handling**: Global exception handlers in FastAPI for consistent error responses
- **Async/await**: Use FastAPI's async capabilities for non-blocking operations
- **Configuration**: Environment variables via Pydantic BaseSettings, never hardcode

## Custom Slash Commands

This project has specialized Claude Code commands:

- `/tech-design-backend-python-fastapi`: Generate technical design from requirements (saves to tech-design.md)
- `/development-backend-python-fastapi`: Implement features following TDD methodology from tech design
- `/code-review-backend-python-fastapi`: Comprehensive code review with quality scoring (saves to code-review.md)

These commands reference docs/requirement.md and enforce enterprise-grade Python/FastAPI standards.

## Project Structure (Expected)

```
loan-prequal-system/
├── services/
│   ├── prequal-api/           # FastAPI REST API
│   │   ├── app/
│   │   │   ├── main.py        # FastAPI app, routers
│   │   │   ├── logic.py       # Business logic
│   │   │   ├── models.py      # Pydantic models
│   │   │   ├── db.py          # Database models & session
│   │   │   └── producer.py    # Kafka producer
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── credit-service/        # Kafka consumer for CIBIL
│   │   ├── app/
│   │   │   ├── main.py        # Consumer loop
│   │   │   └── logic.py       # CIBIL simulation
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── decision-service/      # Kafka consumer for decisions
│       ├── app/
│       │   ├── main.py        # Consumer loop
│       │   ├── logic.py       # Decision engine
│       │   └── db.py          # DB update logic
│       ├── tests/
│       ├── Dockerfile
│       └── pyproject.toml
├── docs/
│   └── requirement.md         # Full requirements specification
├── .pre-commit-config.yaml    # Ruff + Black hooks
├── docker-compose.yml         # Orchestrates all services
├── Makefile                   # Convenience commands
└── README.md
```

## Important Notes

- **No authentication/authorization** in scope for v1 (basic validation only)
- **Simulated CIBIL service** - not real credit bureau integration
- **Local CI/CD only** - no cloud deployment in this phase
- **PAN validation**: Must be 10 characters (format: ABCDE1234F)
- **API response time target**: < 200ms for initial 202 response
- **Kafka consumer resilience**: Implement retry logic and error handling for failed message processing
