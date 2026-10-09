"""Capa compartida de Redis para los microservicios de la libreria.

PostgreSQL = fuente principal. Redis aporta sesiones, refresh tokens,
revocacion JWT (jwt:revoked:<jti>) y cache del catalogo.

Regla: lecturas cacheadas -> fail-open; sesion/revocacion -> fail-closed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover
    redis_lib = None  # type: ignore

_cliente = None
_no_disponible = False
metricas = {"hits": 0, "misses": 0, "errores": 0}


def _url() -> str:
    return os.getenv("REDIS_URL", "redis://:999@localhost:6379/0")


def get_redis():
    """Cliente Redis compartido o None si no hay conexion."""
    global _cliente, _no_disponible
    if _cliente is not None:
        return _cliente
    if _no_disponible or redis_lib is None:
        return None
    try:
        _cliente = redis_lib.Redis.from_url(
            _url(),
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "2")),
            socket_timeout=float(os.getenv("REDIS_TIMEOUT", "2")),
            health_check_interval=30,
        )
        _cliente.ping()
        return _cliente
    except Exception as exc:  # noqa: BLE001
        _no_disponible = True
        metricas["errores"] += 1
        log.warning("Redis no disponible (%s); modo degradado.", exc)
        return None


def redis_health() -> str:
    try:
        cliente = get_redis()
        if cliente is None:
            return "down"
        cliente.ping()
        return "connected"
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return "down"


def exigir_redis():
    """(cliente, None) o (None, (body_503, 503)). Fail-closed."""
    cliente = get_redis()
    if cliente is None:
        return None, ({"error": "Servicio de sesiones no disponible", "redis": "down"}, 503)
    try:
        cliente.ping()
        return cliente, None
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return None, ({"error": "Servicio de sesiones no disponible", "redis": "down"}, 503)


def _cli():
    try:
        return get_redis()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Sesiones (sess:<user_id>:<jti>, TTL 20 min) y refresh (refresh:<jti>, 24 h)
# ---------------------------------------------------------------------------
def guardar_sesion(user_id: str, jti: str, datos: dict, ttl: int) -> bool:
    cli = _cli()
    if cli is None:
        return False
    try:
        cli.setex(f"sess:{user_id}:{jti}", ttl, json.dumps(datos))
        return True
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return False


def leer_sesion(user_id: str, jti: str):
    cli = _cli()
    if cli is None:
        return None
    try:
        crudo = cli.get(f"sess:{user_id}:{jti}")
        metricas["hits" if crudo else "misses"] += 1
        return json.loads(crudo) if crudo else None
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return None


def borrar_sesion(user_id: str, jti: str) -> None:
    cli = _cli()
    if cli is None:
        return
    try:
        cli.delete(f"sess:{user_id}:{jti}")
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1


def guardar_refresh(jti: str, user_id: str, ttl: int) -> bool:
    cli = _cli()
    if cli is None:
        return False
    try:
        cli.setex(f"refresh:{jti}", ttl, user_id)
        return True
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return False


def refresh_valido(jti: str) -> bool:
    cli = _cli()
    if cli is None:
        return False
    try:
        existe = cli.exists(f"refresh:{jti}")
        metricas["hits" if existe else "misses"] += 1
        return bool(existe)
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return False


def borrar_refresh(jti: str) -> None:
    cli = _cli()
    if cli is None:
        return
    try:
        cli.delete(f"refresh:{jti}")
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1


# ---------------------------------------------------------------------------
# Revocacion jwt:revoked:<jti> (fail-closed al validar)
# ---------------------------------------------------------------------------
def revocar_jti(jti: str, ttl: int) -> bool:
    cli = _cli()
    if cli is None:
        return False
    try:
        cli.setex(f"jwt:revoked:{jti}", max(1, ttl), "1")
        return True
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return False


def esta_revocado(jti: str):
    """True/False, o None si Redis no responde (fallar cerrado)."""
    cli = _cli()
    if cli is None:
        return None
    try:
        return bool(cli.exists(f"jwt:revoked:{jti}"))
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return None


# ---------------------------------------------------------------------------
# Cache del catalogo (fail-open)
# ---------------------------------------------------------------------------
def clave_lista(filtros: dict) -> str:
    plano = json.dumps(filtros, sort_keys=True, default=str)
    digest = hashlib.sha1(plano.encode()).hexdigest()[:16]
    return f"books:list:{digest}"


def leer_cache(clave: str):
    cli = _cli()
    if cli is None:
        return None
    try:
        crudo = cli.get(clave)
        metricas["hits" if crudo else "misses"] += 1
        return json.loads(crudo) if crudo else None
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1
        return None


def guardar_cache(clave: str, valor: Any, ttl: int) -> None:
    cli = _cli()
    if cli is None:
        return
    try:
        cli.setex(clave, ttl, json.dumps(valor, default=str))
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1


def invalidar_catalogo(isbn: str | None = None) -> None:
    cli = _cli()
    if cli is None:
        return
    try:
        for clave in cli.scan_iter("books:list:*", count=200):
            cli.delete(clave)
        if isbn:
            cli.delete(f"books:{isbn}")
    except Exception:  # noqa: BLE001
        metricas["errores"] += 1

