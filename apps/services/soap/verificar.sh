#!/bin/bash
# Valida los endpoints del microservicio de libros y guarda la evidencia.
# Prerrequisito: el servicio corriendo en $BASE (por defecto http://localhost:5001)
set -u
BASE="${BASE:-http://localhost:5001}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SALIDA="$DIR/Evidencias"
mkdir -p "$SALIDA"
FECHA=$(date +%Y%m%d-%H%M%S)

echo "Validando $BASE ..."
echo "[1/4] GET /books (XML del catalogo)"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/books?limit=3"          | tee "$SALIDA/$FECHA-1-books-xml.txt" | head -12
echo "[2/4] GET /api/libros/minimo (datos minimos + imagenes)"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/api/libros/minimo?format=json&limit=3" | tee "$SALIDA/$FECHA-2-minimo-json.txt" | head -12
echo "[3/4] GET /api/db-health"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/api/db-health"           | tee "$SALIDA/$FECHA-3-db-health.txt"
echo "[4/7] GET /uploads (portada)"
curl -s -o /dev/null -w 'HTTP %{http_code}  %{content_type}\n' "$BASE/uploads/img_1.svg" | tee "$SALIDA/$FECHA-4-uploads.txt"

# --- Flujo JWT contra el servicio de libros ---
# Requiere: login corriendo en $AUTH (por defecto http://localhost:5002)
# y usuario admin@library.com / Admin123! (ver apps/db/02_seed_30_per_table.sql).
AUTH="${AUTH:-http://localhost:5002}"
echo "[5/7] POST /api/books SIN token (debe 401)"
curl -s -w '\nHTTP %{http_code}\n' -X POST "$BASE/api/books" -H 'Content-Type: application/json' -d '{}' \
  | tee "$SALIDA/$FECHA-5-post-sin-token.txt"

echo "[6/7] login -> POST/PUT/PATCH/DELETE con Bearer (debe 201/200/200/204)"
LOGIN_JSON=$(curl -s -X POST "$AUTH/login?format=json" -H 'Content-Type: application/json' \
  -d '{"email":"admin@library.com","password":"Admin123!"}')
ACCESS=$(echo "$LOGIN_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))')
if [ -z "$ACCESS" ]; then
  echo "No se pudo obtener access_token de $AUTH (¿login caído?)" | tee "$SALIDA/$FECHA-6-crud-bearer.txt"
else
  ISBN="978-999-000-00-0"
  {
    echo "--- POST /api/books ---"
    curl -s -w '\nHTTP %{http_code}\n' -X POST "$BASE/api/books" -H "Authorization: Bearer $ACCESS" \
      -H 'Content-Type: application/json' \
      -d "{\"isbn\":\"$ISBN\",\"titulo\":\"Libro JWT Test\",\"anio\":2024,\"precio\":199.99,\"stock\":5,\"formato\":\"Tapa Blanda\",\"categoria\":\"Novela\"}"
    echo "--- GET /api/books/$ISBN sin token (publico) ---"
    curl -s -o /dev/null -w 'HTTP %{http_code}\n' "$BASE/api/books/$ISBN"
    echo "--- PATCH con Bearer ---"
    curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X PATCH "$BASE/api/books/$ISBN" \
      -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' -d '{"stock":42}'
    echo "--- DELETE con Bearer ---"
    curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X DELETE "$BASE/api/books/$ISBN" \
      -H "Authorization: Bearer $ACCESS"
  } | tee "$SALIDA/$FECHA-6-crud-bearer.txt"
fi

echo "[7/7] POST /refresh (rotacion: 200 y reuso 401)"
REFRESH=$(echo "$LOGIN_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("refresh_token",""))')
if [ -z "$REFRESH" ]; then
  echo "Sin refresh_token; se omite." | tee "$SALIDA/$FECHA-7-refresh.txt"
else
  {
    echo "--- primer uso (debe 200) ---"
    curl -s -w '\nHTTP %{http_code}\n' -X POST "$AUTH/refresh?format=json" \
      -H 'Content-Type: application/json' -d "{\"refresh_token\":\"$REFRESH\"}" | head -c 400; echo
    echo "--- reuso del mismo refresh (debe 401) ---"
    curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST "$AUTH/refresh?format=json" \
      -H 'Content-Type: application/json' -d "{\"refresh_token\":\"$REFRESH\"}"
  } | tee "$SALIDA/$FECHA-7-refresh.txt"
fi
echo
echo "Evidencias en: $SALIDA"
