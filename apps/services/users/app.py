"""Microservicio users: administra usuarios, roles, correos y perfiles."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import redis_store  # noqa: E402
from common.auth import exigir_jwt, quien, respuesta_auth  # noqa: E402

load_dotenv()

app = Flask(__name__)
_origenes = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
CORS(app, origins=_origenes or "*")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "library"),
    "user": os.getenv("DB_USER", "library_user"),
    "password": os.getenv("DB_PASSWORD", "library666"),
}
ADMIN_ROLES = {"Administrador"}
ADMIN_IDS = {1}

swagger = Swagger(app, template={
    "swagger": "2.0",
    "info": {"title": "Library Users API", "version": "1.0.0",
             "description": "Administra usuarios, roles, correos y perfiles."},
})


def get_db():
    return psycopg.connect(**DB_CONFIG, row_factory=dict_row)


def es_admin(claims) -> bool:
    if claims.get("rol") in ADMIN_ROLES:
        return True
    try:
        return int(claims.get("role_id")) in ADMIN_IDS
    except (TypeError, ValueError):
        return False


def fila_usuario(cur, id_usuario):
    cur.execute(
        """SELECT u.id_usuario, u.email, u.id_rol, r.nombre_rol AS rol,
                  u.verificado, u.creado_en, p.nombre, p.apellido_paterno,
                  p.apellido_materno
           FROM usuarios u JOIN roles r ON r.id_rol = u.id_rol
           LEFT JOIN perfiles_usuario p ON p.id_usuario = u.id_usuario
           WHERE u.id_usuario = %s""",
        (id_usuario,),
    )
    fila = cur.fetchone()
    if fila and fila.get("creado_en"):
        fila["creado_en"] = fila["creado_en"].isoformat()
    return fila


@app.route("/health", methods=["GET"])
def health():
    """Salud del servicio + postgres + redis (publico)."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        pg = "connected"
    except Exception:  # noqa: BLE001
        pg = "error"
    return jsonify({"service": "users", "postgres": pg,
                    "redis": redis_store.redis_health(),
                    "metricas_redis": redis_store.metricas}), 200


@app.route("/roles", methods=["GET"])
@exigir_jwt()
def listar_roles():
    """Catalogo de roles (requiere JWT)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_rol, nombre_rol FROM roles ORDER BY id_rol")
            return jsonify({"roles": cur.fetchall()}), 200


@app.route("/users", methods=["GET"])
@exigir_jwt()
def listar_usuarios():
    """Lista usuarios (solo admin)."""
    claims = g.jwt_claims
    if not es_admin(claims):
        return respuesta_auth(403, "Se requiere rol Administrador", "insufficient_scope")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT u.id_usuario, u.email, u.id_rol, r.nombre_rol AS rol,
                          u.verificado, p.nombre, p.apellido_paterno, p.apellido_materno
                   FROM usuarios u JOIN roles r ON r.id_rol = u.id_rol
                   LEFT JOIN perfiles_usuario p ON p.id_usuario = u.id_usuario
                   ORDER BY u.id_usuario"""
            )
            return jsonify({"usuarios": cur.fetchall(),
                            "solicitado_por": quien(claims)}), 200


@app.route("/users/<int:id_usuario>", methods=["GET"])
@exigir_jwt()
def obtener_usuario(id_usuario):
    """Detalle de usuario (admin o el propio)."""
    claims = g.jwt_claims
    if not es_admin(claims) and str(claims.get("sub")) != str(id_usuario):
        return respuesta_auth(403, "Solo puedes ver tu propio perfil", "insufficient_scope")
    with get_db() as conn:
        with conn.cursor() as cur:
            fila = fila_usuario(cur, id_usuario)
    if fila is None:
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify(fila), 200



@app.route("/users", methods=["POST"])
@exigir_jwt()
def crear_usuario():
    """Crea cuenta + perfil (solo admin)."""
    claims = g.jwt_claims
    if not es_admin(claims):
        return respuesta_auth(403, "Se requiere rol Administrador", "insufficient_scope")
    data = request.get_json(silent=True) or {}
    faltan = [c for c in ("email", "password", "nombre", "apellido_paterno",
                          "apellido_materno") if not data.get(c)]
    if faltan:
        return jsonify({"error": "Faltan campos", "campos": faltan}), 400
    if "@" not in str(data["email"]):
        return jsonify({"error": "Correo invalido"}), 400
    rol_id = data.get("id_rol", 2)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id_rol FROM roles WHERE id_rol = %s", (rol_id,))
                if cur.fetchone() is None:
                    return jsonify({"error": f"Rol {rol_id} inexistente"}), 400
                cur.execute(
                    "INSERT INTO usuarios (email, password_hash, id_rol, verificado) "
                    "VALUES (%s, %s, %s, TRUE) RETURNING id_usuario",
                    (data["email"].strip(), generate_password_hash(data["password"]), rol_id),
                )
                nuevo = cur.fetchone()["id_usuario"]
                cur.execute(
                    "INSERT INTO perfiles_usuario (id_usuario, nombre, apellido_paterno,"
                    " apellido_materno) VALUES (%s, %s, %s, %s)",
                    (nuevo, data["nombre"].strip(), data["apellido_paterno"].strip(),
                     data["apellido_materno"].strip()),
                )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            return jsonify({"error": "El correo ya esta registrado"}), 409
        return jsonify({"error": str(exc)}), 500
    return jsonify({"message": "Usuario creado", "id_usuario": nuevo,
                    "creado_por": quien(claims)}), 201


def _actualizar(id_usuario):
    claims = g.jwt_claims
    propio = str(claims.get("sub")) == str(id_usuario)
    if not es_admin(claims) and not propio:
        return respuesta_auth(403, "Solo tu propio perfil", "insufficient_scope")
    data = request.get_json(silent=True) or {}
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id_usuario FROM usuarios WHERE id_usuario = %s",
                            (id_usuario,))
                if cur.fetchone() is None:
                    return jsonify({"error": "Usuario no encontrado"}), 404
                if data.get("email"):
                    cur.execute("UPDATE usuarios SET email = %s WHERE id_usuario = %s",
                                (data["email"].strip(), id_usuario))
                if data.get("password"):
                    cur.execute("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
                                (generate_password_hash(data["password"]), id_usuario))
                if data.get("id_rol") and es_admin(claims):
                    cur.execute("UPDATE usuarios SET id_rol = %s WHERE id_usuario = %s",
                                (data["id_rol"], id_usuario))
                perf = {k: data[k] for k in ("nombre", "apellido_paterno",
                                            "apellido_materno") if data.get(k)}
                if perf:
                    sets = ", ".join(f"{k} = %s" for k in perf)
                    cur.execute(f"UPDATE perfiles_usuario SET {sets} WHERE id_usuario = %s",
                                (*[v.strip() for v in perf.values()], id_usuario))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    return jsonify({"message": "Usuario actualizado", "id_usuario": id_usuario}), 200


@app.route("/users/<int:id_usuario>", methods=["PUT", "PATCH"])
@exigir_jwt()
def actualizar_usuario(id_usuario):
    """Actualiza cuenta/perfil (admin o propio)."""
    return _actualizar(id_usuario)


@app.route("/users/<int:id_usuario>", methods=["DELETE"])
@exigir_jwt()
def eliminar_usuario(id_usuario):
    """Elimina usuario (solo admin; no a si mismo)."""
    claims = g.jwt_claims
    if not es_admin(claims):
        return respuesta_auth(403, "Se requiere rol Administrador", "insufficient_scope")
    if str(claims.get("sub")) == str(id_usuario):
        return jsonify({"error": "No puedes eliminar tu propia cuenta"}), 400
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
            borrados = cur.rowcount
        conn.commit()
    if not borrados:
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify({"message": "Usuario eliminado", "id_usuario": id_usuario}), 200


if __name__ == "__main__":
    puerto = int(os.getenv("FLASK_PORT", "5003"))
    print(f"Microservicio users en http://0.0.0.0:{puerto}")
    app.run(host="0.0.0.0", port=puerto)
