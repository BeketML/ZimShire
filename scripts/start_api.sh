#!/bin/sh
set -e

echo "[zimshire] Running Alembic migrations..."
alembic upgrade head

echo "[zimshire] Setting up LangGraph tables (checkpointer + store)..."
python scripts/setup_langgraph_tables.py

echo "[zimshire] Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
