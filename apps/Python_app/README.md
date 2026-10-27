# Cliente de escritorio Python

Cliente Tkinter que consume **los 6 microservicios** de la librería
(login, books, users, authors, pedidos y pagos). No accede directamente a
PostgreSQL; todas las operaciones usan HTTP con JWT (`Authorization: Bearer`).

## Requisitos

- Python 3.10 o superior.
- `requests`.
- Tkinter instalado en el sistema (`python3-tk` en Debian/Ubuntu).

Instalación:

```bash
python -m pip install -r requirements.txt
```

Ejecución:

```bash
python client_app.py
```

## URLs (por omisión, locales vía `apps/run_all.sh`)

| Servicio | URL por omisión |
|---|---|
| login (auth) | `http://localhost:5000` |
| books (libros) | `http://localhost:5001/books` |
| users (usuarios) | `http://localhost:5003` |
| authors (autores) | `http://localhost:5004` |
| pedidos | `http://localhost:5005` |
| pagos | `http://localhost:5006` |

Desde **Configuración del servidor** se pueden cambiar las 6 URLs. La
configuración se persiste en `~/.libreria_cliente.json`. Tras guardar, el
cliente reconstruye el `ApiClient` con todas las URLs.

La aplicación no concede acceso usando únicamente información local. Al iniciar siempre llama `GET /session`; sin conectividad o con una respuesta `401`, vuelve al login de forma controlada. Esto evita confundir un usuario recordado con una sesión de servidor todavía válida.

## Operaciones HTTP

| Acción | Método | Endpoint |
| --- | --- | --- |
| Registrar | POST | `/register?format=json` |
| Verificar cuenta | GET | `/verify-email/<token>?format=json` (enlace devuelto por registro) |
| Iniciar sesión | POST | `/login?format=json` |
| Consultar sesión | GET | `/session?format=json` |
| Extender sesión | POST | `/session/extend?format=json` |
| Editar perfil | PATCH | `/profile?format=json` |
| Cerrar sesión | POST | `/logout?format=json` |
| Catálogo | GET | URL configurable, por defecto `/books?format=json` |

`requests.Session` conserva la cookie de Flask durante la ejecución. Al autenticarse se persiste únicamente la identidad/respuesta informativa en `~/.libreria_cliente_session.json`; no se guardan contraseñas. La cookie no se trata como válida después de cerrar la aplicación: el servidor debe confirmarla nuevamente con `GET /session`. Logout o una sesión expirada eliminan el archivo local. La aplicación también muestra mensajes diferenciados para credenciales incorrectas (`401`), cuenta no verificada (`403`), endpoint inexistente (`404`) y errores de red.

## Estado del backend revisado

El cliente implementa health checks periódicos cada 30 segundos, comprobación
manual y estados visuales: 🟢 servicio y dependencia disponibles, 🟡 respuesta
accesible pero degradada, 🔴 error de conexión o sin respuesta. La pantalla
comprueba **los 6 microservicios** (login, books, users, authors, pedidos, pagos)
y muestra la fecha/hora de la última comprobación.

El microservicio de autenticación (`apps/services/login/app.py`) implementa
`/register`, `/login`, `/logout`, `/refresh`, `/session`, `/session/extend`,
`/profile` y `/verify-email/<token>`. Emite el par de tokens (access 20 min,
refresh 24 h) y usa Redis para sesión, refresh y revocación.

El servicio de libros (`apps/services/soap/app.py`) expone `/books` (XML por
defecto, JSON con `?format=json`), con caché Redis (`X-Cache: HIT/MISS`) e
invalidación tras cada escritura. El cliente usa `/api/libros` para CRUD,
`/api/libros/isbn/<isbn>` para detalle y `/api/db-health` para la base.

Además del catálogo, el panel incluye **CRUD completo** de los 4 microservicios
nuevos, todos con `Authorization: Bearer <access_token>`:

* **Usuarios** (`:5003`) — listar/crear/editar/eliminar (`GET/POST/PUT/DELETE /users`).
* **Autores** (`:5004`) — CRUD de `/authors` y consulta de libros por autor.
* **Pedidos** (`:5005`) — crear (descuenta stock), cambiar estado (`PATCH /pedidos/<id>/estado`),
  cancelar (`DELETE`) y ver detalle.
* **Pagos** (`:5006`) — registrar pago (`POST /pagos`), listar y consultar por pedido.

Ante un `401` por access caducado, el cliente renueva con `POST /refresh` y
reintenta la operación una vez. Los botones de eliminar piden confirmación y
todas las operaciones se ejecutan contra el microservicio remoto.
