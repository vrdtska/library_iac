BEGIN;

-- Catálogos independientes
CREATE TABLE IF NOT EXISTS categorias (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS formatos (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS autores (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    apellido VARCHAR(150),
    bio TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS generos (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conceptos (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE,
    descripcion TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tabla principal: libro
CREATE TABLE IF NOT EXISTS libros (
    id BIGSERIAL PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    subtitulo VARCHAR(255),
    isbn VARCHAR(20) UNIQUE,
    anio_publicacion SMALLINT CHECK (anio_publicacion BETWEEN 0 AND 9999),
    descripcion TEXT,
    precio NUMERIC(10,2) CHECK (precio >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    formato_id BIGINT NOT NULL REFERENCES formatos(id) ON DELETE RESTRICT,
    categoria_id BIGINT NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Relación muchos a muchos: un libro puede tener varios autores
CREATE TABLE IF NOT EXISTS libros_autores (
    libro_id BIGINT NOT NULL REFERENCES libros(id) ON DELETE CASCADE,
    autor_id BIGINT NOT NULL REFERENCES autores(id) ON DELETE RESTRICT,
    orden SMALLINT NOT NULL DEFAULT 1 CHECK (orden > 0),
    PRIMARY KEY (libro_id, autor_id)
);

-- Relación muchos a muchos: un libro pertenece a varios géneros
CREATE TABLE IF NOT EXISTS libros_generos (
    libro_id BIGINT NOT NULL REFERENCES libros(id) ON DELETE CASCADE,
    genero_id BIGINT NOT NULL REFERENCES generos(id) ON DELETE RESTRICT,
    PRIMARY KEY (libro_id, genero_id)
);

-- Un mismo concepto puede aparecer en distintos libros con definiciones diferentes
CREATE TABLE IF NOT EXISTS libros_conceptos (
    id BIGSERIAL PRIMARY KEY,
    libro_id BIGINT NOT NULL REFERENCES libros(id) ON DELETE CASCADE,
    concepto_id BIGINT NOT NULL REFERENCES conceptos(id) ON DELETE RESTRICT,
    definicion TEXT NOT NULL,
    orden SMALLINT NOT NULL DEFAULT 1 CHECK (orden > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (libro_id, concepto_id)
);

-- Gestión de usuarios registrados
CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100),
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Un máximo de un administrador
CREATE UNIQUE INDEX IF NOT EXISTS ux_unico_admin
    ON usuarios ((1))
    WHERE is_admin IS TRUE;

-- Imágenes asociadas a cada libro
CREATE TABLE IF NOT EXISTS libros_imagenes (
    id BIGSERIAL PRIMARY KEY,
    libro_id BIGINT NOT NULL REFERENCES libros(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    alt_text VARCHAR(255),
    es_portada BOOLEAN NOT NULL DEFAULT FALSE,
    orden SMALLINT NOT NULL DEFAULT 1 CHECK (orden > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices para búsquedas frecuentes
CREATE INDEX IF NOT EXISTS idx_libros_titulo ON libros (titulo);
CREATE INDEX IF NOT EXISTS idx_libros_formato ON libros (formato_id);
CREATE INDEX IF NOT EXISTS idx_libros_categoria ON libros (categoria_id);
CREATE INDEX IF NOT EXISTS idx_libros_autores_libro ON libros_autores (libro_id);
CREATE INDEX IF NOT EXISTS idx_libros_autores_autor ON libros_autores (autor_id);
CREATE INDEX IF NOT EXISTS idx_libros_generos_libro ON libros_generos (libro_id);
CREATE INDEX IF NOT EXISTS idx_libros_generos_genero ON libros_generos (genero_id);
CREATE INDEX IF NOT EXISTS idx_libros_conceptos_libro ON libros_conceptos (libro_id);
CREATE INDEX IF NOT EXISTS idx_libros_conceptos_concepto ON libros_conceptos (concepto_id);
CREATE INDEX IF NOT EXISTS idx_libros_imagenes_libro ON libros_imagenes (libro_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios (email);
CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios (username);

-- Trigger para actualizar updated_at en libros y usuarios
CREATE OR REPLACE FUNCTION actualizar_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_libros_updated_at
BEFORE UPDATE ON libros
FOR EACH ROW
EXECUTE FUNCTION actualizar_timestamp();

CREATE TRIGGER trg_usuarios_updated_at
BEFORE UPDATE ON usuarios
FOR EACH ROW
EXECUTE FUNCTION actualizar_timestamp();

COMMIT;
