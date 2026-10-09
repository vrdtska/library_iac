"""Microservicio de libros de la libreria en linea.

CRUD de libros sobre PostgreSQL (Psycopg 3) con CORS habilitado y
documentacion Swagger. Todas las respuestas admiten negociacion de formato:

    GET /books              -> XML (raiz <library>, <book isbn="...">)
    GET /books?format=json  -> JSON
    ?page=1&limit=8         -> paginacion (carga por peticion)

El XML generado sigue el diseno documentado en apps/services/soap/library.xml:
libro, autores, generos, precio, stock, formato, imagenes y conceptos.
"""

import os
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path

import jwt
import psycopg
import sys
from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask, Response, g, jsonify, request, send_from_directory
from flask_cors import CORS
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import redis_store  # Redis: revocacion JWT + cache catalogo

load_dotenv()

app = Flask(__name__)
# CORS restringido a origenes cliente (CORS_ORIGINS); "*" solo en desarrollo.
_origenes = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
CORS(app, origins=_origenes or "*")

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent          # apps/services/soap
# apps/uploads vive dos niveles arriba de este archivo (apps/services/soap)
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR") or BASE_DIR.parents[1] / "uploads")
CURRENCY = os.getenv("CURRENCY", "USD")
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "8"))
MAX_LIMIT = int(os.getenv("MAX_LIMIT", "100"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "library"),
    "user": os.getenv("DB_USER", "library_user"),
    "password": os.getenv("DB_PASSWORD", "library666"),
}

# ---------------------------------------------------------------------------
# JWT (JSON Web Token)
#
# ESTE servicio es el VERIFICADOR. Comprueba la firma con el secreto
# compartido JWT_SECRET_KEY (mismo valor en los dos .env) y NO hace ninguna
# llamada HTTP al microservicio de login: el token se valida en memoria.
# Asi no se encadena un microservicio detras de la autenticacion y las
# lecturas (GET) siguen siendo publicas.
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Roles admitidos para escribir. Vacio = cualquier usuario autenticado.
JWT_WRITE_ROLES = {
    rol.strip()
    for rol in os.getenv("JWT_WRITE_ROLES", "").split(",")
    if rol.strip()
}
# Metodos que exigen Authorization: Bearer <access_token>.
PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Cache del catalogo (fail-open): lista 60 s, detalle 120 s.
CACHE_LIST_TTL = int(os.getenv("BOOKS_CACHE_LIST_TTL", "60"))
CACHE_ITEM_TTL = int(os.getenv("BOOKS_CACHE_ITEM_TTL", "120"))

swagger = Swagger(
    app,
    template={
        "swagger": "2.0",
        "info": {
            "title": "Library Books API",
            "description": (
                "API REST/XML de libros de la libreria. Soporta ?format=xml|json "
                "(XML por defecto) y paginacion con ?page=&limit=."
            ),
            "version": "2.0.0",
        },
        "basePath": "/",
        "schemes": ["http", "https"],
    },
)


def get_db_connection():
    """Abre conexion a PostgreSQL devolviendo cada fila como diccionario."""
    return psycopg.connect(**DB_CONFIG, row_factory=dict_row)


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------
def serialize(value):
    """Convierte tipos de PostgreSQL a tipos serializables por Flask/JSON."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def serialize_row(row):
    return None if row is None else {k: serialize(v) for k, v in row.items()}


def serialize_rows(rows):
    return [serialize_row(r) for r in rows]


def dict_to_xml(tag, data):
    """Convierte un diccionario (con listas y diccionarios anidados) a XML."""
    root = ET.Element(tag)
    for key, value in data.items():
        if isinstance(value, list):
            container = ET.SubElement(root, str(key))
            for item in value:
                if isinstance(item, dict):
                    container.append(ET.fromstring(dict_to_xml("item", item)))
                else:
                    ET.SubElement(container, "item").text = str(item)
        elif isinstance(value, dict):
            root.append(ET.fromstring(dict_to_xml(str(key), value)))
        else:
            child = ET.SubElement(root, str(key))
            child.text = "" if value is None else str(value)
    return ET.tostring(root, encoding="unicode")


def format_response(data, status_code=200, root="library", xml_str=None):
    """Responde JSON o XML segun ?format=. Sin ?format responde XML."""
    fmt = request.args.get("format", "xml").strip().lower()
    if fmt == "json":
        return jsonify(data), status_code
    cuerpo = xml_str if xml_str is not None else dict_to_xml(root, data)
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + cuerpo,
        status=status_code,
        mimetype="application/xml",
    )


def pagina_solicitada():
    """Normaliza ?page= y ?limit=."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return page, max(1, min(limit, MAX_LIMIT))


def url_absoluta(ruta):
    """Convierte '/uploads/x.svg' en una URL completa usando el host actual."""
    if not ruta:
        return ""
    if ruta.startswith("http://") or ruta.startswith("https://"):
        return ruta
    return request.host_url.rstrip("/") + "/" + ruta.lstrip("/")


# ---------------------------------------------------------------------------
# Proteccion de escrituras con JWT (verificacion LOCAL de la firma)
#
# No hay ninguna llamada HTTP al microservicio de login: este servicio
# comprueba la firma con el secreto compartido y valida caducidad y tipo.
# ---------------------------------------------------------------------------
def token_de_peticion():
    """Extrae el valor de 'Authorization: Bearer <token>'."""
    cabecera = request.headers.get("Authorization", "")
    if not cabecera:
        return None
    partes = cabecera.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1].strip() or None


def respuesta_auth(status, mensaje, codigo="invalid_token"):
    """Devuelve el error respetando ?format= y la cabecera WWW-Authenticate."""
    respuesta = format_response({"error": mensaje, "error_code": codigo}, status)
    if isinstance(respuesta, tuple):
        cuerpo, codigo_http = respuesta
        cuerpo.status_code = codigo_http
        salida = cuerpo
    else:
        salida = respuesta
    salida.headers["WWW-Authenticate"] = (
        f'Bearer realm="escritura_libros", error="{codigo}", error_description="{mensaje}"'
    )
    return salida


@app.before_request
def exigir_jwt_en_escrituras():
    """Protege POST/PUT/PATCH/DELETE. GET/HEAD/OPTIONS quedan publicos."""
    if request.method not in PROTECTED_METHODS:
        return None  # lecturas publicas (catalogo, imagenes, salud)

    if not JWT_SECRET:
        # Falla cerrado: sin secreto no se puede validar nada.
        return respuesta_auth(
            503,
            "El servicio no tiene JWT_SECRET_KEY configurado; no se permiten escrituras.",
            "server_error",
        )

    token = token_de_peticion()
    if not token:
        return respuesta_auth(
            401,
            "Falta la cabecera Authorization: Bearer <access_token>",
            "missing_token",
        )

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return respuesta_auth(401, "El access_token ha expirado", "token_expired")
    except jwt.InvalidTokenError as exc:
        return respuesta_auth(401, f"Access_token invalido: {exc}", "invalid_token")

    if claims.get("type") != "access":
        return respuesta_auth(
            401,
            "Se requiere un access_token",
            "wrong_token_type",
        )

    # Redis: verifica jwt:revoked:<jti> (fail-closed: sin Redis no se escribe)
    revocado = redis_store.esta_revocado(claims.get("jti", ""))
    if revocado is None:
        return respuesta_auth(
            503,
            "Servicio de sesiones no disponible",
            "server_error",
        )
    if revocado:
        return respuesta_auth(401, "Token revocado", "revoked_token")

    if JWT_WRITE_ROLES and claims.get("rol") not in JWT_WRITE_ROLES:
        return respuesta_auth(
            403,
            f"El rol '{claims.get('rol')}' no tiene permisos de escritura "
            f"(se requiere {sorted(JWT_WRITE_ROLES)})",
            "insufficient_scope",
        )

    # Disponible para los handlers (auditoria de quien escribio).
    g.jwt_claims = claims
    return None


def quien_escribio():
    """Identidad del autenticado para las respuestas de escritura."""
    claims = getattr(g, "jwt_claims", None) or {}
    return claims.get("email") or claims.get("sub") or "desconocido"


# ---------------------------------------------------------------------------
# Consultas al esquema real (ver apps/db/01_schema.sql)
# ---------------------------------------------------------------------------
SELECT_LIBROS = """
    SELECT l.isbn,
           l.titulo,
           l.anio,
           l.precio,
           l.stock,
           f.nombre_formato AS formato,
           c.nombre_categoria AS categoria,
           l.creado_en
      FROM libros l
      JOIN formatos   f ON f.id_formato   = l.id_formato
      JOIN categorias c ON c.id_categoria = l.id_categoria
"""


def cargar_relaciones(conn, isbns):
    """Carga autores, generos, imagenes y conceptos de varios libros en una vez.

    Devuelve: {isbn: {"autores": [...], "generos": [...], "imagenes": [...],
                      "conceptos": [...]}}
    """
    resultado = {
        isbn: {"autores": [], "generos": [], "imagenes": [], "conceptos": []}
        for isbn in isbns
    }
    if not isbns:
        return resultado

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT la.isbn, a.nombre_autor
              FROM libro_autor la
              JOIN autores a ON a.id_autor = la.id_autor
             WHERE la.isbn = ANY(%s)
             ORDER BY a.nombre_autor
            """,
            (list(isbns),),
        )
        for fila in cur.fetchall():
            resultado[fila["isbn"]]["autores"].append(fila["nombre_autor"])

        cur.execute(
            """
            SELECT lg.isbn, g.nombre_genero
              FROM libro_genero lg
              JOIN generos g ON g.id_genero = lg.id_genero
             WHERE lg.isbn = ANY(%s)
             ORDER BY g.nombre_genero
            """,
            (list(isbns),),
        )
        for fila in cur.fetchall():
            resultado[fila["isbn"]]["generos"].append(fila["nombre_genero"])

        cur.execute(
            """
            SELECT isbn, file_path, es_portada, texto_alternativo
              FROM libro_imagenes
             WHERE isbn = ANY(%s)
             ORDER BY es_portada DESC, id_imagen
            """,
            (list(isbns),),
        )
        for fila in cur.fetchall():
            resultado[fila["isbn"]]["imagenes"].append(
                {
                    "ruta": fila["file_path"],
                    "url": url_absoluta(fila["file_path"]),
                    "es_portada": bool(fila["es_portada"]),
                    "texto_alternativo": fila["texto_alternativo"] or "",
                }
            )

        cur.execute(
            """
            SELECT lc.isbn, co.termino, lc.definicion_en_libro
              FROM libro_concepto lc
              JOIN conceptos co ON co.id_concepto = lc.id_concepto
             WHERE lc.isbn = ANY(%s)
             ORDER BY co.termino
            """,
            (list(isbns),),
        )
        for fila in cur.fetchall():
            resultado[fila["isbn"]]["conceptos"].append(
                {"termino": fila["termino"], "definicion": fila["definicion_en_libro"]}
            )
    return resultado


def xml_imagenes(parent, imagenes):
    """Anade <images><image url=".." isCover=".." order=".."/></images>."""
    contenedor = ET.SubElement(parent, "images")
    for orden, imagen in enumerate(imagenes, start=1):
        ET.SubElement(
            contenedor,
            "image",
            {
                "url": imagen["url"],
                "path": imagen["ruta"],
                "isCover": "true" if imagen["es_portada"] else "false",
                "order": str(orden),
                "altText": imagen["texto_alternativo"],
            },
        )
    return contenedor


def xml_textos(parent, tag, item_tag, valores):
    contenedor = ET.SubElement(parent, tag)
    for valor in valores:
        ET.SubElement(contenedor, item_tag).text = str(valor)
    return contenedor


def libro_a_xml(book, rel, incluir_conceptos=True, incluir_datos_minimos=False):
    """Construye el elemento <book> del XML del catalogo."""
    elemento = ET.Element("book", {"isbn": str(book["isbn"])})
    ET.SubElement(elemento, "title").text = str(book["titulo"] or "")
    xml_textos(elemento, "authors", "author", rel["autores"])
    ET.SubElement(elemento, "publicationYear").text = str(book["anio"])
    ET.SubElement(
        elemento, "price", {"currency": CURRENCY}
    ).text = f"{book['precio']:.2f}"
    if not incluir_datos_minimos:
        ET.SubElement(elemento, "stock").text = str(book["stock"])
        xml_textos(elemento, "genres", "genre", rel["generos"])
        ET.SubElement(elemento, "format").text = str(book["formato"] or "")
        ET.SubElement(elemento, "category").text = str(book["categoria"] or "")
    xml_imagenes(elemento, rel["imagenes"])
    if incluir_conceptos and rel["conceptos"]:
        contenedor = ET.SubElement(elemento, "concepts")
        for concepto in rel["conceptos"]:
            ET.SubElement(
                contenedor,
                "concept",
                {"name": concepto["termino"], "definition": concepto["definicion"]},
            )
    return elemento


def libro_a_json(book, rel, minimo=False):
    """Version JSON del catalogo (mismos datos que el XML, sin formato)."""
    datos = {
        "isbn": book["isbn"],
        "titulo": book["titulo"],
        "autores": rel["autores"],
        "anio": book["anio"],
        "precio": serialize(book["precio"]),
        "imagenes": rel["imagenes"],
        "portada": next((i["url"] for i in rel["imagenes"] if i["es_portada"]), None),
    }
    if not minimo:
        datos.update(
            {
                "stock": book["stock"],
                "formato": book["formato"],
                "categoria": book["categoria"],
                "generos": rel["generos"],
                "conceptos": rel["conceptos"],
            }
        )
    return datos


# ---------------------------------------------------------------------------
# Endpoints de lectura
# ---------------------------------------------------------------------------
@app.route("/books", methods=["GET"])
@app.route("/api/books", methods=["GET"])   # alias del enunciado
@app.route("/api/libros", methods=["GET"])
def listar_libros():
    """
    Lista el catalogo de libros paginado (XML por defecto)
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
      - name: page
        in: query
        type: integer
        default: 1
      - name: limit
        in: query
        type: integer
        default: 8
    responses:
      200:
        description: Catalogo de libros
      500:
        description: Error de conexion o consulta
    """
    page, limit = pagina_solicitada()
    page, limit = pagina_solicitada()
    fmt = request.args.get("format", "xml").lower()
    # Cache Redis (fail-open): books:list:<hash> TTL 60 s
    cache_key = redis_store.clave_lista({"page": page, "limit": limit, "format": fmt})
    cached = redis_store.leer_cache(cache_key)
    if cached is not None:
        resp = jsonify(cached), 200
        resp[0].headers["X-Cache"] = "HIT"
        return resp
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS total FROM libros")
                total = cur.fetchone()["total"]
                cur.execute(
                    SELECT_LIBROS + " ORDER BY l.titulo LIMIT %s OFFSET %s",
                    (limit, (page - 1) * limit),
                )
                libros = cur.fetchall()
                rel = cargar_relaciones(conn, [b["isbn"] for b in libros])
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error al consultar el catalogo: {exc}"}, 500)

    if request.args.get("format", "xml").lower() == "json":
        cuerpo = {
            "total": total,
            "page": page,
            "limit": limit,
            "libros": [libro_a_json(b, rel[b["isbn"]]) for b in libros],
        }
        redis_store.guardar_cache(cache_key, cuerpo, CACHE_LIST_TTL)
        resp = jsonify(cuerpo), 200
        resp[0].headers["X-Cache"] = "MISS"
        return resp

    raiz = ET.Element("library", {"total": str(total), "page": str(page), "limit": str(limit)})
    for book in libros:
        raiz.append(libro_a_xml(book, rel[book["isbn"]]))
    return format_response(None, 200, xml_str=ET.tostring(raiz, encoding="unicode"))


@app.route("/api/libros/minimo", methods=["GET"])
def listar_libros_minimo():
    """
    Datos minimos de los libros junto con sus imagenes
    ---
    Devuelve por libro: isbn, titulo, autores, anio, precio, stock,
    portada e imagenes. Pensado para el catalogo de la app Electron.
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
      - name: page
        in: query
        type: integer
        default: 1
      - name: limit
        in: query
        type: integer
        default: 8
    responses:
      200:
        description: Catalogo minimo con imagenes
      500:
        description: Error de conexion o consulta
    """
    page, limit = pagina_solicitada()
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS total FROM libros")
                total = cur.fetchone()["total"]
                cur.execute(
                    SELECT_LIBROS + " ORDER BY l.titulo LIMIT %s OFFSET %s",
                    (limit, (page - 1) * limit),
                )
                libros = cur.fetchall()
                rel = cargar_relaciones(conn, [b["isbn"] for b in libros])
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error al consultar el catalogo: {exc}"}, 500)

    if request.args.get("format", "xml").lower() == "json":
        return (
            jsonify(
                {
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "libros": [libro_a_json(b, rel[b["isbn"]], minimo=True) for b in libros],
                }
            ),
            200,
        )

    raiz = ET.Element("library", {"total": str(total), "page": str(page), "limit": str(limit)})
    for book in libros:
        raiz.append(libro_a_xml(book, rel[book["isbn"]], incluir_conceptos=False,
                                 incluir_datos_minimos=False))
    return format_response(None, 200, xml_str=ET.tostring(raiz, encoding="unicode"))


def _obtener_libro(conn, isbn):
    with conn.cursor() as cur:
        cur.execute(SELECT_LIBROS + " WHERE l.isbn = %s", (isbn,))
        return cur.fetchone()


@app.route("/api/libros/isbn/<isbn>", methods=["GET"])
@app.route("/api/libros/<isbn>", methods=["GET"])
@app.route("/api/books/<isbn>", methods=["GET"])   # alias del enunciado
@app.route("/books/<isbn>", methods=["GET"])        # alias del enunciado
def obtener_libro(isbn):
    """
    Obtiene un libro por ISBN con autores, generos, imagenes y conceptos
    ---
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
        example: 978-000-000-01-0
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
    responses:
      200:
        description: Libro encontrado
      404:
        description: Libro no encontrado
    """
    # Cache Redis (fail-open): books:<isbn> solo para JSON
    if request.args.get("format", "xml").lower() == "json":
        hit = redis_store.leer_cache(f"books:{isbn}")
        if hit is not None:
            resp = jsonify(hit), 200
            resp[0].headers["X-Cache"] = "HIT"
            return resp
    try:
        with get_db_connection() as conn:
            book = _obtener_libro(conn, isbn)
            if book is None:
                return format_response({"error": "Libro no encontrado", "isbn": isbn}, 404)
            rel = cargar_relaciones(conn, [isbn])[isbn]
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error al consultar el libro: {exc}"}, 500)

    if request.args.get("format", "xml").lower() == "json":
        cuerpo = libro_a_json(book, rel)
        redis_store.guardar_cache(f"books:{isbn}", cuerpo, CACHE_ITEM_TTL)
        resp = jsonify(cuerpo), 200
        resp[0].headers["X-Cache"] = "MISS"
        return resp
    return format_response(
        None, 200, xml_str=ET.tostring(libro_a_xml(book, rel), encoding="unicode")
    )


@app.route("/api/libros/<isbn>/temas", methods=["GET"])
def obtener_temas(isbn):
    """
    Lista los conceptos definidos para un libro
    ---
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
    responses:
      200:
        description: Conceptos del libro
      404:
        description: Libro no encontrado
    """
    try:
        with get_db_connection() as conn:
            book = _obtener_libro(conn, isbn)
            if book is None:
                return format_response({"error": "Libro no encontrado", "isbn": isbn}, 404)
            rel = cargar_relaciones(conn, [isbn])[isbn]
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error al consultar los temas: {exc}"}, 500)

    if request.args.get("format", "xml").lower() == "json":
        return jsonify({"isbn": isbn, "titulo": book["titulo"], "conceptos": rel["conceptos"]}), 200
    raiz = ET.Element("temas", {"isbn": str(isbn)})
    ET.SubElement(raiz, "titulo").text = str(book["titulo"] or "")
    for concepto in rel["conceptos"]:
        ET.SubElement(raiz, "tema", {"name": concepto["termino"], "definition": concepto["definicion"]})
    return format_response(None, 200, root="temas", xml_str=ET.tostring(raiz, encoding="unicode"))


@app.route("/api/libros/buscar", methods=["GET"])
def buscar_libros():
    """
    Busca libros por atributos del catalogo
    ---
    parameters:
      - name: titulo
        in: query
        type: string
        description: Coincidencia parcial, no distingue mayusculas
      - name: categoria
        in: query
        type: string
        description: Nombre exacto de la categoria
      - name: formato
        in: query
        type: string
        description: Nombre exacto del formato
      - name: anio
        in: query
        type: integer
        description: Anio de publicacion exacto
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: json
    responses:
      200:
        description: Libros que coinciden con el filtro
    """
    filtros, params = [], []
    if request.args.get("titulo"):
        filtros.append("l.titulo ILIKE %s")
        params.append(f"%{request.args['titulo']}%")
    if request.args.get("categoria"):
        filtros.append("c.nombre_categoria ILIKE %s")
        params.append(request.args["categoria"])
    if request.args.get("formato"):
        filtros.append("f.nombre_formato ILIKE %s")
        params.append(request.args["formato"])
    if request.args.get("anio"):
        filtros.append("l.anio = %s")
        params.append(request.args["anio"])
    if request.args.get("stock"):
        filtros.append("l.stock = %s")
        params.append(request.args["stock"])

    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(SELECT_LIBROS + where + " ORDER BY l.titulo", params)
                libros = cur.fetchall()
                rel = cargar_relaciones(conn, [b["isbn"] for b in libros])
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error en la busqueda: {exc}"}, 500)

    if request.args.get("format", "xml").lower() == "xml":
        raiz = ET.Element("library", {"total": str(len(libros))})
        for book in libros:
            raiz.append(libro_a_xml(book, rel[book["isbn"]], incluir_conceptos=False))
        return format_response(None, 200, xml_str=ET.tostring(raiz, encoding="unicode"))
    return jsonify([libro_a_json(b, rel[b["isbn"]], minimo=True) for b in libros]), 200


# ---------------------------------------------------------------------------
# Endpoints de escritura
# ---------------------------------------------------------------------------
def _resolver_id(cur, tabla, columna_nombre, columna_id, valor):
    """Acepta un id numerico o el nombre del catalogo y devuelve el id."""
    if valor is None:
        return None
    if isinstance(valor, int) or str(valor).isdigit():
        return int(valor)
    # 'cur' ya es un cursor (Psycopg 3 no expone .cursor() sobre un cursor):
    # se ejecuta directamente sobre el mismo cursor.
    cur.execute(
        f"SELECT {columna_id} FROM {tabla} WHERE {columna_nombre} ILIKE %s",
        (str(valor).strip(),),
    )
    fila = cur.fetchone()
    if fila is None:
        cur.execute(
            f"INSERT INTO {tabla} ({columna_nombre}) VALUES (%s) RETURNING {columna_id}",
            (str(valor).strip(),),
        )
        return cur.fetchone()[columna_id]
    return fila[columna_id]


def _asignar_autores(cur, isbn, valores):
    for valor in valores or []:
        if isinstance(valor, int) or str(valor).isdigit():
            cur.execute(
                "INSERT INTO libro_autor (isbn, id_autor) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (isbn, int(valor)),
            )
            continue
        cur.execute("SELECT id_autor FROM autores WHERE nombre_autor ILIKE %s", (str(valor).strip(),))
        fila = cur.fetchone()
        if fila is None:
            cur.execute("INSERT INTO autores (nombre_autor) VALUES (%s) RETURNING id_autor",
                        (str(valor).strip(),))
            id_autor = cur.fetchone()["id_autor"]
        else:
            id_autor = fila["id_autor"]
        cur.execute(
            "INSERT INTO libro_autor (isbn, id_autor) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (isbn, id_autor),
        )


def _asignar_generos(cur, isbn, valores):
    for valor in valores or []:
        id_genero = _resolver_id(cur, "generos", "nombre_genero", "id_genero", valor)
        cur.execute(
            "INSERT INTO libro_genero (isbn, id_genero) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (isbn, id_genero),
        )


def _asignar_conceptos(cur, isbn, valores):
    for concepto in valores or []:
        if isinstance(concepto, str):
            termino, definicion = concepto, ""
        else:
            termino = concepto.get("termino") or concepto.get("nombre") or ""
            definicion = concepto.get("definicion") or concepto.get("definicion_en_libro") or ""
        if not termino:
            continue
        id_concepto = _resolver_id(cur, "conceptos", "termino", "id_concepto", termino)
        cur.execute(
            """
            INSERT INTO libro_concepto (isbn, id_concepto, definicion_en_libro)
            VALUES (%s, %s, %s)
            ON CONFLICT (isbn, id_concepto) DO UPDATE SET definicion_en_libro = EXCLUDED.definicion_en_libro
            """,
            (isbn, id_concepto, definicion),
        )


def _asignar_imagenes(cur, isbn, valores):
    for posicion, imagen in enumerate(valores or []):
        if isinstance(imagen, str):
            ruta, es_portada, alt = imagen, posicion == 0, ""
        else:
            ruta = imagen.get("ruta") or imagen.get("file_path") or imagen.get("url") or ""
            es_portada = bool(imagen.get("es_portada", posicion == 0))
            alt = imagen.get("texto_alternativo") or imagen.get("altText") or ""
        if not ruta:
            continue
        if ruta.startswith("http"):
            ruta = "/" + ruta.split("/", 3)[3] if ruta.count("/") > 2 else ruta
        cur.execute(
            "UPDATE libro_imagenes SET es_portada = FALSE WHERE isbn = %s AND es_portada = TRUE",
            (isbn,),
        )
        cur.execute(
            """
            INSERT INTO libro_imagenes (isbn, file_path, es_portada, texto_alternativo)
            VALUES (%s, %s, %s, %s)
            """,
            (isbn, ruta, es_portada, alt),
        )


@app.route("/api/libros", methods=["POST"])
@app.route("/api/books", methods=["POST"])   # alias del enunciado (requiere Bearer)
def crear_libro():
    """
    Crea un libro en el catalogo
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [isbn, titulo, anio, precio, stock, formato, categoria]
          properties:
            isbn: {type: string, example: "978-000-000-99-0"}
            titulo: {type: string, example: Clean Code}
            anio: {type: integer, example: 2008}
            precio: {type: number, example: 450.00}
            stock: {type: integer, example: 12}
            formato: {type: string, example: Tapa Blanda}
            categoria: {type: string, example: Novela}
            autores: {type: array, items: {type: string}}
            generos: {type: array, items: {type: string}}
            conceptos:
              type: array
              items:
                type: object
                properties:
                  termino: {type: string}
                  definicion: {type: string}
            imagenes:
              type: array
              items:
                type: object
                properties:
                  ruta: {type: string, example: "/uploads/img_1.svg"}
                  es_portada: {type: boolean}
                  texto_alternativo: {type: string}
    responses:
      201:
        description: Libro creado
      400:
        description: Faltan campos obligatorios
      409:
        description: El ISBN ya existe
    """
    data = request.get_json(silent=True) or {}
    requeridos = ["isbn", "titulo", "anio", "precio", "stock", "formato", "categoria"]
    faltantes = [c for c in requeridos if data.get(c) in (None, "")]
    if faltantes:
        return format_response({"error": "Faltan campos requeridos", "campos": faltantes}, 400)

    isbn = str(data["isbn"]).strip()
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM libros WHERE isbn = %s", (isbn,))
                if cur.fetchone() is not None:
                    return format_response({"error": "El ISBN ya existe", "isbn": isbn}, 409)
                id_formato = _resolver_id(cur, "formatos", "nombre_formato", "id_formato", data["formato"])
                id_categoria = _resolver_id(cur, "categorias", "nombre_categoria", "id_categoria",
                                            data["categoria"])
                cur.execute(
                    """
                    INSERT INTO libros (isbn, titulo, anio, precio, stock, id_formato, id_categoria)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (isbn, str(data["titulo"]).strip(), int(data["anio"]),
                     float(data["precio"]), int(data["stock"]), id_formato, id_categoria),
                )
                _asignar_autores(cur, isbn, data.get("autores"))
                _asignar_generos(cur, isbn, data.get("generos"))
                _asignar_conceptos(cur, isbn, data.get("conceptos"))
                _asignar_imagenes(cur, isbn, data.get("imagenes"))
            book = _obtener_libro(conn, isbn)
            rel = cargar_relaciones(conn, [isbn])[isbn]
    except psycopg.errors.UniqueViolation:
        return format_response({"error": "El ISBN ya existe", "isbn": isbn}, 409)
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error al crear el libro: {exc}"}, 500)

    redis_store.invalidar_catalogo(isbn)
    return format_response(libro_a_json(book, rel), 201, root="book")


def _actualizar_libro(isbn, parcial):
    data = request.get_json(silent=True) or {}
    if not data:
        return format_response({"error": "No hay campos para actualizar"}, 400)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM libros WHERE isbn = %s", (isbn,))
                if cur.fetchone() is None:
                    return format_response({"error": "Libro no encontrado", "isbn": isbn}, 404)

                asignaciones, params = [], []

                def agregar(campo_sql, columna, conversor=str):
                    if columna in data and data[columna] is not None:
                        asignaciones.append(f"{campo_sql} = %s")
                        params.append(conversor(data[columna]))

                agregar("titulo", "titulo")
                agregar("anio", "anio", int)
                agregar("precio", "precio", float)
                agregar("stock", "stock", int)
                if data.get("formato") is not None:
                    asignaciones.append("id_formato = %s")
                    params.append(_resolver_id(cur, "formatos", "nombre_formato", "id_formato",
                                               data["formato"]))
                if data.get("categoria") is not None:
                    asignaciones.append("id_categoria = %s")
                    params.append(_resolver_id(cur, "categorias", "nombre_categoria", "id_categoria",
                                               data["categoria"]))
                if asignaciones:
                    params.append(isbn)
                    cur.execute(
                        f"UPDATE libros SET {', '.join(asignaciones)} WHERE isbn = %s", params
                    )

                if "autores" in data:
                    cur.execute("DELETE FROM libro_autor WHERE isbn = %s", (isbn,))
                    _asignar_autores(cur, isbn, data["autores"])
                if "generos" in data:
                    cur.execute("DELETE FROM libro_genero WHERE isbn = %s", (isbn,))
                    _asignar_generos(cur, isbn, data["generos"])
                if "conceptos" in data:
                    cur.execute("DELETE FROM libro_concepto WHERE isbn = %s", (isbn,))
                    _asignar_conceptos(cur, isbn, data["conceptos"])
                if "imagenes" in data:
                    cur.execute("DELETE FROM libro_imagenes WHERE isbn = %s", (isbn,))
                    _asignar_imagenes(cur, isbn, data["imagenes"])

            book = _obtener_libro(conn, isbn)
            rel = cargar_relaciones(conn, [isbn])[isbn]
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error al actualizar el libro: {exc}"}, 500)
    redis_store.invalidar_catalogo(isbn)
    return format_response(libro_a_json(book, rel), 200, root="book")


@app.route("/api/libros/<isbn>", methods=["PUT"])
@app.route("/api/books/<isbn>", methods=["PUT"])   # alias del enunciado
def reemplazar_libro(isbn):
    """
    Reemplaza los campos enviados de un libro
    ---
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            titulo: {type: string}
            anio: {type: integer}
            precio: {type: number}
            stock: {type: integer}
            formato: {type: string}
            categoria: {type: string}
            autores: {type: array, items: {type: string}}
            generos: {type: array, items: {type: string}}
            conceptos: {type: array, items: {type: object}}
            imagenes: {type: array, items: {type: object}}
    responses:
      200:
        description: Libro actualizado
      400:
        description: No hay campos para actualizar
      404:
        description: Libro no encontrado
    """
    return _actualizar_libro(isbn, parcial=False)


@app.route("/api/libros/<isbn>", methods=["PATCH"])
@app.route("/api/books/<isbn>", methods=["PATCH"])  # alias del enunciado
def parchear_libro(isbn):
    """
    Actualiza de forma parcial un libro (solo los campos enviados)
    ---
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            stock: {type: integer, example: 25}
    responses:
      200:
        description: Libro actualizado
      404:
        description: Libro no encontrado
    """
    return _actualizar_libro(isbn, parcial=True)


@app.route("/api/libros/<isbn>", methods=["DELETE"])
@app.route("/api/books/<isbn>", methods=["DELETE"])  # alias del enunciado
def eliminar_libro(isbn):
    """
    Elimina un libro del catalogo
    ---
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
    responses:
      204:
        description: Libro eliminado
      404:
        description: Libro no encontrado
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM libros WHERE isbn = %s RETURNING isbn", (isbn,))
                if cur.fetchone() is None:
                    return format_response({"error": "Libro no encontrado", "isbn": isbn}, 404)
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": f"Error al eliminar el libro: {exc}"}, 500)
    redis_store.invalidar_catalogo(isbn)
    return "", 204


# ---------------------------------------------------------------------------
# Imagenes, salud y arranque
# ---------------------------------------------------------------------------
@app.route("/uploads/<path:archivo>", methods=["GET"])
def servir_imagen(archivo):
    """Sirve las imagenes del catalogo (portadas de libro)."""
    return send_from_directory(UPLOADS_DIR, archivo)


@app.route("/api/health", methods=["GET"])
def health():
    """
    Estado del microservicio
    ---
    responses:
      200:
        description: Servicio activo
    """
    return format_response(
        {"status": "ok", "service": "books", "version": "2.0.0", "uploads": str(UPLOADS_DIR),
         "redis": redis_store.redis_health(),
         "cache_ttls": {"lista": CACHE_LIST_TTL, "item": CACHE_ITEM_TTL}}, 200
    )


@app.route("/api/db-health", methods=["GET"])
def db_health():
    """
    Estado del microservicio y su conexion con PostgreSQL
    ---
    responses:
      200:
        description: Base de datos accesible
      500:
        description: Base de datos no accesible
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS total FROM libros")
                total = cur.fetchone()["total"]
        return format_response({"status": "ok", "database": "connected", "libros": total}, 200)
    except Exception as exc:  # noqa: BLE001
        return format_response({"status": "error", "database": "disconnected", "message": str(exc)}, 500)


@app.errorhandler(404)
def no_encontrado(error):
    return format_response({"error": "Endpoint no encontrado", "path": request.path}, 404)


@app.errorhandler(500)
def error_servidor(error):
    return format_response({"error": "Error interno del servidor"}, 500)


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"Microservicio de libros en http://0.0.0.0:{port}  (Swagger: /apidocs/)")
    print(f"Imagenes servidas desde: {UPLOADS_DIR}")
    app.run(host="0.0.0.0", port=port, debug=debug)
