#!/bin/bash
export PYTHONPATH=v2/backend
cd v2/backend
../.venv/bin/uvicorn app.main:app --port 8080 &
echo $! > backend.pid
sleep 2
curl -s "http://127.0.0.1:8080/api/v1/health"
