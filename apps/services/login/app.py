"""Microservicio de autenticacion y sesiones de la libreria.

Expone registro, login, logout, refresh (rotacion), consulta de sesion y
salud. Redis guarda la sesion activa (sess:<user>:<jti>), el refresh activo
(refresh:<jti>) y la revocacion JWT (jwt:revoked:<jti>). Regla: sin Redis no
se emiten ni se canjean tokens (fail-closed -> 503).

Persistencia: PostgreSQL con Psycopg 3. Contrasenas solo con hash PBKDF2.
Respuestas en XML (por defecto) o JSON con ?format=json.
"""

import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import psycopg
import requests
from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask, Response, jsonify, request, session
from itsdangerous import BadTimeSignature, SignatureExpired, URLSafeTimedSerializer
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

# Modulo compartido apps/common (Redis + JWT). Funciona tanto si el servicio
# se ejecuta desde su carpeta como desde la raiz del repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import redis_store  # noqa: E402

load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "Falta SECRET_KEY en el archivo .env. Genera una con: "
        "python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = SECRET_KEY

# ---------------------------------------------------------------------------
# JWT (JSON Web Token)
#
# ESTE servicio es el emisor: firma los tokens con HS256 y el secreto
# JWT_SECRET_KEY. El microservicio de libros sólo VERIFICA la firma con el
# mismo secreto compartido: no tiene que llamar por HTTP a este servicio para
# validar cada escritura (evita encadenar microservicios detrás de tokens).
# ---------------------------------------------------------------------------
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Si no se define JWT_SECRET_KEY se reutiliza SECRET_KEY (mismo secreto en los
# dos .env = la verificación local del servicio de libros funciona sin más.
JWT_SECRET = os.getenv("JWT_SECRET_KEY") or SECRET_KEY
# access_token: 20 minutos (1200 s) segun requerimiento JWT+Redis.
JWT_ACCESS_SECONDS = int(os.getenv("JWT_ACCESS_SECONDS", "1200"))     # 20 min
# refresh_token: largo, sólo para obtener un nuevo access_token.
JWT_REFRESH_SECONDS = int(os.getenv("JWT_REFRESH_SECONDS", "86400"))   # 24 h

serializer = URLSafeTimedSerializer(app.secret_key)

# Rol asignado a los usuarios que se registran por sí mismos.
DEFAULT_ROLE_NAME = os.getenv("DEFAULT_ROLE_NAME", "Usuario Registrado")
# Longitud mínima de contraseña exigida en el registro.
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))
# Si es "true", /register deja la cuenta sin verificar y /login la rechaza (403)
# hasta pasar por /verify-email/<token>. Si es "false" (por defecto) la cuenta
# queda verificada y el flujo registro -> login funciona de inmediato.
REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
# Si es "true", /register intenta enviar el correo de verificación (SendGrid).
SEND_VERIFICATION_EMAIL = os.getenv("SEND_VERIFICATION_EMAIL", "false").lower() == "true"
MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@tudominio.com")

swagger = Swagger(
    app,
    template={
        "swagger": "2.0",
        "info": {
            "title": "Microservicio de Autenticación",
            "description": (
                "API para registro de usuarios, autenticación y sesiones. "
                "Todas las respuestas se negocian con ?format=xml|json "
                "(XML es el formato predeterminado)."
            ),
            "version": "1.0.0",
        },
        "basePath": "/",
        "schemes": ["http", "https"],
    },
)

# Formato de correo razonable (no RFC 5322 completo, pero suficiente para el
# ejercicio): local@dominio.tld sin espacios.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


# ---------------------------------------------------------------------------
# Base de datos (Psycopg 3)
# ---------------------------------------------------------------------------
def get_db_connection():
    """Abre una conexión a PostgreSQL devolviendo filas como diccionarios."""
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "library"),
        user=os.getenv("DB_USER", "library_user"),
        password=os.getenv("DB_PASSWORD", "library666"),
        row_factory=dict_row,
    )


# ---------------------------------------------------------------------------
# Utilidades de entrada / salida
# ---------------------------------------------------------------------------
def parse_request_data(req):
    """Lee el cuerpo de la petición como diccionario (JSON, XML o formulario)."""
    if req.is_json:
        return req.get_json(silent=True) or {}
    if req.content_type and req.content_type.split(";")[0] in ("application/xml", "text/xml"):
        try:
            root = ET.fromstring(req.data)
        except ET.ParseError:
            return {}
        return {child.tag: (child.text or "") for child in root}
    if req.form:
        return req.form.to_dict()
    return {}


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


def format_response(data, status_code=200):
    """Responde en JSON o XML según ``?format=``. Sin ``format`` devuelve XML."""
    fmt = request.args.get("format", "xml").strip().lower()
    if fmt == "json":
        return jsonify(data), status_code
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + dict_to_xml("response", data)
    return Response(xml_str, status=status_code, mimetype="application/xml")


def normalizar_email(email):
    """Minúsculas y sin espacios: el UNIQUE de PostgreSQL es sensible a mayúsculas."""
    return (email or "").strip().lower()


def email_valido(email):
    return bool(EMAIL_RE.match(email or ""))


def verificar_contrasena(password):
    """Mínimo de caracteres; en producción se recommendan mayúscula, número y símbolo."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres"
    return True, None


def enviar_correo_verificacion(email_destino, enlace):
    """Envía el enlace de verificación con la API de SendGrid (opcional)."""
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        print("[AVISO] SENDGRID_API_KEY no configurado: no se envió el correo.")
        return False
    payload = {
        "personalizations": [{"to": [{"email": email_destino}]}],
        "from": {"email": MAIL_FROM},
        "subject": "Verifica tu cuenta en la librería",
        "content": [
            {
                "type": "text/plain",
                "value": f"Confirma tu cuenta entrando a: {enlace}",
            }
        ],
    }
    try:
        respuesta = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        respuesta.raise_for_status()
        return True
    except requests.exceptions.RequestException as exc:
        print(f"[AVISO] No se pudo enviar el correo a {email_destino}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Emisión y control de refresh tokens
# ---------------------------------------------------------------------------
def _ahora():
    """Fecha/hora actual en UTC (los claims de PyJWT se guardan en UTC)."""
    return datetime.now(timezone.utc)


def guardar_refresh_token(jti, id_usuario, expira_en):
    """Persiste el jti del refresh token para poder revocarlo en /logout."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO refresh_tokens (jti, id_usuario, expira_en)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (jti) DO NOTHING
                    """,
                    (jti, id_usuario, expira_en.replace(tzinfo=None)),
                )
    except Exception as exc:  # noqa: BLE001 - no debe impedir iniciar sesión
        print(f"[AVISO] No se pudo guardar el refresh token: {exc}")


def refresh_token_activo(jti):
    """True si el jti existe, no está revocado, no está gastado y no venció."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM refresh_tokens
                     WHERE jti = %s
                       AND NOT usado
                       AND NOT revocado
                       AND expira_en > %s
                    """,
                    (jti, _ahora().replace(tzinfo=None)),
                )
                return cur.fetchone() is not None
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] No se pudo validar el refresh token: {exc}")
        return False


def marcar_refresh_usado(jti):
    """Marca el jti como gastado (rotacion: el refresh viejo deja de servir)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE refresh_tokens SET usado = TRUE WHERE jti = %s",
                    (jti,),
                )
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] No se pudo marcar el refresh token: {exc}")


def revocar_refresh(jti):
    """Marca el jti como revocado en PostgreSQL."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE refresh_tokens SET revocado = TRUE WHERE jti = %s",
                    (jti,),
                )
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] No se pudo revocar el refresh token: {exc}")


def emitir_tokens(id_usuario, email, rol_nombre, rol_id):
    """Firma el par access (20 min) + refresh (24 h) con role_id en claims.

    Persiste el refresh en PostgreSQL y guarda sesion + refresh en Redis.
    Fail-closed: si Redis no guarda ambos, se revoca el refresh y se lanza
    RuntimeError (el endpoint responde 503).
    """
    instante = _ahora()
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())
    access = {
        "sub": str(id_usuario),
        "role_id": int(rol_id),
        "email": email,
        "rol": rol_nombre,
        "scope": "escribir_libros",
        "type": "access",
        "jti": access_jti,
        "iat": instante,
        "exp": instante + timedelta(seconds=JWT_ACCESS_SECONDS),
        "iss": "libreria-login",
    }
    refresh = {
        "sub": str(id_usuario),
        "role_id": int(rol_id),
        "type": "refresh",
        "jti": refresh_jti,
        "iat": instante,
        "exp": instante + timedelta(seconds=JWT_REFRESH_SECONDS),
        "iss": "libreria-login",
    }
    access_token = jwt.encode(access, JWT_SECRET, algorithm=JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh, JWT_SECRET, algorithm=JWT_ALGORITHM)
    expira = datetime.fromtimestamp(refresh["exp"], tz=timezone.utc)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO refresh_tokens (jti, id_usuario, expira_en) "
                "VALUES (%s, %s, %s)",
                (refresh_jti, id_usuario, expira.replace(tzinfo=None)),
            )
        conn.commit()
    ok_sesion = redis_store.guardar_sesion(
        str(id_usuario), access_jti,
        {"email": email, "rol": rol_nombre, "role_id": int(rol_id)},
        JWT_ACCESS_SECONDS,
    )
    ok_refresh = redis_store.guardar_refresh(
        refresh_jti, str(id_usuario), JWT_REFRESH_SECONDS
    )
    if not (ok_sesion and ok_refresh):
        revocar_refresh(refresh_jti)
        raise RuntimeError("Redis no disponible: no se puede emitir la sesion")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": JWT_ACCESS_SECONDS,
        "refresh_expires_in": JWT_REFRESH_SECONDS,
        "access_jti": access_jti,
        "refresh_jti": refresh_jti,
    }


def decodificar_token(token, esperado):
    """Valida firma, caducidad y tipo. Devuelve (claims, error)."""
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None, "El token ha expirado"
    except jwt.InvalidTokenError as exc:
        return None, f"Token inválido: {exc}"
    if claims.get("type") != esperado:
        return None, f"Se esperaba un token tipo '{esperado}' y llegó '{claims.get('type')}'"
    return claims, None


def token_de_peticion():
    """Extrae el valor de la cabecera Authorization: Bearer <token>."""
    cabecera = request.headers.get("Authorization", "")
    if not cabecera:
        return None
    partes = cabecera.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1].strip() or None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health_check():
    """
    Verifica el estado del microservicio y de PostgreSQL
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
        description: Formato de la respuesta
    responses:
      200:
        description: Servicio y base de datos disponibles
      500:
        description: El servicio responde pero PostgreSQL no está disponible
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
        pg_ok = True
    except Exception:  # noqa: BLE001
        pg_ok = False
    rd = redis_store.redis_health()
    body = {
        "status": "ok" if pg_ok else "degraded",
        "service": "auth",
        "database": "connected" if pg_ok else "disconnected",
        "redis": rd,
        "metricas_redis": redis_store.metricas,
        "jwt_access_seconds": JWT_ACCESS_SECONDS,
        "endpoints": ["/register", "/login", "/logout", "/refresh", "/session", "/health"],
    }
    return format_response(body, 200 if pg_ok else 500)


@app.route("/register", methods=["POST"])
def register():
    """
    Registra un nuevo usuario (nombre, apellidos, email y password)
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [nombre, apellido_paterno, apellido_materno, email, password]
          properties:
            nombre:
              type: string
              example: María
            apellido_paterno:
              type: string
              example: López
            apellido_materno:
              type: string
              example: Cervantes
            email:
              type: string
              example: maria.lopez@example.com
            password:
              type: string
              example: ClaveSegura1
    responses:
      201:
        description: Usuario registrado
      400:
        description: Faltan campos, el email no es válido o la contraseña es corta
      409:
        description: El email ya está registrado
    """
    data = parse_request_data(request)
    requeridos = ["nombre", "apellido_paterno", "apellido_materno", "email", "password"]
    faltantes = [campo for campo in requeridos if not str(data.get(campo, "")).strip()]
    if faltantes:
        return format_response(
            {"error": "Faltan campos requeridos", "campos": faltantes}, 400
        )

    email = normalizar_email(data["email"])
    if not email_valido(email):
        return format_response({"error": "El correo electrónico no tiene un formato válido"}, 400)

    password = str(data["password"])
    ok, motivo = verificar_contrasena(password)
    if not ok:
        return format_response({"error": motivo}, 400)

    hashed_pw = generate_password_hash(password)
    verificado = not REQUIRE_EMAIL_VERIFICATION

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # El rol se resuelve por nombre: no se asume un id_rol fijo.
                cur.execute("SELECT id_rol FROM roles WHERE nombre_rol = %s", (DEFAULT_ROLE_NAME,))
                fila = cur.fetchone()
                if fila is None:
                    cur.execute(
                        "INSERT INTO roles (nombre_rol) VALUES (%s) RETURNING id_rol",
                        (DEFAULT_ROLE_NAME,),
                    )
                    id_rol = cur.fetchone()["id_rol"]
                else:
                    id_rol = fila["id_rol"]

                cur.execute(
                    """
                    INSERT INTO usuarios (email, password_hash, id_rol, verificado)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id_usuario
                    """,
                    (email, hashed_pw, id_rol, verificado),
                )
                id_usuario = cur.fetchone()["id_usuario"]

                cur.execute(
                    """
                    INSERT INTO perfiles_usuario (id_usuario, nombre, apellido_paterno, apellido_materno)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        id_usuario,
                        str(data["nombre"]).strip(),
                        str(data["apellido_paterno"]).strip(),
                        str(data["apellido_materno"]).strip(),
                    ),
                )
    except psycopg.errors.UniqueViolation:
        return format_response({"error": "El email ya está registrado"}, 409)
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": str(exc)}, 500)

    # Token firmado (HATEOAS) para verificar el correo, válido 1 hora.
    token = serializer.dumps(email, salt="email-verify-salt")
    verify_link = f"{request.host_url}verify-email/{token}?format=json"
    correo_enviado = None
    if SEND_VERIFICATION_EMAIL:
        correo_enviado = enviar_correo_verificacion(email, verify_link)
    else:
        print(f"[MVP] Enlace de verificación de {email}: {verify_link}")

    return format_response(
        {
            "message": "Usuario registrado exitosamente",
            "id_usuario": id_usuario,
            "email": email,
            "verificado": verificado,
            "_links": {
                "self": "/register",
                "verify_email": verify_link,
                "login": "/login",
            },
        },
        201,
    )


@app.route("/login", methods=["POST"])
def login():
    """
    Autentica al usuario e inicia sesión
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [email, password]
          properties:
            email:
              type: string
              example: admin@library.com
            password:
              type: string
              example: Admin123!
    responses:
      200:
        description: Autenticación exitosa
      400:
        description: Faltan email o password
      401:
        description: Credenciales inválidas
      403:
        description: La cuenta no ha verificado su correo
    """
    data = parse_request_data(request)
    if not data.get("email") or not data.get("password"):
        return format_response({"error": "Email y password son requeridos"}, 400)

    email = normalizar_email(data["email"])
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.id_usuario, u.email, u.password_hash, u.verificado,
                           r.nombre_rol, r.id_rol
                      FROM usuarios u
                      JOIN roles r ON r.id_rol = u.id_rol
                     WHERE u.email = %s
                    """,
                    (email,),
                )
                usuario = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": str(exc)}, 500)

    if not (usuario and check_password_hash(usuario["password_hash"], str(data["password"]))):
        return format_response({"error": "Credenciales invalidas"}, 401)

    if REQUIRE_EMAIL_VERIFICATION and not usuario["verificado"]:
        return format_response(
            {"error": "Cuenta no verificada. Revisa el correo de activacion."}, 403
        )

    session["user_id"] = usuario["id_usuario"]
    session["email"] = usuario["email"]

    # Emision del par de tokens JWT (Redis sesion+refresh; fail-closed 503)
    try:
        tokens = emitir_tokens(
            usuario["id_usuario"], usuario["email"],
            usuario["nombre_rol"], usuario["id_rol"],
        )
    except RuntimeError as exc:
        return format_response({"error": str(exc), "redis": "down"}, 503)

    return format_response(
        {
            "message": "Autenticacion exitosa",
            "id_usuario": usuario["id_usuario"],
            "email": usuario["email"],
            "rol": usuario["nombre_rol"],
            **tokens,
            "_links": {
                "self": "/login",
                "refresh": "/refresh",
                "logout": "/logout",
                "session": "/session",
            },
        },
        200,
    )


@app.route("/logout", methods=["POST"])
def logout():
    """
    Cierra la sesión actual
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
    responses:
      200:
        description: Sesión cerrada
    """
    # Revoca el refresh token si el cliente lo envia (body o cabecera),
    # para que ya no sirva para obtener un nuevo access_token.
    cuerpo = request.get_json(silent=True) or {}
    refresh = cuerpo.get("refresh_token")
    revocado = False
    if refresh:
        claims, _error = decodificar_token(refresh, "refresh")
        if claims:
            revocar_refresh(claims.get("jti"))
            ttl_r = max(1, int(claims.get("exp", 0)) - int(_ahora().timestamp()))
            redis_store.revocar_jti(claims.get("jti", ""), ttl_r)
            redis_store.borrar_refresh(claims.get("jti", ""))
            revocado = True

    # Redis: revoca tambien el access Bearer si llega en la cabecera.
    bearer = token_de_peticion()
    if bearer:
        cb, _err = decodificar_token(bearer, "access")
        if cb:
            ttl_a = max(1, int(cb.get("exp", 0)) - int(_ahora().timestamp()))
            redis_store.revocar_jti(cb.get("jti", ""), ttl_a)
            redis_store.borrar_sesion(str(cb.get("sub")), cb.get("jti", ""))

    session.pop("user_id", None)
    session.pop("email", None)
    return format_response(
        {"message": "Sesion cerrada exitosamente", "refresh_token_revocado": revocado}, 200
    )


def _canjear_refresh(refresh):
    """Valida, rota (PG + Redis) y emite un par nuevo. Devuelve (body, status)."""
    claims, error = decodificar_token(refresh, "refresh")
    if error:
        return {"error": error}, 401

    if not refresh_token_activo(claims.get("jti")):
        return {"error": "Refresh token revocado, ya usado o inexistente"}, 401

    # Redis: el refresh debe existir y no estar revocado (fail-closed).
    if not redis_store.refresh_valido(claims["jti"]):
        _rev = redis_store.esta_revocado(claims["jti"])
        if _rev is None:
            return {"error": "Servicio de sesiones no disponible", "redis": "down"}, 503
        return {"error": "Refresh token revocado, ya usado o inexistente"}, 401

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.id_usuario, u.email, r.nombre_rol, r.id_rol
                      FROM usuarios u
                      JOIN roles r ON r.id_rol = u.id_rol
                     WHERE u.id_usuario = %s
                    """,
                    (int(claims["sub"]),),
                )
                usuario = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}, 500

    if usuario is None:
        return {"error": "Usuario inexistente"}, 401

    # Rotacion: el refresh antiguo deja de ser valido (PG + Redis).
    marcar_refresh_usado(claims.get("jti"))
    redis_store.borrar_refresh(claims["jti"])
    ttl_viejo = max(1, int(claims.get("exp", 0)) - int(_ahora().timestamp()))
    redis_store.revocar_jti(claims["jti"], ttl_viejo)

    try:
        tokens = emitir_tokens(
            usuario["id_usuario"], usuario["email"],
            usuario["nombre_rol"], usuario["id_rol"],
        )
    except RuntimeError as exc:
        return {"error": str(exc), "redis": "down"}, 503

    return {
        "message": "Tokens renovados",
        "id_usuario": usuario["id_usuario"],
        "email": usuario["email"],
        **tokens,
        "_links": {"self": "/refresh", "logout": "/logout"},
    }, 200


def _claims_access_valido():
    """(claims, None) si el access Bearer es valido, no revocado y tiene sesion.

    (None, (body, status)) para responder directamente (401/503).
    """
    token = token_de_peticion()
    if not token:
        return None, ({"error": "Se requiere Authorization: Bearer <access_token>"}, 401)
    claims, error = decodificar_token(token, "access")
    if error:
        return None, ({"error": error}, 401)
    _rev = redis_store.esta_revocado(claims.get("jti", ""))
    if _rev is None:
        return None, ({"error": "Servicio de sesiones no disponible", "redis": "down"}, 503)
    if _rev:
        return None, ({"error": "Token revocado"}, 401)
    if redis_store.leer_sesion(str(claims.get("sub")), claims.get("jti", "")) is None:
        return None, ({"error": "Sesion no encontrada o expirada"}, 401)
    return claims, None


@app.route("/refresh", methods=["POST"])
def refresh_token():
    """
    Emite un nuevo access_token a partir de un refresh_token válido (rotación)
    ---
    El refresh_token viaja en el cuerpo (JSON o XML) o en la cabecera
    `Authorization: Bearer <refresh_token>`. Cada refresh se usa una sola vez:
    al canjearlo se emite uno nuevo y el anterior queda marcado como usado.
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
      - name: body
        in: body
        required: false
        schema:
          type: object
          properties:
            refresh_token:
              type: string
              example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    responses:
      200:
        description: Nuevo par de tokens emitido
      400:
        description: Falta el refresh_token
      401:
        description: Refresh token invalido, expirado, revocado o ya usado
      503:
        description: Redis no disponible (fail-closed)
    """
    data = parse_request_data(request)
    refresh = data.get("refresh_token") or token_de_peticion()
    if not refresh:
        return format_response(
            {"error": "Se requiere refresh_token en el cuerpo o en Authorization"}, 400
        )
    body, status = _canjear_refresh(refresh)
    return format_response(body, status)


@app.route("/session", methods=["GET"])
def check_session():
    """
    Consulta si existe una sesión autenticada
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
    responses:
      200:
        description: Hay sesión autenticada
      401:
        description: No hay sesión autenticada
    """
    # 1) Si llega un access_token en Authorization, la respuesta lo decide.
    token = token_de_peticion()
    if token:
        claims, error = decodificar_token(token, "access")
        if error:
            return format_response({"authenticated": False, "error": error}, 401)
        # Redis: fail-closed si cae; 401 si el jti esta revocado o sin sesion.
        _rev = redis_store.esta_revocado(claims.get("jti", ""))
        if _rev is None:
            return format_response({"error": "Servicio de sesiones no disponible",
                                    "redis": "down"}, 503)
        if _rev:
            return format_response({"authenticated": False, "error": "Token revocado"}, 401)
        if redis_store.leer_sesion(str(claims.get("sub")), claims.get("jti", "")) is None:
            return format_response({"authenticated": False,
                                    "error": "Sesion no encontrada o expirada"}, 401)
        return format_response(
            {
                "authenticated": True,
                "id_usuario": claims.get("sub"),
                "email": claims.get("email", ""),
                "rol": claims.get("rol", ""),
                "role_id": claims.get("role_id"),
                "via": "jwt",
            },
            200,
        )

    # 2) Compatibilidad con la cookie de sesión de Flask (cliente web/Tk sin JWT).
    if "user_id" in session:
        return format_response(
            {
                "authenticated": True,
                "id_usuario": session["user_id"],
                "email": session.get("email", ""),
                "via": "session",
            },
            200,
        )
    return format_response({"authenticated": False}, 401)


@app.route("/session/extend", methods=["POST"])
def extend_session():
    """
    Extiende la sesión rotando el refresh_token (mismo flujo que /refresh)
    ---
    Acepta refresh_token en el cuerpo (JSON/XML) o en Authorization: Bearer.
    El refresh viajado queda usado y se emite un par nuevo.
    responses:
      200:
        description: Par de tokens renovado
      400:
        description: Falta el refresh_token
      401:
        description: Refresh token invalido o ya usado
      503:
        description: Redis no disponible (fail-closed)
    """
    data = parse_request_data(request)
    refresh = data.get("refresh_token") or token_de_peticion()
    if not refresh:
        return format_response(
            {"error": "Se requiere refresh_token en el cuerpo o en Authorization"}, 400
        )
    body, status = _canjear_refresh(refresh)
    return format_response(body, status)


@app.route("/profile", methods=["PATCH", "PUT"])
def update_profile():
    """
    Actualiza el perfil del usuario autenticado (nombre, apellidos, password)
    ---
    Requiere Authorization: Bearer <access_token> valido y con sesion activa
    en Redis (fail-closed 503 si Redis esta caido).
    responses:
      200:
        description: Perfil actualizado
      400:
        description: Sin campos que actualizar
      401:
        description: Sin sesion valida
    """
    claims, err = _claims_access_valido()
    if err:
        return format_response(err[0], err[1])

    data = parse_request_data(request)
    campos = {"nombre", "apellido_paterno", "apellido_materno"}
    sets, params = [], []
    for campo in sorted(campos):
        valor = str(data.get(campo, "")).strip()
        if valor:
            sets.append(f"{campo} = %s")
            params.append(valor)
    password = str(data.get("password", ""))
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if sets:
                    params.append(int(claims["sub"]))
                    cur.execute(
                        f"UPDATE perfiles_usuario SET {', '.join(sets)} "
                        "WHERE id_usuario = %s",
                        params,
                    )
                if password:
                    ok, motivo = verificar_contrasena(password)
                    if not ok:
                        return format_response({"error": motivo}, 400)
                    cur.execute(
                        "UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
                        (generate_password_hash(password), int(claims["sub"])),
                    )
                cur.execute(
                    """SELECT u.email, p.nombre, p.apellido_paterno, p.apellido_materno
                         FROM usuarios u
                         LEFT JOIN perfiles_usuario p ON p.id_usuario = u.id_usuario
                        WHERE u.id_usuario = %s""",
                    (int(claims["sub"]),),
                )
                perfil = cur.fetchone()
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": str(exc)}, 500)

    if not sets and not password:
        return format_response({"error": "No hay campos para actualizar"}, 400)

    return format_response(
        {"message": "Perfil actualizado", "id_usuario": claims.get("sub"), **(perfil or {})},
        200,
    )


@app.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    """
    Verifica el correo del usuario mediante el token firmado (HATEOAS)
    ---
    parameters:
      - name: token
        in: path
        type: string
        required: true
        description: Token recibido en el correo de activación
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
    responses:
      200:
        description: Cuenta verificada
      400:
        description: Token inválido o expirado
      404:
        description: El usuario del token no existe
    """
    try:
        email = serializer.loads(token, salt="email-verify-salt", max_age=3600)
    except SignatureExpired:
        return format_response({"error": "El enlace ha expirado"}, 400)
    except BadTimeSignature:
        return format_response({"error": "Token inválido"}, 400)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE usuarios SET verificado = TRUE WHERE email = %s RETURNING id_usuario",
                    (email,),
                )
                actualizado = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return format_response({"error": str(exc)}, 500)

    if actualizado:
        return format_response(
            {
                "message": "Cuenta verificada exitosamente",
                "id_usuario": actualizado["id_usuario"],
                "email": email,
                "_links": {"self": f"/verify-email/{token}", "login": "/login"},
            },
            200,
        )
    return format_response({"error": "Usuario no encontrado"}, 404)


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"Microservicio de autenticación en http://0.0.0.0:{port}  (Swagger: /apidocs/)")
    print(f"Verificación de correo obligatoria: {REQUIRE_EMAIL_VERIFICATION}")
    app.run(host="0.0.0.0", port=port, debug=debug)
