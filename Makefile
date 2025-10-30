.PHONY: install lint format test test-unit test-integration test-e2e coverage clean run-local docker-build docker-up docker-down migrations run-prequal run-credit run-decision

# Installation
install:
	poetry install

# Code Quality
lint:
	poetry run ruff check services/

format:
	poetry run black services/
	poetry run ruff check --fix services/

# Testing
test:
	poetry run pytest

test-unit:
	poetry run pytest -m "not integration and not e2e"

test-integration:
	poetry run pytest -m integration

test-e2e:
	poetry run pytest -m e2e

coverage:
	poetry run pytest --cov=services --cov-report=html --cov-report=term-missing
	@echo "Coverage report generated in htmlcov/index.html"

# Database Migrations
migrations-generate:
	cd infrastructure/postgres && poetry run alembic revision --autogenerate -m "$(message)"

migrations-upgrade:
	cd infrastructure/postgres && poetry run alembic upgrade head

migrations-downgrade:
	cd infrastructure/postgres && poetry run alembic downgrade -1

# Docker
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Local Development
run-local: docker-up migrations-upgrade
	@echo "Infrastructure started. Run services individually:"
	@echo "  make run-prequal        - Run prequal-api service"
	@echo "  make run-credit         - Run credit-service"
	@echo "  make run-decision       - Run decision-service"

# Run Individual Services
run-prequal:
	@./scripts/run_prequal_api.sh

run-credit:
	@./scripts/run_credit_service.sh

run-decision:
	@./scripts/run_decision_service.sh

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf htmlcov/
	rm -rf .coverage

# Help
help:
	@echo "Available commands:"
	@echo "  make install           - Install dependencies with Poetry"
	@echo "  make lint              - Run Ruff linter"
	@echo "  make format            - Format code with Black and auto-fix with Ruff"
	@echo "  make test              - Run all tests"
	@echo "  make test-unit         - Run unit tests only"
	@echo "  make test-integration  - Run integration tests only"
	@echo "  make test-e2e          - Run end-to-end tests"
	@echo "  make coverage          - Generate coverage report"
	@echo "  make docker-build      - Build Docker images"
	@echo "  make docker-up         - Start infrastructure (PostgreSQL, Kafka)"
	@echo "  make docker-down       - Stop infrastructure"
	@echo "  make run-local         - Start infrastructure and prepare for local development"
	@echo "  make run-prequal       - Run prequal-api service (port 8000)"
	@echo "  make run-credit        - Run credit-service (Kafka consumer)"
	@echo "  make run-decision      - Run decision-service (Kafka consumer)"
	@echo "  make clean             - Remove generated files and caches"
