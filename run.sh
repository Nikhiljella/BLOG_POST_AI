#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
  echo "Warning: .env was not found. Copy .env.example to .env and fill in your keys."
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

. .venv/bin/activate

echo "Installing dependencies..."
python -m pip install -r requirements.txt

python main.py "$@"
