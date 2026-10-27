"""Pruebas de ``common.auth``: verificación JWT compartida por los servicios.

Se arma una mini-app Flask con un endpoint protegido por ``@exigir_jwt`` y se
comprueban: token válido, token ausente (401), token expirado (401), tipo
incorrecto (401), jti revocado (401) y Redis caído -> fail-closed (503).
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Auto-arranque del path: funciona sin importar el directorio de ejecución.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("JWT_SECRET_KEY", "secreto-de-prueba-1234567890-abcdefghijklmnopqrstuvwxyz")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

import jwt as pyjwt  # noqa: E402
from flask import Flask, g, jsonify  # noqa: E402

from common import auth  # noqa: E402

SECRET = os.environ["JWT_SECRET_KEY"]
ALG = "HS256"


def _token(tipo: str = "access", exp_segundos: int = 1200, jti: str = "jti-1",
           rol: str = "Usuario Registrado", role_id: int = 2) -> str:
    ahora = datetime.now(timezone.utc)
    claims = {
        "sub": "7",
        "role_id": role_id,
        "email": "user@library.com",
        "rol": rol,
        "type": tipo,
        "jti": jti,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=exp_segundos),
    }
    return pyjwt.encode(claims, SECRET, algorithm=ALG)


def _app() -> Flask:
    app = Flask(__name__)

    @app.route("/protegido")
    @auth.exigir_jwt()
    def protegido():
        return jsonify({"sub": g.jwt_claims.get("sub")})

    @app.route("/solo-admin")
    @auth.exigir_jwt(roles={"Administrador"})
    def solo_admin():
        return jsonify({"ok": True})

    return app


class AuthJwtTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _app().test_client()
        # Por defecto Redis "responde" y nada está revocado.
        self._orig_rev = auth.esta_revocado
        auth.esta_revocado = lambda jti: False

    def tearDown(self) -> None:
        auth.esta_revocado = self._orig_rev

    def test_token_valido_pasa(self) -> None:
        r = self.client.get("/protegido", headers={"Authorization": f"Bearer {_token()}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["sub"], "7")

    def test_sin_token_401(self) -> None:
        r = self.client.get("/protegido")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error_code"], "missing_token")

    def test_token_expirado_401(self) -> None:
        r = self.client.get("/protegido", headers={"Authorization": f"Bearer {_token(exp_segundos=-10)}"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error_code"], "token_expired")

    def test_tipo_incorrecto_401(self) -> None:
        # Un refresh no debe servir como access.
        r = self.client.get("/protegido", headers={"Authorization": f"Bearer {_token(tipo='refresh')}"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error_code"], "wrong_token_type")

    def test_firma_invalida_401(self) -> None:
        malo = pyjwt.encode({"sub": "7", "type": "access", "jti": "x"}, "otra-clave", algorithm=ALG)
        r = self.client.get("/protegido", headers={"Authorization": f"Bearer {malo}"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error_code"], "invalid_token")

    def test_jti_revocado_401(self) -> None:
        auth.esta_revocado = lambda jti: True
        r = self.client.get("/protegido", headers={"Authorization": f"Bearer {_token()}"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error_code"], "revoked_token")

    def test_redis_caido_503_fail_closed(self) -> None:
        # esta_revocado devuelve None => fail-closed, NO se acepta el token.
        auth.esta_revocado = lambda jti: None
        r = self.client.get("/protegido", headers={"Authorization": f"Bearer {_token()}"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["error_code"], "server_error")

    def test_rol_insuficiente_403(self) -> None:
        r = self.client.get("/solo-admin", headers={"Authorization": f"Bearer {_token(rol='Usuario Registrado')}"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error_code"], "insufficient_scope")

    def test_rol_admin_pasa(self) -> None:
        r = self.client.get("/solo-admin", headers={"Authorization": f"Bearer {_token(rol='Administrador', role_id=1)}"})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
