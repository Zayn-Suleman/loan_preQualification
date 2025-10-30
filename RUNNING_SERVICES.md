# Running Services Guide

This guide explains how to run the individual microservices for the Loan Prequalification System.

## Prerequisites

1. Docker containers must be running (PostgreSQL, Kafka, Zookeeper):
   ```bash
   docker-compose up -d
   ```

2. Verify all infrastructure is healthy:
   ```bash
   docker-compose ps
   ```

## Running Services

### Option 1: Using Makefile Commands (Recommended)

```bash
# Start prequal-api service (FastAPI REST API)
make run-prequal

# Start credit-service (Kafka consumer)
make run-credit

# Start decision-service (Kafka consumer)
make run-decision
```

### Option 2: Using Shell Scripts Directly

```bash
# Prequal API Service
./scripts/run_prequal_api.sh

# Credit Service
./scripts/run_credit_service.sh

# Decision Service
./scripts/run_decision_service.sh
```

## Service Details

### 1. Prequal API Service

**Command:** `make run-prequal`

**Details:**
- Port: 8000
- API Documentation: http://localhost:8000/docs
- Interactive API: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health
- Readiness Check: http://localhost:8000/ready
- Metrics: http://localhost:8000/metrics

**What it does:**
- Accepts POST requests to `/applications` for loan applications
- Returns 202 Accepted with application_id
- Stores encrypted application data in PostgreSQL
- Publishes events to Kafka for async processing

**Example API Call:**
```bash
curl -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -d '{
    "pan_number": "ABCDE1234F",
    "applicant_name": "John Doe",
    "monthly_income_inr": 50000,
    "loan_amount_inr": 500000,
    "loan_type": "PERSONAL"
  }'
```

### 2. Credit Service (Not Yet Implemented)

**Command:** `make run-credit`

**Details:**
- Runs as a Kafka consumer
- Consumes from: `loan_applications_submitted` topic
- Publishes to: `credit_reports_generated` topic

**What it will do:**
- Listen for new loan applications
- Simulate CIBIL score calculation
- Publish credit report with score back to Kafka

**Status:**
- Script created and ready
- Service implementation pending

### 3. Decision Service (Not Yet Implemented)

**Command:** `make run-decision`

**Details:**
- Runs as a Kafka consumer
- Consumes from: `credit_reports_generated` topic
- Updates: PostgreSQL application status

**What it will do:**
- Listen for credit reports
- Apply business rules for loan approval
- Update application status (PRE_APPROVED, REJECTED, MANUAL_REVIEW)

**Status:**
- Script created and ready
- Service implementation pending

## Troubleshooting

### Port 8000 Already in Use

```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

### Environment Variables Not Loading

Check that each service has a `.env` file:
```bash
ls -la services/prequal-api/.env
ls -la services/credit-service/.env
ls -la services/decision-service/.env
```

### Database Connection Issues

1. Verify PostgreSQL is running:
   ```bash
   docker-compose ps postgres
   ```

2. Test connection:
   ```bash
   docker exec -it loan-prequal-postgres psql -U loan_user -d loan_prequalification
   ```

### Kafka Connection Issues

1. Verify Kafka is running:
   ```bash
   docker-compose ps kafka
   ```

2. Check Kafka topics:
   ```bash
   docker exec -it loan-prequal-kafka kafka-topics --list --bootstrap-server localhost:9092
   ```

## Stopping Services

- Press `Ctrl+C` in the terminal where the service is running
- Or use `make docker-down` to stop all infrastructure

## Development Workflow

1. Start infrastructure:
   ```bash
   make docker-up
   ```

2. Run database migrations:
   ```bash
   make migrations-upgrade
   ```

3. Start services in separate terminal windows:
   ```bash
   # Terminal 1
   make run-prequal

   # Terminal 2 (when implemented)
   make run-credit

   # Terminal 3 (when implemented)
   make run-decision
   ```

4. Test the API at http://localhost:8000/docs

## Additional Commands

```bash
# View all available make commands
make help

# Run tests
make test

# Check code quality
make lint

# Format code
make format

# View Docker logs
docker-compose logs -f prequal-api
```
