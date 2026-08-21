1. Diseña una base de datos para una aplicación web monilítica que gestione una librería en línea mediante aceso directo a PostgreSQL.

3. El diseño debe contemplar la administración de usuarios registrados y manejar imágenes.

3. El diseño debe conservar definiciones de conceptos asociadas a cada libro.

4. El diseño base debe partir que todo libro sea la tabla principal de la base de datos. 

5. Un libro puede tener varios autores.

6. Un libro puede pertenecer a varios géneros.

7. UN libro opuede definir muchos conceptos y un mismo concepto puede aparecer en distintos libros con definiciones diferentes.

8. Un libro puede tener varias imágenes.

9. Formato y categoría son catálogos independientes.

10. Debe existir como máximo un administrador.

11. Utiliza el patrón arquitectónico macro-arquitectura monolítica.

12. Utiliza el patrón de diseño MVC (Modelo Vista Controlador) para la GUI.

13. Aplica el enfoque de organización de código modular (por módulos).

14. Utiliza el esquema de base de datos de Postgres del archivo /data/db_schema.sql

15. Crea un archivo README.md con la lógica del sistema e incluye los pasos para ejecutar, replicar y desplegar el sistema en un sistema Linux Cent0S 10 Stream; anexa también la configuración de la base de datos de postgres usando el usuario: 'library_user' con password '999' con la base de datos 'library'.