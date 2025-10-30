/# Technical Design: Loan Prequalification Service

## Document Version
- **Version**: 2.0 (Revised)
- **Last Updated**: 2024-01-15
- **Status**: Ready for Implementation
- **Previous Version Issues Addressed**: 5 Critical Issues from Tech Design Review

## Revision Summary

This revised technical design addresses all **5 Critical Issues** identified in the technical design review:

1. ✅ **Data Consistency & Idempotency**: Added optimistic locking (version column), idempotent message processing (processed_messages table), and transactional outbox pattern
2. ✅ **Schema Syntax Errors**: Corrected PRIMARY KEY and INDEX syntax, added composite indexes for query optimization
3. ✅ **PAN Security in Kafka**: PAN now encrypted end-to-end (at-rest AND in-transit through Kafka)
4. ✅ **Transaction Boundaries**: Implemented transactional outbox pattern for prequal-api, transactional message processing for consumers
5. ✅ **Error Response Schema**: Defined comprehensive error codes catalog with request_id for correlation

**Additional Improvements**:
- Added duplicate application prevention (24-hour window)
- Enhanced health check specifications
- Deterministic CIBIL calculation with seeded randomness
- Comprehensive audit logging throughout
- PAN masking in all API responses

## 1. Overview
- **Estimated Complexity**: High
- **Architecture Pattern**: Event-Driven Microservices with Transactional Outbox
- **Target Load**: ~10,000+ applications/day (~7 applications/minute peak)
- **API SLA**: 500ms response time for status checks, 202 immediate response for submissions
- **Database**: PostgreSQL with connection pooling and optimistic locking
- **Message Broker**: Kafka with consumer groups and idempotent processing
- **Deployment Model**: Docker Compose (local/dev), containerized for production
- **Data Consistency**: Eventual consistency with strong guarantees via outbox pattern

## 2. Business Requirements Summary

The Loan Prequalification Service provides instant, high-level loan eligibility decisions for the Indian credit market. The system:

- Accepts minimal loan applications (PAN number, income, loan amount)
- Asynchronously simulates CIBIL score checking based on PAN and income
- Applies business rules to determine prequalification status (PRE_APPROVED, REJECTED, MANUAL_REVIEW)
- Provides fast, resilient user-facing API while complex processing happens in background
- Ensures loose coupling through event-driven architecture

**Key Business Rules**:
- CIBIL score < 650 → REJECTED
- CIBIL score ≥ 650 AND monthly income > (loan_amount / 48) → PRE_APPROVED
- CIBIL score ≥ 650 AND monthly income ≤ (loan_amount / 48) → MANUAL_REVIEW

## 3. Technical Requirements

### 3.1 Functional Requirements

**FR1: Application Submission**
- Accept POST /applications with applicant details (PAN, name, income, loan amount, loan type)
- Validate input using Pydantic models
- Persist application with PENDING status to PostgreSQL
- Publish event to Kafka topic `loan_applications_submitted`
- Return 202 Accepted with application_id immediately

**FR2: Application Status Retrieval**
- Accept GET /applications/{application_id}/status
- Return current status from PostgreSQL (PENDING, PRE_APPROVED, REJECTED, MANUAL_REVIEW)
- Return 404 if application_id not found

**FR3: Credit Score Simulation**
- Consume from `loan_applications_submitted` Kafka topic
- Simulate CIBIL score (300-900) based on:
  - Test PAN mappings: "ABCDE1234F" → 790, "FGHIJ5678K" → 610
  - Default logic: Base 650 + income adjustments + loan type adjustments + random variation
- Publish result to `credit_reports_generated` Kafka topic

**FR4: Decision Engine**
- Consume from `credit_reports_generated` Kafka topic
- Apply business rules based on CIBIL score and income-to-loan ratio
- Update application status in PostgreSQL
- Update cibil_score field in database

**FR5: Data Validation**
- PAN format: 10 characters (5 letters, 4 digits, 1 letter)
- Monetary values: Positive decimals only
- Loan type: Enum validation (PERSONAL, HOME, AUTO)

**FR6: Error Handling**
- Return 422 for validation errors with clear messages
- Handle Kafka consumer failures with retries and dead letter queue
- Handle database connection failures with circuit breaker

### 3.2 Non-Functional Requirements

**NFR1: Performance**
- API response time: < 500ms for GET requests (p95)
- API response time: < 100ms for POST requests (immediate 202 return)
- Kafka message processing: < 2 seconds end-to-end (submission to final decision)
- Database query optimization: Indexed on application_id, status, created_at

**NFR2: Scalability**
- Horizontal scaling support for all three microservices
- Kafka consumer groups for parallel message processing
- Database connection pooling (min: 5, max: 20 per service)
- Target: 10,000+ applications/day (~7/min sustained, ~50/min peak)

**NFR3: Reliability**
- Kafka consumer retry mechanism with exponential backoff (3 retries, max 10s delay)
- Dead letter queue for failed messages after max retries
- Circuit breaker for database connections (failure threshold: 5, timeout: 30s)
- At-least-once message delivery guarantee with idempotent processing
- Transactional outbox pattern for reliable message publishing

**NFR4: Security**
- PAN encryption at rest using AES-256 in PostgreSQL
- PAN encryption in transit through Kafka messages
- PAN masking in API responses (show only last 4 characters)
- Audit logging for all PAN data access with timestamp and service identity
- No authentication/authorization in v1 (future consideration)

**NFR5: Observability**
- Structured JSON logging to stdout (parseable by log aggregators)
- Health check endpoints: /health (liveness), /ready (readiness)
- Prometheus metrics: request counts, latencies, error rates, Kafka lag
- Grafana dashboards: API performance, Kafka throughput, database connection pool
- Correlation IDs: application_id used to trace requests across services

**NFR6: Maintainability**
- Code coverage: Minimum 85% (business logic 95%+)
- Pre-commit hooks: Ruff (linting), Black (formatting)
- OpenAPI 3.0 documentation auto-generated by FastAPI
- Docstrings for all public functions (Google style)

## 4. Architecture Overview

### 4.1 High-Level Design

```
┌─────────────────┐
│   API Client    │
│  (Applicant)    │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────────────────────────────────────────┐
│            prequal-api (FastAPI)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │   Router     │→ │   Service    │→ │ Kafka    │ │
│  │  /apps       │  │   Layer      │  │ Producer │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
└──────────┬──────────────────────────────────────────┘
           │
           ▼
    ┌──────────────┐
    │  PostgreSQL  │
    │  (Primary)   │
    └──┬───────────┘
       │
       │ Read/Write
       │
    ┌──┴───────────────────────────────────────┐
    │                                           │
    ▼                                           ▼
┌─────────────────┐                   ┌─────────────────┐
│ Kafka Cluster   │                   │ Prometheus      │
│ Topics:         │                   │ (Metrics)       │
│ 1. loan_apps... │                   └─────────────────┘
│ 2. credit_rep...│                            │
│ 3. DLQ topics   │                            ▼
└────┬────────┬───┘                   ┌─────────────────┐
     │        │                       │   Grafana       │
     │        │                       │  (Dashboards)   │
     │        │                       └─────────────────┘
     │        │
     ▼        ▼
┌────────┐  ┌────────────┐
│ credit-│  │ decision-  │
│ service│  │  service   │
│(Consumer)  │(Consumer)  │
└────────┘  └─────┬──────┘
     │            │
     │            │ Update Status
     └────────────┴──────────────┐
                                 ▼
                          ┌──────────────┐
                          │  PostgreSQL  │
                          └──────────────┘
```

**Event Flow**:
1. User → POST /applications → prequal-api
2. prequal-api → Save to PostgreSQL (status: PENDING)
3. prequal-api → Publish to `loan_applications_submitted`
4. credit-service → Consume from `loan_applications_submitted`
5. credit-service → Calculate CIBIL score
6. credit-service → Publish to `credit_reports_generated`
7. decision-service → Consume from `credit_reports_generated`
8. decision-service → Apply business rules
9. decision-service → Update PostgreSQL (status: PRE_APPROVED/REJECTED/MANUAL_REVIEW)
10. User → GET /applications/{id}/status → prequal-api returns updated status

### 4.2 Affected Microservices

**New Microservices (All to be created)**:

1. **prequal-api**
   - Port: 8000
   - Responsibility: REST API gateway, application persistence, event publishing
   - Dependencies: PostgreSQL, Kafka (producer)

2. **credit-service**
   - Responsibility: CIBIL score simulation, credit report generation
   - Dependencies: Kafka (consumer + producer)

3. **decision-service**
   - Responsibility: Decision engine, status updates
   - Dependencies: Kafka (consumer), PostgreSQL

**Supporting Infrastructure**:
- PostgreSQL (port 5432)
- Kafka + Zookeeper (ports 9092, 2181)
- Prometheus (port 9090)
- Grafana (port 3000)

## 5. Detailed Design

### 5.1 Data Model

**PostgreSQL Schema**:

```sql
-- Table: applications
CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pan_number_encrypted BYTEA NOT NULL,  -- AES-256 encrypted
    pan_number_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash for lookups
    applicant_name VARCHAR(255),
    monthly_income_inr DECIMAL(12, 2) NOT NULL CHECK (monthly_income_inr > 0),
    loan_amount_inr DECIMAL(12, 2) NOT NULL CHECK (loan_amount_inr > 0),
    loan_type VARCHAR(20) NOT NULL CHECK (loan_type IN ('PERSONAL', 'HOME', 'AUTO')),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PRE_APPROVED', 'REJECTED', 'MANUAL_REVIEW')),
    cibil_score INTEGER CHECK (cibil_score BETWEEN 300 AND 900),
    version INTEGER NOT NULL DEFAULT 1,  -- For optimistic locking
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for applications table
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_created_at ON applications(created_at DESC);
CREATE INDEX idx_applications_pan_hash ON applications(pan_number_hash);
CREATE INDEX idx_applications_id_status ON applications(id, status);  -- Composite for common queries

-- Unique constraint to prevent duplicate recent applications
CREATE UNIQUE INDEX idx_unique_recent_pan ON applications(pan_number_hash)
WHERE created_at > NOW() - INTERVAL '24 hours' AND status != 'REJECTED';

-- Table: audit_log (for PAN access tracking)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    application_id UUID NOT NULL REFERENCES applications(id),
    service_name VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,  -- 'READ', 'WRITE', 'UPDATE'
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for audit_log table
CREATE INDEX idx_audit_log_application_id ON audit_log(application_id);
CREATE INDEX idx_audit_log_accessed_at ON audit_log(accessed_at DESC);
CREATE INDEX idx_audit_app_time ON audit_log(application_id, accessed_at DESC);  -- Composite

-- Table: processed_messages (for idempotent message processing)
CREATE TABLE processed_messages (
    id BIGSERIAL PRIMARY KEY,
    message_id VARCHAR(255) NOT NULL UNIQUE,  -- application_id + topic + partition + offset
    topic_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_processed_messages_id ON processed_messages(message_id);
CREATE INDEX idx_processed_messages_processed_at ON processed_messages(processed_at DESC);

-- Table: outbox_events (for transactional outbox pattern)
CREATE TABLE outbox_events (
    id BIGSERIAL PRIMARY KEY,
    aggregate_id UUID NOT NULL,  -- application_id
    aggregate_type VARCHAR(50) NOT NULL,  -- 'APPLICATION'
    event_type VARCHAR(100) NOT NULL,  -- 'ApplicationSubmitted', 'CreditReportGenerated'
    payload JSONB NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at TIMESTAMP
);

CREATE INDEX idx_outbox_unpublished ON outbox_events(published, created_at) WHERE published = FALSE;
CREATE INDEX idx_outbox_aggregate ON outbox_events(aggregate_id);

-- Trigger for updated_at and version increment
CREATE OR REPLACE FUNCTION update_updated_at_and_version()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_applications_metadata
    BEFORE UPDATE ON applications
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_and_version();
```

**Data Consistency Strategy**:

1. **Optimistic Locking**: Version column on applications table prevents concurrent update conflicts
2. **Idempotent Processing**: processed_messages table tracks consumed Kafka messages to prevent duplicate processing
3. **Transactional Outbox**: outbox_events table ensures reliable message publishing with database transactions
4. **Duplicate Prevention**: Unique index on pan_number_hash prevents duplicate applications within 24 hours

**Encryption Strategy**:

1. **At-Rest Encryption**:
   - PAN numbers encrypted using AES-256-GCM with application-level encryption
   - Stored as BYTEA in PostgreSQL (pan_number_encrypted column)
   - Encryption key stored as environment variable (future: use key management service)

2. **In-Transit Encryption (Kafka)**:
   - PAN encrypted before publishing to Kafka topics
   - Messages contain encrypted PAN, not plaintext
   - Consumers decrypt PAN when processing (audit logged)
   - Maintains end-to-end encryption from API → Kafka → Consumer

3. **Hashing for Lookups**:
   - PAN hash (SHA-256) stored separately (pan_number_hash column)
   - Enables duplicate detection without decryption
   - Used for unique constraint enforcement

4. **Decryption Policy**:
   - Decryption only when necessary for processing
   - All decrypt operations audit logged
   - Masked PAN (XXXXX1234F) in API responses

### 5.2 API Design

**Pydantic Models**:

**Request Models**:
- `ApplicationCreateRequest`:
  - pan_number: str (10 characters, validated with regex ^[A-Z]{5}[0-9]{4}[A-Z]{1}$)
  - applicant_name: str (max 255 characters)
  - monthly_income_inr: Decimal (positive, max 12 digits)
  - loan_amount_inr: Decimal (positive, max 12 digits)
  - loan_type: Enum[PERSONAL, HOME, AUTO]

**Response Models**:
- `ApplicationCreateResponse`:
  - application_id: UUID
  - status: str (PENDING)
  - created_at: datetime
  - request_id: str (for correlation)

- `ApplicationStatusResponse`:
  - application_id: UUID
  - status: str (PENDING | PRE_APPROVED | REJECTED | MANUAL_REVIEW)
  - cibil_score: Optional[int] (300-900, null if PENDING)
  - pan_number_masked: str (XXXXX1234F)
  - updated_at: datetime
  - request_id: str

- `ErrorResponse`:
  - error_code: str (machine-readable, e.g., "INVALID_PAN_FORMAT")
  - message: str (human-readable description)
  - details: Optional[Dict[str, Any]] (field-level validation errors)
  - request_id: str (for support correlation)
  - timestamp: datetime
  - path: str (request path that failed)

**Standard Error Codes**:
- `INVALID_PAN_FORMAT`: PAN must be 10 characters (5 letters, 4 digits, 1 letter)
- `NEGATIVE_AMOUNT`: Income and loan amount must be positive values
- `INVALID_LOAN_TYPE`: Loan type must be PERSONAL, HOME, or AUTO
- `APPLICATION_NOT_FOUND`: Application ID does not exist in system
- `DUPLICATE_APPLICATION`: Application with same PAN submitted within 24 hours
- `SERVICE_UNAVAILABLE`: Database or Kafka temporarily unavailable
- `DATABASE_ERROR`: Database operation failed
- `KAFKA_PUBLISH_ERROR`: Failed to publish event to message broker

**Endpoints**:

**POST /applications**
- Request Body: ApplicationCreateRequest
- Response: 202 Accepted, ApplicationCreateResponse
- Error Responses:
  - 422: Validation error (invalid PAN, negative amounts)
  - 503: Service unavailable (DB/Kafka down)

**GET /applications/{application_id}/status**
- Path Parameter: application_id (UUID)
- Response: 200 OK, ApplicationStatusResponse
- PAN masking: Return masked PAN (XXXXX1234F) in response
- Error Responses:
  - 404: Application not found
  - 503: Service unavailable

**GET /health**
- Response: 200 OK, {"status": "healthy"}
- Checks: Basic service running

**GET /ready**
- Response: 200 OK if all dependencies available, 503 otherwise
- Checks: PostgreSQL connection, Kafka producer connection

**GET /metrics**
- Response: Prometheus metrics in text format
- Metrics: http_requests_total, http_request_duration_seconds, kafka_messages_published_total, db_connections_active

### 5.3 Service Layer Design

**prequal-api Service Layers**:

1. **Router Layer** (FastAPI routes)
   - Handle HTTP request/response
   - Input validation via Pydantic
   - Exception handling

2. **Service Layer** (Business logic)
   - ApplicationService.create_application() **[Transactional Outbox Pattern]**
     - Begin database transaction
     - Encrypt PAN using EncryptionService
     - Generate PAN hash for duplicate detection
     - Check for duplicate using pan_number_hash (unique constraint)
     - Save application to database (status: PENDING)
     - Create outbox_event record with encrypted PAN payload
     - Log audit entry (action: WRITE)
     - Commit transaction
     - Return application_id and status
     - **Note**: Separate background process publishes from outbox to Kafka

   - ApplicationService.get_application_status()
     - Fetch application from database by ID
     - Decrypt PAN if needed (audit logged)
     - Mask PAN in response (XXXXX1234F)
     - Log audit entry (action: READ)
     - Return status with request_id for correlation

3. **Repository Layer** (Data access)
   - ApplicationRepository.save(application) - Insert with optimistic lock version=1
   - ApplicationRepository.find_by_id(id) - SELECT with version for optimistic locking
   - ApplicationRepository.update_status(id, status, expected_version) - UPDATE with WHERE version check
   - OutboxRepository.create_event(aggregate_id, event_type, payload)
   - AuditLogRepository.log_access(app_id, service_name, action)

4. **Outbox Publisher** (Background Process)
   - OutboxPublisher.poll_and_publish()
     - Query unpublished events (WHERE published = FALSE ORDER BY created_at)
     - For each event: publish to Kafka with encrypted PAN
     - Mark event as published (UPDATE published = TRUE, published_at = NOW())
     - Runs every 100ms to maintain low latency
     - Uses database transaction for each batch

5. **Kafka Producer Wrapper**
   - KafkaProducer.publish(topic, message)
     - Serialize message (encrypted PAN included)
     - Retry logic with exponential backoff (3 attempts)
     - Circuit breaker pattern (5 failures → open, 30s timeout)
     - Return success/failure status

6. **Encryption Service**
   - EncryptionService.encrypt_pan(pan_plaintext) → bytes
   - EncryptionService.decrypt_pan(pan_encrypted) → str (audit logged)
   - EncryptionService.hash_pan(pan_plaintext) → str (SHA-256)
   - Uses AES-256-GCM authenticated encryption

**credit-service Service Layers**:

1. **Kafka Consumer** **[Idempotent Processing]**
   - Subscribe to `loan_applications_submitted` topic
   - For each message:
     - Generate message_id: f"{application_id}:{topic}:{partition}:{offset}"
     - Check processed_messages table for duplicate
     - If already processed: skip and commit offset
     - If new: proceed to processing
   - Deserialize message (decrypt PAN if needed for processing)
   - Error handling: retry 3 times, then send to DLQ

2. **CIBIL Simulation Service**
   - CibilService.calculate_score(application_data) **[Deterministic]**
     - Decrypt PAN (audit logged)
     - Check test PAN mappings (ABCDE1234F → 790, FGHIJ5678K → 610)
     - Apply default logic: base 650 + income adjustments + loan type adjustments
     - Add random variation (-5 to +5) using seeded random (application_id as seed for consistency)
     - Cap between 300-900
     - Return CIBIL score

3. **Kafka Producer & Transaction**
   - Begin database transaction
   - Insert into processed_messages (message_id, topic, processed_at)
   - Publish to `credit_reports_generated` with encrypted PAN
   - Commit Kafka offset
   - Commit database transaction
   - **Note**: If publish fails, entire transaction rolls back and message reprocessed

**decision-service Service Layers**:

1. **Kafka Consumer** **[Idempotent Processing]**
   - Subscribe to `credit_reports_generated` topic
   - For each message:
     - Generate message_id: f"{application_id}:{topic}:{partition}:{offset}"
     - Check processed_messages table for duplicate
     - If already processed: skip and commit offset
     - If new: proceed to processing
   - Deserialize message (decrypt PAN if needed)
   - Error handling: retry 3 times, then send to DLQ

2. **Decision Engine Service**
   - DecisionService.evaluate(application_data, cibil_score) **[Business Rules]**
     - Rule 1: If cibil_score < 650 → REJECTED
     - Rule 2: If cibil_score >= 650 AND monthly_income > (loan_amount / 48) → PRE_APPROVED
     - Rule 3: If cibil_score >= 650 AND monthly_income <= (loan_amount / 48) → MANUAL_REVIEW
     - Return final status

3. **Repository Layer & Transaction** **[Optimistic Locking]**
   - Begin database transaction
   - ApplicationRepository.update_status_with_version(app_id, status, cibil_score, expected_version)
     - UPDATE applications SET status = ?, cibil_score = ?, version = version + 1
     - WHERE id = ? AND version = expected_version
     - If affected rows = 0: optimistic lock conflict (retry or log)
   - Insert into processed_messages (message_id, topic, processed_at)
   - AuditLogRepository.log_access(app_id, 'decision-service', 'UPDATE')
   - Commit Kafka offset
   - Commit database transaction

### 5.4 Integration Points

**Kafka Topics Configuration**:

1. **loan_applications_submitted**
   - Partitions: 3 (for parallel processing)
   - Replication Factor: 1 (local dev), 3 (production)
   - Retention: 7 days
   - Compression: lz4 (for encrypted binary data)
   - Message Schema:
     ```json
     {
       "application_id": "uuid",
       "pan_number_encrypted": "base64-encoded-bytes",  // AES-256-GCM encrypted
       "pan_number_hash": "string",  // SHA-256 hash for correlation
       "applicant_name": "string",
       "monthly_income_inr": "decimal",
       "loan_amount_inr": "decimal",
       "loan_type": "string",
       "created_at": "timestamp",
       "message_version": "v1"  // For schema evolution
     }
     ```
   - **Security Note**: PAN encrypted before publishing, consumers decrypt when processing

2. **credit_reports_generated**
   - Partitions: 3
   - Replication Factor: 1 (local), 3 (prod)
   - Retention: 7 days
   - Compression: lz4
   - Message Schema:
     ```json
     {
       "application_id": "uuid",
       "pan_number_encrypted": "base64-encoded-bytes",  // AES-256-GCM encrypted
       "pan_number_hash": "string",  // SHA-256 hash
       "cibil_score": "integer",
       "monthly_income_inr": "decimal",
       "loan_amount_inr": "decimal",
       "loan_type": "string",
       "generated_at": "timestamp",
       "message_version": "v1"
     }
     ```
   - **Security Note**: PAN remains encrypted throughout the pipeline

3. **loan_applications_submitted_dlq** (Dead Letter Queue)
   - For messages that fail processing in credit-service after max retries
   - Manual intervention required

4. **credit_reports_generated_dlq** (Dead Letter Queue)
   - For messages that fail processing in decision-service after max retries

**Kafka Consumer Configuration**:
- Consumer Group IDs: `credit-service-group`, `decision-service-group`
- Auto Commit: False (manual commit after successful processing)
- Max Poll Records: 10
- Session Timeout: 30s
- Retry Policy: 3 attempts with exponential backoff (1s, 2s, 4s)
- Error Handling: Send to DLQ after max retries

**Database Connection Pooling**:
- Pool Size: Min 5, Max 20 connections per service
- Connection Timeout: 10s
- Idle Timeout: 600s (10 minutes)
- Health Check: Every 30s

**Circuit Breaker Configuration**:
- Failure Threshold: 5 consecutive failures
- Timeout: 30s (half-open state)
- Success Threshold: 2 consecutive successes to close
- Applied to: Database connections, Kafka producer

## 6. Implementation Plan

### 6.1 Dependencies

**Technical Dependencies**:
- Python 3.10+
- FastAPI 0.104+
- Pydantic 2.0+
- SQLAlchemy 2.0+
- psycopg2-binary (PostgreSQL driver)
- confluent-kafka-python (Kafka client)
- cryptography (for AES encryption)
- pytest 7.0+
- pytest-cov
- ruff, black (code quality)
- prometheus-client (metrics)
- uvicorn (ASGI server)

**Infrastructure Dependencies**:
- PostgreSQL 15+
- Kafka 3.5+ with Zookeeper
- Docker & Docker Compose
- Prometheus
- Grafana

**Implementation Order** (Updated for v2.0):

**Phase 1: Foundation & Infrastructure** (Week 1)
- Setup PostgreSQL with corrected schema (applications, audit_log, processed_messages, outbox_events)
- Setup Kafka with 3 topics + 2 DLQ topics
- Configure docker-compose with all services
- Implement database migrations (Alembic)
- Create EncryptionService (AES-256-GCM) with unit tests

**Phase 2: prequal-api Core** (Week 2)
- Implement POST /applications with transactional outbox pattern
- Implement GET /applications/{id}/status with PAN masking
- Implement health (/health, /ready) and metrics (/metrics) endpoints
- Add duplicate detection (24-hour unique constraint)
- Comprehensive unit tests (95% coverage target)
- Error handling with standard error codes

**Phase 3: Outbox Publisher & Kafka Integration** (Week 2-3)
- Implement OutboxPublisher background process (polls every 100ms)
- Publish to loan_applications_submitted with encrypted PAN
- Add circuit breaker for Kafka producer
- Integration tests with real Kafka

**Phase 4: credit-service** (Week 3)
- Implement idempotent Kafka consumer
- Implement CIBIL simulation with deterministic seeded random
- Transactional message processing (DB + Kafka offset commit)
- Publish to credit_reports_generated with encrypted PAN
- Unit tests for CIBIL logic (test PANs, default logic, edge cases)
- Integration tests with Kafka and PostgreSQL

**Phase 5: decision-service** (Week 4)
- Implement idempotent Kafka consumer
- Implement decision engine with business rules
- Optimistic locking for status updates (version check)
- Audit logging for all updates
- Unit tests for decision rules (all 3 outcomes)
- Integration tests with database

**Phase 6: End-to-End Testing** (Week 4-5)
- E2E tests: POST → PENDING → PRE_APPROVED flow
- E2E tests: REJECTED and MANUAL_REVIEW scenarios
- Duplicate application prevention tests
- Idempotency tests (reprocess same Kafka message)
- Optimistic lock conflict tests
- Performance/load tests (10K apps/day, 50/min burst)

**Phase 7: Observability & Production Readiness** (Week 5)
- Setup Prometheus metrics for all services
- Create 4 Grafana dashboards (API, Kafka, Database, Business)
- Configure alerting rules (critical and warning)
- Structured JSON logging across all services
- DLQ monitoring and manual intervention procedures
- Runbook documentation

### 6.2 Environment Configuration

**Environment Variables** (per service):
- `DATABASE_URL`: PostgreSQL connection string
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses
- `ENCRYPTION_KEY`: AES encryption key (32 bytes, base64 encoded)
- `LOG_LEVEL`: INFO, DEBUG, ERROR
- `PROMETHEUS_PORT`: Metrics endpoint port
- `SERVICE_NAME`: For audit logging

## 7. Testing Strategy

### 7.1 Unit Tests (Pytest)

**prequal-api**:
- Test Pydantic model validation (invalid PAN, negative amounts)
- Test EncryptionService (encrypt/decrypt/hash)
- Test ApplicationService with mocked repository and Kafka
- Test PAN masking logic

**credit-service**:
- Test CIBIL simulation logic with test PANs
- Test default calculation logic (income/loan type adjustments)
- Test score capping (300-900)
- Mock Kafka consumer/producer

**decision-service**:
- Test decision rules (all three outcomes)
- Test edge cases (exactly 650 score, exact income ratio)
- Mock Kafka consumer and repository

**Target Coverage**: 95%+ for business logic modules

### 7.2 Integration Tests (Pytest + Docker)

**API Integration Tests**:
- Test POST /applications with real PostgreSQL
- Verify encrypted PAN storage
- Verify Kafka message published
- Test GET /applications/{id}/status retrieval

**Kafka Integration Tests**:
- Test credit-service consumes and produces messages
- Test decision-service consumes and updates database
- Test message serialization/deserialization

**Database Integration Tests**:
- Test connection pooling under load
- Test transaction rollback on errors
- Test database triggers (updated_at)

**Target Coverage**: 85%+ overall

### 7.3 End-to-End Tests (Pytest)

**Scenario 1: Successful Prequalification**
1. POST application with high income, good test PAN
2. Poll GET /status until status changes from PENDING
3. Verify final status is PRE_APPROVED
4. Verify CIBIL score is populated

**Scenario 2: Rejected Application**
1. POST application with low-income test PAN
2. Poll GET /status
3. Verify final status is REJECTED

**Scenario 3: Manual Review**
1. POST application with good score but insufficient income ratio
2. Verify final status is MANUAL_REVIEW

**Scenario 4: Error Handling**
- Test with invalid PAN format (expect 422)
- Test with non-existent application_id (expect 404)

### 7.4 Performance Tests

**Load Test**:
- Tool: Locust or pytest-benchmark
- Target: 10,000 applications/day (~7/min sustained)
- Verify API response times < 500ms (p95)
- Verify end-to-end processing < 2s

**Stress Test**:
- Simulate 50 applications/min burst
- Monitor Kafka lag, database connection pool
- Verify no message loss

## 8. Deployment Considerations

### 8.1 Docker Compose Setup

**Services**:
- prequal-api (build from Dockerfile)
- credit-service (build from Dockerfile)
- decision-service (build from Dockerfile)
- postgres (official image)
- kafka + zookeeper (confluentinc/cp-kafka)
- prometheus (official image)
- grafana (official image)

**Volumes**:
- postgres-data (persist database)
- kafka-data (persist messages)
- prometheus-data (persist metrics)
- grafana-data (persist dashboards)

**Networks**:
- backend-network (all services communicate)

**Health Checks**:
- All services: Docker HEALTHCHECK directive
- Restart policy: on-failure with max 3 retries

### 8.2 Scaling Considerations

**Horizontal Scaling**:
- prequal-api: Scale to N instances behind load balancer
- credit-service: Scale to N instances (Kafka consumer group handles partition assignment)
- decision-service: Scale to N instances (Kafka consumer group)

**Vertical Scaling**:
- Database: Increase connection pool size
- Kafka: Increase partitions for higher throughput

**Bottleneck Mitigation**:
- PostgreSQL: Add read replicas for GET /status queries
- Kafka: Increase partitions from 3 to 6+ for higher parallelism

## 9. Monitoring & Observability

### 9.1 Structured Logging

**Log Format** (JSON):
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "prequal-api",
  "correlation_id": "application_id",
  "message": "Application created",
  "context": {
    "application_id": "uuid",
    "status": "PENDING",
    "loan_type": "PERSONAL"
  }
}
```

**Key Log Events**:
- Application submitted
- Kafka message published/consumed
- Database query executed
- Error occurred (with stack trace)
- PAN accessed (audit log)

### 9.2 Metrics (Prometheus)

**API Metrics**:
- `http_requests_total` (counter): Total requests by endpoint, method, status
- `http_request_duration_seconds` (histogram): Request latency
- `http_requests_in_progress` (gauge): Active requests

**Kafka Metrics**:
- `kafka_messages_published_total` (counter): By topic
- `kafka_messages_consumed_total` (counter): By topic, consumer group
- `kafka_consumer_lag` (gauge): Messages behind
- `kafka_publish_errors_total` (counter)

**Database Metrics**:
- `db_connections_active` (gauge): Active connections
- `db_connections_idle` (gauge): Idle connections
- `db_query_duration_seconds` (histogram): Query latency

**Business Metrics**:
- `applications_submitted_total` (counter)
- `applications_by_status_total` (counter): By status
- `cibil_score_distribution` (histogram)

### 9.3 Grafana Dashboards

**Dashboard 1: API Performance**
- Request rate (requests/sec)
- Error rate (4xx, 5xx)
- Latency (p50, p95, p99)
- Active connections

**Dashboard 2: Kafka Throughput**
- Messages published/consumed per topic
- Consumer lag by group
- DLQ message count
- Processing time per message

**Dashboard 3: Database Health**
- Connection pool utilization
- Query latency
- Active transactions
- Table sizes

**Dashboard 4: Business Insights**
- Applications submitted per hour
- Status distribution (pie chart)
- CIBIL score distribution (histogram)
- Average processing time

### 9.4 Alerting Rules

**Critical Alerts** (PagerDuty/Email):
- API error rate > 5% for 5 minutes
- Kafka consumer lag > 1000 messages for 10 minutes
- Database connection pool exhausted
- Service down (health check failing)

**Warning Alerts** (Slack):
- API latency p95 > 500ms for 5 minutes
- DLQ messages accumulating
- Disk space > 80%

## 10. Security Considerations

### 10.1 Data Protection

**PAN Encryption (End-to-End)**:
- Algorithm: AES-256-GCM (authenticated encryption with AEAD)
- Key Management: Environment variable (v1), future: AWS KMS/HashiCorp Vault
- Key Rotation: Manual (v1), future: automated 90-day rotation
- **At-Rest**: Encrypted BYTEA in PostgreSQL (pan_number_encrypted column)
- **In-Transit**: PAN encrypted in Kafka messages (base64-encoded encrypted bytes)
- **Processing**: Consumers decrypt only when needed for business logic (audit logged)
- **Encryption Points**:
  - API: Encrypts on POST /applications before DB save
  - Outbox Publisher: Publishes already-encrypted PAN to Kafka
  - Consumers: Decrypt for processing, re-encrypt if forwarding

**PAN Masking**:
- API Response: Show only last 4 characters (XXXXX1234F)
- Logs: Never log full PAN, use application_id for correlation
- Audit: Log all decrypt operations

**Database Security**:
- Connection: SSL/TLS enforced (sslmode=require)
- Credentials: Environment variables, never hardcoded
- Least Privilege: Each service has dedicated DB user with minimal permissions

### 10.2 Audit Logging

**Audit Events**:
- PAN encryption (on application creation)
- PAN decryption (if ever needed)
- Status update (by decision-service)
- Application retrieval (GET /status)

**Audit Log Schema**:
- application_id, service_name, action, accessed_at
- Retention: 1 year
- Access: Read-only for auditors

### 10.3 Input Validation

**Pydantic Validators**:
- PAN: Regex `^[A-Z]{5}[0-9]{4}[A-Z]{1}$`
- Income/Amount: Positive decimals, max 12 digits
- Loan Type: Enum (PERSONAL, HOME, AUTO)
- Application ID: Valid UUID format

**SQL Injection Prevention**:
- Use SQLAlchemy ORM (parameterized queries)
- Never construct raw SQL with string concatenation

**API Rate Limiting** (Future):
- Not in v1 scope, but recommended for production

### 10.4 Future Authentication/Authorization

**Recommendations for v2**:
- OAuth2 with JWT tokens
- API keys for service-to-service
- Role-based access control (RBAC)
- Rate limiting per API key

## 11. Risk Assessment

### 11.1 Technical Risks

**Risk 1: Database Bottleneck**
- **Likelihood**: Medium
- **Impact**: High (API timeouts)
- **Mitigation**:
  - Connection pooling (max 20)
  - Indexed queries (id, status, created_at)
  - Read replicas for GET queries
  - Monitoring db_query_duration_seconds

**Risk 2: Kafka Consumer Lag**
- **Likelihood**: Medium (under high load)
- **Impact**: Medium (delayed processing)
- **Mitigation**:
  - Horizontal scaling (consumer groups)
  - Increase partitions to 6+
  - Monitor kafka_consumer_lag
  - Alert if lag > 1000 messages

**Risk 3: Message Loss**
- **Likelihood**: Low
- **Impact**: High (data loss, inconsistent state)
- **Mitigation**:
  - Kafka replication factor 3 (production)
  - Manual commit after successful processing
  - DLQ for failed messages
  - Idempotent message processing

**Risk 4: Encryption Key Compromise**
- **Likelihood**: Low
- **Impact**: Critical (PAN data leak)
- **Mitigation**:
  - Store key in environment variable (v1)
  - Future: Key management service (KMS)
  - Audit all decrypt operations
  - Key rotation capability

**Risk 5: Service Cascading Failures**
- **Likelihood**: Medium
- **Impact**: High (entire system down)
- **Mitigation**:
  - Circuit breaker for DB/Kafka
  - Service isolation (one service failure doesn't affect others)
  - Health checks and auto-restart
  - Graceful degradation (return cached status)

### 11.2 Operational Risks

**Risk 1: Insufficient Monitoring**
- **Mitigation**: Comprehensive Prometheus metrics + Grafana dashboards

**Risk 2: Inadequate Error Handling**
- **Mitigation**: DLQ for failed messages, global exception handlers

**Risk 3: Data Inconsistency**
- **Mitigation**: Database transactions, Kafka manual commit, audit logs

**Risk 4: Performance Degradation**
- **Mitigation**: Load testing before deployment, autoscaling, alerts

## 12. Open Questions

### 12.1 Clarification Needed

1. **Data Retention**: How long should applications be retained in PostgreSQL? (Suggested: 1 year for active, archive older)

2. **CIBIL Score Caching**: Should we cache CIBIL scores for the same PAN? (Suggested: No caching in v1 for simplicity)

3. ~~**Duplicate Applications**: Should we prevent duplicate applications for the same PAN within a time window?~~ **[RESOLVED in v2.0]** - Implemented 24-hour unique constraint on pan_number_hash

4. **Manual Review Process**: What happens to applications marked MANUAL_REVIEW? (Suggested: Out of scope, assume external team handles)

5. **Status Transitions**: Can status ever go backwards (e.g., PRE_APPROVED → MANUAL_REVIEW)? (Assumed: No, status is final with optimistic locking preventing conflicts)

6. ~~**Kafka Message Ordering**: Is strict ordering required per application?~~ **[RESOLVED in v2.0]** - Not required, idempotent processing handles out-of-order messages

7. **Historical Status Tracking**: Should we store status history (PENDING → PRE_APPROVED) or just current status? (Assumed: Just current status in v1, audit_log provides access history)

8. **Load Balancer**: Will prequal-api run behind a load balancer? (Suggested: Not in local dev, but plan for future with sticky sessions for outbox publisher)

### 12.2 Future Enhancements

1. **Authentication & Authorization**: OAuth2, API keys, RBAC
2. **Read Replicas**: For GET /status queries under high load
3. **Caching Layer**: Redis for application status caching
4. **Event Sourcing**: Store all state changes as events
5. **Real CIBIL Integration**: Replace simulation with actual API
6. **Notification Service**: Email/SMS for status updates
7. **Admin Dashboard**: UI for viewing applications, analytics
8. **A/B Testing**: Different decision rules for experimentation

---

## Appendix A: Changes from v1.0 to v2.0

### Database Schema Changes
- Added `version` column to `applications` table for optimistic locking
- Fixed PRIMARY KEY and INDEX syntax (separated into CREATE INDEX statements)
- Added composite indexes for query performance
- Added `processed_messages` table for idempotency
- Added `outbox_events` table for transactional outbox pattern
- Added unique constraint on `pan_number_hash` for 24-hour duplicate prevention
- Updated trigger to increment version on updates

### API Changes
- Added `request_id` to all responses for correlation
- Added `pan_number_masked` to ApplicationStatusResponse
- Defined comprehensive error code catalog (8 standard codes)
- Enhanced error response with timestamp and path

### Service Architecture Changes
- **prequal-api**: Implemented transactional outbox pattern instead of direct Kafka publishing
- **OutboxPublisher**: New background process to publish from outbox to Kafka
- **credit-service**: Added idempotent message processing with processed_messages table
- **decision-service**: Added idempotent message processing and optimistic locking for updates

### Security Changes
- **Critical**: PAN now encrypted in Kafka messages (was plaintext in v1.0)
- End-to-end encryption: API → Database → Kafka → Consumers
- All decrypt operations audit logged

### Kafka Message Schema Changes
- Added `pan_number_encrypted` field (base64-encoded bytes)
- Added `pan_number_hash` field for correlation without decryption
- Added `message_version` field for schema evolution
- Removed plaintext `pan_number` field
- Added lz4 compression for encrypted data

### Testing Changes
- Added idempotency test scenarios
- Added optimistic lock conflict tests
- Added duplicate application prevention tests
- Updated E2E tests to verify encrypted PAN in Kafka

### Implementation Phase Changes
- Restructured into 7 phases over 5 weeks (was 7 phases unspecified duration)
- Phase 1: Added database migration setup (Alembic)
- Phase 3: New phase for outbox publisher implementation
- Phase 6: Expanded E2E testing with new scenarios
- Phase 7: Added DLQ monitoring procedures

---

**Document Version**: 2.0 (Revised)
**Last Updated**: 2024-01-15
**Author**: Technical Architecture Team
**Status**: Ready for Implementation
**Review Status**: All 5 Critical Issues Resolved
