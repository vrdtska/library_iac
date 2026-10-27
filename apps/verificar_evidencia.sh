#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# verificar_evidencia.sh - evidencias curl de TODO el sistema (JWT + Redis)
#
# Recorre: health de los 6 servicios, login (tokens), cache del catalogo
# (X-Cache HIT/MISS + invalidacion), escritura sin token (401), CRUD de
# users/authors/pedidos/pagos con Bearer, y logout + token revocado (401).
#
# Uso:
#   ./apps/run_all.sh start            # levanta los 6 servicios (+PG y Redis)
#   bash apps/verificar_evidencia.sh   # genera Evidencias/evidencia_<ts>.txt
#
# Requisitos: curl, jq (opcional; si no esta, se imprime el cuerpo crudo).
# ---------------------------------------------------------------------------
set -u

BASE_AUTH="http://localhost:5000"
BASE_BOOKS="http://localhost:5001"
BASE_USERS="http://localhost:5003"
BASE_AUTHORS="http://localhost:5004"
BASE_PEDIDOS="http://localhost:5005"
BASE_PAGOS="http://localhost:5006"

EMAIL="admin@library.com"
PASSWORD="Admin123!"

OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/Evidencias"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/evidencia_$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$OUT") 2>&1

hr() { printf '\n===== %s =====\n' "$1"; }

# curl que muestra metodo, URL, codigo HTTP, X-Cache y cuerpo en UNA sola llamada.
req() {
    local metodo="$1" url="$2"; shift 2
    echo "--- $metodo $url $* ---"
    curl -sS -D /tmp/_hdr.txt -o /tmp/_body.txt -w "HTTP %{http_code}\n" -X "$metodo" "$url" "$@"
    echo "X-Cache: $(awk 'tolower($1)=="x-cache:"{print $2}' /tmp/_hdr.txt)"
    if command -v jq >/dev/null 2>&1; then jq . /tmp/_body.txt 2>/dev/null || cat /tmp/_body.txt; else cat /tmp/_body.txt; fi
    echo
}

hr "1. HEALTH de los 6 microservicios (publico)"
for s in "$BASE_AUTH/health?format=json" "$BASE_BOOKS/api/health" \
         "$BASE_USERS/health" "$BASE_AUTHORS/health" "$BASE_PEDIDOS/health" "$BASE_PAGOS/health"; do
    echo "--- GET $s ---"; curl -sS "$s"; echo; echo
done

hr "2. LOGIN -> access_token (20 min) + refresh_token (24 h)"
LOGIN_JSON=$(curl -sS -X POST "$BASE_AUTH/login?format=json" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
echo "$LOGIN_JSON" | (command -v jq >/dev/null 2>&1 && jq . || cat)
ACCESS=$(echo "$LOGIN_JSON" | (command -v jq >/dev/null 2>&1 && jq -r .access_token || sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'))
REFRESH=$(echo "$LOGIN_JSON" | (command -v jq >/dev/null 2>&1 && jq -r .refresh_token || sed -n 's/.*"refresh_token":"\([^"]*\)".*/\1/p'))
echo
if [ -z "${ACCESS:-}" ] || [ "$ACCESS" = "null" ]; then
    echo "[ERROR] No se obtuvo access_token. Revisa credenciales/servicios."; exit 1
fi
AUTH=(-H "Authorization: Bearer $ACCESS")

hr "3. CACHE del catalogo: primer GET = MISS, segundo = HIT (TTL 60s)"
req GET "$BASE_BOOKS/books?format=json"
req GET "$BASE_BOOKS/books?format=json"

hr "4. Escritura SIN token -> 401 (books exige Bearer)"
req POST "$BASE_BOOKS/api/libros" -H "Content-Type: application/json" -d '{"isbn":"978-EV-0001","titulo":"Evidencia"}'

hr "5. USERS :5003 (todo con Bearer; listar/crear exige admin)"
req GET "$BASE_USERS/roles" "${AUTH[@]}"
req GET "$BASE_USERS/users" "${AUTH[@]}"
req POST "$BASE_USERS/users" "${AUTH[@]}" -H "Content-Type: application/json" \
    -d '{"email":"evidencia.user@library.com","password":"Evidencia123","nombre":"Evi","apellido_paterno":"User","apellido_materno":"Test","id_rol":2}'

hr "6. AUTHORS :5004 (GET publico; escritura con Bearer)"
req GET "$BASE_AUTHORS/authors"
req POST "$BASE_AUTHORS/authors" "${AUTH[@]}" -H "Content-Type: application/json" -d '{"nombre_autor":"Autor Evidencia"}'

hr "7. PEDIDOS :5005 (crear descuenta stock; todo con Bearer)"
req GET "$BASE_PEDIDOS/pedidos" "${AUTH[@]}"
req POST "$BASE_PEDIDOS/pedidos" "${AUTH[@]}" -H "Content-Type: application/json" \
    -d '{"items":[{"isbn":"978-000-000-01-0","cantidad":1}]}'

hr "8. PAGOS :5006 (registrar pago; todo con Bearer)"
req GET "$BASE_PAGOS/pagos" "${AUTH[@]}"
echo "(Para registrar un pago real usa un id_pedido existente:)  POST $BASE_PAGOS/pagos  {id_pedido,monto,metodo}"

hr "9. INVALIDACION de cache: tras escribir, el GET vuelve a ser MISS"
req POST "$BASE_BOOKS/api/libros" "${AUTH[@]}" -H "Content-Type: application/json" \
    -d '{"isbn":"978-EV-0002","titulo":"Evidencia Cache","anio":2024,"precio":10.5,"stock":3,"formato":"Tapa dura","categoria":"Ficcion"}'
req GET "$BASE_BOOKS/books?format=json"

hr "10. LOGOUT -> revoca refresh y access (jwt:revoked:<jti>)"
req POST "$BASE_AUTH/logout?format=json" -H "Content-Type: application/json" \
    -d "{\"refresh_token\":\"$REFRESH\"}" "${AUTH[@]}"

hr "11. Token REVOCADO -> 401 en books (verificacion de revocacion)"
req POST "$BASE_BOOKS/api/libros" "${AUTH[@]}" -H "Content-Type: application/json" \
    -d '{"isbn":"978-EV-0003","titulo":"No deberia crearse"}'

hr "12. REFRESH con token ya usado/revocado -> 401 (rotacion)"
req POST "$BASE_AUTH/refresh?format=json" -H "Content-Type: application/json" \
    -d "{\"refresh_token\":\"$REFRESH\"}"

echo
echo "[OK] Evidencia guardada en: $OUT"
