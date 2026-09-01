#!/bin/bash

# Script para ejecutar el Microservicio de Libros
# Asegúrate de ejecutar setup.sh primero

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verificar que .env existe
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "ERROR: Archivo .env no encontrado"
    echo "Por favor, copia .env.example a .env y configúralo"
    exit 1
fi

# Activar entorno virtual
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "El entorno virtual no existe. Ejecuta setup.sh primero:"
    echo "  bash setup.sh"
    exit 1
fi

echo "=================================="
echo "Library Books Microservice"
echo "=================================="
echo "Activando entorno virtual..."
source "$PROJECT_DIR/venv/bin/activate"

echo ""
echo "Iniciando servidor Flask..."
echo "Servidor disponible en: http://localhost:5000"
echo "Documentación Swagger: http://localhost:5000/apidocs"
echo ""
echo "Presiona Ctrl+C para detener el servidor"
echo ""

# Ejecutar la aplicación
python "$PROJECT_DIR/app.py"
