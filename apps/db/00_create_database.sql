-- db/00_create_database.sql
-- Crea la base de datos y el usuario de aplicación en PostgreSQL.
--
-- Uso (como superusuario de PostgreSQL):
--     psql -U postgres -f 00_create_database.sql
--
-- Credenciales canónicas del proyecto (ver .env de cada microservicio):
--     base de datos : library
--     usuario       : library_user
--     contraseña    : library666
--
-- Para cambiar la contraseña más adelante:
--     psql -U postgres -c "ALTER ROLE library_user LOGIN PASSWORD 'nueva_clave';"

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- 1. Base de datos
-- PostgreSQL no admite "CREATE DATABASE IF NOT EXISTS", se emula con \gexec.
-- ---------------------------------------------------------------------------
SELECT 'CREATE DATABASE library'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'library')\gexec

-- ---------------------------------------------------------------------------
-- 2. Usuario de aplicación (rol con permiso de login)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'library_user') THEN
        CREATE ROLE library_user LOGIN PASSWORD 'library666';
    ELSE
        ALTER ROLE library_user LOGIN PASSWORD 'library666';
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Privilegios
-- GRANT sobre la base de datos se concede desde fuera; los objetos (esquema
-- public) se conceden tras conectarse a la base de datos.
-- ---------------------------------------------------------------------------
GRANT ALL PRIVILEGES ON DATABASE library TO library_user;

\connect library

GRANT ALL ON SCHEMA public TO library_user;
ALTER SCHEMA public OWNER TO library_user;

\echo 'Base de datos library y usuario library_user listos.'
\echo 'Continúa con:  psql -U library_user -d library -f 01_schema.sql'
