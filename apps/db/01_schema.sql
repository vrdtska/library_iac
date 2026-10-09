-- db/01_schema.sql
-- Esquema normalizado de la librería. Conectarse ANTES de ejecutar:
--     psql -U library_user -d library -f 01_schema.sql
--
-- Reglas de negocio incluidas:
--   * 'libros' es la entidad principal (ISBN como clave primaria).
--   * Un libro tiene varios autores, varios géneros y varias imágenes.
--   * Un concepto puede repetirse en distintos libros con definición propia.
--   * 'formatos' y 'categorias' son catálogos independientes.
--   * Existe como máximo un administrador (índice único parcial).

-- ---------------------------------------------------------------------------
-- Control de acceso
-- ---------------------------------------------------------------------------
CREATE TABLE roles (
    id_rol SERIAL PRIMARY KEY,
    nombre_rol VARCHAR(50) UNIQUE NOT NULL
);

-- 'password_hash' vive en la cuenta del usuario: no hay tabla de contraseñas.
-- 'verificado' lo consume el microservicio de autenticación (apps/services/login).
CREATE TABLE usuarios (
    id_usuario SERIAL PRIMARY KEY,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    id_rol INT NOT NULL REFERENCES roles(id_rol) ON DELETE RESTRICT,
    verificado BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Regla de negocio: sólo puede existir UN administrador (id_rol = 1)
CREATE UNIQUE INDEX unico_administrador_idx ON usuarios(id_rol) WHERE id_rol = 1;

-- Perfil 1:1 con la cuenta (normalizado, sin datos personales en 'usuarios')
CREATE TABLE perfiles_usuario (
    id_perfil SERIAL PRIMARY KEY,
    id_usuario INT UNIQUE NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    apellido_paterno VARCHAR(100) NOT NULL,
    apellido_materno VARCHAR(100) NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Catálogos independientes
-- ---------------------------------------------------------------------------
CREATE TABLE formatos (
    id_formato SERIAL PRIMARY KEY,
    nombre_formato VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE categorias (
    id_categoria SERIAL PRIMARY KEY,
    nombre_categoria VARCHAR(100) UNIQUE NOT NULL
);

-- ---------------------------------------------------------------------------
-- Entidades del catálogo
-- ---------------------------------------------------------------------------
CREATE TABLE autores (
    id_autor SERIAL PRIMARY KEY,
    nombre_autor VARCHAR(150) NOT NULL
);

CREATE TABLE generos (
    id_genero SERIAL PRIMARY KEY,
    nombre_genero VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE conceptos (
    id_concepto SERIAL PRIMARY KEY,
    termino VARCHAR(150) UNIQUE NOT NULL
);

CREATE TABLE libros (
    isbn VARCHAR(20) PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    anio INT NOT NULL CHECK (anio >= 1000 AND anio <= 9999),
    precio NUMERIC(10,2) NOT NULL CHECK (precio >= 0),
    stock INT NOT NULL CHECK (stock >= 0),
    id_formato INT NOT NULL REFERENCES formatos(id_formato) ON DELETE RESTRICT,
    id_categoria INT NOT NULL REFERENCES categorias(id_categoria) ON DELETE RESTRICT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE libro_autor (
    isbn VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    id_autor INT NOT NULL REFERENCES autores(id_autor) ON DELETE CASCADE,
    PRIMARY KEY (isbn, id_autor)
);

CREATE TABLE libro_genero (
    isbn VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    id_genero INT NOT NULL REFERENCES generos(id_genero) ON DELETE CASCADE,
    PRIMARY KEY (isbn, id_genero)
);

-- Un mismo concepto puede aparecer en distintos libros con definiciones distintas
CREATE TABLE libro_concepto (
    isbn VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    id_concepto INT NOT NULL REFERENCES conceptos(id_concepto) ON DELETE CASCADE,
    definicion_en_libro TEXT NOT NULL,
    PRIMARY KEY (isbn, id_concepto)
);

CREATE TABLE libro_imagenes (
    id_imagen SERIAL PRIMARY KEY,
    isbn VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    file_path VARCHAR(255) NOT NULL,
    es_portada BOOLEAN DEFAULT FALSE,
    texto_alternativo VARCHAR(255)
);

-- Regla de negocio: sólo una portada por libro
CREATE UNIQUE INDEX unica_portada_por_libro_idx ON libro_imagenes(isbn) WHERE es_portada = TRUE;

-- Índices de apoyo para las búsquedas del microservicio
CREATE INDEX libros_titulo_idx ON libros (titulo);
CREATE INDEX libro_imagenes_isbn_idx ON libro_imagenes (isbn);
