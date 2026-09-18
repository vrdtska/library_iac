import os
import xml.etree.ElementTree as ET
from flask import Flask, request, session, jsonify, Response
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# --- CONEXIÓN A DB ---
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=RealDictCursor
    )

# --- UTILIDADES DE FORMATO ---
def parse_request_data(req):
    """Parsea el payload entrante ya sea JSON o XML."""
    if req.is_json:
        return req.get_json()
    elif req.content_type == 'application/xml' or req.content_type == 'text/xml':
        root = ET.fromstring(req.data)
        return {child.tag: child.text for child in root}
    return {}

def dict_to_xml(tag, d):
    """Convierte un diccionario plano a un string XML."""
    elem = ET.Element(tag)
    for key, val in d.items():
        child = ET.SubElement(elem, key)
        child.text = str(val)
    return ET.tostring(elem, encoding='unicode')

def format_response(data, status_code=200):
    """Formatea la respuesta en XML (por defecto) o JSON según ?format="""
    fmt = request.args.get('format', 'xml').lower()
    
    if fmt == 'json':
        return jsonify(data), status_code
    
    # XML por defecto
    xml_str = f'<?xml version="1.0" encoding="UTF-8"?>\n{dict_to_xml("response", data)}'
    return Response(xml_str, status=status_code, mimetype='application/xml')

# --- ENDPOINTS ---

@app.route('/health', methods=['GET'])
def health_check():
    """Verifica el estado del microservicio y PostgreSQL."""
    try:
        conn = get_db_connection()
        conn.close()
        return format_response({"status": "ok", "database": "connected"}, 200)
    except Exception as e:
        return format_response({"status": "error", "message": str(e)}, 500)

@app.route('/register', methods=['POST'])
def register():
    """Registra un nuevo usuario."""
    data = parse_request_data(request)
    
    required_fields = ['nombre', 'apellido_paterno', 'apellido_materno', 'email', 'password']
    if not all(field in data for field in required_fields):
        return format_response({"error": "Faltan campos requeridos"}, 400)
    
    hashed_pw = generate_password_hash(data['password'])
    default_role_id = 2 # Asumiendo que 2 es el rol de usuario normal
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # OJO: Esta consulta asume que agregaste los campos de nombre a la tabla usuarios
        query = """
            INSERT INTO usuarios (nombre, apellido_paterno, apellido_materno, email, password_hash, id_rol)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_usuario
        """
        cur.execute(query, (
            data['nombre'], data['apellido_paterno'], data['apellido_materno'],
            data['email'], hashed_pw, default_role_id
        ))
        new_user_id = cur.fetchone()['id_usuario']
        conn.commit()
        cur.close()
        conn.close()
        
        return format_response({"message": "Usuario registrado exitosamente", "id_usuario": new_user_id}, 201)
    
    except psycopg2.IntegrityError:
        conn.rollback()
        return format_response({"error": "El email ya está registrado"}, 409)
    except Exception as e:
        return format_response({"error": str(e)}, 500)

@app.route('/login', methods=['POST'])
def login():
    """Autentica al usuario e inicia sesión."""
    data = parse_request_data(request)
    
    if 'email' not in data or 'password' not in data:
        return format_response({"error": "Email y password son requeridos"}, 400)
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id_usuario, password_hash FROM usuarios WHERE email = %s", (data['email'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], data['password']):
            session['user_id'] = user['id_usuario']
            return format_response({"message": "Autenticacion exitosa"}, 200)
        else:
            return format_response({"error": "Credenciales invalidas"}, 401)
            
    except Exception as e:
        return format_response({"error": str(e)}, 500)

@app.route('/logout', methods=['POST'])
def logout():
    """Cierra la sesión."""
    session.pop('user_id', None)
    return format_response({"message": "Sesion cerrada exitosamente"}, 200)

@app.route('/session', methods=['GET'])
def check_session():
    """Consulta si existe una sesión autenticada."""
    if 'user_id' in session:
        return format_response({"authenticated": True, "id_usuario": session['user_id']}, 200)
    else:
        return format_response({"authenticated": False}, 401)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)