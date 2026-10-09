"""Microservicio authors: autores y su relacion con libros."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import redis_store  # noqa: E402
from common.auth import exigir_jwt, quien  # noqa: E402

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
swagger = Swagger(app, template={
    "swagger": "2.0",
    "info": {"title": "Library Authors API", "version": "1.0.0",
             "description": "Autores y su relacion con libros."},
})


def get_db():
    return psycopg.connect(**DB_CONFIG, row_factory=dict_row)


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
    return jsonify({"service": "authors", "postgres": pg,
                    "redis": redis_store.redis_health(),
                    "metricas_redis": redis_store.metricas}), 200


@app.route("/authors", methods=["GET"])
def listar():
    """Lista autores con conteo de libros (publico)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT a.id_autor, a.nombre_autor,
                          COUNT(la.isbn) AS libros
                   FROM autores a LEFT JOIN libro_autor la
                     ON la.id_autor = a.id_autor
                   GROUP BY a.id_autor ORDER BY a.nombre_autor"""
            )
            return jsonify({"autores": cur.fetchall()}), 200


@app.route("/authors/<int:id_autor>", methods=["GET"])
def obtener(id_autor):
    """Detalle de autor (publico)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_autor, nombre_autor FROM autores WHERE id_autor = %s",
                        (id_autor,))
            fila = cur.fetchone()
            if fila is None:
                return jsonify({"error": "Autor no encontrado"}), 404
            return jsonify(fila), 200


@app.route("/authors/<int:id_autor>/books", methods=["GET"])
def libros_de_autor(id_autor):
    """Libros de un autor (publico)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT l.isbn, l.titulo, l.anio, l.precio, l.stock
                     FROM libro_autor la JOIN libros l ON l.isbn = la.isbn
                    WHERE la.id_autor = %s ORDER BY l.titulo""",
                (id_autor,),
            )
            return jsonify({"id_autor": id_autor, "libros": cur.fetchall()}), 200


@app.route("/authors", methods=["POST"])
@exigir_jwt()
def crear():
    """Crea un autor (requiere Bearer)."""
    data = request.get_json(silent=True) or {}
    nombre = str(data.get("nombre_autor", "")).strip()
    if not nombre:
        return jsonify({"error": "nombre_autor requerido"}), 400
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO autores (nombre_autor) VALUES (%s) RETURNING id_autor",
                        (nombre,))
            nuevo = cur.fetchone()["id_autor"]
        conn.commit()
    return jsonify({"message": "Autor creado", "id_autor": nuevo,
                    "creado_por": quien()}), 201


@app.route("/authors/<int:id_autor>", methods=["PUT", "PATCH"])
@exigir_jwt()
def actualizar(id_autor):
    """Actualiza un autor (requiere Bearer)."""
    data = request.get_json(silent=True) or {}
    nombre = str(data.get("nombre_autor", "")).strip()
    if not nombre:
        return jsonify({"error": "nombre_autor requerido"}), 400
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE autores SET nombre_autor = %s WHERE id_autor = %s",
                        (nombre, id_autor))
            if not cur.rowcount:
                return jsonify({"error": "Autor no encontrado"}), 404
        conn.commit()
    return jsonify({"message": "Autor actualizado", "id_autor": id_autor}), 200


@app.route("/authors/<int:id_autor>", methods=["DELETE"])
@exigir_jwt()
def eliminar(id_autor):
    """Elimina un autor (requiere Bearer)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM autores WHERE id_autor = %s", (id_autor,))
            if not cur.rowcount:
                return jsonify({"error": "Autor no encontrado"}), 404
        conn.commit()
    return jsonify({"message": "Autor eliminado", "id_autor": id_autor}), 200


@app.route("/books/<isbn>/authors", methods=["POST"])
@exigir_jwt()
def asignar(isbn):
    """Asigna autores a un libro (requiere Bearer)."""
    data = request.get_json(silent=True) or {}
    ids = data.get("autores") or ([data["id_autor"]] if data.get("id_autor") else [])
    if not ids:
        return jsonify({"error": "autores o id_autor requerido"}), 400
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT isbn FROM libros WHERE isbn = %s", (isbn,))
            if cur.fetchone() is None:
                return jsonify({"error": "Libro no encontrado"}), 404
            for aid in ids:
                cur.execute("SELECT id_autor FROM autores WHERE id_autor = %s", (aid,))
                if cur.fetchone() is None:
                    return jsonify({"error": f"Autor {aid} inexistente"}), 400
                cur.execute("INSERT INTO libro_autor (isbn, id_autor) VALUES (%s, %s)"
                            " ON CONFLICT DO NOTHING", (isbn, aid))
        conn.commit()
    return jsonify({"message": "Autores asignados", "isbn": isbn}), 200


if __name__ == "__main__":
    puerto = int(os.getenv("FLASK_PORT", "5004"))
    print(f"Microservicio authors en http://0.0.0.0:{puerto}")
    app.run(host="0.0.0.0", port=puerto)
