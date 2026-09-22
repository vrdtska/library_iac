-- db/00_create_database.sql
-- Ejecutar como usuario 'postgres' (superusuario)

-- 1. Crear base de datos
CREATE DATABASE library_db;

-- 2. Crear usuario de aplicación
CREATE USER library_app WITH ENCRYPTED PASSWORD 'SecurePass123!';

-- 3. Otorgar privilegios mínimos necesarios al usuario sobre la base de datos
GRANT ALL PRIVILEGES ON DATABASE library_db TO library_app;
ALTER DATABASE library_db OWNER TO library_app;

-- Nota: Las tablas y el esquema (01_schema.sql) deben ejecutarse 
-- conectándose directamente a la base de datos 'library_db' con el usuario 'library_app'.
