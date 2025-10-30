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

### Phase 1: Foundation & Infrastructure (Completed)
- ✅ Project structure and dependencies
- ✅ Docker Compose configuration (PostgreSQL, Kafka, Prometheus, Grafana)
- ✅ EncryptionService with comprehensive tests (15 test cases)
- ✅ Makefile with development commands
- ✅ Pre-commit hooks (Ruff, Black)
- ✅ Poetry configuration with all required dependencies

### Phase 2: prequal-api Core (Next)
- [ ] POST /applications with transactional outbox pattern
- [ ] GET /applications/{id}/status with PAN masking
- [ ] Health endpoints (/health, /ready, /metrics)
- [ ] Error handling with standard error codes
- [ ] Comprehensive unit tests (95% coverage target)

### Phase 3: Outbox Publisher & Kafka Integration
- [ ] OutboxPublisher background process (polls every 100ms)
- [ ] Circuit breaker for Kafka producer
- [ ] Integration tests with real Kafka

### Phase 4: credit-service
- [ ] Idempotent Kafka consumer
- [ ] CIBIL simulation with deterministic seeded random
- [ ] Transactional message processing

### Phase 5: decision-service
- [ ] Idempotent Kafka consumer
- [ ] Decision engine with business rules
- [ ] Optimistic locking for status updates

### Phase 6: End-to-End Testing
- [ ] Full workflow tests (POST → PENDING → PRE_APPROVED)
- [ ] Idempotency and optimistic lock conflict tests
- [ ] Performance tests (10K apps/day, 50/min burst)

### Phase 7: Observability & Production Readiness
- [ ] Prometheus metrics for all services
- [ ] Grafana dashboards (API, Kafka, Database, Business)
- [ ] Structured JSON logging
- [ ] Alerting rules

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
# All tests with coverage
pytest

# Watch mode for TDD
pytest --watch

# Specific test file
pytest services/shared/tests/test_encryption.py -v

# Coverage report
pytest --cov=services --cov-report=html
open htmlcov/index.html
```

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
