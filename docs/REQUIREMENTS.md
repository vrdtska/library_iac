### Requisitos funcionales detallados

* **RF1 - Gestión de Identidad y Sesiones**: Registro de usuarios nuevos (por defecto rol cliente), inicio de sesión con validación de hash criptográfico, manejo de sesiones persistentes en base de datos con expiración y cierre seguro de sesión (*logout* con invalidación de cookie).
* **RF2 - Consulta y Búsqueda Avanzada**: Visualización paginada del catálogo público, filtros dinámicos por género, autor, rango de precios y búsqueda fonética o por subcadena en título e ISBN-13 con índices B-Tree/GIN optimizados.
* **RF3 - Operaciones CRUD Centralizadas**: Creación, consulta, modificación y baja lógica/física de entidades maestras (libros, autores, categorías, formatos y conceptos).
* **RF4 - Manejo de Cardinalidad M:N Compleja**: Asociación atómica y transaccional entre un libro y múltiples autores, múltiples géneros y múltiples etiquetas conceptuales sin redundancia multivaluada.
* **RF5 - Gestión Segura de Archivos (Uploads)**: Carga de portadas con verificación de *magic numbers* (firmas binarias), limitación de tamaño máximo a 2 MB por archivo, almacenamiento en disco bajo nombres UUIDv4 y registro relacional de metadatos.
* **RF6 - Control de Inventario y Precios**: Restricciones de integridad de dominio (`CHECK (stock >= 0)`, `CHECK (price > 0.00)`) con actualización atómica de existencias.
* **RF7 - Control de Acceso y Gestión Administrativa**: Rutas protegidas exclusivas para el usuario Administrador con guardas a nivel de middleware. 