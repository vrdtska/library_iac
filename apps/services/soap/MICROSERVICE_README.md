# Microservicio de libros - Flask + Psycopg 3 + PostgreSQL

CRUD del catalogo de libros con CORS habilitado, salida **XML (por defecto)** o
**JSON** segun `?format=`, paginacion por peticion, Swagger en `/apidocs/` y
servicio de imagenes en `/uploads/`.

El XML que produce sigue el diseno de `library.xml` (raiz `library`, `<book isbn="...">`).

## Requisitos

- Python 3.10 o superior
- PostgreSQL 12 o superior
- `uv` o `pip`

## 1. Base de datos

Desde la raiz del proyecto:

```bash
psql -U postgres -f apps/db/00_create_database.sql
psql -U library_user -d library -f apps/db/01_schema.sql
psql -U library_user -d library -f apps/db/02_seed_30_per_table.sql
```

Si la base ya existia con el esquema anterior, aplica solo la migracion:

```bash
psql -U library_user -d library -f apps/db/03_migracion_verificado.sql
```

## 2. Configuracion

```bash
cp .env.example .env
```

| Variable | Por defecto | Descripcion |
| --- | --- | --- |
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` | Servidor PostgreSQL |
| `DB_NAME` | `library` | Base de datos |
| `DB_USER` / `DB_PASSWORD` | `library_user` / `library666` | Credenciales |
| `FLASK_PORT` | `5001` | Puerto del microservicio |
| `CURRENCY` | `USD` | Atributo `currency` del XML |
| `DEFAULT_LIMIT` / `MAX_LIMIT` | `8` / `100` | Paginado |
| `UPLOADS_DIR` | `apps/uploads` | Carpeta de imagenes |

## 3. Ejecucion

```bash
bash setup.sh     # crea .venv e instala dependencias
bash run.sh       # arranca en http://0.0.0.0:5001
```

Alternativa con recarga automatica: `bash flask_run.sh`

- Catalogo XML: <http://localhost:5001/books>
- Swagger: <http://localhost:5001/apidocs/>

## 4. Formato de respuesta

Sin `?format` la respuesta es **XML**. Con `?format=json` es **JSON**.

```bash
curl http://localhost:5001/books                      # XML
curl "http://localhost:5001/books?format=json"        # JSON
```

```xml
<library total="30" page="1" limit="8">
  <book isbn="978-000-000-01-0">
    <title>Libro de Prueba 1</title>
    <authors>
      <author>Ana Ruiz</author>
      <author>Luis Paz</author>
    </authors>
    <publicationYear>2026</publicationYear>
    <price currency="USD">979.78</price>
    <stock>31</stock>
    <genres><genre>...</genre></genres>
    <format>Tapa Blanda</format>
    <category>...</category>
    <images>
      <image url="http://localhost:5001/uploads/img_1.svg" path="/uploads/img_1.svg"
             isCover="true" order="1" altText="Portada de libro 1"/>
    </images>
    <concepts>
      <concept name="..." definition="..."/>
    </concepts>
  </book>
</library>
```

## 5. Endpoints

### Catalogo

| Metodo | Endpoint | Funcion |
| --- | --- | --- |
| GET | `/books` | Catalogo paginado (alias que consume Electron) |
| GET | `/api/libros` | Igual que `/books` |
| GET | `/api/libros/minimo` | **Datos minimos + imagenes** (para el catalogo) |
| GET | `/api/libros/<isbn>` | Detalle por ISBN |
| GET | `/api/libros/isbn/<isbn>` | Alias del detalle |
| GET | `/api/libros/<isbn>/temas` | Conceptos definidos en ese libro |
| GET | `/api/libros/buscar` | Filtros `?titulo=&categoria=&formato=&anio=&stock=` |

Parametros comunes de lectura: `?page=1&limit=8&format=xml|json`.

### Escritura (JSON)

| Metodo | Endpoint | Funcion |
| --- | --- | --- |
| POST | `/api/libros` | Crear libro |
| PUT | `/api/libros/<isbn>` | Actualizar campos enviados |
| PATCH | `/api/libros/<isbn>` | Actualizacion parcial |
| DELETE | `/api/libros/<isbn>` | Eliminar (204) |

El identificador es el **ISBN**, que es la clave primaria de `libros`.
`formato` y `categoria` aceptan el nombre o el id; si el nombre no existe se crea.
Si se envian `autores`, `generos`, `conceptos` o `imagenes`, se reemplazan por los nuevos.

```bash
curl -X POST http://localhost:5001/api/libros \
  -H "Content-Type: application/json" \
  -d '{
    "isbn": "978-000-000-99-0",
    "titulo": "Clean Code",
    "anio": 2008,
    "precio": 450.00,
    "stock": 12,
    "formato": "Tapa Blanda",
    "categoria": "Programacion",
    "autores": ["Robert C. Martin"],
    "generos": ["Desarrollo de Software"],
    "imagenes": [{"ruta": "/uploads/img_1.svg", "es_portada": true,
                  "texto_alternativo": "Portada de Clean Code"}]
  }'

curl -X PATCH http://localhost:5001/api/libros/978-000-000-99-0 \
  -H "Content-Type: application/json" -d '{"stock": 25}'

curl -X DELETE http://localhost:5001/api/libros/978-000-000-99-0
```

### Imagenes

`GET /uploads/<archivo>` sirve las portadas de `apps/uploads`.
En el XML, cada `<image>` trae `url` (absoluta, lista para el `<img>` del cliente)
y `path` (relativa).

### Salud

| Metodo | Endpoint | Funcion |
| --- | --- | --- |
| GET | `/api/health` | El microservicio responde |
| GET | `/api/db-health` | Estado de PostgreSQL y total de libros |

## 6. Estructura

```text
apps/services/soap/
├── app.py                  # microservicio Flask (sin blueprints)
├── library.xml             # diseño XML de referencia
├── styles.css
├── requirements.txt
├── .env.example            # plantilla de configuración
├── setup.sh / run.sh / flask_run.sh
└── MICROSERVICE_README.md
```

## 7. Problemas frecuentes

**`password authentication failed for user "library_user"`**
La base no existe todavia o la contraseña no coincide:

```bash
psql -U postgres -f ../../db/00_create_database.sql
```

**Las imagenes no cargan (404)**
Confirma que el archivo exista en `apps/uploads` y que `UPLOADS_DIR` apunte ahi.
Las rutas del seed son `/uploads/img_<n>.svg`.

**`column ... does not exist`**
La base tiene el esquema viejo. Aplica `apps/db/03_migracion_verificado.sql`.
