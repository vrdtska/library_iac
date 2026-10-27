"""Módulo de Chatbot especializado con Ollama y sugerencias contextuales.

Proporciona endpoints para:
  1. POST /api/chat         -> Chatbot especializado con contexto del catálogo (streaming ndjson).
  2. POST /api/chat/simple  -> Chatbot con respuesta síncrona en JSON.
  3. GET  /api/sugerencias  -> Sugerencias breves no invasivas basadas en el libro o acción actual.
  4. GET  /api/chat/estado  -> Verificación de estado de Ollama y modelos disponibles.
"""

import json
import logging
import os
import time
from flask import Blueprint, Response, jsonify, request
import requests

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat_bp", __name__)

# Configuración de Ollama
# El contenedor de Docker mapea el puerto 9000 del host -> 11434 del contenedor.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:9000").rstrip("/")
OLLAMA_FALLBACK_URL = os.getenv("OLLAMA_FALLBACK_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))

# Cache en memoria del catálogo para evitar sobrecargar PostgreSQL en cada consulta del chat
_catalogo_cache = {
    "texto": None,
    "resumen": None,
    "timestamp": 0,
    "ttl": 300,  # 5 minutos
}


def _get_active_ollama_url():
    """Detecta si responde la URL principal o la de respaldo (puerto 9000 o 11434)."""
    for url in [OLLAMA_URL, OLLAMA_FALLBACK_URL]:
        try:
            r = requests.get(f"{url}/api/tags", timeout=2)
            if r.status_code == 200:
                return url
        except Exception:
            continue
    return OLLAMA_URL


def invalidar_cache_catalogo():
    """Invalida la caché del catálogo cuando hay cambios en los libros."""
    _catalogo_cache["texto"] = None
    _catalogo_cache["resumen"] = None
    _catalogo_cache["timestamp"] = 0


def _obtener_contexto_catalogo():
    """Obtiene y compila todo el catálogo con detalles técnicos desde PostgreSQL."""
    ahora = time.time()
    if _catalogo_cache["texto"] and (ahora - _catalogo_cache["timestamp"] < _catalogo_cache["ttl"]):
        return _catalogo_cache["texto"], _catalogo_cache["resumen"]

    try:
        from app import SELECT_LIBROS, cargar_relaciones, get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(SELECT_LIBROS + " ORDER BY l.isbn")
                libros = cur.fetchall()
                if not libros:
                    return "El catálogo actualmente no tiene libros registrados.", []
                rel = cargar_relaciones(conn, [b["isbn"] for b in libros])

        lineas = []
        resumen_libros = []
        for b in libros:
            isbn = b["isbn"]
            r = rel.get(isbn, {})
            autores = ", ".join(r.get("autores", [])) or "Desconocido"
            generos = ", ".join(r.get("generos", [])) or "General"
            conceptos = r.get("conceptos", [])
            conceptos_str = ""
            if conceptos:
                conceptos_str = "; ".join(
                    [f"[{c['termino']}: {c['definicion']}]" for c in conceptos]
                )

            item = (
                f"- ISBN: {isbn} | Título: '{b['titulo']}' | Año: {b['anio']} | "
                f"Autores: {autores} | Géneros: {generos} | Formato: {b['formato']} | "
                f"Categoría: {b['categoria']} | Precio: ${b['precio']:.2f} | Stock: {b['stock']} unidades"
            )
            if conceptos_str:
                item += f" | Conceptos técnicos explicados: {conceptos_str}"

            lineas.append(item)
            resumen_libros.append({
                "isbn": isbn,
                "titulo": b["titulo"],
                "autores": autores,
                "generos": generos,
                "conceptos": [c["termino"] for c in conceptos],
                "precio": float(b["precio"]),
                "stock": b["stock"]
            })

        texto_catalogo = "\n".join(lineas)
        _catalogo_cache["texto"] = texto_catalogo
        _catalogo_cache["resumen"] = resumen_libros
        _catalogo_cache["timestamp"] = ahora
        return texto_catalogo, resumen_libros

    except Exception as exc:
        logger.error("Error al obtener contexto del catálogo: %s", exc)
        return "Error consultando el catálogo en la base de datos.", []


def _construir_system_prompt():
    texto_catalogo, _ = _obtener_contexto_catalogo()
    prompt = f"""Eres el Asistente Técnico y Especialista de la librería 'Librería EG'.
Tu misión es atender a los usuarios de la plataforma de escritorio (Electron), respondiendo con precisión a cualquier consulta sobre los libros de nuestra base de datos y su contenido técnico.

Posees conocimiento completo del catálogo actual:
{texto_catalogo}

Directrices obligatorias:
1. Responde siempre en español, de forma clara, cordial y profesional.
2. Si el usuario pregunta por un concepto técnico (por ejemplo IaaS, SaaS u otros conceptos del catálogo), explica la definición exacta que se encuentra en el libro e indica el título y el ISBN del libro donde se define.
3. Si te piden recomendaciones, analiza los géneros, autores y conceptos del catálogo para sugerir los títulos más pertinentes que tengamos en stock.
4. Si consultan por precios, disponibilidad de stock, formatos (Tapa Blanda, Tapa Dura, eBook) o autores, usa los datos exactos del catálogo.
5. Si te preguntan sobre un tema o libro que no existe en el catálogo, indícalo cortésmente y ofrece los títulos más afines disponibles.
6. Mantén las respuestas bien estructuradas (puedes usar viñetas breves o negritas para legibilidad en la aplicación)."""
    return prompt


# ---------------------------------------------------------------------------
# Endpoints de la API
# ---------------------------------------------------------------------------

@chat_bp.route("/api/chat/estado", methods=["GET"])
def estado_ollama():
    """Verifica si Ollama está disponible y lista los modelos instalados."""
    url = _get_active_ollama_url()
    try:
        r = requests.get(f"{url}/api/tags", timeout=3)
        if r.status_code == 200:
            data = r.json()
            modelos = [m.get("name") for m in data.get("models", [])]
            return jsonify({
                "ollama": "connected",
                "url": url,
                "modelo_configurado": OLLAMA_MODEL,
                "modelos_disponibles": modelos,
                "modelo_listo": any(OLLAMA_MODEL in m for m in modelos)
            }), 200
    except Exception as exc:
        logger.warning("Ollama no responde en %s: %s", url, exc)

    return jsonify({
        "ollama": "disconnected",
        "url": url,
        "modelo_configurado": OLLAMA_MODEL,
        "error": "No se pudo conectar al servicio de Ollama."
    }), 503


@chat_bp.route("/api/chat", methods=["POST"])
def chat_stream():
    """Chatbot con Ollama y contexto completo del catálogo (streaming ndjson)."""
    data = request.get_json(silent=True) or {}
    mensaje_usuario = data.get("mensaje", "").strip()
    if not mensaje_usuario:
        return jsonify({"error": "El campo 'mensaje' es requerido."}), 400

    historial = data.get("historial", [])
    system_prompt = _construir_system_prompt()

    # Formatear mensajes para la API /api/chat de Ollama
    mensajes_ollama = [{"role": "system", "content": system_prompt}]

    for h in historial:
        rol = "assistant" if h.get("rol") in ("assistant", "bot") else "user"
        contenido = h.get("contenido") or h.get("content") or ""
        if contenido:
            mensajes_ollama.append({"role": rol, "content": contenido})

    mensajes_ollama.append({"role": "user", "content": mensaje_usuario})

    url = _get_active_ollama_url()

    def generar():
        try:
            with requests.post(
                f"{url}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": mensajes_ollama,
                    "stream": True,
                    "options": {
                        "temperature": 0.4,
                        "num_ctx": 4096
                    }
                },
                stream=True,
                timeout=OLLAMA_TIMEOUT
            ) as r:
                if r.status_code != 200:
                    yield json.dumps({
                        "error": f"Error de Ollama ({r.status_code}): {r.text}"
                    }) + "\n"
                    return

                for linea in r.iter_lines():
                    if linea:
                        try:
                            trozo = json.loads(linea.decode("utf-8"))
                            fragmento = trozo.get("message", {}).get("content", "")
                            fin = trozo.get("done", False)
                            if fragmento or fin:
                                yield json.dumps({"fragmento": fragmento, "fin": fin}) + "\n"
                        except Exception:
                            continue

        except requests.exceptions.RequestException as exc:
            yield json.dumps({
                "error": f"No se pudo conectar con Ollama en {url}. Verifique que el servicio esté activo: {str(exc)}"
            }) + "\n"

    return Response(generar(), mimetype="application/x-ndjson")


@chat_bp.route("/api/chat/simple", methods=["POST"])
def chat_simple():
    """Chatbot con respuesta completa síncrona en JSON."""
    data = request.get_json(silent=True) or {}
    mensaje_usuario = data.get("mensaje", "").strip()
    if not mensaje_usuario:
        return jsonify({"error": "El campo 'mensaje' es requerido."}), 400

    historial = data.get("historial", [])
    system_prompt = _construir_system_prompt()

    mensajes_ollama = [{"role": "system", "content": system_prompt}]
    for h in historial:
        rol = "assistant" if h.get("rol") in ("assistant", "bot") else "user"
        contenido = h.get("contenido") or h.get("content") or ""
        if contenido:
            mensajes_ollama.append({"role": rol, "content": contenido})

    mensajes_ollama.append({"role": "user", "content": mensaje_usuario})

    url = _get_active_ollama_url()
    try:
        r = requests.post(
            f"{url}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": mensajes_ollama,
                "stream": False,
                "options": {
                    "temperature": 0.4,
                    "num_ctx": 4096
                }
            },
            timeout=OLLAMA_TIMEOUT
        )
        if r.status_code != 200:
            return jsonify({"error": f"Error de Ollama: {r.text}"}), 502

        res_json = r.json()
        respuesta = res_json.get("message", {}).get("content", "")
        return jsonify({"respuesta": respuesta}), 200

    except requests.exceptions.RequestException as exc:
        return jsonify({
            "error": f"Fallo al conectar con Ollama en {url}: {str(exc)}"
        }), 503


@chat_bp.route("/api/sugerencias", methods=["GET"])
def obtener_sugerencia():
    """Genera sugerencias contextuales no invasivas y breves (1-2 frases).

    Parámetros opcionales:
      - isbn: ISBN del libro con el que el usuario interactúa o visualiza.
      - accion: 'ver_libro', 'navegar', 'catalogo'
      - pagina: Número de página actual
    """
    isbn = request.args.get("isbn")
    accion = request.args.get("accion", "navegar")
    pagina = request.args.get("pagina", "1")

    _, resumen_libros = _obtener_contexto_catalogo()

    # Si hay un ISBN específico, buscamos la información puntual de ese libro
    libro_seleccionado = None
    if isbn and resumen_libros:
        for lib in resumen_libros:
            if lib["isbn"] == isbn:
                libro_seleccionado = lib
                break

    url = _get_active_ollama_url()

    # Construir un prompt extremadamente conciso enfocado en generar un 'tip' o recomendación sutil
    if libro_seleccionado:
        titulo = libro_seleccionado["titulo"]
        autores = libro_seleccionado["autores"]
        generos = libro_seleccionado["generos"]
        conceptos = ", ".join(libro_seleccionado["conceptos"]) if libro_seleccionado["conceptos"] else "general"
        prompt_sugerencia = (
            f"Eres el asistente de la librería. El usuario está observando el libro '{titulo}' de {autores} (Género: {generos}, Conceptos: {conceptos}).\n"
            f"Genera un único consejo o dato curioso NO INVASIVO de máximo 20 palabras en español, invitándolo sutilmente a consultar o explorar otro libro afín.\n"
            f"Solo devuelve la frase, sin introducciones ni comillas."
        )
    else:
        # Sugerencia general del catálogo
        prompt_sugerencia = (
            f"Eres el asistente de la librería. El usuario está navegando la página {pagina} del catálogo con {len(resumen_libros)} libros técnicos disponibles.\n"
            f"Genera un único consejo o sugerencia de lectura breve y amigable de máximo 20 palabras en español para guiar al usuario sin ser invasivo.\n"
            f"Solo devuelve la frase, sin introducciones ni comillas."
        )

    try:
        r = requests.post(
            f"{url}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt_sugerencia,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 50,
                    "stop": ["\n\n", "User:", "Asistente:"]
                }
            },
            timeout=8
        )
        if r.status_code == 200:
            texto_sug = r.json().get("response", "").strip()
            # Limpiar comillas iniciales y finales si las colocó
            texto_sug = texto_sug.strip('"\'.')
            return jsonify({
                "sugerencia": texto_sug,
                "isbn": isbn,
                "accion": accion,
                "tipo": "tip"
            }), 200

    except Exception as exc:
        logger.debug("Ollama no respondió a tiempo para la sugerencia: %s", exc)

    # Fallback estático elegante si Ollama está ocupado o tardó más de 8s (fail-soft no invasivo)
    if libro_seleccionado and libro_seleccionado["conceptos"]:
        fallback = f"¿Sabías que '{libro_seleccionado['titulo']}' explica conceptos como {libro_seleccionado['conceptos'][0]}? Pregúntale a nuestro asistente."
    elif libro_seleccionado:
        fallback = f"¿Buscas más libros del género {libro_seleccionado['generos']}? Consulta con el asistente en cualquier momento."
    else:
        fallback = "Explora los conceptos técnicos de cada libro o haz click en el asistente 💬 para resolver tus dudas."

    return jsonify({
        "sugerencia": fallback,
        "isbn": isbn,
        "accion": accion,
        "tipo": "tip_fallback"
    }), 200
