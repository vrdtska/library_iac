#!/bin/bash
# Arranca el microservicio de libros en el puerto 5001.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

[ -f ".env" ] || { echo "ERROR: falta .env (copialo de .env.example)"; exit 1; }

if [ ! -d ".venv" ]; then
    echo "El entorno virtual no existe. Ejecutá primero:  bash setup.sh"
    exit 1
fi

source .venv/bin/activate
PORT="${FLASK_PORT:-5001}"
echo "Microservicio de libros -> http://0.0.0.0:${PORT}"
echo "Catalogo XML            -> http://localhost:${PORT}/books"
echo "Swagger                 -> http://localhost:${PORT}/apidocs/"
exec python app.py
