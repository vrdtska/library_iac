#!/bin/bash
# Alternativa con el servidor de desarrollo de Flask (recarga automatica).
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
[ -d ".venv" ] || { echo "Ejecutá primero: bash setup.sh"; exit 1; }
source .venv/bin/activate
export FLASK_APP=app.py
exec flask run --host=0.0.0.0 --port="${FLASK_PORT:-5001}"
