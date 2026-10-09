-- db/03_migracion_verificado.sql
-- Migración para bases de datos creadas con el esquema anterior.
-- Ejecutar conectado a la base 'library':
--     psql -U library_user -d library -f 03_migracion_verificado.sql
--
-- Es idempotente: se puede ejecutar más de una vez sin efectos secundarios.

-- Columna que consume el microservicio de autenticación (apps/services/login)
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS verificado BOOLEAN NOT NULL DEFAULT FALSE;

-- Perfil 1:1 con la cuenta (el esquema antiguo no lo tenía)
CREATE TABLE IF NOT EXISTS perfiles_usuario (
    id_perfil SERIAL PRIMARY KEY,
    id_usuario INT UNIQUE NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    apellido_paterno VARCHAR(100) NOT NULL,
    apellido_materno VARCHAR(100) NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

\echo 'Migración aplicada: usuarios.verificado y perfiles_usuario listos.'
