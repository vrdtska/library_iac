#!/bin/bash
# Valida los endpoints del microservicio de autenticacion y guarda la evidencia.
# Prerrequisito: el servicio corriendo en $BASE (por defecto http://localhost:5002)
set -u
BASE="${BASE:-http://localhost:5002}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SALIDA="$DIR/Evidencias"
mkdir -p "$SALIDA"
FECHA=$(date +%Y%m%d-%H%M%S)
EMAIL="prueba_${FECHA}@example.com"
PASS="ClaveSegura1"
COOKIES=$(mktemp)

ejecutar() {
    local nombre="$1"; shift
    local archivo="$SALIDA/${FECHA}-${nombre}.txt"
    {
        echo "### $nombre"
        echo "# $1"
        echo
    } > "$archivo"
    "$@" >> "$archivo" 2>&1
    echo "guardado: $(basename "$archivo")"
}

echo "Validando $BASE ..."
echo

echo "[1/5] GET /health (XML)"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/health" | tee "$SALIDA/$FECHA-1-health-xml.txt"

echo "[2/5] POST /register (XML por defecto)"
curl -s -w '\nHTTP %{http_code}\n' -X POST "$BASE/register" -H 'Content-Type: application/json' \
  -d "{\"nombre\":\"Prueba\",\"apellido_paterno\":\"Automatica\",\"apellido_materno\":\"QA\",\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | tee "$SALIDA/$FECHA-2-register-xml.txt"

echo "[3/5] POST /register?format=json"
curl -s -w '\nHTTP %{http_code}\n' -X POST "$BASE/register?format=json" -H 'Content-Type: application/json' \
  -d "{\"nombre\":\"Prueba\",\"apellido_paterno\":\"Automatica\",\"apellido_materno\":\"QA\",\"email\":\"json_${EMAIL}\",\"password\":\"$PASS\"}" \
  | tee "$SALIDA/$FECHA-3-register-json.txt"

echo "[4/7] POST /login + GET /session (con cookie)"
LOGIN_JSON=$(curl -s -c "$COOKIES" -X POST "$BASE/login?format=json" \
  -H 'Content-Type: application/json' -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
echo "$LOGIN_JSON" | tee "$SALIDA/$FECHA-4-login-session-json.txt"
ACCESS=$(echo "$LOGIN_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))')
REFRESH=$(echo "$LOGIN_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("refresh_token",""))')
{
  echo "--- GET /session con cookie ---"
  curl -s -b "$COOKIES" -w '\nHTTP %{http_code}\n' "$BASE/session"
} | tee -a "$SALIDA/$FECHA-4-login-session-json.txt"

echo "[5/7] POST /logout (revoca refresh_token)"
curl -s -b "$COOKIES" -w '\nHTTP %{http_code}\n' -X POST "$BASE/logout?format=json" \
  -H 'Content-Type: application/json' -d "{\"refresh_token\":\"$REFRESH\"}" \
  | tee "$SALIDA/$FECHA-5-logout-json.txt"

echo "[6/7] POST /refresh con token revocado (debe 401)"
curl -s -w '\nHTTP %{http_code}\n' -X POST "$BASE/refresh?format=json" \
  -H 'Content-Type: application/json' -d "{\"refresh_token\":\"$REFRESH\"}" \
  | tee "$SALIDA/$FECHA-6-refresh-revocado.txt"

echo "[7/7] GET /session con Bearer (via jwt)"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/session?format=json" \
  -H "Authorization: Bearer $ACCESS" \
  | tee "$SALIDA/$FECHA-7-session-bearer.txt"

rm -f "$COOKIES"
echo
echo "Evidencias en: $SALIDA"
