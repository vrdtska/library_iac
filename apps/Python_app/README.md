# Cliente de escritorio Python

Cliente Tkinter para los microservicios de autenticación y libros. No accede directamente a PostgreSQL; todas las operaciones usan HTTP.

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

## URLs

Valores iniciales:

- Autenticación remota: `http://34.51.108.65:5000`
- Libros remoto: `http://34.51.108.65:5001/books`

Desde **Configuración del servidor** se pueden cambiar por las URLs públicas de GCP. La configuración se persiste en `~/.libreria_cliente.json`.

Para pruebas locales, cambia las URLs desde **Configuración del servidor** a:

- Autenticación local: `http://localhost:5000`
- Libros local: `http://localhost:5001/books`

La configuración remota predeterminada de esta entrega apunta a `34.51.108.65`.

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

El cliente implementa health checks periódicos cada 30 segundos, comprobación manual y estados visuales: 🟢 servicio y dependencia disponibles, 🟡 respuesta accesible pero degradada, 🔴 error de conexión o sin respuesta. La pantalla muestra fecha/hora de la última comprobación.

El microservicio de autenticación disponible en este repositorio implementa `/register`, `/login`, `/logout`, `/session` y `/verify-email/<token>`. No se encontraron implementaciones de `/verify`, `/session/extend` ni `/profile`; el cliente llama esos endpoints porque forman parte de la actividad y muestra un mensaje claro si el servicio responde `404`.

El servicio de libros está en `apps/services/soap/app.py` y expone `/books` con XML por defecto y JSON al usar `?format=json`. El cliente usa `/api/libros` para CRUD, `/api/libros/isbn/<isbn>` para detalle y `/api/db-health` para comprobar la base de datos. El panel separa catálogo, administración de libros, estado de servicios, sesión/perfil y configuración del servidor.

El repositorio revisado no expone literalmente todos los endpoints del enunciado: el CRUD disponible usa `/api/libros/<id>`, no `/books/<isbn>`, y actualmente implementa `PUT` pero no `PATCH`. La interfaz llama `PATCH` para demostrar la diferencia requerida y presenta el error HTTP real si el backend aún no lo soporta; no oculta ni simula la operación.
