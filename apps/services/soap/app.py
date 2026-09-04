#!/usr/bin/env python3
"""
Microservicio Flask para gestión CRUD de libros
Conexión a PostgreSQL con manejo de CORS y documentación Swagger
"""

import os
import json
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from flasgger import Swagger
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Inicializar Flask
app = Flask(__name__)
CORS(app)

# Configuración de Swagger
swagger = Swagger(app, template={
    "swagger": "2.0",
    "info": {
        "title": "Library Books API",
        "description": "API REST para gestión de libros en una librería en línea",
        "version": "1.0.0",
        "contact": {
            "name": "Librería API Support"
        }
    },
    "host": "localhost:5000",
    "basePath": "/api",
    "schemes": ["http", "https"]
})

# Configuración de base de datos
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', 5432),
    'database': os.getenv('DB_NAME', 'library'),
    'user': os.getenv('DB_USER', 'library_user'),
    'password': os.getenv('DB_PASSWORD', 'library666')
}

def get_db_connection():
    """Obtiene una conexión a la base de datos PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"Error de conexión a la base de datos: {e}")
        return None

def serialize_row(row):
    """Serializa una fila de base de datos a JSON"""
    if row is None:
        return None
    result = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result

def serialize_rows(rows):
    """Serializa múltiples filas de base de datos a JSON"""
    return [serialize_row(row) for row in rows]

# ============================================================================
# ENDPOINTS CRUD PARA LIBROS
# ============================================================================

@app.route('/api/libros', methods=['GET'])
def get_all_books():
    fmt = request.args.get('format', 'json').strip().lower()
    
    libros = [
        {"id": 1, "isbn": "11111111", "titulo": "Libro 1"},
        {"id": 2, "isbn": "22222222", "titulo": "Libro 2"}
    ]

    if fmt == 'xml':
        root = ET.Element('libros')
        for item in libros:
            book_el = ET.SubElement(root, 'libro')
            for k, v in item.items():
                child = ET.SubElement(book_el, str(k))
                child.text = str(v) if v is not None else ""
        xml_data = ET.tostring(root, encoding='utf-8', method='xml')
        return Response(xml_data, status=200, mimetype='application/xml')

    return jsonify(libros), 200

@app.route('/api/libros/<int:libro_id>', methods=['GET'])
def get_book_by_id(libro_id):
    """
    Obtiene un libro por ID
    ---
    tags:
      - Books
    parameters:
      - name: libro_id
        in: path
        type: integer
        required: true
        description: ID del libro
    responses:
      200:
        description: Libro encontrado
      404:
        description: Libro no encontrado
      500:
        description: Error en el servidor
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, titulo, subtitulo, isbn, anio_publicacion, 
                   descripcion, precio, stock, formato_id, categoria_id, 
                   created_at, updated_at
            FROM libros
            WHERE id = %s
        """, (libro_id,))
        book = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if book is None:
            return jsonify({"error": "Libro no encontrado"}), 404
        
        return jsonify(serialize_row(book)), 200
    except psycopg2.Error as e:
        return jsonify({"error": f"Error en la consulta: {str(e)}"}), 500

@app.route('/api/libros/isbn/<isbn>', methods=['GET'])
def get_book_by_isbn(isbn):
    # 1. Obtener el formato solicitado (por defecto 'json')
    fmt = request.args.get('format', 'json').strip().lower()

    # 2. Consultar la base de datos (ejemplo conceptual)
    # libro = db_find_book_by_isbn(isbn)
    libro = {
        "id": 1,
        "isbn": isbn,
        "titulo": "Clean Code",
        "precio": 450.00,
        "stock": 10
    }

    if not libro:
        if fmt == 'xml':
            error_xml = "<error><mensaje>Libro no encontrado</mensaje></error>"
            return Response(error_xml, status=404, mimetype='application/xml')
        return jsonify({"error": "Libro no encontrado"}), 404

    # 3. Retornar según el parámetro format
    if fmt == 'xml':
        xml_data = dict_to_xml('libro', libro)
        return Response(xml_data, status=200, mimetype='application/xml')
    else:
        return jsonify(libro), 200

@app.route('/api/libros/<identifier>/temas', methods=['GET'])
def get_book_themes(identifier):
    """
    Obtener nombre del libro, ISBN y sus temas con descripción.
    Permite buscar por ID numérico o por ISBN.
    Soporta ?format=json (default) y ?format=xml.
    ---
    tags:
      - Libros
    parameters:
      - name: identifier
        in: path
        type: string
        required: true
        description: ID del libro o código ISBN
      - name: format
        in: query
        type: string
        required: false
        description: Formato de respuesta (json o xml)
    responses:
      200:
        description: Datos del libro y sus temas asociados
      404:
        description: Libro no encontrado
    """
    fmt = request.args.get('format', 'json').strip().lower()

    # 1. Obtener conexión a PostgreSQL
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 2. Consultar el libro y sus conceptos mediante JOIN
        query = """
            SELECT 
                l.id AS libro_id,
                l.titulo,
                l.isbn,
                c.id AS concepto_id,
                c.nombre AS tema_nombre,
                c.descripcion AS tema_descripcion,
                lc.definicion_contextual
            FROM libros l
            LEFT JOIN libro_conceptos lc ON l.id = lc.libro_id
            LEFT JOIN conceptos c ON lc.concepto_id = c.id
            WHERE l.isbn = %s OR CAST(l.id AS TEXT) = %s
            ORDER BY c.nombre ASC;
        """
        cur.execute(query, (identifier, identifier))
        rows = cur.fetchall()

        if not rows:
            if fmt == 'xml':
                return Response(
                    "<error><mensaje>Libro no encontrado</mensaje></error>",
                    status=404,
                    mimetype='application/xml'
                )
            return jsonify({"error": "Libro no encontrado"}), 404

        # 3. Estructurar la información
        first_row = rows[0]
        resultado = {
            "id": first_row["libro_id"],
            "titulo": first_row["titulo"],
            "isbn": first_row["isbn"],
            "temas": []
        }

        for row in rows:
            if row["concepto_id"] is not None:
                resultado["temas"].append({
                    "id": row["concepto_id"],
                    "nombre": row["tema_nombre"],
                    "descripcion": row["tema_descripcion"] or "",
                    "definicion_contextual": row["definicion_contextual"] or ""
                })

        # 4. Respuesta en XML o JSON
        if fmt == 'xml':
            xml_output = book_themes_to_xml(resultado)
            return Response(xml_output, status=200, mimetype='application/xml')

        return jsonify(resultado), 200

    except Exception as e:
        if fmt == 'xml':
            return Response(
                f"<error><mensaje>{str(e)}</mensaje></error>",
                status=500,
                mimetype='application/xml'
            )
        return jsonify({"error": "Error interno del servidor", "detalle": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/libros/buscar', methods=['GET'])
def search_books():
    """
    Busca libros por atributos (título, autor, género, categoría)
    ---
    tags:
      - Books
    parameters:
      - name: titulo
        in: query
        type: string
        description: Título del libro (búsqueda parcial)
      - name: categoria_id
        in: query
        type: integer
        description: ID de la categoría
      - name: formato_id
        in: query
        type: integer
        description: ID del formato
      - name: anio_publicacion
        in: query
        type: integer
        description: Año de publicación
    responses:
      200:
        description: Resultados de búsqueda
      500:
        description: Error en el servidor
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        query = """
            SELECT id, titulo, subtitulo, isbn, anio_publicacion, 
                   descripcion, precio, stock, formato_id, categoria_id, 
                   created_at, updated_at
            FROM libros
            WHERE 1=1
        """
        params = []
        
        titulo = request.args.get('titulo')
        if titulo:
            query += " AND titulo ILIKE %s"
            params.append(f"%{titulo}%")
        
        categoria_id = request.args.get('categoria_id')
        if categoria_id:
            query += " AND categoria_id = %s"
            params.append(categoria_id)
        
        formato_id = request.args.get('formato_id')
        if formato_id:
            query += " AND formato_id = %s"
            params.append(formato_id)
        
        anio_publicacion = request.args.get('anio_publicacion')
        if anio_publicacion:
            query += " AND anio_publicacion = %s"
            params.append(anio_publicacion)
        
        query += " ORDER BY id"
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params)
        books = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(serialize_rows(books)), 200
    except psycopg2.Error as e:
        return jsonify({"error": f"Error en la búsqueda: {str(e)}"}), 500

@app.route('/api/libros', methods=['POST'])
def create_book():
    """
    Crea un nuevo libro
    ---
    tags:
      - Books
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - titulo
            - formato_id
            - categoria_id
          properties:
            titulo:
              type: string
            subtitulo:
              type: string
            isbn:
              type: string
            anio_publicacion:
              type: integer
            descripcion:
              type: string
            precio:
              type: number
            stock:
              type: integer
            formato_id:
              type: integer
            categoria_id:
              type: integer
    responses:
      201:
        description: Libro creado exitosamente
      400:
        description: Datos inválidos
      500:
        description: Error en el servidor
    """
    if not request.json:
        return jsonify({"error": "Se requiere JSON en el cuerpo de la solicitud"}), 400
    
    data = request.json
    
    # Validación básica
    if not data.get('titulo') or not data.get('formato_id') or not data.get('categoria_id'):
        return jsonify({"error": "Campos requeridos: titulo, formato_id, categoria_id"}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            INSERT INTO libros (titulo, subtitulo, isbn, anio_publicacion, descripcion, 
                              precio, stock, formato_id, categoria_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, titulo, isbn, anio_publicacion, precio, stock, 
                      formato_id, categoria_id, created_at
        """, (
            data.get('titulo'),
            data.get('subtitulo'),
            data.get('isbn'),
            data.get('anio_publicacion'),
            data.get('descripcion'),
            data.get('precio', 0),
            data.get('stock', 0),
            data.get('formato_id'),
            data.get('categoria_id')
        ))
        
        new_book = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(serialize_row(new_book)), 201
    except psycopg2.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Error al crear el libro: {str(e)}"}), 500

@app.route('/api/libros/<int:libro_id>', methods=['PUT'])
def update_book(libro_id):
    """
    Actualiza un libro existente
    ---
    tags:
      - Books
    parameters:
      - name: libro_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            titulo:
              type: string
            subtitulo:
              type: string
            isbn:
              type: string
            anio_publicacion:
              type: integer
            descripcion:
              type: string
            precio:
              type: number
            stock:
              type: integer
            formato_id:
              type: integer
            categoria_id:
              type: integer
    responses:
      200:
        description: Libro actualizado exitosamente
      400:
        description: Datos inválidos
      404:
        description: Libro no encontrado
      500:
        description: Error en el servidor
    """
    if not request.json:
        return jsonify({"error": "Se requiere JSON en el cuerpo de la solicitud"}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        data = request.json
        
        # Verificar que el libro existe
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM libros WHERE id = %s", (libro_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({"error": "Libro no encontrado"}), 404
        
        # Construir la consulta UPDATE dinámicamente
        updates = []
        params = []
        
        for field in ['titulo', 'subtitulo', 'isbn', 'anio_publicacion', 'descripcion', 
                      'precio', 'stock', 'formato_id', 'categoria_id']:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])
        
        if not updates:
            conn.close()
            return jsonify({"error": "No hay campos para actualizar"}), 400
        
        params.append(libro_id)
        
        query = f"UPDATE libros SET {', '.join(updates)} WHERE id = %s RETURNING *"
        
        cursor.execute(query, params)
        updated_book = cursor.fetchone()
        conn.commit()
        
        # Obtener como diccionario
        cursor.execute("""
            SELECT id, titulo, subtitulo, isbn, anio_publicacion, descripcion, 
                   precio, stock, formato_id, categoria_id, created_at, updated_at
            FROM libros WHERE id = %s
        """, (libro_id,))
        
        cursor_dict = conn.cursor(cursor_factory=RealDictCursor)
        cursor_dict.execute("""
            SELECT id, titulo, subtitulo, isbn, anio_publicacion, descripcion, 
                   precio, stock, formato_id, categoria_id, created_at, updated_at
            FROM libros WHERE id = %s
        """, (libro_id,))
        result = cursor_dict.fetchone()
        
        cursor.close()
        cursor_dict.close()
        conn.close()
        
        return jsonify(serialize_row(result)), 200
    except psycopg2.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Error al actualizar el libro: {str(e)}"}), 500

@app.route('/api/libros/<int:libro_id>', methods=['DELETE'])
def delete_book(libro_id):
    """
    Elimina un libro
    ---
    tags:
      - Books
    parameters:
      - name: libro_id
        in: path
        type: integer
        required: true
    responses:
      204:
        description: Libro eliminado exitosamente
      404:
        description: Libro no encontrado
      500:
        description: Error en el servidor
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        cursor = conn.cursor()
        
        # Verificar que el libro existe
        cursor.execute("SELECT id FROM libros WHERE id = %s", (libro_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({"error": "Libro no encontrado"}), 404
        
        # Eliminar el libro
        cursor.execute("DELETE FROM libros WHERE id = %s", (libro_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        return '', 204
    except psycopg2.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Error al eliminar el libro: {str(e)}"}), 500

# ============================================================================
# ENDPOINT DE PRUEBA Y SALUD
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Verifica el estado del servicio
    ---
    tags:
      - Health
    responses:
      200:
        description: Servicio en buen estado
    """
    return jsonify({
        "status": "ok",
        "message": "Library Books API is running"
    }), 200

@app.route('/api/db-health', methods=['GET'])
def db_health_check():
    """
    Verifica la conexión a la base de datos
    ---
    tags:
      - Health
    responses:
      200:
        description: Conexión a BD exitosa
      500:
        description: Error de conexión
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({
            "status": "error",
            "message": "Database connection failed"
        }), 500
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "ok",
            "message": "Database connection successful"
        }), 200
    except psycopg2.Error as e:
        return jsonify({
            "status": "error",
            "message": f"Database error: {str(e)}"
        }), 500

# ============================================================================
# MANEJO DE ERRORES GLOBAL
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Maneja errores 404"""
    return jsonify({"error": "Endpoint no encontrado"}), 404

@app.errorhandler(500)
def internal_error(error):
    """Maneja errores 500"""
    return jsonify({"error": "Error interno del servidor"}), 500

@app.before_request
def before_request():
    """Configuración antes de cada solicitud"""
    # CORS ya se maneja con Flask-CORS
    pass

# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False') == 'True'
    
    print(f"""
    ╔════════════════════════════════════════════════════════════╗
    ║  Library Books Microservice - Flask API                   ║
    ║  Version: 1.0.0                                           ║
    ║  Database: PostgreSQL                                     ║
    ║  CORS: Enabled                                            ║
    ║  Swagger: http://localhost:{port}/apidocs                  ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
