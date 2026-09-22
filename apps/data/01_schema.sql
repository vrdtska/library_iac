-- db/01_schema.sql
-- Conectarse a la base de datos 'library_db' antes de ejecutar.

CREATE TABLE roles (
    id_rol SERIAL PRIMARY KEY,
    nombre_rol VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE usuarios (
    id_usuario SERIAL PRIMARY KEY,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    id_rol INT NOT NULL REFERENCES roles(id_rol) ON DELETE RESTRICT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Regla de negocio: Sólo puede existir UN administrador (asumiendo id_rol = 1)
CREATE UNIQUE INDEX unico_administrador_idx ON usuarios(id_rol) WHERE id_rol = 1;

CREATE TABLE formatos (
    id_formato SERIAL PRIMARY KEY,
    nombre_formato VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE categorias (
    id_categoria SERIAL PRIMARY KEY,
    nombre_categoria VARCHAR(100) UNIQUE NOT NULL
);

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

-- Regla de negocio: Sólo puede haber una portada por libro
CREATE UNIQUE INDEX unica_portada_por_libro_idx ON libro_imagenes(isbn) WHERE es_portada = TRUE;
