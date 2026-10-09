-- db/05_pedidos_pagos.sql
-- Tablas de pedidos y pagos (microservicios pedidos/pagos).
-- Ejecutar conectado a la base 'library':
--     psql -U library_user -d library -f 05_pedidos_pagos.sql
-- Es idempotente: se puede ejecutar mas de una vez.

-- ---------------------------------------------------------------------------
-- Pedidos: cabecera del pedido de un usuario.
-- Estados validos: pendiente -> pagado | cancelado ; pagado -> enviado -> entregado
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pedidos (
    id_pedido  SERIAL PRIMARY KEY,
    id_usuario INT NOT NULL REFERENCES usuarios(id_usuario) ON DELETE RESTRICT,
    estado     VARCHAR(20) NOT NULL DEFAULT 'pendiente'
               CHECK (estado IN ('pendiente','pagado','enviado','entregado','cancelado')),
    total      NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (total >= 0),
    creado_en  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS pedidos_usuario_idx ON pedidos (id_usuario);
CREATE INDEX IF NOT EXISTS pedidos_estado_idx ON pedidos (estado);

CREATE TABLE IF NOT EXISTS pedido_items (
    id_item        SERIAL PRIMARY KEY,
    id_pedido      INT NOT NULL REFERENCES pedidos(id_pedido) ON DELETE CASCADE,
    isbn           VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE RESTRICT,
    cantidad       INT NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(10,2) NOT NULL CHECK (precio_unitario >= 0),
    UNIQUE (id_pedido, isbn)
);
CREATE INDEX IF NOT EXISTS pedido_items_pedido_idx ON pedido_items (id_pedido);

-- ---------------------------------------------------------------------------
-- Pagos: abonos contra un pedido. Cuando la suma cubre el total, el pedido
-- pasa a 'pagado' (lo hace el microservicio de pagos en transaccion).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pagos (
    id_pago   SERIAL PRIMARY KEY,
    id_pedido INT NOT NULL REFERENCES pedidos(id_pedido) ON DELETE CASCADE,
    monto     NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    metodo    VARCHAR(30) NOT NULL DEFAULT 'tarjeta'
              CHECK (metodo IN ('tarjeta','efectivo','transferencia','oxxo')),
    estado    VARCHAR(20) NOT NULL DEFAULT 'completado'
              CHECK (estado IN ('completado','reembolsado')),
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS pagos_pedido_idx ON pagos (id_pedido);

\echo 'Tablas pedidos, pedido_items y pagos listas.'
