# Catalogo de Libros - Cliente Electron

Aplicacion de escritorio que consume **unicamente XML** del microservicio Flask de
libros (`apps/services/soap/app.py`) y muestra el catalogo en cards: imagen, titulo,
autores, anio de publicacion, ISBN y precio.

## 1. Requisitos

- Node.js LTS (20 o superior): <https://nodejs.org/>
- El microservicio de libros corriendo (por defecto en el puerto **5001**)

## 2. Ejecutar en Windows 11

1. Abre **PowerShell** o el **Simbolo del sistema**.
2. Ve a la carpeta de la aplicacion:

   ```powershell
   cd "C:\ruta\de\tu\proyecto\libreria_eg\apps\Electron_app"
   ```

3. Instala las dependencias (solo la primera vez, descarga Electron):

   ```powershell
   npm install
   ```

4. Arranca la aplicacion:

   ```powershell
   npm start
   ```

5. En la ventana, pulsa **"Configurar microservicio"** y escribe:

   | Campo | Ejemplo |
   | --- | --- |
   | URL base del microservicio | `http://10.224.0.2:5001` |
   | Endpoint del catalogo | `/api/libros/minimo` |
   | Libros por pagina | `8` |

   La configuracion se guarda con `localStorage` y se recuerda la proxima vez.

Para empaquetar como instalador `.exe`:

```powershell
npm install --save-dev electron-builder
npx electron-builder --win
```

## 3. Ejecutar en Linux (Fedora)

```bash
cd apps/Electron_app
npm install
npm start
```

En Fedora puede hacer falta arrancarlo en una sesión sin Wayland:

```bash
npm start -- --no-sandbox
```

## 4. Endpoints compatibles

La app solo pide XML. Funciona con cualquiera de estos:

| Endpoint | Que devuelve |
| --- | --- |
| `/api/libros/minimo` | Datos minimos + imagenes (recomendado) |
| `/books` o `/api/libros` | Catalogo completo con generos, formato y conceptos |

Formato del XML esperado (segun `library.xml`):

```xml
<library total="30" page="1" limit="8">
  <book isbn="978-000-000-01-0">
    <title>Libro de Prueba 1</title>
    <authors><author>Ana Ruiz</author><author>Luis Paz</author></authors>
    <publicationYear>2026</publicationYear>
    <price currency="USD">979.78</price>
    <images>
      <image url="http://host:5001/uploads/img_1.svg" isCover="true" altText="Portada"/>
    </images>
  </book>
</library>
```

La app tambien acepta `<year>`, `<author>` plano e `<image>` con la ruta como texto,
por compatibilidad. Las imagenes relativas (`/uploads/...`) se resuelven contra la
URL base configurada.

## 5. Paginacion

Cada cambio de pagina hace una peticion nueva al microservicio
(`?page=N&limit=M`) y el total se lee del atributo `total` del elemento `<library>`.

## 6. CORS

La app corre en el contexto del navegador de Electron, por eso el microservicio
tiene `flask-cors` habilitado y responde `Access-Control-Allow-Origin: *`.
Si cambias el origen, ajusta `CORS(app)` en `app.py`.

## 7. Estructura

```text
apps/Electron_app/
├── main.js        # ventana principal
├── index.html     # interfaz + consumo del XML
├── style.css      # estilos
└── package.json
```

## 8. Nota de seguridad

`main.js` usa `nodeIntegration: true` y `contextIsolation: false` para que el HTML
pueda hacer `fetch` sin depender de APIs propias de Electron. Si en el futuro la app carga contenido remoto,
activa un `preload` con `contextIsolation: true`.
