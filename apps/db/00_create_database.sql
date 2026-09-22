-- db/00_create_database.sql
-- Ejecutar como usuario 'postgres' (superusuario)

-- 1. Crear base de datos
CREATE DATABASE IF NOT EXISTS library;

-- 2. Crear usuario de aplicación
CREATE USER IF NOT EXISTS library_user WITH ENCRYPTED PASSWORD '999';

-- 3. Otorgar privilegios mínimos necesarios al usuario sobre la base de datos
GRANT ALL PRIVILEGES ON DATABASE library TO library_user;
ALTER DATABASE library OWNER TO library_user;
