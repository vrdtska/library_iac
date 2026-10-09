"""Verificacion JWT compartida por los 6 microservicios.

El login EMITE; todos los servicios VERIFICAN localmente (firma HS256 con
JWT_SECRET_KEY compartido) + lista de revocacion en Redis (fail-closed).

Claims exigidos: sub (=user_id), role_id, type=access, jti, exp.
"""
from __future__ import annotations

import os
from functools import wraps

import jwt as pyjwt
from flask import g, request

from .redis_store import esta_revocado

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def _secreto() -> str:
    return os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY", "")


def token_de_peticion():
    cabecera = request.headers.get("Authorization", "")
    if not cabecera:
        return None
    partes = cabecera.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1].strip() or None


def verificar_access(token: str):
    """(claims, None) o (None, (mensaje, codigo_error, status))."""
    secreto = _secreto()
    if not secreto:
        return None, ("JWT no configurado en el servidor", "server_error", 503)
    try:
        claims = pyjwt.decode(token, secreto, algorithms=[ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        return None, ("El access_token ha expirado", "token_expired", 401)
    except pyjwt.InvalidTokenError as exc:
        return None, (f"Access_token invalido: {exc}", "invalid_token", 401)
    if claims.get("type") != "access":
        return None, (f"Se requiere access_token (llego '{claims.get('type')}')", "wrong_token_type", 401)
    jti = claims.get("jti", "")
    rev = esta_revocado(jti)
    if rev is None:
        return None, ("Servicio de sesiones no disponible", "server_error", 503)
    if rev:
        return None, ("Token revocado", "revoked_token", 401)
    return claims, None


def respuesta_auth(status: int, mensaje: str, codigo: str):
    from flask import jsonify

    resp = jsonify({"error": mensaje, "error_code": codigo})
    resp.status_code = status
    resp.headers["WWW-Authenticate"] = (
        f'Bearer realm="libreria", error="{codigo}", error_description="{mensaje}"'
    )
    return resp


def exigir_jwt(roles: set[str] | None = None, roles_id: set[int] | None = None):
    """Decorador: Bearer obligatorio + rol autorizado (nombre o id)."""

    def deco(func):
        @wraps(func)
        def inner(*args, **kwargs):
            token = token_de_peticion()
            if not token:
                return respuesta_auth(401, "Falta Authorization: Bearer <access_token>", "missing_token")
            claims, error = verificar_access(token)
            if error:
                mensaje, codigo, status = error
                return respuesta_auth(status, mensaje, codigo)
            if roles and claims.get("rol") not in roles:
                return respuesta_auth(
                    403,
                    f"Rol '{claims.get('rol')}' sin permiso (se requiere {sorted(roles)})",
                    "insufficient_scope",
                )
            if roles_id:
                try:
                    rid = int(claims.get("role_id"))
                except (TypeError, ValueError):
                    rid = None
                if rid not in roles_id:
                    return respuesta_auth(403, "Rol sin permiso para esta operacion", "insufficient_scope")
            g.jwt_claims = claims
            return func(*args, **kwargs)

        return inner

    return deco


def quien(claims=None) -> str:
    claims = claims or getattr(g, "jwt_claims", None) or {}
    return claims.get("email") or str(claims.get("sub") or "desconocido")
