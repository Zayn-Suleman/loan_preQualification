#!/bin/bash

# Script to run the credit-service (Kafka consumer)
# Usage: ./scripts/run_credit_service.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$PROJECT_ROOT/services/credit-service"

echo "=========================================="
echo "Starting Credit Service (Kafka Consumer)"
echo "=========================================="
echo ""
echo "Service Directory: $SERVICE_DIR"
echo "Function: CIBIL Score Calculation"
echo ""

# Check if app/main.py exists
if [ ! -f "$SERVICE_DIR/app/main.py" ]; then
    echo "ERROR: Credit service not implemented yet"
    echo "Expected file: $SERVICE_DIR/app/main.py"
    exit 1
fi

# Check if .env file exists
if [ ! -f "$SERVICE_DIR/.env" ]; then
    echo "ERROR: .env file not found in $SERVICE_DIR"
    echo "Please create a .env file from .env.example"
    exit 1
fi

# Change to service directory
cd "$SERVICE_DIR"

# Load environment variables from .env
if [ -f .env ]; then
    echo "Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | xargs)
fi

# Activate virtual environment if exists, otherwise use poetry
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo "Using virtual environment: $PROJECT_ROOT/.venv"
else
    echo "Using poetry environment"
fi

echo ""
echo "Starting Kafka consumer..."
echo "Topics:"
echo "  - Input: $INPUT_TOPIC"
echo "  - Output: $OUTPUT_TOPIC"
echo "Press Ctrl+C to stop"
echo ""

# Run the credit service
python -m app.main
