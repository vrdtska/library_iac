"""Microservicio pedidos: crea y gestiona pedidos, lineas, stock y estados."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from psycopg.rows import dict_row

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
TRANSICIONES = {
    "pendiente": {"pagado", "cancelado"},
    "pagado": {"enviado", "cancelado"},
    "enviado": {"entregado"},
    "entregado": set(),
    "cancelado": set(),
}
ADMIN_ROLES = {"Administrador"}
ADMIN_IDS = {1}
swagger = Swagger(app, template={
    "swagger": "2.0",
    "info": {"title": "Library Pedidos API", "version": "1.0.0",
             "description": "Pedidos, lineas, stock y estados."},
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
    return jsonify({"service": "pedidos", "postgres": pg,
                    "redis": redis_store.redis_health(),
                    "metricas_redis": redis_store.metricas}), 200


def _detalle(cur, id_pedido):
    cur.execute("SELECT * FROM pedidos WHERE id_pedido = %s", (id_pedido,))
    ped = cur.fetchone()
    if ped is None:
        return None
    ped["total"] = float(ped["total"])
    ped["creado_en"] = ped["creado_en"].isoformat()
    cur.execute("SELECT isbn, cantidad, precio_unitario::float AS precio_unitario"
                " FROM pedido_items WHERE id_pedido = %s", (id_pedido,))
    ped["items"] = cur.fetchall()
    return ped


@app.route("/pedidos", methods=["POST"])
@exigir_jwt()
def crear():
    """Crea pedido en pendiente y descuenta stock (requiere Bearer)."""
    claims = g.jwt_claims
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"error": "items requerido: [{isbn, cantidad}]"}), 400
    uid = data.get("id_usuario", claims.get("sub"))
    if not es_admin(claims) and str(uid) != str(claims.get("sub")):
        return respuesta_auth(403, "Solo tus propios pedidos", "insufficient_scope")
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                total = Decimal("0")
                lineas = []
                for it in items:
                    cur.execute("SELECT precio, stock FROM libros WHERE isbn = %s "
                                "FOR UPDATE", (it.get("isbn"),))
                    libro = cur.fetchone()
                    if libro is None:
                        conn.rollback()
                        return jsonify({"error": f"ISBN {it.get('isbn')} inexistente"}), 400
                    cant = int(it.get("cantidad", 0))
                    if cant <= 0 or libro["stock"] < cant:
                        conn.rollback()
                        return jsonify({"error": f"Stock insuficiente {it.get('isbn')}"}), 400
                    total += Decimal(str(libro["precio"])) * cant
                    lineas.append((it["isbn"], cant, libro["precio"]))
                cur.execute("INSERT INTO pedidos (id_usuario, estado, total) "
                            "VALUES (%s, 'pendiente', %s) RETURNING id_pedido",
                            (uid, total))
                pid = cur.fetchone()["id_pedido"]
                for isbn, cant, precio in lineas:
                    cur.execute("INSERT INTO pedido_items (id_pedido, isbn, cantidad,"
                                " precio_unitario) VALUES (%s, %s, %s)",
                                (pid, isbn, cant, precio))
                    cur.execute("UPDATE libros SET stock = stock - %s WHERE isbn = %s",
                                (cant, isbn))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    # El stock cambio: la cache del catalogo debe refrescarse (fail-open)
    for isbn, _c, _p in lineas:
        redis_store.invalidar_catalogo(isbn)
    return jsonify({"message": "Pedido creado", "id_pedido": pid,
                    "total": float(total), "creado_por": quien(claims)}), 201


@app.route("/pedidos", methods=["GET"])
@exigir_jwt()
def listar():
    """Lista pedidos propios (o todos si admin)."""
    claims = g.jwt_claims
    with get_db() as conn:
        with conn.cursor() as cur:
            if es_admin(claims):
                cur.execute("SELECT id_pedido, id_usuario, estado, total::float AS total"
                            " FROM pedidos ORDER BY id_pedido DESC LIMIT 100")
            else:
                cur.execute("SELECT id_pedido, id_usuario, estado, total::float AS total"
                            " FROM pedidos WHERE id_usuario = %s ORDER BY id_pedido DESC",
                            (claims.get("sub"),))
            return jsonify({"pedidos": cur.fetchall()}), 200


@app.route("/pedidos/<int:pid>", methods=["GET"])
@exigir_jwt()
def obtener(pid):
    """Detalle de pedido (propio o admin)."""
    claims = g.jwt_claims
    with get_db() as conn:
        with conn.cursor() as cur:
            ped = _detalle(cur, pid)
    if ped is None:
        return jsonify({"error": "Pedido no encontrado"}), 404
    if not es_admin(claims) and str(ped["id_usuario"]) != str(claims.get("sub")):
        return respuesta_auth(403, "No es tu pedido", "insufficient_scope")
    return jsonify(ped), 200


@app.route("/pedidos/<int:pid>/estado", methods=["PATCH"])
@exigir_jwt()
def cambiar_estado(pid):
    """Avanza el estado segun la maquina permitida."""
    claims = g.jwt_claims
    nuevo = (request.get_json(silent=True) or {}).get("estado", "")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_usuario, estado FROM pedidos WHERE id_pedido=%s", (pid,))
            ped = cur.fetchone()
            if ped is None:
                return jsonify({"error": "Pedido no encontrado"}), 404
            if not es_admin(claims) and str(ped["id_usuario"]) != str(claims.get("sub")):
                return respuesta_auth(403, "No es tu pedido", "insufficient_scope")
            if nuevo not in TRANSICIONES.get(ped["estado"], set()) and not es_admin(claims):
                return jsonify({"error": f"Transicion {ped['estado']}->{nuevo} no permitida",
                                "permitidas": sorted(TRANSICIONES[ped["estado"]])}), 400
            cur.execute("UPDATE pedidos SET estado=%s WHERE id_pedido=%s", (nuevo, pid))
        conn.commit()
    return jsonify({"message": "Estado actualizado", "id_pedido": pid, "estado": nuevo}), 200


@app.route("/pedidos/<int:pid>", methods=["DELETE"])
@exigir_jwt()
def cancelar(pid):
    """Cancela pedido pendiente y devuelve stock."""
    claims = g.jwt_claims
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_usuario, estado FROM pedidos WHERE id_pedido=%s", (pid,))
            ped = cur.fetchone()
            if ped is None:
                return jsonify({"error": "Pedido no encontrado"}), 404
            if not es_admin(claims) and str(ped["id_usuario"]) != str(claims.get("sub")):
                return respuesta_auth(403, "No es tu pedido", "insufficient_scope")
            if ped["estado"] != "pendiente":
                return jsonify({"error": "Solo pendiente se cancela"}), 400
            cur.execute("SELECT isbn, cantidad FROM pedido_items WHERE id_pedido=%s", (pid,))
            isbns = []
            for it in cur.fetchall():
                cur.execute("UPDATE libros SET stock=stock+%s WHERE isbn=%s",
                            (it["cantidad"], it["isbn"]))
                isbns.append(it["isbn"])
            cur.execute("UPDATE pedidos SET estado='cancelado' WHERE id_pedido=%s", (pid,))
        conn.commit()
    for isbn in isbns:
        redis_store.invalidar_catalogo(isbn)
    return jsonify({"message": "Pedido cancelado", "id_pedido": pid}), 200


if __name__ == "__main__":
    puerto = int(os.getenv("FLASK_PORT", "5005"))
    print(f"Microservicio pedidos en http://0.0.0.0:{puerto}")
    app.run(host="0.0.0.0", port=puerto)

