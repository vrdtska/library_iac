-- db/04_refresh_tokens.sql
-- Almacena los refresh tokens emitidos por el microservicio de login para
-- poder revocarlos en /logout y detectar rotaciones (reutilizacion de un jti
-- ya gastado = posible robo del token).
--
-- Ejecutar conectado a la base 'library':
--     psql -U library_user -d library -f 04_refresh_tokens.sql
--
-- Es idempotente: se puede ejecutar mas de una vez.

CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti          UUID PRIMARY KEY,
    id_usuario   INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    emitido_en   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en    TIMESTAMP NOT NULL,
    usado        BOOLEAN NOT NULL DEFAULT FALSE,
    revocado     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS refresh_tokens_usuario_idx ON refresh_tokens (id_usuario);
CREATE INDEX IF NOT EXISTS refresh_tokens_expira_idx  ON refresh_tokens (expira_en);

\echo 'Tabla refresh_tokens lista.'
