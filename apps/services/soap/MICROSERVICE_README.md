# Library Books Microservice - Flask API

Microservicio REST construido con Flask para gestionar operaciones CRUD de libros en una librería en línea. Conectado directamente a PostgreSQL con soporte CORS y documentación automática con Swagger.

## Características

- ✅ **CRUD Completo**: Crear, leer, actualizar y eliminar libros
- ✅ **Búsqueda Avanzada**: Por ISBN, título, categoría, formato, año de publicación
- ✅ **CORS Habilitado**: Acceso desde cualquier dominio
- ✅ **Swagger/OpenAPI**: Documentación interactiva en `/apidocs`
- ✅ **Variables de Entorno**: Credenciales seguras en archivo `.env`
- ✅ **Manejo de Errores**: Respuestas JSON consistentes
- ✅ **Health Checks**: Endpoints de verificación de estado

## Requisitos

- Python 3.8 o superior
- PostgreSQL 12 o superior
- pip (gestor de paquetes de Python)

## Instalación

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

El archivo `.env` ya está configurado con:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=library
DB_USER=library_user
DB_PASSWORD=library666
FLASK_ENV=development
FLASK_DEBUG=True
```

Modifica estos valores según tu configuración de PostgreSQL.

### 3. Asegurar que la base de datos esté creada

```bash
psql -h localhost -U library_user -d library -f ../../data/library_schema.sql
```

## Ejecución

### Modo desarrollo

```bash
python app.py
```

Esto iniciará el servidor en `http://localhost:5000`

### Modo producción

```bash
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

## Documentación Swagger

Una vez que el servidor esté ejecutándose, accede a la documentación interactiva:

```
http://localhost:5000/apidocs
```

Aquí puedes:
- Ver todos los endpoints disponibles
- Ver el esquema de solicitudes/respuestas
- Probar los endpoints directamente desde el navegador

## Endpoints API

### 1. Obtener todos los libros

**GET** `/api/libros`

```bash
curl http://localhost:5000/api/libros
```

**Respuesta:**
```json
[
  {
    "id": 1,
    "titulo": "To Kill a Mockingbird",
    "isbn": "978-0-06-112008-4",
    "anio_publicacion": 1960,
    "precio": 15.99,
    "stock": 45,
    "formato_id": 1,
    "categoria_id": 1,
    "created_at": "2024-01-15T10:30:00"
  }
]
```

### 2. Obtener libro por ID

**GET** `/api/libros/{id}`

```bash
curl http://localhost:5000/api/libros/1
```

### 3. Buscar libro por ISBN

**GET** `/api/libros/isbn/{isbn}`

```bash
curl http://localhost:5000/api/libros/isbn/978-0-06-112008-4
```

### 4. Buscar libros por atributos

**GET** `/api/libros/buscar?titulo=...&categoria_id=...&formato_id=...&anio_publicacion=...`

```bash
curl "http://localhost:5000/api/libros/buscar?titulo=Mockingbird&categoria_id=1"
```

**Parámetros de búsqueda:**
- `titulo`: Búsqueda parcial de título (case-insensitive)
- `categoria_id`: ID de la categoría
- `formato_id`: ID del formato
- `anio_publicacion`: Año exacto de publicación

### 5. Crear un nuevo libro

**POST** `/api/libros`

```bash
curl -X POST http://localhost:5000/api/libros \
  -H "Content-Type: application/json" \
  -d '{
    "titulo": "New Book",
    "subtitulo": "A Subtitle",
    "isbn": "978-1-234-56789-0",
    "anio_publicacion": 2024,
    "descripcion": "Una descripción del libro",
    "precio": 29.99,
    "stock": 100,
    "formato_id": 1,
    "categoria_id": 2
  }'
```

**Campos requeridos:**
- `titulo` (string)
- `formato_id` (integer)
- `categoria_id` (integer)

**Campos opcionales:**
- `subtitulo` (string)
- `isbn` (string, única)
- `anio_publicacion` (integer)
- `descripcion` (string)
- `precio` (number, >= 0)
- `stock` (integer, >= 0)

### 6. Actualizar un libro

**PUT** `/api/libros/{id}`

```bash
curl -X PUT http://localhost:5000/api/libros/1 \
  -H "Content-Type: application/json" \
  -d '{
    "titulo": "Updated Title",
    "precio": 19.99,
    "stock": 75
  }'
```

Puedes actualizar cualquier cantidad de campos, no es necesario enviar todos.

### 7. Eliminar un libro

**DELETE** `/api/libros/{id}`

```bash
curl -X DELETE http://localhost:5000/api/libros/1
```

Devuelve un código 204 (No Content) si tiene éxito.

### 8. Verificar estado del servicio

**GET** `/api/health`

```bash
curl http://localhost:5000/api/health
```

**Respuesta:**
```json
{
  "status": "ok",
  "message": "Library Books API is running"
}
```

### 9. Verificar conexión a base de datos

**GET** `/api/db-health`

```bash
curl http://localhost:5000/api/db-health
```

**Respuesta si es exitosa:**
```json
{
  "status": "ok",
  "message": "Database connection successful"
}
```

## Manejo de CORS

El microservicio tiene CORS habilitado para aceptar solicitudes desde cualquier dominio. Los headers CORS se incluyen automáticamente en todas las respuestas:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

Para una configuración más restrictiva en producción, edita `app.py` y modifica:

```python
CORS(app, resources={r"/api/*": {"origins": ["https://tu-dominio.com"]}})
```

## Códigos de respuesta HTTP

| Código | Significado |
|--------|-------------|
| 200 | OK - Solicitud exitosa |
| 201 | Created - Recurso creado exitosamente |
| 204 | No Content - Eliminación exitosa (sin cuerpo) |
| 400 | Bad Request - Datos inválidos |
| 404 | Not Found - Recurso no encontrado |
| 500 | Internal Server Error - Error del servidor |

## Manejo de errores

Todas las respuestas de error incluyen un JSON con detalle:

```json
{
  "error": "Descripción del error"
}
```

Ejemplos:
```json
{"error": "Libro no encontrado"}
{"error": "Se requiere JSON en el cuerpo de la solicitud"}
{"error": "Campos requeridos: titulo, formato_id, categoria_id"}
{"error": "No se pudo conectar a la base de datos"}
```

## Seguridad

### Credenciales de base de datos

Las credenciales están en un archivo `.env` que **NO debe ser comprometido**:

- ✅ Usa `.env` para desarrollo
- ✅ En producción, usa variables de entorno del sistema
- ✅ Nunca hagas commit de `.env` a repositorios públicos

### SQL Injection

Se usan prepared statements con `psycopg2` para prevenir inyecciones SQL:

```python
cursor.execute("SELECT * FROM libros WHERE isbn = %s", (isbn,))
```

### CORS

CORS está configurado para aceptar solicitudes desde cualquier origen. En producción, restringe a dominios específicos.

## Serialización de datos

El microservicio serializa correctamente:
- Números decimales (precios) → float JSON
- Timestamps PostgreSQL → ISO 8601 string
- Valores NULL → null JSON

## Ejemplos de uso

### Ejemplo 1: Listar todos los libros

```bash
curl -s http://localhost:5000/api/libros | python -m json.tool
```

### Ejemplo 2: Crear un libro

```bash
curl -X POST http://localhost:5000/api/libros \
  -H "Content-Type: application/json" \
  -d '{
    "titulo": "El Quijote",
    "isbn": "978-0-7475-3269-9",
    "anio_publicacion": 1605,
    "descripcion": "Una de las obras maestras de la literatura española",
    "precio": 25.00,
    "stock": 50,
    "formato_id": 1,
    "categoria_id": 3
  }' | python -m json.tool
```

### Ejemplo 3: Buscar por título

```bash
curl -s "http://localhost:5000/api/libros/buscar?titulo=quijote" | python -m json.tool
```

### Ejemplo 4: Actualizar stock

```bash
curl -X PUT http://localhost:5000/api/libros/1 \
  -H "Content-Type: application/json" \
  -d '{"stock": 120}' | python -m json.tool
```

## Estructura del proyecto

```
/apps/services/soap/
├── app.py              # Microservicio principal
├── requirements.txt    # Dependencias de Python
├── .env               # Variables de entorno (NO subir a repositorio)
├── README.md          # Esta documentación
├── library.xml        # Referencia de diseño XML
├── server.py          # (Existente) Posible servidor anterior
└── styles*.css        # (Existente) Estilos para presentación
```

## Solución de problemas

### Error: "No se pudo conectar a la base de datos"

1. Verifica que PostgreSQL esté ejecutándose:
   ```bash
   psql -U library_user -d library -c "SELECT 1"
   ```

2. Verifica las credenciales en `.env`

3. Verifica que la base de datos y tablas existan:
   ```bash
   psql -U library_user -d library -c "\dt"
   ```

### Error: "Libro no encontrado"

Asegúrate de que el ID existe en la base de datos:

```bash
psql -U library_user -d library -c "SELECT id FROM libros WHERE id = 1"
```

### Error CORS

Si obtienes errores CORS desde el navegador:

1. Verifica que el microservicio esté ejecutándose
2. Verifica que `Flask-CORS` esté instalado: `pip install Flask-CORS`
3. Revisa la consola del navegador para más detalles

### Puerto en uso

Si el puerto 5000 está en uso:

```bash
python app.py
# O cambia el puerto en .env
```

## Despliegue en producción

### Usando Gunicorn

```bash
pip install gunicorn
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

### Usando Docker

Crea un `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV FLASK_APP=app.py
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

Build:
```bash
docker build -t library-api .
docker run -p 5000:5000 --env-file .env library-api
```

### Con Nginx (reverse proxy)

```nginx
upstream library_api {
    server localhost:5000;
}

server {
    listen 80;
    server_name api.mibiblioteca.com;

    location / {
        proxy_pass http://library_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Monitoreo

Accede al endpoint de health regularmente:

```bash
watch -n 5 'curl -s http://localhost:5000/api/db-health | jq .'
```

## Licencia

Este proyecto es parte de la librería en línea arquitectura monolítica.

## Soporte

Para problemas o sugerencias, revisa el documento principal README.md en la raíz del proyecto.
