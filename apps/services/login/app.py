import os
import xml.etree.ElementTree as ET
from flask import Flask, request, session, jsonify, Response
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import requests
from flasgger import Swagger

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
serializer = URLSafeTimedSerializer(app.secret_key)

# --- CONFIGURACIÓN DE SWAGGER ---
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Microservicio de Autenticación",
        "description": "API para el manejo de usuarios, registro y sesiones (Soporta JSON y XML dinámicamente mediante ?format=)",
        "version": "1.0.0"
    }
}
swagger = Swagger(app, template=swagger_template)

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

# --- UTILIDADES ---
def parse_request_data(req):
    if req.is_json:
        return req.get_json()
    elif req.content_type in ['application/xml', 'text/xml']:
        root = ET.fromstring(req.data)
        return {child.tag: child.text for child in root}
    return {}

def dict_to_xml(tag, d):
    elem = ET.Element(tag)
    for key, val in d.items():
        if isinstance(val, dict):
            child_xml = dict_to_xml(key, val)
            child = ET.fromstring(child_xml)
            elem.append(child)
        else:
            child = ET.SubElement(elem, key)
            child.text = str(val)
    return ET.tostring(elem, encoding='unicode')

def format_response(data, status_code=200):
    fmt = request.args.get('format', 'xml').lower()
    if fmt == 'json':
        return jsonify(data), status_code
    xml_str = f'<?xml version="1.0" encoding="UTF-8"?>\n{dict_to_xml("response", data)}'
    return Response(xml_str, status=status_code, mimetype='application/xml')

def enviar_correo_verificacion(email_destino, enlace):
    """Envío vía API REST (Asegúrate de ajustar los parámetros de tu proveedor aquí)"""
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {os.getenv('SMTP_PASSWORD')}",
        "Content-Type": "application/json"
    }
    data = {
        "personalizations": [{"to": [{"email": email_destino}]}],
        "from": {"email": "sistema@tudominio.com"}, 
        "subject": "Verifica tu cuenta en el repositorio",
        "content": [{"type": "text/plain", "value": f"Hola,\n\nPor favor haz clic en el siguiente enlace:\n{enlace}"}]
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error enviando correo HTTP: {e}")

# --- ENDPOINTS ---

@app.route('/health', methods=['GET'])
def health_check():
    """
    Verifica el estado del microservicio y PostgreSQL
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
        description: Formato de respuesta
    responses:
      200:
        description: Estado de salud de la aplicación
    """
    try:
        conn = get_db_connection()
        conn.close()
        return format_response({"status": "ok", "database": "connected"}, 200)
    except Exception as e:
        return format_response({"status": "error", "message": str(e)}, 500)

@app.route('/register', methods=['POST'])
def register():
    """
    Registra un nuevo usuario
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
          properties:
            nombre:
              type: string
            apellido_paterno:
              type: string
            apellido_materno:
              type: string
            email:
              type: string
            password:
              type: string
    responses:
      201:
        description: Usuario registrado
      400:
        description: Faltan campos
      409:
        description: Email ya registrado
    """
    data = parse_request_data(request)
    required_fields = ['nombre', 'apellido_paterno', 'apellido_materno', 'email', 'password']
    if not all(field in data for field in required_fields):
        return format_response({"error": "Faltan campos requeridos"}, 400)
    
    hashed_pw = generate_password_hash(data['password'])
    default_role_id = 2 
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("INSERT INTO usuarios (email, password_hash, id_rol, verificado) VALUES (%s, %s, %s, FALSE) RETURNING id_usuario", (data['email'], hashed_pw, default_role_id))
        new_user_id = cur.fetchone()['id_usuario']
        
        cur.execute("INSERT INTO perfiles_usuario (id_usuario, nombre, apellido_paterno, apellido_materno) VALUES (%s, %s, %s, %s)", (new_user_id, data['nombre'], data['apellido_paterno'], data['apellido_materno']))
        conn.commit()
        cur.close()
        conn.close()

        token = serializer.dumps(data['email'], salt='email-verify-salt')
        verify_link = f"{request.host_url}verify-email/{token}?format=json"
        
        # enviar_correo_verificacion(data['email'], verify_link)
        
        # Generar token de verificación que expira en 1 hora
        token = serializer.dumps(data['email'], salt='email-verify-salt')
        verify_link = f"{request.host_url}verify-email/{token}?format=json"
        
        # OMITIMOS EL ENVÍO REAL PARA EL MVP
        # enviar_correo_verificacion(data['email'], verify_link)
        print(f"\n[MVP TEST] Enlace HATEOAS generado: {verify_link}\n")
        
        return format_response({
            "message": "Usuario registrado (Modo MVP: Usa el enlace adjunto para verificar)",
            "id_usuario": new_user_id,
            "_links": {
                "self": "/register",
                "verify_email": verify_link,  # Copias este enlace para probar el GET
                "login": "/login"
            }
        }, 201)
    
    except psycopg2.IntegrityError:
        conn.rollback()
        return format_response({"error": "El email ya está registrado"}, 409)
    except Exception as e:
        return format_response({"error": str(e)}, 500)

@app.route('/login', methods=['POST'])
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
          properties:
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: Autenticación exitosa
      401:
        description: Credenciales inválidas
      403:
        description: Cuenta no verificada
    """
    data = parse_request_data(request)
    if 'email' not in data or 'password' not in data:
        return format_response({"error": "Email y password son requeridos"}, 400)
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id_usuario, password_hash, verificado FROM usuarios WHERE email = %s", (data['email'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], data['password']):
            if not user['verificado']:
                return format_response({"error": "Cuenta inactiva. Verifica tu correo primero."}, 403)
            session['user_id'] = user['id_usuario']
            return format_response({"message": "Autenticación exitosa", "id_usuario": user['id_usuario']}, 200)
        return format_response({"error": "Credenciales inválidas"}, 401)
            
    except Exception as e:
        return format_response({"error": str(e)}, 500)

@app.route('/logout', methods=['POST'])
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
    session.pop('user_id', None)
    return format_response({"message": "Sesion cerrada exitosamente"}, 200)

@app.route('/session', methods=['GET'])
def check_session():
    """
    Consulta si existe una sesión activa
    ---
    parameters:
      - name: format
        in: query
        type: string
        enum: [xml, json]
        default: xml
    responses:
      200:
        description: Usuario autenticado
      401:
        description: No autenticado
    """
    if 'user_id' in session:
        return format_response({"authenticated": True, "id_usuario": session['user_id']}, 200)
    return format_response({"authenticated": False}, 401)

@app.route('/verify-email/<token>', methods=['GET'])
def verify_email(token):
    """
    Verifica el correo mediante el token HATEOAS
    ---
    parameters:
      - name: token
        in: path
        type: string
        required: true
        description: Token enviado por correo
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
    """
    try:
        email = serializer.loads(token, salt='email-verify-salt', max_age=3600)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios SET verificado = TRUE WHERE email = %s RETURNING id_usuario", (email,))
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if updated:
            return format_response({
                "message": "Cuenta verificada exitosamente",
                "email": email,
                "_links": {"self": f"/verify-email/{token}", "login": "/login"}
            }, 200)
        return format_response({"error": "Usuario no encontrado"}, 404)
            
    except SignatureExpired:
        return format_response({"error": "El enlace ha expirado"}, 400)
    except BadTimeSignature:
        return format_response({"error": "Token inválido"}, 400)
    except Exception as e:
        return format_response({"error": str(e)}, 500)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)