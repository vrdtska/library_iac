"""Microservicio pagos: registra pagos y actualiza el estado del pedido."""
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
ADMIN_ROLES = {"Administrador"}
ADMIN_IDS = {1}
METODOS = {"tarjeta", "efectivo", "transferencia", "oxxo"}
swagger = Swagger(app, template={
    "swagger": "2.0",
    "info": {"title": "Library Pagos API", "version": "1.0.0",
             "description": "Pagos y actualizacion del estado del pedido."},
})


def get_db():
    return psycopg.connect(**DB_CONFIG, row_factory=dict_row)


def es_admin(claims) -> bool:
    if claims.get("rol") in ADMIN_ROLES:
        return True
    try:
        return int(claims.get("role_id") or -1) in ADMIN_IDS
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
    return jsonify({"service": "pagos", "postgres": pg,
                    "redis": redis_store.redis_health(),
                    "metricas_redis": redis_store.metricas}), 200


@app.route("/pagos", methods=["POST"])
@exigir_jwt()
def registrar():
    """Registra un pago; si cubre el total, el pedido pasa a pagado."""
    claims = g.jwt_claims
    data = request.get_json(silent=True) or {}
    try:
        monto = Decimal(str(data.get("monto", "0")))
    except Exception:  # noqa: BLE001
        return jsonify({"error": "monto invalido"}), 400
    if monto <= 0:
        return jsonify({"error": "monto debe ser > 0"}), 400
    metodo = str(data.get("metodo", "tarjeta"))
    if metodo not in METODOS:
        return jsonify({"error": f"metodo invalido", "validos": sorted(METODOS)}), 400
    pid = data.get("id_pedido")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_pedido, id_usuario, estado, total FROM pedidos"
                        " WHERE id_pedido=%s FOR UPDATE", (pid,))
            ped = cur.fetchone()
            if ped is None:
                return jsonify({"error": "Pedido no encontrado"}), 404
            if not es_admin(claims) and str(ped["id_usuario"]) != str(claims.get("sub")):
                return respuesta_auth(403, "No es tu pedido", "insufficient_scope")
            if ped["estado"] == "cancelado":
                return jsonify({"error": "Pedido cancelado"}), 400
            cur.execute("INSERT INTO pagos (id_pedido, monto, metodo) "
                        "VALUES (%s, %s, %s) RETURNING id_pago", (pid, monto, metodo))
            pago = cur.fetchone()["id_pago"]
            cur.execute("SELECT COALESCE(SUM(monto),0) AS s FROM pagos "
                        "WHERE id_pedido=%s AND estado='completado'", (pid,))
            suma = cur.fetchone()["s"]
            nuevo_estado = None
            if suma >= ped["total"] and ped["estado"] == "pendiente":
                cur.execute("UPDATE pedidos SET estado='pagado' WHERE id_pedido=%s", (pid,))
                nuevo_estado = "pagado"
        conn.commit()
    return jsonify({"message": "Pago registrado", "id_pago": pago,
                    "pagado_acumulado": float(suma), "pedido_estado": nuevo_estado or "pendiente",
                    "registrado_por": quien(claims)}), 201


@app.route("/pagos", methods=["GET"])
@exigir_jwt()
def listar():
    """Lista pagos (admin todos; usuario los de sus pedidos)."""
    claims = g.jwt_claims
    with get_db() as conn:
        with conn.cursor() as cur:
            if es_admin(claims):
                cur.execute("SELECT * FROM pagos ORDER BY id_pago DESC LIMIT 100")
            else:
                cur.execute("SELECT g.* FROM pagos g JOIN pedidos p "
                            "ON p.id_pedido=g.id_pedido WHERE p.id_usuario=%s "
                            "ORDER BY g.id_pago DESC", (claims.get("sub"),))
            pagos = cur.fetchall()
    for p in pagos:
        p["monto"] = float(p["monto"])
        p["creado_en"] = p["creado_en"].isoformat()
    return jsonify({"pagos": pagos}), 200


@app.route("/pagos/<int:id_pago>", methods=["GET"])
@exigir_jwt()
def obtener(id_pago):
    """Detalle de pago (propio o admin)."""
    claims = g.jwt_claims
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT g.*, p.id_usuario FROM pagos g JOIN pedidos p "
                        "ON p.id_pedido=g.id_pedido WHERE g.id_pago=%s", (id_pago,))
            pago = cur.fetchone()
    if pago is None:
        return jsonify({"error": "Pago no encontrado"}), 404
    if not es_admin(claims) and str(pago["id_usuario"]) != str(claims.get("sub")):
        return respuesta_auth(403, "No es tu pago", "insufficient_scope")
    pago["monto"] = float(pago["monto"])
    pago["creado_en"] = pago["creado_en"].isoformat()
    return jsonify(pago), 200


@app.route("/pedidos/<int:pid>/pagos", methods=["GET"])
@exigir_jwt()
def por_pedido(pid):
    """Pagos de un pedido (propio o admin)."""
    claims = g.jwt_claims
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_usuario FROM pedidos WHERE id_pedido=%s", (pid,))
            ped = cur.fetchone()
            if ped is None:
                return jsonify({"error": "Pedido no encontrado"}), 404
            if not es_admin(claims) and str(ped["id_usuario"]) != str(claims.get("sub")):
                return respuesta_auth(403, "No es tu pedido", "insufficient_scope")
            cur.execute("SELECT * FROM pagos WHERE id_pedido=%s ORDER BY id_pago", (pid,))
            pagos = cur.fetchall()
    for p in pagos:
        p["monto"] = float(p["monto"])
        p["creado_en"] = p["creado_en"].isoformat()
    return jsonify({"id_pedido": pid, "pagos": pagos}), 200


if __name__ == "__main__":
    puerto = int(os.getenv("FLASK_PORT", "5006"))
    print(f"Microservicio pagos en http://0.0.0.0:{puerto}")
    app.run(host="0.0.0.0", port=puerto)
