 library-monolith/
├── config/
│   ├── database.js          # Pool de conexiones pg y configuración de parámetros
│   └── session.js           # Almacenamiento y configuración segura de cookies de sesión
├── controllers/
│   ├── authController.js    # Lógica de flujo para login, registro y logout
│   ├── bookController.js    # Coordinación de peticiones del catálogo y vistas de detalle
│   └── adminController.js   # Acciones restringidas de edición, carga y eliminación
├── middleware/
│   ├── authenticate.js      # Verificación de sesión activa
│   ├── authorize.js         # Validación de privilegios por rol (RBAC)
│   ├── upload.js            # Interceptor Multer con filtrado de tipo de archivo
│   └── errorHandler.js      # Captura global de excepciones con sanitización de trazas
├── services/
│   ├── bookService.js       # Reglas de negocio y orquestación de transacciones
│   ├── authService.js       # Criptografía, validación de contraseñas y unicidad de Admin
│   └── fileService.js       # Manejo físico de imágenes en sistema de archivos
├── routes/
│   ├── authRoutes.js        # /library/auth/*
│   ├── bookRoutes.js        # /library/books/*
│   └── adminRoutes.js       # /library/admin/*
├── views/
│   ├── layouts/
│   │   └── main.ejs         # Plantilla maestra con navbar, footer y alerts
│   ├── books/
│   │   ├── index.ejs        # Galería del catálogo con buscador y filtros
│   │   └── detail.ejs       # Ficha técnica completa del libro e imágenes asociadas
│   └── admin/
│       ├── form.ejs         # Formulario de alta/edición de libros con multiselect
│       └── dashboard.ejs    # Consola de administración
├── public/
│   ├── css/                 # Hojas de estilo estáticas
│   └── js/                  # Scripts cliente auxiliares
├── uploads/                 # Directorio aislado para almacenamiento de imágenes
├── data/
│   ├── schema.sql           # Definición de DDL, índices y triggers de 4FN
│   └── seed.sql             # Datos iniciales para pruebas reproducibles
├── .env.example             # Plantilla de variables de entorno (sin credenciales)
├── app.js                   # Inicialización de la aplicación Express y middlewares
└── package.json             # Dependencias del proyecto