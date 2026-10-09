#!/bin/bash
# Prepara el entorno virtual del microservicio de libros.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -f ".env" ]; then
    echo "ERROR: falta el archivo .env"
    echo "Copiá la plantilla:  cp .env.example .env"
    exit 1
fi

if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    uv pip install --python .venv/bin/python -r requirements.txt
else
    python3 -m venv .venv
    ./.venv/bin/pip install -r requirements.txt
fi

echo ""
echo "Entorno listo. Arrancá el servicio con:  bash run.sh"
