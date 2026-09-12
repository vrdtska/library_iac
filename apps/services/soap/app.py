import os
import json
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response
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
    "host": "localhost:5001",
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
# FUNCIONES AUXILIARES PARA XML
# ============================================================================

def dict_to_xml(tag, d):
    """Convierte un diccionario a una cadena XML."""
    elem = ET.Element(tag)
    for key, val in d.items():
        child = ET.SubElement(elem, str(key))
        child.text = str(val) if val is not None else ""
    return ET.tostring(elem, encoding='utf-8', method='xml')

def book_themes_to_xml(resultado):
    """Estructura el diccionario anidado de temas a una cadena XML."""
    root = ET.Element('libro')
    
    # Propiedades raíz
    for key in ['id', 'titulo', 'isbn']:
        child = ET.SubElement(root, key)
        child.text = str(resultado.get(key, ''))
        
    # Arreglo de temas
    temas_el = ET.SubElement(root, 'temas')
    for tema in resultado.get('temas', []):
        tema_el = ET.SubElement(temas_el, 'tema')
        for key, val in tema.items():
            child = ET.SubElement(tema_el, str(key))
            child.text = str(val) if val is not None else ""
            
    return ET.tostring(root, encoding='utf-8', method='xml')

# ============================================================================
# ENDPOINTS CRUD PARA LIBROS
# ============================================================================

@app.route('/api/libros', methods=['GET'])
@app.route('/books', methods=['GET']) # Alias para coincidir con la URL de tu app Electron
def get_all_books():
    # Establecemos XML como predeterminado para este mock
    fmt = request.args.get('format', 'xml').strip().lower()
    
    mock_books = [
        {
            "id": 1,
            "title": "El Lenguaje de Programación C++",
            "author": "Bjarne Stroustrup",
            "isbn": "978-8478290467",
            "stock": 15,
            "year": 2013,
            "genre": "Desarrollo de Software",
            "price": 850.00,
            "image": "https://via.placeholder.com/300x450/2563eb/ffffff?text=C%2B%2B+Stroustrup"
        },
        {
            "id": 2,
            "title": "Fundación",
            "author": "Isaac Asimov",
            "isbn": "978-8497599245",
            "stock": 42,
            "year": 1951,
            "genre": "Ciencia Ficción",
            "price": 350.00,
            "image": "https://via.placeholder.com/300x450/1f2937/ffffff?text=Fundacion"
        },
        { 
            "id": 3,
            "title": "Python for Data Analysis",
            "author": "Wes McKinney",
            "isbn": "978-1491957660",
            "stock": 8,
            "year": 2017,
            "genre": "Data Science",
            "price": 920.50,
            "image": "https://via.placeholder.com/300x450/10b981/ffffff?text=Python+Data"
        },
        {
            "id": 4,
            "title": "Dance Music Manual",
            "author": "Rick Snoman",
            "isbn": "978-0415825645",
            "stock": 0,
            "year": 2013,
            "genre": "Ingeniería de Audio",
            "price": 1150.00,
            "image": "https://via.placeholder.com/300x450/ef4444/ffffff?text=Dance+Music"
        },
        {
            "id": 5,
            "title": "Operating System Concepts",
            "author": "Abraham Silberschatz",
            "isbn": "978-1118063330",
            "stock": 20,
            "year": 2012,
            "genre": "Sistemas Operativos",
            "price": 1400.00,
            "image": "https://via.placeholder.com/300x450/8b5cf6/ffffff?text=OS+Concepts"
        },
        {
            "id": 6,
            "title": "Clean Code",
            "author": "Robert C. Martin",
            "isbn": "978-0132350884",
            "stock": 5,
            "year": 2008,
            "genre": "Desarrollo de Software",
            "price": 600.00,
            "image": "https://via.placeholder.com/300x450/3b82f6/ffffff?text=Clean+Code"
        },
        {
            "id": 7,
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "978-0441172719",
            "stock": 12,
            "year": 1965,
            "genre": "Ciencia Ficción",
            "price": 400.00,
            "image": "https://via.placeholder.com/300x450/d97706/ffffff?text=Dune"
        },
        {
            "id": 8,
            "title": "Design Patterns",
            "author": "Erich Gamma, et al.",
            "isbn": "978-0201633610",
            "stock": 3,
            "year": 1994,
            "genre": "Desarrollo de Software",
            "price": 1050.00,
            "image": "https://via.placeholder.com/300x450/065f46/ffffff?text=Design+Patterns"
        },
        {
            "id": 9,
            "title": "Neuromante",
            "author": "William Gibson",
            "isbn": "978-8445077065",
            "stock": 0,
            "year": 1984,
            "genre": "Cyberpunk",
            "price": 280.00,
            "image": "https://via.placeholder.com/300x450/9d174d/ffffff?text=Neuromante"
        },
        {
            "id": 10,
            "title": "Grokking Algorithms",
            "author": "Aditya Bhargava",
            "isbn": "978-1617292231",
            "stock": 18,
            "year": 2016,
            "genre": "Ciencias de la Computación",
            "price": 750.00,
            "image": "https://via.placeholder.com/300x450/047857/ffffff?text=Algorithms"
        }
    ]

    if fmt == 'xml':
        root = ET.Element('catalog')
        for item in mock_books:
            book_el = ET.SubElement(root, 'book')
            for k, v in item.items():
                child = ET.SubElement(book_el, str(k))
                child.text = str(v) if v is not None else ""
        
        xml_data = ET.tostring(root, encoding='utf-8', method='xml')
        return Response(xml_data, status=200, mimetype='application/xml')

    return jsonify(mock_books), 200

@app.route('/api/libros/<int:libro_id>', methods=['GET'])
def get_book_by_id(libro_id):
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
    fmt = request.args.get('format', 'json').strip().lower()

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

    if fmt == 'xml':
        xml_data = dict_to_xml('libro', libro)
        return Response(xml_data, status=200, mimetype='application/xml')
    else:
        return jsonify(libro), 200

@app.route('/api/libros/<identifier>/temas', methods=['GET'])
def get_book_themes(identifier):
    fmt = request.args.get('format', 'json').strip().lower()

    conn = get_db_connection()
    if not conn:
        if fmt == 'xml':
            return Response("<error><mensaje>Sin base de datos</mensaje></error>", status=500, mimetype='application/xml')
        return jsonify({"error": "Sin base de datos"}), 500

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
            SELECT 
                l.id AS libro_id,
                l.titulo,
                l.isbn,
                c.id AS concepto_id,
                c.nombre AS tema_nombre,
                c.descripcion AS tema_descripcion,
                lc.definicion AS definicion_contextual
            FROM libros l
            LEFT JOIN libros_conceptos lc ON l.id = lc.libro_id
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
    if not request.json:
        return jsonify({"error": "Se requiere JSON en el cuerpo de la solicitud"}), 400
    
    data = request.json
    
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
    if not request.json:
        return jsonify({"error": "Se requiere JSON en el cuerpo de la solicitud"}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        data = request.json
        
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM libros WHERE id = %s", (libro_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({"error": "Libro no encontrado"}), 404
        
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
        conn.commit()
        
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
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM libros WHERE id = %s", (libro_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({"error": "Libro no encontrado"}), 404
        
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
    return jsonify({
        "status": "ok",
        "message": "Library Books API is running"
    }), 200

@app.route('/api/db-health', methods=['GET'])
def db_health_check():
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
    return jsonify({"error": "Endpoint no encontrado"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Error interno del servidor"}), 500

# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == '__main__':
    # Puerto ajustado a 5001 por defecto como se solicitó
    port = int(os.getenv('FLASK_PORT', 5001))
    debug = os.getenv('FLASK_DEBUG', 'False') == 'True'
    
    print(f"""
    ╔════════════════════════════════════════════════════════════╗
    ║  Library Books Microservice - Flask API                   ║
    ║  Version: 1.0.1 (XML Refactored)                          ║
    ║  Database: PostgreSQL                                     ║
    ║  CORS: Enabled                                            ║
    ║  Swagger: http://localhost:{port}/apidocs                  ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=debug)