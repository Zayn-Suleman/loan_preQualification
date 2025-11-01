## E2E Tests for Loan Prequalification System

End-to-end tests that verify the complete workflow from application submission to final decision.

### Prerequisites

1. **Docker and Docker Compose** installed
2. **Python 3.10+** with dependencies installed
3. **All infrastructure services running** (PostgreSQL, Kafka, Zookeeper)

### Running E2E Tests

#### 1. Start All Services

```bash
# From project root
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
docker-compose ps

# Check logs if needed
docker-compose logs -f prequal-api
```

#### 2. Run E2E Tests

```bash
# Run all E2E tests
pytest tests/test_e2e_workflow.py -v

# Run specific test class
pytest tests/test_e2e_workflow.py::TestE2EWorkflow -v

# Run single test
pytest tests/test_e2e_workflow.py::TestE2EWorkflow::test_pre_approved_flow -v

# Run with output
pytest tests/test_e2e_workflow.py -v -s
```

#### 3. Stop Services

```bash
docker-compose down
```

### Test Coverage

#### TestE2EWorkflow
- ✅ `test_services_health` - Verify all services are healthy
- ✅ `test_pre_approved_flow` - Complete flow for approved application
- ✅ `test_rejected_flow` - Complete flow for rejected application
- ✅ `test_duplicate_pan` - Duplicate PAN rejection
- ✅ `test_invalid_application_id` - Non-existent application lookup
- ✅ `test_test_pan_deterministic_behavior` - Test PAN consistency

#### TestE2EErrorHandling
- ✅ `test_invalid_pan_format` - Invalid PAN validation
- ✅ `test_underage_applicant` - Age validation

#### TestE2EPerformance
- ✅ `test_api_response_time` - API latency measurement

### Test Flow

Each test follows this pattern:

1. **Submit Application** (POST /applications)
   - Returns 202 Accepted with application_id
   - Application saved to database with PENDING status

2. **Async Processing**
   - Kafka message published to `loan_applications_submitted`
   - credit-service consumes, calculates CIBIL score
   - Kafka message published to `credit_reports_generated`
   - decision-service consumes, applies business rules
   - Database updated with final decision

3. **Poll Status** (GET /applications/{id}/status)
   - Poll every 2 seconds (default)
   - Wait up to 45 seconds for final decision
   - Final status: PRE_APPROVED, REJECTED, or MANUAL_REVIEW

4. **Verify Results**
   - Check application status
   - Verify credit score calculated
   - Verify decision reason provided
   - Check database state matches

### Environment Variables

```bash
# API endpoint (default: http://localhost:8000)
export API_BASE_URL=http://localhost:8000

# Database connection (default: local postgres)
export DATABASE_URL=postgresql://loan_user:loan_password@localhost:5432/loan_prequalification
```

### Troubleshooting

#### Services Not Running
```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs prequal-api
docker-compose logs credit-service
docker-compose logs decision-service
```

#### Tests Timing Out
- Increase timeout in `wait_for_decision()` (default: 45s)
- Check Kafka consumer logs for processing issues
- Verify database connectivity

#### Database Connection Errors
```bash
# Test database connection
docker-compose exec postgres psql -U loan_user -d loan_prequalification -c "SELECT 1"

# Check tables
docker-compose exec postgres psql -U loan_user -d loan_prequalification -c "\dt"
```

#### Kafka Issues
```bash
# Check Kafka topics
docker-compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Check consumer groups
docker-compose exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --list
```

### Test Data

#### Test PANs with Predetermined Scores
- `ABCDE1234F` → 790 (High score, likely approved)
- `FGHIJ5678K` → 610 (Low score, likely rejected)

#### Sample Application
```json
{
  "pan_number": "ABCDE1234F",
  "first_name": "Rajesh",
  "last_name": "Kumar",
  "date_of_birth": "1990-01-15",
  "email": "rajesh.kumar@example.com",
  "phone_number": "9876543210",
  "requested_amount": 500000.00
}
```

### Expected Results

| Scenario | CIBIL Score | Income vs Amount | Expected Status |
|----------|-------------|------------------|----------------|
| Good credit + sufficient income | ≥ 650 | Income > (Amount/48) | PRE_APPROVED |
| Good credit + insufficient income | ≥ 650 | Income ≤ (Amount/48) | MANUAL_REVIEW |
| Poor credit | < 650 | Any | REJECTED |

### CI/CD Integration

E2E tests can be run in CI/CD pipelines:

```yaml
# .github/workflows/ci.yml
e2e-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Start services
      run: docker-compose up -d
    - name: Wait for services
      run: sleep 60
    - name: Run E2E tests
      run: pytest tests/test_e2e_workflow.py -v
    - name: Stop services
      run: docker-compose down
```

### Performance Benchmarks

- **API Response Time**: < 200ms target (< 1000ms acceptable)
- **E2E Processing Time**: 10-30 seconds typical
- **Database Query Time**: < 50ms
- **Kafka Message Latency**: < 100ms
