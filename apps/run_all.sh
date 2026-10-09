#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_all.sh - levanta los 6 microservicios de libreria_eg
#
#   login    :5000   auth + JWT (emisor) + Redis sesiones/refresh/revocacion
#   books    :5001   catalogo SOAP/REST + cache Redis del catalogo
#   users    :5003   perfiles de usuario
#   authors  :5004   autores
#   pedidos  :5005   pedidos + stock
#   pagos    :5006   pagos de pedidos
#
# Uso:
#   ./run_all.sh            # arranca todo en background con logs en logs/
#   ./run_all.sh stop       # detiene todo
#   ./run_all.sh status     # estado de los puertos
#
# Requisitos: PostgreSQL con la BD "library" y Redis (REDIS_URL) activos.
# ---------------------------------------------------------------------------
set -u

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$APP_DIR/logs"
PY="${PYTHON:-python3}"
mkdir -p "$LOG_DIR"

SERVICIOS=(login soap users authors pedidos pagos)
# puerto por servicio (coincide con FLASK_PORT de cada .env / default del app)
puerto_de() {
    case "$1" in
        login) echo 5000 ;;
        soap)  echo 5001 ;;
        users) echo 5003 ;;
        authors) echo 5004 ;;
        pedidos) echo 5005 ;;
        pagos) echo 5006 ;;
        *) echo 0 ;;
    esac
}

arrancar() {
    for svc in "${SERVICIOS[@]}"; do
        dir="$APP_DIR/services/$svc"
        puerto="$(puerto_de "$svc")"
        if [ ! -f "$dir/app.py" ]; then
            echo "[AVISO] $svc: no existe $dir/app.py, se omite"
            continue
        fi
        # Si ya escucha en el puerto, no se vuelve a lanzar.
        if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2>/dev/null; then
            exec 3>&- 3<&-
            echo "[OK] $svc ya responde en :$puerto"
            continue
        fi
        ( cd "$dir" && \
          FLASK_PORT="$puerto" "$PY" app.py > "$LOG_DIR/$svc.log" 2>&1 & \
          echo $! > "$LOG_DIR/$svc.pid" )
        echo "[..] $svc arrancando en :$puerto (log: logs/$svc.log)"
    done
    echo
    echo "Esperando a que los servicios respondan..."
    for svc in "${SERVICIOS[@]}"; do
        puerto="$(puerto_de "$svc")"
        ok=""
        for _ in $(seq 1 20); do
            if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2>/dev/null; then
                exec 3>&- 3<&-
                ok=1; break
            fi
            sleep 0.5
        done
        if [ -n "$ok" ]; then
            echo "  [OK]  $svc :$puerto"
        else
            echo "  [??]  $svc :$puerto no responde todavia (ver logs/$svc.log)"
        fi
    done
    echo
    echo "Swagger books : http://localhost:5001/apidocs/"
    echo "Health login  : http://localhost:5000/health?format=json"
}

detener() {
    for svc in "${SERVICIOS[@]}"; do
        pidfile="$LOG_DIR/$svc.pid"
        if [ -f "$pidfile" ]; then
            pid="$(cat "$pidfile")"
            if kill "$pid" 2>/dev/null; then
                echo "[OK] $svc (pid $pid) detenido"
            else
                echo "[--] $svc (pid $pid) ya no corria"
            fi
            rm -f "$pidfile"
        else
            echo "[--] $svc sin pid registrado"
        fi
    done
}

estado() {
    for svc in "${SERVICIOS[@]}"; do
        puerto="$(puerto_de "$svc")"
        if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2>/dev/null; then
            exec 3>&- 3<&-
            echo "[OK]  $svc escuchando en :$puerto"
        else
            echo "[OFF] $svc no escucha en :$puerto"
        fi
    done
}

case "${1:-start}" in
    start) arrancar ;;
    stop)  detener ;;
    status) estado ;;
    *) echo "Uso: $0 [start|stop|status]"; exit 1 ;;
esac
