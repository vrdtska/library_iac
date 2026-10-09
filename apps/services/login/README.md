# Microservicio de autenticacion - Flask + Psycopg 3 + PostgreSQL

Registro de usuarios, inicio y cierre de sesion, consulta de sesion y verificacion
de salud. Todas las respuestas se pueden pedir en **XML (por defecto)** o en **JSON**.

## 1. Requisitos

- Python 3.10 o superior
- PostgreSQL 12 o superior
- `uv` o `pip`

## 2. Base de datos

Usa la base `library` del proyecto (misma que el microservicio de libros):

```bash
psql -U postgres -f apps/db/00_create_database.sql
psql -U library_user -d library -f apps/db/01_schema.sql
psql -U library_user -d library -f apps/db/02_seed_30_per_table.sql
```

Si la base ya existia con el esquema anterior:

```bash
psql -U library_user -d library -f apps/db/03_migracion_verificado.sql
```

### Con PostgreSQL en Docker (como esta montado en este proyecto)

El proyecto usa el contenedor `freshtrack_db` (`postgres:17-alpine`) publicado en
`0.0.0.0:5432`. No hace falta instalar PostgreSQL en el host:

```bash
# 1. Base de datos + rol (como superusuario del contenedor)
PGPASSWORD=999 psql -h 127.0.0.1 -p 5432 -U postgres -f apps/db/00_create_database.sql

# 2. Esquema y datos (como usuario de la aplicacion)
export PGPASSWORD=library666
psql -h 127.0.0.1 -p 5432 -U library_user -d library -f apps/db/01_schema.sql
psql -h 127.0.0.1 -p 5432 -U library_user -d library -f apps/db/02_seed_30_per_table.sql

# 3. Comprobacion
psql -h 127.0.0.1 -p 5432 -U library_user -d library -c "select count(*) from libros"
```

Credenciales del contenedor: superusuario `postgres`/`999`, aplicacion
`library_user`/`library666`. El `.env` de este servicio ya apunta a
`localhost:5432` / base `library`, asi que no hay que cambiar nada.

Verifica el resultado con:

```bash
curl http://localhost:5002/health          # database: connected
bash apps/services/login/verificar.sh      # guarda las evidencias en Evidencias/
```

## 3. Configuracion

## 3. Configuracion

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # SECRET_KEY
```

| Variable | Por defecto | Descripcion |
| --- | --- | --- |
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` | Servidor PostgreSQL |
| `DB_NAME` | `library` | Base de datos |
| `DB_USER` / `DB_PASSWORD` | `library_user` / `library666` | Credenciales |
| `SECRET_KEY` | (obligatoria) | Firma de las sesiones de Flask |
| `FLASK_PORT` | `5002` | Puerto (5000 estaba ocupado por `iac-proyecto/run.py`) |
| `DEFAULT_ROLE_NAME` | `Usuario Registrado` | Rol al registrarse |
| `MIN_PASSWORD_LENGTH` | `8` | Longitud minima de contrasena |
| `REQUIRE_EMAIL_VERIFICATION` | `false` | Si es `true`, `/login` exige verificar el correo |
| `SEND_VERIFICATION_EMAIL` | `false` | Si es `true`, envia el correo con SendGrid |
| `SENDGRID_API_KEY` | (vacio) | Clave de SendGrid, nunca subas el `.env` |

## 4. Ejecucion

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python app.py
```

- Servicio: <http://localhost:5002>
- Swagger: <http://localhost:5002/apidocs/>

## 5. Endpoints

| Metodo | Endpoint | Funcion |
| --- | --- | --- |
| POST | `/register` | Registra un usuario (nombre, apellido paterno, apellido materno, email, password) |
| POST | `/login` | Autentica e inicia sesion |
| POST | `/logout` | Cierra la sesion |
| GET | `/session` | Indica si hay sesion autenticada |
| GET | `/health` | Estado del microservicio y de PostgreSQL |
| GET | `/verify-email/<token>` | Verifica el correo con el token firmado (extra) |

El cuerpo se acepta en **JSON**, **XML** o formulario. La respuesta usa
`?format=xml|json`; sin el parametro devuelve **XML**.

## 6. Ejemplos

Registro (XML por defecto):

```bash
curl -X POST "http://localhost:5002/register" \
  -H "Content-Type: application/json" \
  -d '{"nombre":"María","apellido_paterno":"López","apellido_materno":"Cervantes",
       "email":"maria@example.com","password":"ClaveSegura1"}'
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <message>Usuario registrado exitosamente</message>
  <id_usuario>31</id_usuario>
  <email>maria@example.com</email>
  <verificado>True</verificado>
  <_links>
    <self>/register</self>
    <verify_email>http://localhost:5002/verify-email/...</verify_email>
    <login>/login</login>
  </_links>
</response>
```

Login guardando la cookie de sesion:

```bash
curl -c cookies.txt -X POST "http://localhost:5002/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email":"maria@example.com","password":"ClaveSegura1"}'

curl -b cookies.txt "http://localhost:5002/session?format=json"
curl -b cookies.txt -X POST "http://localhost:5002/logout?format=json"
```

Usuarios del seed:

| Email | Contrasena | Rol |
| --- | --- | --- |
| `admin@library.com` | `Admin123!` | Administrador |
| `user2@library.com` … `user30@library.com` | `Usuario123!` | Usuario Registrado |

## 7. Notas de seguridad

- Las contrasenas se guardan solo como hash PBKDF2 (`werkzeug.security`).
- El campo `password_hash` vive en `usuarios`: no hay tabla de contrasenas aparte.
- El email se normaliza a minusculas y se valida antes de insertar; la unicidad la
  garantiza el `UNIQUE` de la columna (409 si se repite).
- `SECRET_KEY` es obligatoria: el servicio no arranca sin ella.
- Nunca subas el `.env` al repositorio (ya esta en `.gitignore`).
