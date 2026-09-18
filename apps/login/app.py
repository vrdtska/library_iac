import os
import xml.etree.ElementTree as ET
from flask import Flask, request, session, jsonify, Response
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import smtplib
from email.mime.text import MIMEText

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
serializer = URLSafeTimedSerializer(app.secret_key)

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
    """Convierte un diccionario (incluso anidado) a un string XML."""
    elem = ET.Element(tag)
    for key, val in d.items():
        if isinstance(val, dict):
            # Llamada recursiva para diccionarios anidados
            child_xml = dict_to_xml(key, val)
            child = ET.fromstring(child_xml)
            elem.append(child)
        else:
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

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def enviar_correo_verificacion(email_destino, enlace):
    """Envía un correo real usando un SMTP Relay de terceros."""
    remitente = "sistema@tudominio.com" # Cambia esto por un correo válido registrado en tu proveedor
    
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = email_destino
    msg['Subject'] = "Verifica tu cuenta en el repositorio"
    
    cuerpo = f"Hola,\n\nPor favor haz clic en el siguiente enlace para verificar tu cuenta y acceder al sistema:\n{enlace}\n\nSi no solicitaste este registro, ignora este correo."
    msg.attach(MIMEText(cuerpo, 'plain'))
    
    try:
        # Conexión al proveedor transaccional en el puerto 587
        server = smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT")))
        server.starttls() # Encripta la comunicación (requerido por SendGrid/Brevo)
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Error enviando correo: {e}")

@app.route('/register', methods=['POST'])
def register():
    """Registra un nuevo usuario y devuelve enlaces HATEOAS."""
    data = parse_request_data(request)
    
    required_fields = ['nombre', 'apellido_paterno', 'apellido_materno', 'email', 'password']
    if not all(field in data for field in required_fields):
        return format_response({"error": "Faltan campos requeridos"}, 400)
    
    hashed_pw = generate_password_hash(data['password'])
    default_role_id = 2 
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query_usuarios = """
            INSERT INTO usuarios (email, password_hash, id_rol, verificado)
            VALUES (%s, %s, %s, FALSE) RETURNING id_usuario
        """
        cur.execute(query_usuarios, (data['email'], hashed_pw, default_role_id))
        new_user_id = cur.fetchone()['id_usuario']
        
        query_perfiles = """
            INSERT INTO perfiles_usuario (id_usuario, nombre, apellido_paterno, apellido_materno)
            VALUES (%s, %s, %s, %s)
        """
        cur.execute(query_perfiles, (
            new_user_id, data['nombre'], data['apellido_paterno'], data['apellido_materno']
        ))
        
        conn.commit()
        cur.close()
        conn.close()

        # Generar token de verificación que expira en 3600 segundos (1 hora)
        token = serializer.dumps(data['email'], salt='email-verify-salt')
        # Asumiendo que ejecutas en localhost:5000; ajusta el dominio en producción
        verify_link = f"http://34.51.80.78:5000/verify-email/{token}?format=json"
        
        enviar_correo_verificacion(data['email'], verify_link)

        # Estructura HATEOAS
        response_data = {
            "message": "Usuario registrado exitosamente. Revisa tu correo para verificar la cuenta.",
            "id_usuario": new_user_id,
            "_links": {
                "self": "/register",
                "verify_email": verify_link,
                "login": "/login"
            }
        }
        return format_response(response_data, 201)
    
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

@app.route('/verify-email/<token>', methods=['GET'])
def verify_email(token):
    """Verifica el correo del usuario validando el token."""
    try:
        # max_age=3600 significa que el enlace expira en 1 hora
        email = serializer.loads(token, salt='email-verify-salt', max_age=3600)
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios SET verificado = TRUE WHERE email = %s RETURNING id_usuario", (email,))
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if updated:
            response_data = {
                "message": "Cuenta verificada exitosamente",
                "email": email,
                "_links": {
                    "self": f"/verify-email/{token}",
                    "login": "/login"
                }
            }
            return format_response(response_data, 200)
        else:
            return format_response({"error": "Usuario no encontrado"}, 404)
            
    except SignatureExpired:
        return format_response({"error": "El enlace de verificación ha expirado"}, 400)
    except BadTimeSignature:
        return format_response({"error": "Token de verificación inválido"}, 400)
    except Exception as e:
        return format_response({"error": str(e)}, 500)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)