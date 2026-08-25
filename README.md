# Librería en línea - arquitectura monolítica con PostgreSQL

## 1. Objetivo del sistema

La aplicación web monolítica gestiona una librería en línea con acceso directo a PostgreSQL. Su propósito principal es administrar el catálogo de libros, autores, géneros, conceptos asociados, imágenes, formatos, categorías y usuarios registrados.

La base del sistema parte de la entidad principal `libros`, y la estructura de datos permite soportar relaciones complejas sin perder integridad ni escalabilidad dentro de una aplicación monolítica.

## 2. Patrones de diseño aplicados

### 2.1 Arquitectura macro-arquitectura monolítica

Se adopta una arquitectura monolítica porque todos los módulos del sistema comparten la misma base de código, la misma base de datos y la misma capa de despliegue. Esto facilita:

- implementación rápida,
- menor complejidad operativa inicial,
- integración directa con PostgreSQL,
- mantenimiento centralizado del dominio de negocio.

### 2.2 MVC para la interfaz gráfica

Se organiza la aplicación con el patrón Modelo - Vista - Controlador:

- Modelo: acceso a PostgreSQL, validaciones de negocio y lógica del dominio.
- Vista: formularios, pantallas y renderizado de las interfaces web.
- Controlador: recibe peticiones del usuario, invoca servicios y responde con vistas o JSON.

### 2.3 Organización modular

El sistema se estructura por módulos funcionales, agrupados bajo una sola aplicación:

- `users`: autenticación, perfiles y administración de usuarios
- `catalog`: catálogo de libros, categorías y formatos
- `authors`: administración de autores
- `genres`: manejo de géneros
- `concepts`: conceptos asociados por libro
- `media`: imágenes y portadas
- `admin`: administración del sistema y validaciones globales
- `core`: configuración, utilidades, conexión a base de datos y servicios transversales

## 3. Modelo de datos

### 3.1 Entidades principales

- `libros`: tabla principal del sistema
- `autores`: autores asociados a distintos libros
- `generos`: géneros del catálogo
- `conceptos`: términos de estudio o conceptos asociados a libros
- `formatos`: catálogo de formatos de libro
- `categorias`: catálogo de categorías del catálogo
- `usuarios`: usuarios registrados del sistema
- `libros_imagenes`: imágenes vinculadas a cada libro

### 3.2 Relaciones clave

- Un libro puede tener varios autores.
- Un libro puede pertenecer a varios géneros.
- Un mismo concepto puede aparecer en distintos libros con definiciones diferentes.
- Un libro puede tener varias imágenes.
- El formato y la categoría son catálogos independientes.
- Existe como máximo un administrador.

### 3.3 Regla de negocio importante

La restricción de administrador único se implementa con un índice único condicional en la tabla `usuarios`:

- solo puede haber un registro con `is_admin = true`

## 4. Esquema de PostgreSQL

El esquema base de la base de datos está definido en:

- [db/schema.sql](db/schema.sql)
- [data/db_schema.sql](data/db_schema.sql)
- [data/library_schema.sql](data/library_schema.sql)

La estructura principal incluye:

- tablas maestras: `libros`, `autores`, `generos`, `conceptos`, `formatos`, `categorias`
- tablas de relación: `libros_autores`, `libros_generos`, `libros_conceptos`
- tabla de usuarios: `usuarios`
- tabla de imágenes: `libros_imagenes`
- índices y triggers para `updated_at`

## 5. Diagrama lógico de relación

```text
categorias 1 ---- * libros
formatos   1 ---- * libros
libros     1 ---- * libros_autores * ---- 1 autores
libros     1 ---- * libros_generos * ---- 1 generos
libros     1 ---- * libros_conceptos * ---- 1 conceptos
libros     1 ---- * libros_imagenes
usuarios   1 ---- 0..1 administrador
```

## 6. Requisitos del sistema

### Entorno Linux

- CentOS 10 Stream
- PostgreSQL 15 o superior recomendado
- Python 3.12 o superior (si se desea una versión web con Flask o Django modular)
- Nginx (opcional para despliegue con reverse proxy)
- Firewall de sistema habilitado para puertos 80, 443 y 5432

## 7. Instalación y configuración de PostgreSQL

### 7.1 Instalar PostgreSQL en CentOS 10 Stream

```bash
sudo dnf update -y
sudo dnf install -y postgresql postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

### 7.2 Crear la base de datos y el usuario

```bash
sudo -u postgres psql <<'SQL'
CREATE USER library_user WITH PASSWORD '999';
CREATE DATABASE library OWNER library_user;
GRANT ALL PRIVILEGES ON DATABASE library TO library_user;
SQL
```

### 7.3 Configurar acceso local

Ajusta el archivo de autenticación de PostgreSQL si es necesario:

```bash
sudo nano /var/lib/pgsql/data/pg_hba.conf
```

Y asegúrate de incluir una regla local tipo:

```text
local   library      library_user      md5
host    library      library_user      127.0.0.1/32    md5
host    library      library_user      ::1/128         md5
```

Luego reinicia PostgreSQL:

```bash
sudo systemctl restart postgresql
```

## 8. Importación del esquema

Desde la raíz del proyecto, ejecuta:

```bash
psql -h localhost -U library_user -d library -f /home/vrdtska/Documents/integracion/libreria_eg/data/db_schema.sql
```

Si se desea usar el esquema del proyecto ya definido en el repositorio:

```bash
psql -h localhost -U library_user -d library -f /home/vrdtska/Documents/integracion/libreria_eg/db/schema.sql
```

## 9. Carga de datos iniciales recomendada

Se recomienda insertar al menos:

- 3 categorías
- 3 formatos
- 5 géneros
- 5 autores
- 5 libros
- 1 usuario administrador

Ejemplo de usuario administrador:

```sql
INSERT INTO usuarios (nombre, apellido, email, username, password_hash, is_admin, activo)
VALUES ('Administrador', 'Principal', 'admin@libreria.local', 'admin', '$2b$12$examplehashplaceholder', TRUE, TRUE);
```

> En producción se debe usar una contraseña hasheada con BCrypt o Argon2.

## 10. Ejecución del sistema

### Opción A: aplicación web monolítica con Python + Flask

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask psycopg2-binary python-dotenv
```

Luego se configura el archivo `.env`:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=library
DB_USER=library_user
DB_PASSWORD=999
```

La aplicación puede estructurarse así:

```text
apps/
  config/
  controllers/
  models/
  views/
  services/
  routes/
  modules/
    users/
    catalog/
    authors/
    genres/
    concepts/
    media/
    admin/
```

## 11. Despliegue en CentOS 10 Stream

### 11.1 Ejecutar la app con un servicio systemd

```bash
sudo nano /etc/systemd/system/libreria.service
```

Ejemplo:

```ini
[Unit]
Description=Libreria en linea monolitica
After=network.target

[Service]
WorkingDirectory=/opt/libreria
ExecStart=/opt/libreria/.venv/bin/python app.py
Restart=always
User=root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now libreria
sudo systemctl status libreria
```

### 11.2 Pubicar con Nginx

```bash
sudo dnf install -y nginx
sudo systemctl enable --now nginx
```

Configurar un virtual host para el puerto 80 o 443 y reenviar tráfico a la app local en el puerto configurado.

## 12. Seguridad recomendada

- no exponer PostgreSQL directamente a Internet,
- usar variables de entorno para credenciales,
- habilitar contraseñas seguras y hash con BCrypt/Argon2,
- limitar acceso a la base de datos solo al usuario de la aplicación,
- mantener copias de seguridad con `pg_dump`.

## 13. Copia de seguridad

```bash
pg_dump -h localhost -U library_user -d library > backup_library.sql
```

Restaurar:

```bash
psql -h localhost -U library_user -d library < backup_library.sql
```

## 14. Resumen

El sistema está diseñado como una aplicación monolítica modular con SQL en PostgreSQL, organizada alrededor de la tabla principal `libros`, con relaciones muchos a muchos y soporte para usuarios, imágenes y conceptos. La estructura de datos cumple con todas las reglas del caso de uso y está lista para ser implementada en CentOS 10 Stream con una configuración de base de datos PostgreSQL usando:

- usuario: `library_user`
- password: `999`
- base de datos: `library`

## 15. Archivo SQL principal

El esquema final usable se encuentra en:

- [db/schema.sql](db/schema.sql)
- [data/db_schema.sql](data/db_schema.sql)
