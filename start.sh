#!/usr/bin/env bash
set -e

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-9999}"

# Create .venv and install dependencies
uv sync

# Activate the virtual environment
source .venv/bin/activate

# Start the server
uvicorn main:app --host "$HOST" --port "$PORT"
