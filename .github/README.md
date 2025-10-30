# GitHub Actions CI/CD Pipeline

This directory contains GitHub Actions workflows for automated CI/CD.

## Workflows

### `ci.yml` - Continuous Integration Pipeline

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

**Jobs:**

#### 1. Lint and Format Check
- Runs Ruff linter on all services
- Checks Black formatting compliance
- Ensures code quality standards

#### 2. Run Tests
- Executes all unit tests:
  - Encryption Service (15 tests)
  - Credit Service (17 tests)
  - Decision Service (18 tests)
- Generates coverage report
- Uploads coverage to Codecov (optional)

#### 3. Security Scan
- Runs Safety check for dependency vulnerabilities
- Identifies known security issues in packages

#### 4. Docker Build Test
- Validates `docker-compose.yml` configuration
- Tests Docker image builds

#### 5. CI Summary
- Provides consolidated status of all jobs

## Local CI/CD (Pre-commit Hooks)

The project uses pre-commit hooks for local development:

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

**Pre-commit checks:**
- Ruff linting
- Black formatting
- Trailing whitespace removal
- YAML/JSON validation
- Large file detection

## Makefile Commands

```bash
make lint       # Run Ruff linter
make format     # Format with Black + Ruff auto-fix
make test       # Run all tests with coverage
make test-unit  # Run unit tests only
```

## Status Badges

Add to your README.md:

```markdown
![CI Pipeline](https://github.com/Zayn-Suleman/loan_preQualification/actions/workflows/ci.yml/badge.svg)
```

## Coverage Reports

Coverage reports are generated on each CI run and can be viewed in:
- GitHub Actions artifacts
- Codecov (if configured)

## Requirements

- Python 3.10+
- Poetry 1.7.0+
- Docker & Docker Compose

## Notes

- All tests must pass before merging
- Code coverage target: 85% overall, 95% for business logic
- Security scans run on every push
