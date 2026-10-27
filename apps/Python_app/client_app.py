"""Cliente de escritorio para los microservicios de autenticación y libros.

Uso:
    python client_app.py

Las URLs se guardan en ~/.libreria_cliente.json y también pueden configurarse
manualmente desde la pantalla de configuración. El cliente nunca accede a la
base de datos: toda la comunicación se realiza mediante HTTP.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable
import requests


CONFIG_PATH = Path.home() / ".libreria_cliente.json"
SESSION_PATH = Path.home() / ".libreria_cliente_session.json"
# Por defecto, los microservicios locales levantados con apps/run_all.sh.
# Ambas URLs son configurables desde la pantalla de Configuracion o editando
# ~/.libreria_cliente.json.
DEFAULT_AUTH_URL = "http://localhost:5000"
DEFAULT_BOOKS_URL = "http://localhost:5001/books"
DEFAULT_USERS_URL = "http://localhost:5003"
DEFAULT_AUTHORS_URL = "http://localhost:5004"
DEFAULT_PEDIDOS_URL = "http://localhost:5005"
DEFAULT_PAGOS_URL = "http://localhost:5006"
TIMEOUT = 10


class ServiceError(Exception):
    """Error HTTP o de transporte presentado al usuario."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Cliente HTTP con JWT (Bearer) para los 6 microservicios.

    * El servicio de autenticación entrega ``access_token`` + ``refresh_token``.
    * Toda operacion de escritura (y las lecturas protegidas de users/pedidos/
      pagos) se envia con ``Authorization: Bearer <access_token>``.
    * Si el servidor responde 401 (token caducado) se renueva el token con
      ``POST /refresh`` y se reintenta la operacion una sola vez.
    * Los endpoints de auth que usan cookie o cuerpo (login, register, refresh,
      logout, session/extend, verify-email) no llevan Bearer automatico.
    """

    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    # Endpoints de auth que viajan por cookie de sesion o por cuerpo, sin Bearer.
    AUTH_SIN_BEARER = ("/login", "/register", "/refresh", "/logout",
                       "/session/extend", "/verify-email")

    def __init__(self, auth_url: str, books_url: str, users_url: str = "",
                 authors_url: str = "", pedidos_url: str = "", pagos_url: str = ""):
        self.auth_url = auth_url.rstrip("/")
        self.books_url = books_url.strip()
        self.users_url = (users_url or "").strip()
        self.authors_url = (authors_url or "").strip()
        self.pedidos_url = (pedidos_url or "").strip()
        self.pagos_url = (pagos_url or "").strip()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.access_token: str | None = None
        self.refresh_token: str | None = None

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------
    def guardar_tokens(self, data: Any) -> None:
        if isinstance(data, dict):
            self.access_token = data.get("access_token") or self.access_token
            self.refresh_token = data.get("refresh_token") or self.refresh_token

    def limpiar_tokens(self) -> None:
        self.access_token = None
        self.refresh_token = None

    def _lleva_bearer(self, method: str, url: str) -> bool:
        """Decide si una petición concreta necesita la cabecera Authorization."""
        if not self.access_token:
            return False
        ruta = url.split("?")[0].rstrip("/")
        # Endpoints de auth que viajan por cookie de sesion o por cuerpo.
        if ruta.startswith(self.auth_url) or ruta.endswith(self.AUTH_SIN_BEARER):
            if any(ruta.endswith(ep) for ep in self.AUTH_SIN_BEARER):
                return False
            # /session y /profile del servicio de auth sí aceptan/usán Bearer.
            return ruta.endswith("/session") or ruta.endswith("/profile")
        # users, pedidos y pagos: TODAS sus operaciones (tambien GET) exigen JWT.
        for protegido in (self.users_url, self.pedidos_url, self.pagos_url):
            if protegido and ruta.startswith(protegido.rstrip("/")):
                return True
        # books y authors: GET público; solo escrituras llevan Bearer.
        return method.upper() in self.WRITE_METHODS

    @staticmethod
    def _message(response: requests.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return str(payload.get("error") or payload.get("message") or payload.get("detalle") or payload)
            return str(payload)
        except ValueError:
            return response.text.strip() or f"HTTP {response.status_code}"

    # ------------------------------------------------------------------
    # Peticiones
    # ------------------------------------------------------------------
    def _enviar(self, method: str, url: str, kwargs: dict[str, Any]) -> requests.Response:
        try:
            return self.session.request(method, url, timeout=TIMEOUT, **kwargs)
        except requests.exceptions.Timeout as exc:
            raise ServiceError("El servicio tardó demasiado en responder.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ServiceError("No se pudo conectar con el microservicio. Verifica la URL y que esté activo.") from exc
        except requests.exceptions.RequestException as exc:
            raise ServiceError(f"Error de red: {exc}") from exc

    @staticmethod
    def _poner_bearer(kwargs: dict[str, Any], token: str) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        return kwargs

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        con_bearer = self._lleva_bearer(method, url)
        if con_bearer:
            kwargs = self._poner_bearer(kwargs, self.access_token or "")

        response = self._enviar(method, url, kwargs)

        # Access token caducado: se renueva con /refresh y se reintenta una vez.
        if con_bearer and response.status_code == 401 and self.refresh_token:
            try:
                self.refrescar_tokens()
            except ServiceError:
                self.limpiar_tokens()
                raise ServiceError(self._message(response), 401)
            kwargs = self._poner_bearer(kwargs, self.access_token or "")
            response = self._enviar(method, url, kwargs)

        if not 200 <= response.status_code < 300:
            raise ServiceError(self._message(response), response.status_code)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return response.text

    def auth(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        separator = "&" if "?" in endpoint else "?"
        return self.request(method, f"{self.auth_url}{endpoint}{separator}format=json", **kwargs)

    def register(self, data: dict[str, str]) -> Any:
        return self.auth("POST", "/register", json=data)

    def login(self, email: str, password: str) -> Any:
        data = self.auth("POST", "/login", json={"email": email, "password": password})
        self.guardar_tokens(data)
        return data

    def refrescar_tokens(self) -> Any:
        """Renueva el access_token con el refresh_token (rotación)."""
        if not self.refresh_token:
            raise ServiceError("No hay refresh_token disponible para renovar la sesión.", 401)
        data = self.auth("POST", "/refresh", json={"refresh_token": self.refresh_token})
        self.guardar_tokens(data)
        return data

    def session_status(self) -> Any:
        return self.auth("GET", "/session")

    def logout(self) -> Any:
        try:
            # Se envía el refresh_token en el cuerpo para que el servidor lo
            # revoke: así ya no puede usarse para obtener un nuevo access_token.
            return self.auth("POST", "/logout", json={"refresh_token": self.refresh_token})
        finally:
            self.limpiar_tokens()
            self.session.cookies.clear()

    def verify_url(self, url: str) -> Any:
        # El enlace enviado por el servicio ya incluye ?format=json.
        return self.request("GET", url)

    def extend_session(self) -> Any:
        return self.auth("POST", "/session/extend")

    def update_profile(self, data: dict[str, str]) -> Any:
        return self.auth("PATCH", "/profile", json=data)

    def get_books(self, params: dict[str, Any] | None = None) -> Any:
        url = self.books_url
        separator = "&" if "?" in url else "?"
        try:
            return self.request("GET", f"{url}{separator}format=json", params=params or {})
        except ServiceError as exc:
            # Algunas instalaciones exponen el catálogo bajo /api/libros.
            if exc.status_code == 404:
                base = self.books_url.split("/books", 1)[0]
                return self.request("GET", f"{base}/api/libros?format=json", params=params or {})
            raise

    def get_book(self, identifier: str) -> Any:
        base = self.books_url.split("/books", 1)[0]
        return self.request("GET", f"{base}/api/libros/isbn/{identifier}?format=json")

    def create_book(self, data: dict[str, Any]) -> Any:
        base = self.books_url.split("/books", 1)[0]
        return self.request("POST", f"{base}/api/libros", json=data)

    def update_book(self, book_id: str, data: dict[str, Any], method: str = "PUT") -> Any:
        base = self.books_url.split("/books", 1)[0]
        return self.request(method, f"{base}/api/libros/{book_id}", json=data)

    def delete_book(self, book_id: str) -> Any:
        base = self.books_url.split("/books", 1)[0]
        return self.request("DELETE", f"{base}/api/libros/{book_id}")

    def health(self, service: str) -> Any:
        """Health de cualquiera de los 6 microservicios."""
        if service == "auth":
            return self.auth("GET", "/health")
        if service == "books":
            base = self.books_url.split("/books", 1)[0]
            return self.request("GET", f"{base}/api/db-health")
        base = getattr(self, f"{service}_url", "")
        return self.request("GET", f"{base}/health")

    # ------------------------------------------------------------------
    # Users (usuarios, roles, correos, contraseñas)  :5003
    # ------------------------------------------------------------------
    def list_roles(self) -> Any:
        return self.request("GET", f"{self.users_url}/roles")

    def list_users(self) -> Any:
        return self.request("GET", f"{self.users_url}/users")

    def get_user(self, user_id: int) -> Any:
        return self.request("GET", f"{self.users_url}/users/{user_id}")

    def create_user(self, data: dict[str, Any]) -> Any:
        return self.request("POST", f"{self.users_url}/users", json=data)

    def update_user(self, user_id: int, data: dict[str, Any], method: str = "PUT") -> Any:
        return self.request(method, f"{self.users_url}/users/{user_id}", json=data)

    def delete_user(self, user_id: int) -> Any:
        return self.request("DELETE", f"{self.users_url}/users/{user_id}")

    # ------------------------------------------------------------------
    # Authors (autores y su relación con libros)  :5004
    # ------------------------------------------------------------------
    def list_authors(self) -> Any:
        return self.request("GET", f"{self.authors_url}/authors")

    def get_author(self, author_id: int) -> Any:
        return self.request("GET", f"{self.authors_url}/authors/{author_id}")

    def author_books(self, author_id: int) -> Any:
        return self.request("GET", f"{self.authors_url}/authors/{author_id}/books")

    def create_author(self, data: dict[str, Any]) -> Any:
        return self.request("POST", f"{self.authors_url}/authors", json=data)

    def update_author(self, author_id: int, data: dict[str, Any], method: str = "PUT") -> Any:
        return self.request(method, f"{self.authors_url}/authors/{author_id}", json=data)

    def delete_author(self, author_id: int) -> Any:
        return self.request("DELETE", f"{self.authors_url}/authors/{author_id}")

    def assign_author(self, isbn: str, autores: list[int]) -> Any:
        return self.request("POST", f"{self.authors_url}/books/{isbn}/authors",
                            json={"autores": autores})

    # ------------------------------------------------------------------
    # Pedidos (pedidos, líneas, stock, estados)  :5005
    # ------------------------------------------------------------------
    def list_orders(self) -> Any:
        return self.request("GET", f"{self.pedidos_url}/pedidos")

    def get_order(self, order_id: int) -> Any:
        return self.request("GET", f"{self.pedidos_url}/pedidos/{order_id}")

    def create_order(self, items: list[dict[str, Any]], id_usuario: int | None = None) -> Any:
        payload: dict[str, Any] = {"items": items}
        if id_usuario is not None:
            payload["id_usuario"] = id_usuario
        return self.request("POST", f"{self.pedidos_url}/pedidos", json=payload)

    def change_order_state(self, order_id: int, estado: str) -> Any:
        return self.request("PATCH", f"{self.pedidos_url}/pedidos/{order_id}/estado",
                            json={"estado": estado})

    def cancel_order(self, order_id: int) -> Any:
        return self.request("DELETE", f"{self.pedidos_url}/pedidos/{order_id}")

    # ------------------------------------------------------------------
    # Pagos (pagos y actualización del estado del pedido)  :5006
    # ------------------------------------------------------------------
    def list_payments(self) -> Any:
        return self.request("GET", f"{self.pagos_url}/pagos")

    def get_payment(self, payment_id: int) -> Any:
        return self.request("GET", f"{self.pagos_url}/pagos/{payment_id}")

    def order_payments(self, order_id: int) -> Any:
        return self.request("GET", f"{self.pagos_url}/pedidos/{order_id}/pagos")

    def create_payment(self, data: dict[str, Any]) -> Any:
        return self.request("POST", f"{self.pagos_url}/pagos", json=data)


def load_config() -> dict[str, str]:
    defaults = {
        "auth_url": DEFAULT_AUTH_URL,
        "books_url": DEFAULT_BOOKS_URL,
        "users_url": DEFAULT_USERS_URL,
        "authors_url": DEFAULT_AUTHORS_URL,
        "pedidos_url": DEFAULT_PEDIDOS_URL,
        "pagos_url": DEFAULT_PAGOS_URL,
    }
    try:
        values = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(values, dict):
            for key, default in defaults.items():
                defaults[key] = str(values.get(key, default))
    except (OSError, json.JSONDecodeError):
        pass
    return defaults


def save_config(config: dict[str, str]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def load_session_state() -> dict[str, Any]:
    """Carga usuario, tokens JWT y fecha de guardado (si existen)."""
    try:
        values = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        if isinstance(values, dict):
            return values
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_session_state(user: dict[str, Any], api: "ApiClient | None" = None) -> None:
    """Persiste la identidad y los tokens JWT en el equipo local.

    Sólo se guardan los tokens (no la contraseña). Su validez siempre la
    decide el servidor: al arrancar se comprueba con GET /session y, si el
    access_token caducó, se renueva con POST /refresh.
    """
    payload: dict[str, Any] = {
        "user": user,
        "saved_at": __import__("datetime").datetime.now().isoformat(),
    }
    if api is not None:
        payload["access_token"] = api.access_token
        payload["refresh_token"] = api.refresh_token
    SESSION_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def clear_session_state() -> None:
    try:
        SESSION_PATH.unlink()
    except FileNotFoundError:
        pass


class ClientApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Librería · Cliente de microservicios")
        self.root.geometry("900x650")
        self.root.minsize(760, 520)
        self.config = load_config()
        self.api = ApiClient(**self.config)
        self.current_frame: tk.Widget | None = None
        self.user: dict[str, Any] = {}
        self.session_state = load_session_state()
        # Restaura los tokens JWT guardados en el arranque anterior.
        self.api.access_token = self.session_state.get("access_token")
        self.api.refresh_token = self.session_state.get("refresh_token")
        self.show_startup()

    def clear(self) -> None:
        if self.current_frame is not None:
            self.current_frame.destroy()

    def frame(self) -> ttk.Frame:
        self.clear()
        self.current_frame = ttk.Frame(self.root, padding=24)
        self.current_frame.pack(fill="both", expand=True)
        return self.current_frame

    def run_request(self, operation: Callable[[], Any], on_success: Callable[[Any], None], on_error: Callable[[ServiceError], None] | None = None) -> None:
        """Ejecuta HTTP fuera del hilo de Tk y actualiza la interfaz de forma segura."""
        def worker() -> None:
            try:
                result = operation()
                self.root.after(0, lambda: on_success(result))
            except ServiceError as error:
                self.root.after(0, lambda error=error: (on_error or self.show_error)(error))

        threading.Thread(target=worker, daemon=True).start()

    def startup_error(self, exc: ServiceError) -> None:
        # Sin conexión no se puede confirmar una sesión; no se concede acceso offline.
        self.show_login("No fue posible validar la sesión con el servidor. Puedes reintentar cuando tengas conectividad.")
        self.show_error(exc)

    def show_error(self, exc: ServiceError) -> None:
        if exc.status_code == 401:
            messagebox.showerror("No autenticado", "La sesión no es válida o las credenciales son incorrectas.")
        elif exc.status_code == 403:
            messagebox.showwarning("Cuenta no disponible", "La cuenta todavía no está verificada o no tiene autorización.")
        elif exc.status_code == 404:
            messagebox.showwarning("Endpoint no disponible", f"El servicio no implementa esta operación: {exc}")
        else:
            messagebox.showerror("Error del servicio", str(exc))

    @staticmethod
    def heading(parent: tk.Widget, title: str, subtitle: str | None = None) -> None:
        ttk.Label(parent, text=title, font=("TkDefaultFont", 20, "bold")).pack(pady=(0, 4))
        if subtitle:
            ttk.Label(parent, text=subtitle, wraplength=650).pack(pady=(0, 18))

    def show_startup(self) -> None:
        """Al arrancar, valida en el servidor la cookie persistida antes del panel."""
        frame = self.frame()
        self.heading(frame, "Comprobando sesión", "La sesión local no se considera válida hasta confirmarla con GET /session.")
        ttk.Label(frame, text="Conectando con el microservicio de autenticación…").pack(pady=24)
        self.run_request(self.api.session_status, self.restored_session, self.startup_error)

    def restored_session(self, data: Any) -> None:
        if isinstance(data, dict) and data.get("authenticated") is False:
            clear_session_state()
            self.api.limpiar_tokens()
            self.show_login("La sesión del servidor expiró. Vuelve a iniciar sesión.")
            return
        self.user = data if isinstance(data, dict) else self.session_state.get("user", {})
        save_session_state(self.user, self.api)
        self.show_dashboard()

    def show_login(self, notice: str | None = None) -> None:
        frame = self.frame()
        self.heading(frame, "Iniciar sesión", notice or "Conéctate al microservicio de autenticación.")
        form = ttk.Frame(frame)
        form.pack(pady=10)
        email = self.field(form, "Correo electrónico")
        password = self.field(form, "Contraseña", masked=True)

        def submit() -> None:
            if not email.get().strip() or not password.get():
                messagebox.showwarning("Datos incompletos", "Escribe el correo y la contraseña.")
                return
            self.run_request(lambda: self.api.login(email.get().strip(), password.get()), self.logged_in)

        ttk.Button(form, text="Iniciar sesión", command=submit).pack(fill="x", pady=(14, 6))
        ttk.Button(form, text="Crear una cuenta", command=self.show_register).pack(fill="x")
        ttk.Button(frame, text="Configuración de servicios", command=self.show_settings).pack(pady=24)

    def logged_in(self, data: Any) -> None:
        self.user = data if isinstance(data, dict) else {}
        # Persiste identidad + access_token + refresh_token (no la contraseña).
        save_session_state(self.user, self.api)
        self.show_dashboard()

    def show_register(self) -> None:
        frame = self.frame()
        self.heading(frame, "Registrar usuario", "La cuenta queda pendiente de verificación hasta abrir el enlace generado por el servicio.")
        form = ttk.Frame(frame)
        form.pack(pady=4)
        fields = {
            "nombre": self.field(form, "Nombre"),
            "apellido_paterno": self.field(form, "Apellido paterno"),
            "apellido_materno": self.field(form, "Apellido materno"),
            "email": self.field(form, "Correo electrónico"),
            "password": self.field(form, "Contraseña", masked=True),
        }

        def submit() -> None:
            data = {key: entry.get().strip() for key, entry in fields.items()}
            if not all(data.values()):
                messagebox.showwarning("Datos incompletos", "Todos los campos son obligatorios.")
                return
            self.run_request(lambda: self.api.register(data), self.registered)

        ttk.Button(form, text="Registrar", command=submit).pack(fill="x", pady=(14, 6))
        ttk.Button(form, text="Volver al inicio de sesión", command=self.show_login).pack(fill="x")

    def registered(self, data: Any) -> None:
        link = data.get("_links", {}).get("verify_email") if isinstance(data, dict) else None
        if link:
            self.show_verification(link)
        else:
            messagebox.showinfo("Registro exitoso", "Usuario registrado. Revisa el correo para verificar la cuenta.")
            self.show_login()

    def show_verification(self, initial_link: str = "") -> None:
        frame = self.frame()
        self.heading(frame, "Verificar cuenta", "El backend genera un enlace de verificación durante el registro. Pégalo aquí para llamar a GET /verify-email/<token>.")
        link = ttk.Entry(frame, width=90)
        link.insert(0, initial_link)
        link.pack(fill="x", pady=12)

        def verify() -> None:
            if not link.get().strip():
                messagebox.showwarning("Enlace requerido", "Pega el enlace de verificación recibido.")
                return
            self.run_request(lambda: self.api.verify_url(link.get().strip()), lambda _: self.verified())

        ttk.Button(frame, text="Verificar cuenta", command=verify).pack(pady=5)
        ttk.Button(frame, text="Ir al inicio de sesión", command=self.show_login).pack(pady=5)

    def verified(self) -> None:
        messagebox.showinfo("Cuenta verificada", "La cuenta fue verificada. Ya puedes iniciar sesión.")
        self.show_login()

    def show_dashboard(self) -> None:
        frame = self.frame()
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Panel de cliente", font=("TkDefaultFont", 20, "bold")).pack(side="left")
        ttk.Button(top, text="Cerrar sesión", command=self.do_logout).pack(side="right")
        ttk.Label(frame, text="La sesión local solo recuerda la última identidad conocida; el servidor se valida en cada arranque.").pack(anchor="w", pady=(8, 18))

        sections = ttk.Frame(frame)
        sections.pack(fill="x", pady=8)
        session_box = ttk.LabelFrame(sections, text="Sesión y perfil", padding=10)
        session_box.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ttk.Button(session_box, text="Verificar sesión", command=self.check_session).pack(fill="x", pady=2)
        ttk.Button(session_box, text="Extender sesión", command=self.extend_session).pack(fill="x", pady=2)
        ttk.Button(session_box, text="Editar perfil", command=self.show_profile).pack(fill="x", pady=2)

        catalog_box = ttk.LabelFrame(sections, text="Catálogo de libros", padding=10)
        catalog_box.pack(side="left", fill="both", expand=True, padx=6)
        ttk.Button(catalog_box, text="Consultar catálogo", command=self.show_books).pack(fill="x", pady=2)

        admin_box = ttk.LabelFrame(sections, text="Administración de libros", padding=10)
        admin_box.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ttk.Button(admin_box, text="Abrir administración", command=self.show_book_admin).pack(fill="x", pady=2)

        micro_box = ttk.LabelFrame(frame, text="Microservicios (CRUD con JWT)", padding=10)
        micro_box.pack(fill="x", pady=8)
        ttk.Button(micro_box, text="Usuarios", command=self.show_users, width=18).pack(side="left", padx=4)
        ttk.Button(micro_box, text="Autores", command=self.show_authors, width=18).pack(side="left", padx=4)
        ttk.Button(micro_box, text="Pedidos", command=self.show_orders, width=18).pack(side="left", padx=4)
        ttk.Button(micro_box, text="Pagos", command=self.show_payments, width=18).pack(side="left", padx=4)

        lower = ttk.Frame(frame)
        lower.pack(fill="x", pady=8)
        ttk.Button(lower, text="Estado de los servicios", command=self.show_service_status).pack(side="left", padx=(0, 8))
        ttk.Button(lower, text="Configuración del servidor", command=self.show_settings).pack(side="left")

        info = ttk.LabelFrame(frame, text="Sesión restaurada")
        info.pack(fill="both", expand=True, pady=12)
        text = tk.Text(info, height=8, state="disabled", wrap="word")
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.configure(state="normal")
        text.insert("1.0", json.dumps(self.user, indent=2, ensure_ascii=False))
        text.configure(state="disabled")

    def check_session(self) -> None:
        self.run_request(self.api.session_status, self.session_checked)

    def session_checked(self, data: Any) -> None:
        if isinstance(data, dict) and data.get("authenticated") is False:
            clear_session_state()
            self.user = {}
            messagebox.showwarning("Sesión expirada", "El servidor ya no reconoce la sesión.")
            self.show_login()
            return
        messagebox.showinfo("Sesión activa", json.dumps(data, ensure_ascii=False, indent=2))

    def extend_session(self) -> None:
        def show_extended(data: Any) -> None:
            messagebox.showinfo("Sesión", json.dumps(data, ensure_ascii=False, indent=2))

        self.run_request(self.api.extend_session, show_extended)

    def do_logout(self) -> None:
        def completed(_: Any) -> None:
            clear_session_state()
            self.user = {}
            self.show_login("Sesión cerrada correctamente.")
        self.run_request(self.api.logout, completed)

    def show_service_status(self) -> None:
        frame = self.frame()
        self.heading(frame, "Estado de los servicios", "🟢 saludable · 🟡 accesible/degradado · 🔴 inaccesible. Última comprobación: se actualiza automáticamente cada 30 segundos.")
        result = tk.Text(frame, height=12, state="disabled", wrap="word")
        result.pack(fill="both", expand=True, pady=12)
        self.status_text = result
        ttk.Button(frame, text="Comprobar ahora", command=lambda: self.check_health(result)).pack(pady=(0, 8))
        self.check_health(result)
        ttk.Button(frame, text="Volver", command=self.show_dashboard).pack()
        self.health_after_id = self.root.after(30000, lambda: self.check_health(result))

    # (clave del servicio, etiqueta visible) de los 6 microservicios.
    SERVICIOS_SALUD = (("auth", "Login"), ("books", "Libros"), ("users", "Usuarios"),
                       ("authors", "Autores"), ("pedidos", "Pedidos"), ("pagos", "Pagos"))

    def check_health(self, result: tk.Text | None = None) -> None:
        result = result or getattr(self, "status_text", None)
        if result is None:
            return
        timestamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result.configure(state="normal")
        result.delete("1.0", "end")
        result.insert("end", f"Última comprobación: {timestamp}\n")
        result.configure(state="disabled")

        def append(label: str, icon: str, detail: str) -> None:
            result.configure(state="normal")
            result.insert("end", f"{label}: {icon} {detail}\n")
            result.configure(state="disabled")

        def icono_de(data: Any) -> str:
            # Los 4 servicios nuevos reportan postgres/redis; auth/books usan status.
            if not isinstance(data, dict):
                return "🟢"
            if str(data.get("status", "ok")).lower() in ("error", "degraded"):
                return "🟡"
            if data.get("postgres") == "error" or data.get("database") == "disconnected":
                return "🟡"
            return "🟢"

        for clave, etiqueta in self.SERVICIOS_SALUD:
            def ok(data: Any, etiqueta=etiqueta) -> None:
                append(etiqueta, icono_de(data), "Disponible")

            def fail(error: ServiceError, etiqueta=etiqueta) -> None:
                append(etiqueta, "🔴", str(error))

            self.run_request(lambda c=clave: self.api.health(c), ok, fail)

    def show_book_admin(self) -> None:
        frame = self.frame()
        self.heading(frame, "Administración de libros", "Selecciona una operación. Todos los botones ejecutan peticiones HTTP reales.")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(0, 14))
        ttk.Button(actions, text="＋ CREAR LIBRO", command=self.show_create_book, width=20).pack(side="left", padx=4)
        ttk.Button(actions, text="Actualizar / eliminar", command=self.show_edit_book, width=20).pack(side="left", padx=4)
        ttk.Button(actions, text="Volver", command=self.show_dashboard, width=14).pack(side="right", padx=4)
        ttk.Label(frame, text="Crear libro usa POST /api/libros. Actualizar/eliminar usa el ID que devuelve el servicio.", wraplength=700).pack(anchor="w", pady=12)

    def show_create_book(self) -> None:
        frame = self.frame()
        self.heading(frame, "Crear libro", "POST /api/libros")

        # La barra de acciones se coloca antes del formulario para que siempre
        # sea visible incluso cuando la ventana tenga poca altura.
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(0, 10))
        submit_button = ttk.Button(actions, text="ENVIAR POST · CREAR LIBRO", width=28)
        submit_button.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="VOLVER A ADMINISTRACIÓN", command=self.show_book_admin, width=25).pack(side="left")

        form = ttk.LabelFrame(frame, text="Datos del libro", padding=12)
        form.pack(fill="x", padx=8)
        fields: dict[str, ttk.Entry] = {}
        definitions = (
            ("isbn", "ISBN"),
            ("titulo", "Título"),
            ("subtitulo", "Subtítulo"),
            ("anio_publicacion", "Año de publicación"),
            ("descripcion", "Descripción"),
            ("precio", "Precio"),
            ("stock", "Existencia"),
            ("formato_id", "Formato ID"),
            ("categoria_id", "Categoría ID"),
        )
        for index, (key, label) in enumerate(definitions):
            row, column = divmod(index, 2)
            cell = ttk.Frame(form)
            cell.grid(row=row, column=column, sticky="ew", padx=8, pady=5)
            ttk.Label(cell, text=label).pack(anchor="w")
            fields[key] = ttk.Entry(cell, width=32)
            fields[key].pack(fill="x", pady=(2, 0))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        status = ttk.Label(frame, text="Completa los campos y presiona ENVIAR POST · CREAR LIBRO.", wraplength=700)
        status.pack(anchor="w", pady=(10, 4))
        output = tk.Text(frame, height=7, state="disabled", wrap="word")
        output.pack(fill="both", expand=True, pady=(4, 0))

        def submit() -> None:
            try:
                data = {
                    "titulo": fields["titulo"].get().strip(),
                    "subtitulo": fields["subtitulo"].get().strip() or None,
                    "isbn": fields["isbn"].get().strip() or None,
                    "anio_publicacion": int(fields["anio_publicacion"].get()) if fields["anio_publicacion"].get().strip() else None,
                    "descripcion": fields["descripcion"].get().strip() or None,
                    "precio": float(fields["precio"].get() or 0),
                    "stock": int(fields["stock"].get() or 0),
                    "formato_id": int(fields["formato_id"].get()),
                    "categoria_id": int(fields["categoria_id"].get()),
                }
            except ValueError:
                messagebox.showwarning("Datos inválidos", "Precio, existencia, formato y categoría deben ser valores válidos.")
                return
            if not data["titulo"]:
                messagebox.showwarning("Dato requerido", "El título es obligatorio.")
                fields["titulo"].focus_set()
                return

            submit_button.configure(state="disabled")
            status.configure(text="Enviando POST /api/libros al microservicio…")

            def completed(result: Any) -> None:
                submit_button.configure(state="normal")
                status.configure(text="Libro creado correctamente. Respuesta del servicio:")
                self.show_operation_result(output, result)
                messagebox.showinfo("Libro creado", "El libro fue enviado correctamente al microservicio.")

            def failed(error: ServiceError) -> None:
                submit_button.configure(state="normal")
                status.configure(text=f"No se pudo crear el libro: {error}")
                self.show_error(error)

            self.run_request(lambda: self.api.create_book(data), completed, failed)

        submit_button.configure(command=submit)
        fields["titulo"].focus_set()

    def show_operation_result(self, output: tk.Text, data: Any) -> None:
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        output.configure(state="disabled")

    def show_edit_book(self) -> None:
        frame = self.frame()
        self.heading(frame, "Actualizar o eliminar libro", "PUT reemplaza campos enviados; PATCH modifica solo el precio.")
        form = ttk.Frame(frame)
        form.pack(fill="x", padx=20)
        fields = {key: self.field(form, label) for key, label in [("id", "ID del libro"), ("isbn", "ISBN"), ("titulo", "Título"), ("subtitulo", "Subtítulo"), ("anio_publicacion", "Año de publicación"), ("descripcion", "Descripción"), ("precio", "Precio"), ("stock", "Existencia"), ("formato_id", "Formato ID"), ("categoria_id", "Categoría ID")]}
        output = tk.Text(frame, height=8, state="disabled", wrap="word")
        output.pack(fill="both", expand=True, pady=12)

        def values() -> dict[str, Any]:
            data: dict[str, Any] = {}
            text_fields = ("titulo", "subtitulo", "isbn", "descripcion")
            for key in text_fields:
                value = fields[key].get().strip()
                if value:
                    data[key] = value
            numeric_fields = ("anio_publicacion", "stock", "formato_id", "categoria_id")
            for key in numeric_fields:
                value = fields[key].get().strip()
                if value:
                    data[key] = int(value)
            price = fields["precio"].get().strip()
            if price:
                data["precio"] = float(price)
            return data

        def put() -> None:
            self.run_request(lambda: self.api.update_book(fields["id"].get().strip(), values(), "PUT"), lambda result: self.show_operation_result(output, result))

        def patch() -> None:
            try:
                price = float(fields["precio"].get())
            except ValueError:
                messagebox.showwarning("Dato inválido", "Escribe un precio válido para PATCH.")
                return
            self.run_request(lambda: self.api.update_book(fields["id"].get().strip(), {"precio": price}, "PATCH"), lambda result: self.show_operation_result(output, result))

        def remove() -> None:
            if messagebox.askyesno("Confirmar eliminación", "¿Deseas eliminar este libro del servicio remoto?"):
                self.run_request(lambda: self.api.delete_book(fields["id"].get().strip()), lambda result: self.show_operation_result(output, result))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="PUT · Actualización completa", command=put).pack(side="left", padx=3)
        ttk.Button(buttons, text="PATCH · Solo precio", command=patch).pack(side="left", padx=3)
        ttk.Button(buttons, text="DELETE · Eliminar", command=remove).pack(side="left", padx=3)
        ttk.Button(frame, text="Volver", command=self.show_book_admin).pack(pady=8)

    def show_profile(self) -> None:
        frame = self.frame()
        self.heading(frame, "Editar perfil", "Esta pantalla llama PATCH /profile. Si el microservicio aún no expone ese endpoint, se mostrará HTTP 404.")
        form = ttk.Frame(frame)
        form.pack(pady=10)
        fields = {
            "nombre": self.field(form, "Nombre"),
            "apellido_paterno": self.field(form, "Apellido paterno"),
            "apellido_materno": self.field(form, "Apellido materno"),
        }

        def submit() -> None:
            data = {key: entry.get().strip() for key, entry in fields.items() if entry.get().strip()}
            if not data:
                messagebox.showwarning("Datos incompletos", "Escribe al menos un campo.")
                return
            self.run_request(lambda: self.api.update_profile(data), lambda result: self.profile_updated(result))

        ttk.Button(form, text="Guardar cambios", command=submit).pack(fill="x", pady=(14, 6))
        ttk.Button(form, text="Volver", command=self.show_dashboard).pack(fill="x")

    def profile_updated(self, result: Any) -> None:
        messagebox.showinfo("Perfil actualizado", json.dumps(result, ensure_ascii=False, indent=2))
        self.show_dashboard()

    def show_books(self) -> None:
        frame = self.frame()
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Catálogo de libros", font=("TkDefaultFont", 20, "bold")).pack(side="left")
        ttk.Button(top, text="Volver", command=self.show_dashboard).pack(side="right")
        ttk.Label(frame, text=f"Endpoint: {self.api.books_url}").pack(anchor="w", pady=(6, 10))
        filters = ttk.Frame(frame)
        filters.pack(fill="x", pady=(0, 10))
        filter_fields = {key: self.field(filters, label) for key, label in [("isbn", "ISBN"), ("title", "Título"), ("year", "Año"), ("min_price", "Precio mínimo"), ("max_price", "Precio máximo")]}
        def search() -> None:
            params = {}
            if filter_fields["isbn"].get().strip():
                params["isbn"] = filter_fields["isbn"].get().strip()
            if filter_fields["title"].get().strip():
                params["titulo"] = filter_fields["title"].get().strip()
            if filter_fields["year"].get().strip():
                params["anio_publicacion"] = filter_fields["year"].get().strip()
            self.book_filters = {key: entry.get().strip() for key, entry in filter_fields.items() if entry.get().strip()}
            self.run_request(lambda: self.api.get_books(params), self.render_books)

        self.book_filters = {}
        ttk.Button(filters, text="Buscar / actualizar", command=search).pack(anchor="w", pady=5)

        columns = ("isbn", "title", "author", "genre", "year", "price", "stock", "format", "category", "image")
        table = ttk.Treeview(frame, columns=columns, show="headings")
        labels = {"isbn": "ISBN", "title": "Título", "author": "Autor", "genre": "Género", "year": "Año", "price": "Precio", "stock": "Existencia", "format": "Formato", "category": "Categoría", "image": "Imagen"}
        for column in columns:
            table.heading(column, text=labels[column])
            table.column(column, width=140 if column in ("title", "author", "image") else 90)
        table.pack(fill="both", expand=True)
        self.books_table = table
        self.run_request(self.api.get_books, self.render_books)
        table.bind("<Double-1>", lambda _: self.show_book_detail(table))

    def show_book_detail(self, table: ttk.Treeview) -> None:
        selected = table.selection()
        if not selected:
            return
        values = table.item(selected[0], "values")
        isbn = values[0] if values else ""
        if not isbn or isbn == "N/A":
            messagebox.showwarning("Detalle", "El libro seleccionado no tiene ISBN.")
            return
        def show_detail(data: Any) -> None:
            messagebox.showinfo("Detalle del libro", json.dumps(data, ensure_ascii=False, indent=2))

        self.run_request(lambda: self.api.get_book(isbn), show_detail)

    def render_books(self, payload: Any) -> None:
        table = getattr(self, "books_table", None)
        if table is None:
            return
        rows = self.extract_book_rows(payload)
        active_filters = getattr(self, "book_filters", {})
        rows = self.filter_book_rows(rows, active_filters)
        for item in table.get_children():
            table.delete(item)
        for book in rows:
            if not isinstance(book, dict):
                continue
            table.insert("", "end", values=(
                book.get("isbn", "N/A"),
                book.get("title", book.get("titulo", "Sin título")),
                book.get("author", book.get("autor", "Desconocido")),
                book.get("genre", book.get("genero", "N/A")),
                book.get("year", book.get("anio_publicacion", "N/A")),
                book.get("price", book.get("precio", "N/A")),
                book.get("stock", "N/A"),
                book.get("format", book.get("formato_id", "N/A")),
                book.get("category", book.get("categoria_id", "N/A")),
                "Sin imagen" if not book.get("image") else "Disponible",
            ))
        if not rows:
            messagebox.showinfo("Catálogo", "No se encontraron libros con los criterios indicados o el servicio devolvió un formato vacío.")

    @staticmethod
    def extract_book_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("books", "libros", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # Permite mostrar respuestas que representan un único libro.
        if any(key in payload for key in ("isbn", "titulo", "title", "id")):
            return [payload]
        return []

    @staticmethod
    def filter_book_rows(rows: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
        def value(book: dict[str, Any], *keys: str) -> str:
            return next((str(book[key]) for key in keys if book.get(key) is not None), "")

        result = []
        for book in rows:
            if filters.get("isbn") and filters["isbn"].lower() not in value(book, "isbn").lower():
                continue
            if filters.get("title") and filters["title"].lower() not in value(book, "title", "titulo").lower():
                continue
            if filters.get("year") and filters["year"] != value(book, "year", "anio_publicacion"):
                continue
            try:
                price = float(value(book, "price", "precio") or 0)
                if filters.get("min_price") and price < float(filters["min_price"]):
                    continue
                if filters.get("max_price") and price > float(filters["max_price"]):
                    continue
            except ValueError:
                continue
            result.append(book)
        return result

    def show_settings(self) -> None:
        frame = self.frame()
        self.heading(frame, "Configuración", "Las URLs se guardan localmente en ~/.libreria_cliente.json.")
        form = ttk.Frame(frame)
        form.pack(fill="x", padx=30)
        campos = [
            ("auth_url", "URL de autenticación (login)"),
            ("books_url", "URL de libros (books)"),
            ("users_url", "URL de usuarios (users)"),
            ("authors_url", "URL de autores (authors)"),
            ("pedidos_url", "URL de pedidos (pedidos)"),
            ("pagos_url", "URL de pagos (pagos)"),
        ]
        entries = {key: self.field(form, label, self.config.get(key, "")) for key, label in campos}

        def save() -> None:
            nueva = {key: entry.get().strip() for key, entry in entries.items()}
            if not nueva["auth_url"] or not nueva["books_url"]:
                messagebox.showwarning("URLs requeridas", "Autenticación y libros son obligatorias.")
                return
            self.config = {key: (val.rstrip("/") if key == "auth_url" else val)
                           for key, val in nueva.items()}
            save_config(self.config)
            self.api = ApiClient(**self.config)
            messagebox.showinfo("Configuración guardada", "Las URLs fueron actualizadas.")
            self.show_login()

        ttk.Button(form, text="Guardar", command=save).pack(fill="x", pady=(14, 6))
        ttk.Button(form, text="Cancelar", command=self.show_login).pack(fill="x")

    @staticmethod
    def field(parent: tk.Widget, label: str, value: str = "", masked: bool = False) -> ttk.Entry:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(7, 2))
        entry = ttk.Entry(parent, width=60, show="*" if masked else "")
        if value:
            entry.insert(0, value)
        entry.pack(fill="x")
        return entry

    # ------------------------------------------------------------------
    # Infraestructura reutilizable para las pantallas CRUD
    # ------------------------------------------------------------------
    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _extract_rows(payload: Any, list_key: str | None) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            if list_key and isinstance(payload.get(list_key), list):
                return [r for r in payload[list_key] if isinstance(r, dict)]
            for key in ("usuarios", "autores", "pedidos", "pagos", "roles",
                        "data", "items", "results"):
                if isinstance(payload.get(key), list):
                    return [r for r in payload[key] if isinstance(r, dict)]
        return []

    def _crud_screen(self, spec: dict[str, Any]) -> None:
        """Pantalla CRUD genérica (listar/crear/actualizar/eliminar) con JWT."""
        frame = self.frame()
        self.heading(frame, spec["title"], spec.get("subtitle", ""))
        columns = spec["columns"]
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=9)
        for key, header, width in columns:
            table.heading(key, text=header)
            table.column(key, width=width, anchor="w")
        table.pack(fill="both", expand=True, pady=(4, 8))
        spec["_rows"] = []

        def load() -> None:
            def ok(payload: Any) -> None:
                rows = self._extract_rows(payload, spec.get("list_key"))
                spec["_rows"] = rows
                table.delete(*table.get_children())
                for row in rows:
                    table.insert("", "end", values=[self._cell(row.get(k, "")) for k, _h, _w in columns])
                if not rows:
                    messagebox.showinfo(spec["title"], "Sin registros para mostrar.")
            self.run_request(spec["list_fn"], ok)

        def selected_row() -> dict[str, Any] | None:
            sel = table.selection()
            if not sel:
                return None
            idx = table.index(sel[0])
            rows = spec.get("_rows", [])
            return rows[idx] if idx < len(rows) else None

        form = ttk.LabelFrame(frame, text="Datos (deja vacío lo que no quieras cambiar)", padding=10)
        form.pack(fill="x", pady=(0, 8))
        entries: dict[str, ttk.Entry] = {}
        for key, label, kind in spec.get("form_fields", []):
            entries[key] = self.field(form, label, masked=(kind == "password"))

        def build_data() -> dict[str, Any]:
            data: dict[str, Any] = {}
            for key, label, kind in spec.get("form_fields", []):
                raw = entries[key].get().strip()
                if raw == "":
                    continue
                try:
                    data[key] = int(raw) if kind == "int" else float(raw) if kind == "float" else raw
                except ValueError:
                    messagebox.showwarning("Dato inválido", f"'{label}' debe ser numérico.")
                    raise
            return data

        def fill_form(row: dict[str, Any]) -> None:
            for key, _label, _kind in spec.get("form_fields", []):
                entries[key].delete(0, "end")
                val = row.get(key)
                if val is not None:
                    entries[key].insert(0, str(val))

        def create() -> None:
            try:
                data = build_data()
            except ValueError:
                return
            if not data:
                messagebox.showwarning("Sin datos", "Completa al menos un campo.")
                return
            self.run_request(lambda: spec["create_fn"](data),
                             lambda _r: (messagebox.showinfo(spec["title"], "Creado correctamente."), load()))

        def update() -> None:
            row = selected_row()
            if row is None:
                messagebox.showwarning("Selecciona", "Elige un registro de la tabla.")
                return
            id_value = row.get(spec["id_key"])
            try:
                data = build_data()
            except ValueError:
                return
            if not data:
                messagebox.showwarning("Sin datos", "Completa al menos un campo a cambiar.")
                return
            self.run_request(lambda: spec["update_fn"](id_value, data, spec.get("update_method", "PUT")),
                             lambda _r: (messagebox.showinfo(spec["title"], "Actualizado correctamente."), load()))

        def delete() -> None:
            row = selected_row()
            if row is None:
                messagebox.showwarning("Selecciona", "Elige un registro de la tabla.")
                return
            id_value = row.get(spec["id_key"])
            if not messagebox.askyesno("Confirmar", f"¿Eliminar el registro {id_value}?"):
                return
            self.run_request(lambda: spec["delete_fn"](id_value),
                             lambda _r: (messagebox.showinfo(spec["title"], "Eliminado correctamente."), load()))

        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        ttk.Button(bar, text="Refrescar", command=load).pack(side="left", padx=3)
        ttk.Button(bar, text="Crear", command=create).pack(side="left", padx=3)
        ttk.Button(bar, text="Actualizar", command=update).pack(side="left", padx=3)
        ttk.Button(bar, text="Eliminar", command=delete).pack(side="left", padx=3)
        for label, action in spec.get("extra_actions", []):
            def run_action(action=action) -> None:
                row = selected_row()
                if row is None:
                    messagebox.showwarning("Selecciona", "Elige un registro de la tabla.")
                    return
                action(row)
            ttk.Button(bar, text=label, command=run_action).pack(side="left", padx=3)
        ttk.Button(frame, text="Volver", command=self.show_dashboard).pack(pady=6)

        table.bind("<Double-1>", lambda _e: (fill_form(r) if (r := selected_row()) else None))
        load()

    # ------------------------------------------------------------------
    # Users :5003
    # ------------------------------------------------------------------
    def show_users(self) -> None:
        self._crud_screen({
            "title": "Usuarios",
            "subtitle": "GET /users exige JWT y rol Administrador. Crear/editar/eliminar usan Bearer.",
            "list_fn": self.api.list_users,
            "list_key": "usuarios",
            "id_key": "id_usuario",
            "columns": [("id_usuario", "ID", 60), ("email", "Correo", 220),
                        ("nombre", "Nombre", 140), ("apellido_paterno", "Ap. paterno", 130),
                        ("apellido_materno", "Ap. materno", 130), ("rol", "Rol", 150),
                        ("id_rol", "id_rol", 60), ("verificado", "Verificado", 90)],
            "form_fields": [("email", "Correo", "text"), ("password", "Contraseña", "password"),
                            ("nombre", "Nombre", "text"), ("apellido_paterno", "Apellido paterno", "text"),
                            ("apellido_materno", "Apellido materno", "text"), ("id_rol", "ID de rol", "int")],
            "create_fn": self.api.create_user,
            "update_fn": self.api.update_user,
            "delete_fn": self.api.delete_user,
        })

    # ------------------------------------------------------------------
    # Authors :5004
    # ------------------------------------------------------------------
    def show_authors(self) -> None:
        def ver_libros(row: dict[str, Any]) -> None:
            self.run_request(lambda: self.api.author_books(row["id_autor"]),
                             lambda data: messagebox.showinfo(
                                 "Libros del autor", json.dumps(data, ensure_ascii=False, indent=2)))

        self._crud_screen({
            "title": "Autores",
            "subtitle": "GET /authors es público; crear/editar/eliminar exigen Bearer.",
            "list_fn": self.api.list_authors,
            "list_key": "autores",
            "id_key": "id_autor",
            "columns": [("id_autor", "ID", 60), ("nombre_autor", "Nombre", 300),
                        ("libros", "# Libros", 90)],
            "form_fields": [("nombre_autor", "Nombre del autor", "text")],
            "create_fn": self.api.create_author,
            "update_fn": self.api.update_author,
            "delete_fn": self.api.delete_author,
            "extra_actions": [("Ver libros", ver_libros)],
        })

    # ------------------------------------------------------------------
    # Pedidos :5005
    # ------------------------------------------------------------------
    def show_orders(self) -> None:
        frame = self.frame()
        self.heading(frame, "Pedidos", "Crear descuenta stock; PATCH /estado avanza la máquina de estados; DELETE cancela (solo pendiente). Todas exigen Bearer.")
        columns = [("id_pedido", "ID", 60), ("id_usuario", "Usuario", 80),
                   ("estado", "Estado", 110), ("total", "Total", 90), ("creado_en", "Creado", 170)]
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=8)
        for key, header, width in columns:
            table.heading(key, text=header)
            table.column(key, width=width, anchor="w")
        table.pack(fill="both", expand=True, pady=(4, 8))
        self._orders_rows: list[dict[str, Any]] = []

        def load() -> None:
            def ok(payload: Any) -> None:
                self._orders_rows = self._extract_rows(payload, "pedidos")
                table.delete(*table.get_children())
                for row in self._orders_rows:
                    table.insert("", "end", values=[self._cell(row.get(k, "")) for k, _h, _w in columns])
                if not self._orders_rows:
                    messagebox.showinfo("Pedidos", "Sin pedidos para mostrar.")
            self.run_request(self.api.list_orders, ok)

        def selected() -> dict[str, Any] | None:
            sel = table.selection()
            if not sel:
                return None
            idx = table.index(sel[0])
            return self._orders_rows[idx] if idx < len(self._orders_rows) else None

        def detalle(row: dict[str, Any]) -> None:
            self.run_request(lambda: self.api.get_order(row["id_pedido"]),
                             lambda data: messagebox.showinfo(
                                 f"Pedido {row['id_pedido']}", json.dumps(data, ensure_ascii=False, indent=2)))

        def cambiar_estado(row: dict[str, Any]) -> None:
            nuevo = simpledialog.askstring("Cambiar estado",
                                           "Nuevo estado (pendiente, pagado, enviado, entregado, cancelado):")
            if not nuevo:
                return
            self.run_request(lambda: self.api.change_order_state(row["id_pedido"], nuevo.strip()),
                             lambda _r: (messagebox.showinfo("Pedidos", "Estado actualizado."), load()))

        def cancelar(row: dict[str, Any]) -> None:
            if not messagebox.askyesno("Cancelar", f"¿Cancelar el pedido {row['id_pedido']}?"):
                return
            self.run_request(lambda: self.api.cancel_order(row["id_pedido"]),
                             lambda _r: (messagebox.showinfo("Pedidos", "Pedido cancelado."), load()))

        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        ttk.Button(bar, text="Refrescar", command=load).pack(side="left", padx=3)
        ttk.Button(bar, text="Crear pedido", command=lambda: self.show_create_order(load)).pack(side="left", padx=3)
        ttk.Button(bar, text="Cambiar estado",
                   command=lambda: (cambiar_estado(r) if (r := selected()) else messagebox.showwarning("Selecciona", "Elige un pedido."))).pack(side="left", padx=3)
        ttk.Button(bar, text="Cancelar",
                   command=lambda: (cancelar(r) if (r := selected()) else messagebox.showwarning("Selecciona", "Elige un pedido."))).pack(side="left", padx=3)
        ttk.Button(bar, text="Detalle",
                   command=lambda: (detalle(r) if (r := selected()) else messagebox.showwarning("Selecciona", "Elige un pedido."))).pack(side="left", padx=3)
        ttk.Button(frame, text="Volver", command=self.show_dashboard).pack(pady=6)
        load()

    def show_create_order(self, on_done: Any) -> None:
        frame = self.frame()
        self.heading(frame, "Crear pedido", "Cada línea: ISBN y cantidad. El stock se descuenta al crear.")
        form = ttk.Frame(frame)
        form.pack(fill="x", padx=20)
        usuario = self.field(form, "ID de usuario (opcional; por omisión el del token)")
        ttk.Label(form, text="Líneas del pedido (ISBN,cantidad por línea)").pack(anchor="w", pady=(10, 2))
        lineas = tk.Text(form, height=7, wrap="word")
        lineas.insert("1.0", "978-000-000-01-0,1")
        lineas.pack(fill="both", expand=True)

        def enviar() -> None:
            items: list[dict[str, Any]] = []
            for raw in lineas.get("1.0", "end").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                partes = [p.strip() for p in raw.split(",")]
                if len(partes) != 2 or not partes[1].isdigit():
                    messagebox.showwarning("Línea inválida", f"Usa el formato ISBN,cantidad: '{raw}'")
                    return
                items.append({"isbn": partes[0], "cantidad": int(partes[1])})
            if not items:
                messagebox.showwarning("Sin líneas", "Agrega al menos una línea.")
                return
            uid_raw = usuario.get().strip()
            uid = int(uid_raw) if uid_raw.isdigit() else None
            self.run_request(lambda: self.api.create_order(items, uid),
                             lambda _r: (messagebox.showinfo("Pedidos", "Pedido creado."), on_done()))

        ttk.Button(form, text="Crear pedido", command=enviar).pack(fill="x", pady=(14, 6))
        ttk.Button(form, text="Volver", command=self.show_orders).pack(fill="x")

    # ------------------------------------------------------------------
    # Pagos :5006
    # ------------------------------------------------------------------
    def show_payments(self) -> None:
        frame = self.frame()
        self.heading(frame, "Pagos", "Registrar un pago; si cubre el total, el pedido pasa a 'pagado'. Todas las operaciones exigen Bearer.")
        columns = [("id_pago", "ID", 60), ("id_pedido", "Pedido", 80),
                   ("monto", "Monto", 90), ("metodo", "Método", 120),
                   ("estado", "Estado", 110), ("creado_en", "Creado", 170)]
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=8)
        for key, header, width in columns:
            table.heading(key, text=header)
            table.column(key, width=width, anchor="w")
        table.pack(fill="both", expand=True, pady=(4, 8))
        self._pagos_rows: list[dict[str, Any]] = []

        def load() -> None:
            def ok(payload: Any) -> None:
                self._pagos_rows = self._extract_rows(payload, "pagos")
                table.delete(*table.get_children())
                for row in self._pagos_rows:
                    table.insert("", "end", values=[self._cell(row.get(k, "")) for k, _h, _w in columns])
                if not self._pagos_rows:
                    messagebox.showinfo("Pagos", "Sin pagos para mostrar.")
            self.run_request(self.api.list_payments, ok)

        def por_pedido() -> None:
            pid = simpledialog.askinteger("Pagos por pedido", "ID del pedido:")
            if not pid:
                return
            self.run_request(lambda: self.api.order_payments(pid),
                             lambda data: messagebox.showinfo(
                                 f"Pagos del pedido {pid}", json.dumps(data, ensure_ascii=False, indent=2)))

        form = ttk.LabelFrame(frame, text="Registrar pago", padding=10)
        form.pack(fill="x", pady=(6, 8))
        pedido = self.field(form, "ID del pedido")
        monto = self.field(form, "Monto")
        metodo = self.field(form, "Método (tarjeta, efectivo, transferencia, oxxo)")

        def registrar() -> None:
            try:
                data = {"id_pedido": int(pedido.get()), "monto": float(monto.get()),
                        "metodo": metodo.get().strip() or "tarjeta"}
            except ValueError:
                messagebox.showwarning("Dato inválido", "Pedido debe ser entero y monto numérico.")
                return
            self.run_request(lambda: self.api.create_payment(data),
                             lambda _r: (messagebox.showinfo("Pagos", "Pago registrado."), load()))

        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        ttk.Button(bar, text="Refrescar", command=load).pack(side="left", padx=3)
        ttk.Button(bar, text="Registrar pago", command=registrar).pack(side="left", padx=3)
        ttk.Button(bar, text="Pagos por pedido", command=por_pedido).pack(side="left", padx=3)
        ttk.Button(frame, text="Volver", command=self.show_dashboard).pack(pady=6)
        load()


if __name__ == "__main__":
    root = tk.Tk()
    ClientApp(root)
    root.mainloop()
