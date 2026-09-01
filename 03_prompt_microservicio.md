1. Escribe un microservicio en flask (no blueprints) con una conexión a la base de datos Postgres para generar los endpoints necesarios para las operaciones CRUD de libros. Usa la librería psycopg. Deposítalo en /apps/services/soap

2. Usa como referencia el esquema de base de datos en /data/library_schema.sql y el diseño XML de /apps/dservices/soap/library.xml

3. El microservicio debe mostrar todos los libros, buscar por isbn por atributos, modificar, borrar y actualizar libros.

4. Toma en consideracion el problema CORS ya que este microservicio será accedido mediante clientes fuera del dominio.

5. Los datos de la base de datos de postgres son: user: library_user, password: library666, y la base de datos: library. Utiliza estos datos de acceso en un archivo .env, no los expongas en el código.

6. Utiliza Swagger para la documentación del Microservicio.
