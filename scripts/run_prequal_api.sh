#!/bin/bash

# Script to run the prequal-api service
# Usage: ./scripts/run_prequal_api.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$PROJECT_ROOT/services/prequal-api"

echo "=========================================="
echo "Starting Prequal API Service"
echo "=========================================="
echo ""
echo "Service Directory: $SERVICE_DIR"
echo "Port: 8000"
echo "API Docs: http://localhost:8000/docs"
echo ""

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

# Run migrations if needed
echo "Checking database migrations..."
cd "$PROJECT_ROOT/infrastructure/postgres"
if [ -f "alembic.ini" ]; then
    alembic upgrade head || echo "WARNING: Migration failed or not configured"
fi

cd "$SERVICE_DIR"

echo ""
echo "Starting FastAPI server..."
echo "Press Ctrl+C to stop"
echo ""

# Run uvicorn with reload for development
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
