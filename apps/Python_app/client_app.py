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
from tkinter import messagebox, ttk
from typing import Any, Callable
import requests


CONFIG_PATH = Path.home() / ".libreria_cliente.json"
SESSION_PATH = Path.home() / ".libreria_cliente_session.json"
# Por defecto, los microservicios locales levantados con apps/run_all.sh.
# Ambas URLs son configurables desde la pantalla de Configuracion o editando
# ~/.libreria_cliente.json.
DEFAULT_AUTH_URL = "http://localhost:5000"
DEFAULT_BOOKS_URL = "http://localhost:5001/books"
TIMEOUT = 10


class ServiceError(Exception):
    """Error HTTP o de transporte presentado al usuario."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Cliente HTTP con cookies de sesión y JWT (Bearer) en el CRUD de libros.

    * El servicio de autenticación entrega ``access_token`` + ``refresh_token``.
    * Toda operación de escritura contra el servicio de libros se envía con
      ``Authorization: Bearer <access_token>``.
    * Si el servidor responde 401 (token caducado) se renueva el token con
      ``POST /refresh`` y se reintenta la operación una sola vez.
    * El servicio de auth sólo recibe Bearer en ``GET /session``; el resto de
      sus endpoints se llaman con la cookie de sesión de Flask.
    """

    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, auth_url: str, books_url: str):
        self.auth_url = auth_url.rstrip("/")
        self.books_url = books_url.strip()
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
        if url.split("?")[0].rstrip("/").endswith("/session"):
            return True  # el servicio de auth acepta Bearer en /session
        if url.startswith(self.auth_url):
            return False  # login, register, refresh, logout: cookie o body
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
        if service == "auth":
            return self.auth("GET", "/health")
        base = self.books_url.split("/books", 1)[0]
        return self.request("GET", f"{base}/api/db-health")


def load_config() -> dict[str, str]:
    try:
        values = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(values, dict):
            return {
                "auth_url": str(values.get("auth_url", DEFAULT_AUTH_URL)),
                "books_url": str(values.get("books_url", DEFAULT_BOOKS_URL)),
            }
    except (OSError, json.JSONDecodeError):
        pass
    return {"auth_url": DEFAULT_AUTH_URL, "books_url": DEFAULT_BOOKS_URL}


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
        self.api = ApiClient(self.config["auth_url"], self.config["books_url"])
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
        result = tk.Text(frame, height=10, state="disabled", wrap="word")
        result.pack(fill="both", expand=True, pady=12)
        self.status_text = result
        ttk.Button(frame, text="Comprobar ahora", command=lambda: self.check_health(result)).pack(pady=(0, 8))

        def write_status(label: str, value: str) -> None:
            result.configure(state="normal")
            result.insert("end", f"{label}: {value}\n")
            result.configure(state="disabled")

        def update_status(label: str, icon: str, detail: str) -> None:
            write_status(label, f"{icon} {detail}")

        def on_auth(data: Any) -> None:
            status = str(data.get("status", "ok")).lower() if isinstance(data, dict) else "ok"
            icon = "🟢" if status == "ok" else "🟡"
            update_status("Login", icon, data.get("message", "Servicio disponible") if isinstance(data, dict) else "Servicio disponible")
            self.run_request(lambda: self.api.health("books"), on_books, lambda exc: update_status("Libros", "🔴", str(exc)))

        def on_books(data: Any) -> None:
            status = str(data.get("status", "ok")).lower() if isinstance(data, dict) else "ok"
            icon = "🟢" if status == "ok" else "🟡"
            update_status("Libros", icon, data.get("message", "Servicio disponible") if isinstance(data, dict) else "Servicio disponible")

        self.check_health(result)
        ttk.Button(frame, text="Volver", command=self.show_dashboard).pack()
        self.health_after_id = self.root.after(30000, lambda: self.check_health(result))

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

        def auth_result(data: Any) -> None:
            append("Login", "🟢" if data.get("status") == "ok" else "🟡", data.get("message", "Disponible"))

        def auth_error(error: ServiceError) -> None:
            append("Login", "🔴", str(error))

        def books_result(data: Any) -> None:
            append("Libros", "🟢" if data.get("status") == "ok" else "🟡", data.get("message", "Disponible"))

        def books_error(error: ServiceError) -> None:
            append("Libros", "🔴", str(error))

        self.run_request(lambda: self.api.health("auth"), auth_result, auth_error)
        self.run_request(lambda: self.api.health("books"), books_result, books_error)

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
        auth = self.field(form, "URL de autenticación", self.config["auth_url"])
        books = self.field(form, "URL de libros", self.config["books_url"])

        def save() -> None:
            auth_url, books_url = auth.get().strip(), books.get().strip()
            if not auth_url or not books_url:
                messagebox.showwarning("URLs requeridas", "Ambas URLs son obligatorias.")
                return
            self.config = {"auth_url": auth_url.rstrip("/"), "books_url": books_url}
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


if __name__ == "__main__":
    root = tk.Tk()
    ClientApp(root)
    root.mainloop()
