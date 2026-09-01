#!/bin/bash

# Script de instalación y prueba del Microservicio de Libros
# Library Books Microservice Setup Script

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=================================="
echo "Library Books Microservice Setup"
echo "=================================="
echo "Directorio del proyecto: $PROJECT_DIR"
echo ""

# Función para imprimir secciones
print_section() {
    echo ""
    echo ">>> $1"
    echo "=================================="
}

# Verificar Python
print_section "Verificando Python"
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 no está instalado"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✓ Encontrado: $PYTHON_VERSION"

# Verificar pip
print_section "Verificando pip"
if ! command -v pip3 &> /dev/null; then
    echo "ERROR: pip3 no está instalado"
    exit 1
fi
PIP_VERSION=$(pip3 --version)
echo "✓ Encontrado: $PIP_VERSION"

# Verificar archivo .env
print_section "Verificando archivo .env"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "ERROR: Archivo .env no encontrado en $PROJECT_DIR"
    exit 1
fi
echo "✓ Archivo .env encontrado"
echo "Contenido:"
cat "$PROJECT_DIR/.env" | sed 's/DB_PASSWORD=.*/DB_PASSWORD=***HIDDEN***/g'

# Verificar requirements.txt
print_section "Verificando requirements.txt"
if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "ERROR: Archivo requirements.txt no encontrado"
    exit 1
fi
echo "✓ Archivo requirements.txt encontrado"
echo "Dependencias:"
cat "$PROJECT_DIR/requirements.txt"

# Crear entorno virtual
print_section "Creando entorno virtual"
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "El entorno virtual ya existe"
else
    python3 -m venv "$PROJECT_DIR/venv"
    echo "✓ Entorno virtual creado"
fi

# Activar entorno virtual
print_section "Activando entorno virtual"
source "$PROJECT_DIR/venv/bin/activate"
echo "✓ Entorno virtual activado"

# Instalar dependencias
print_section "Instalando dependencias"
pip install --upgrade pip setuptools wheel
pip install -r "$PROJECT_DIR/requirements.txt"
echo "✓ Dependencias instaladas"

# Mostrar versiones instaladas
print_section "Versiones de paquetes instalados"
pip list | grep -E "Flask|psycopg|flasgger|python-dotenv|Flask-CORS" || true

# Verificar que app.py existe
print_section "Verificando archivo app.py"
if [ ! -f "$PROJECT_DIR/app.py" ]; then
    echo "ERROR: Archivo app.py no encontrado"
    exit 1
fi
echo "✓ Archivo app.py encontrado ($(wc -l < "$PROJECT_DIR/app.py") líneas)"

# Validar sintaxis de Python
print_section "Validando sintaxis de app.py"
python3 -m py_compile "$PROJECT_DIR/app.py"
echo "✓ Sintaxis válida"

# Resumen
print_section "Resumen de la instalación"
echo ""
echo "✓ Microservicio listo para usar"
echo ""
echo "Para ejecutar el microservicio:"
echo "  cd $PROJECT_DIR"
echo "  source venv/bin/activate"
echo "  python app.py"
echo ""
echo "Documentación Swagger estará disponible en:"
echo "  http://localhost:5000/apidocs"
echo ""
echo "Health check:"
echo "  curl http://localhost:5000/api/health"
echo ""
echo "Database health check:"
echo "  curl http://localhost:5000/api/db-health"
echo ""
echo "Listar todos los libros:"
echo "  curl http://localhost:5000/api/libros"
echo ""
echo "Deactivar entorno virtual:"
echo "  deactivate"
echo ""
