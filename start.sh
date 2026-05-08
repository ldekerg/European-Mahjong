#!/bin/bash
cd "$(dirname "$0")"
~/.local/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
