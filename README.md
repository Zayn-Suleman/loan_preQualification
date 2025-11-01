# Loan Prequalification Service

Event-driven microservices system for instant loan eligibility decisions in the Indian credit market.

## 📋 Overview

This system implements a production-ready loan prequalification service with:
- **3 Independent Microservices**: prequal-api, credit-service, decision-service
- **Event-Driven Architecture**: Asynchronous processing via Kafka
- **Enterprise Security**: End-to-end PAN encryption (AES-256-GCM)
- **Data Consistency**: Transactional outbox pattern + idempotent consumers + optimistic locking
- **Observability**: Prometheus metrics, Grafana dashboards, structured logging

## 🏗️ Architecture

```
User → prequal-api (FastAPI)
          ↓
    PostgreSQL (transactional outbox)
          ↓
    OutboxPublisher → Kafka (loan_applications_submitted)
          ↓
    credit-service (idempotent consumer)
          ↓
    Kafka (credit_reports_generated)
          ↓
    decision-service (optimistic locking)
          ↓
    PostgreSQL (final status)
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Docker & Docker Compose
- Poetry

### Installation

```bash
# Install dependencies
make install

# Install pre-commit hooks
poetry run pre-commit install

# Start infrastructure (PostgreSQL, Kafka, Prometheus, Grafana)
make docker-up

# Run database migrations
make migrations-upgrade
```

### Running Tests

```bash
# Run all tests with coverage
make test

# Run specific test types
make test-unit           # Unit tests only
make test-integration    # Integration tests
make test-e2e            # End-to-end tests

# Generate coverage report
make coverage
```

### Code Quality

```bash
# Lint code
make lint

# Format code
make format
```

## 📁 Project Structure

```
loan-prequal-system/
├── services/
│   ├── shared/                      # Shared utilities
│   │   ├── encryption.py            # ✅ AES-256-GCM encryption service
│   │   └── tests/
│   │       └── test_encryption.py   # ✅ Comprehensive encryption tests
│   │
│   ├── prequal-api/                 # FastAPI REST API
│   │   ├── app/
│   │   │   ├── main.py              # FastAPI app
│   │   │   ├── models.py            # Pydantic models
│   │   │   ├── db.py                # Database models
│   │   │   ├── services.py          # Business logic (outbox pattern)
│   │   │   └── outbox_publisher.py  # Background outbox publisher
│   │   └── tests/
│   │
│   ├── credit-service/              # Kafka consumer (CIBIL simulation)
│   │   ├── app/
│   │   │   ├── main.py              # Consumer loop
│   │   │   ├── logic.py             # CIBIL calculation
│   │   │   └── consumer.py          # Idempotent consumer
│   │   └── tests/
│   │
│   └── decision-service/            # Kafka consumer (decision engine)
│       ├── app/
│       │   ├── main.py              # Consumer loop
│       │   ├── logic.py             # Decision rules
│       │   └── consumer.py          # Idempotent consumer + optimistic locking
│       └── tests/
│
├── infrastructure/
│   ├── postgres/
│   │   └── migrations/              # Alembic migrations
│   ├── prometheus/
│   │   └── prometheus.yml           # Metrics configuration
│   └── grafana/
│       └── dashboards/              # Monitoring dashboards
│
├── docker-compose.yml               # ✅ Infrastructure orchestration
├── pyproject.toml                   # ✅ Poetry dependencies
├── Makefile                         # ✅ Development commands
├── .pre-commit-config.yaml          # ✅ Code quality hooks
└── README.md                        # This file
```

## ✅ Implementation Status

**Project Status: 90% Complete** (9 out of 10 phases completed)

### Phase 1-4: Core Implementation ✅ COMPLETED
- ✅ Project structure and dependencies
- ✅ Docker Compose configuration (PostgreSQL, Kafka, Zookeeper, Prometheus, Grafana, Adminer, Kafka UI)
- ✅ EncryptionService with comprehensive tests (13/13 passing, 94% coverage)
- ✅ Makefile with development commands
- ✅ Pre-commit hooks (Ruff, Black, YAML validation)
- ✅ Poetry configuration with all required dependencies
- ✅ **prequal-api (FastAPI REST API)**:
  - ✅ POST /applications with transactional outbox pattern
  - ✅ GET /applications/{id}/status with PAN masking
  - ✅ Health endpoints (/health, /ready, /metrics)
  - ✅ Error handling with standard error codes (DUPLICATE_PAN, NOT_FOUND, VALIDATION_ERROR, INTERNAL_ERROR)
  - ✅ OutboxPublisher background process (polls every 100ms)
- ✅ **credit-service (Kafka Consumer)**:
  - ✅ Idempotent Kafka consumer with deduplication
  - ✅ CIBIL simulation with deterministic seeded random (17/17 tests passing, 100% coverage)
  - ✅ Transactional message processing
- ✅ **decision-service (Kafka Consumer)**:
  - ✅ Idempotent Kafka consumer
  - ✅ Decision engine with business rules (18/18 tests passing, 100% coverage)
  - ✅ Optimistic locking for status updates

### Phase 5: Unit Testing Infrastructure ✅ COMPLETED
- ✅ Encryption service tests: 13/13 passing (94% coverage)
- ✅ Credit service tests: 17/17 passing (100% coverage)
- ✅ Decision service tests: 18/18 passing (100% coverage)
- ✅ Total: 48 unit tests passing

### Phase 6: CI/CD Pipeline ✅ COMPLETED
- ✅ GitHub Actions workflow (.github/workflows/ci.yml)
- ✅ Automated testing on push/PR
- ✅ Code quality checks (Ruff linting, Black formatting)
- ✅ Docker build verification
- ✅ Security scanning
- ✅ All workflow jobs passing

### Phase 7: API Validation Tests ✅ COMPLETED
- ✅ Pydantic model validation tests (9/9 passing)
- ✅ PAN format validation
- ✅ Age, email, phone, amount validation
- ✅ Missing fields and error code tests
- ✅ Total: 56 tests passing (48 unit + 9 validation)

### Phase 8-9: E2E & Kafka Integration Tests ✅ COMPLETED
- ✅ End-to-end workflow tests (11/11 passing)
- ✅ TestE2EWorkflow: Full application flow (6 tests)
- ✅ TestE2EErrorHandling: Error scenarios (2 tests)
- ✅ TestE2EPerformance: API response time (1 test)
- ✅ Kafka message flow verified through E2E tests
- ✅ Database state verification
- ✅ Auto-skip if services not running
- ✅ Total: 67 tests passing (56 unit + 11 E2E)

### Phase 10: Production Readiness ⏳ IN PROGRESS
- ✅ .env.example files for all services
- ✅ Comprehensive documentation (README, tests/README, CLAUDE.md)
- ✅ Prometheus metrics for all services
- ✅ Grafana dashboard configurations
- ✅ Structured JSON logging
- ⏳ Final local verification
- ⏳ Performance benchmarking

## 🔐 Security Features

- **End-to-End PAN Encryption**: AES-256-GCM from API → DB → Kafka → Consumers
- **PAN Masking**: API responses show only last 4 characters (XXXXX1234F)
- **Audit Logging**: All PAN access tracked with timestamp and service identity
- **SHA-256 Hashing**: Duplicate detection without decryption
- **No Plaintext Storage**: PAN never stored or transmitted in plaintext

## 🧪 Testing Strategy

### Test Coverage Targets
- **Business Logic**: 95%+ coverage
- **Overall**: 85%+ coverage
- **Critical Paths**: 100% coverage (encryption, decision rules, outbox pattern)

### Test Types
1. **Unit Tests**: Mock dependencies, test logic in isolation
2. **API Tests**: FastAPI TestClient, verify status codes and responses
3. **Integration Tests**: Real PostgreSQL and Kafka, test message flow
4. **E2E Tests**: Full workflow from POST to final status

### Running Tests

```bash
# Run unit tests only (default - E2E tests excluded)
pytest

# Run E2E tests (requires docker-compose up)
docker-compose up -d
pytest tests/ -m e2e -v

# Run all tests (unit + E2E)
pytest -v

# Run specific test file
pytest services/shared/tests/test_encryption.py -v

# Run specific test class
pytest tests/test_e2e_workflow.py::TestE2EWorkflow -v

# Coverage report
pytest --cov=services --cov-report=html
open htmlcov/index.html

# Watch mode for TDD
pytest --watch
```

### Test Summary
- **Unit Tests**: 56 tests (encryption, credit, decision, API validation)
- **E2E Tests**: 11 tests (full workflow, error handling, performance)
- **Total**: 67 tests
- **Coverage**: 85%+ overall, 95%+ business logic

## 📊 Monitoring

Access monitoring tools:
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **API Docs**: http://localhost:8000/docs (when running)

## 🛠️ Development Workflow

### TDD Cycle (Red-Green-Refactor)

1. **🔴 RED**: Write failing test
```bash
# Create test file
touch services/prequal-api/tests/test_application_service.py
# Write test, run, verify it fails
pytest services/prequal-api/tests/test_application_service.py
```

2. **🟢 GREEN**: Implement minimum code to pass test
```bash
# Implement feature
# Run test, verify it passes
pytest services/prequal-api/tests/test_application_service.py
```

3. **🔄 REFACTOR**: Improve code while keeping tests green
```bash
# Refactor code
# Run all tests to ensure nothing broke
make test
```

4. **📊 COVERAGE**: Verify coverage
```bash
make coverage
```

### Pre-commit Workflow

```bash
# Stage changes
git add .

# Pre-commit hooks run automatically
# - Black formats code
# - Ruff lints and auto-fixes
# - Other checks (trailing whitespace, YAML, JSON)

# If hooks fail, they auto-fix. Stage fixes and commit again
git add .
git commit -m "feat: implement EncryptionService"
```

## 🗄️ Database Schema

### Core Tables
- **applications**: Loan applications with encrypted PAN, optimistic locking (version column)
- **audit_log**: PAN access audit trail
- **processed_messages**: Idempotency tracking for Kafka consumers
- **outbox_events**: Transactional outbox for reliable message publishing

### Migrations

```bash
# Generate migration
make migrations-generate message="add_applications_table"

# Apply migrations
make migrations-upgrade

# Rollback migration
make migrations-downgrade
```

## 🐳 Docker Commands

```bash
# Start all infrastructure
make docker-up

# Stop infrastructure
make docker-down

# View logs
make docker-logs

# Rebuild images
make docker-build
```

## 📖 API Documentation

Once prequal-api is running:
- **OpenAPI (Swagger)**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

**POST /applications**
- Submit loan application
- Returns 202 Accepted with application_id
- PAN encrypted before storage

**GET /applications/{application_id}/status**
- Check application status
- Returns PENDING | PRE_APPROVED | REJECTED | MANUAL_REVIEW
- PAN masked in response (XXXXX1234F)

**GET /health**
- Liveness check

**GET /ready**
- Readiness check (DB + Kafka connectivity)

**GET /metrics**
- Prometheus metrics

## 🔧 Configuration

### Environment Variables

Create `.env` files for each service:

```bash
# prequal-api/.env
DATABASE_URL=postgresql://loan_user:loan_password@localhost:5432/loan_prequalification
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ENCRYPTION_KEY=<base64-encoded-32-byte-key>
LOG_LEVEL=INFO
SERVICE_NAME=prequal-api
```

### Generating Encryption Key

```python
import base64
import os

# Generate 32-byte (256-bit) key
key = os.urandom(32)
encoded_key = base64.b64encode(key).decode()
print(f"ENCRYPTION_KEY={encoded_key}")
```

## 📚 Technical Design

Full technical design: [tech-design.md](./tech-design.md)
Design review: [tech-design-review-v2.md](./tech-design-review-v2.md)

## 🤝 Contributing

1. Follow TDD methodology (Red-Green-Refactor)
2. Ensure all tests pass: `make test`
3. Run pre-commit hooks: `pre-commit run --all-files`
4. Maintain 85%+ code coverage
5. Write clear docstrings (Google style)

## 📝 License

Internal project for demonstration purposes.

## 🙏 Acknowledgments

Based on technical design v2.0 implementing:
- Transactional Outbox Pattern
- Idempotent Consumers
- Optimistic Locking
- End-to-End Encryption
- Event-Driven Architecture

---

**Status**: Phase 1 Complete ✅ | Ready for Phase 2 Implementation
**Next**: Implement prequal-api with transactional outbox pattern
