Objetivo: Desarrollar una aplicación de escritorio en Python que funcione como cliente de los microservicios de autenticación y gestión de libros desarrollados durante el curso.

La finalidad de esta actividad no es únicamente construir una interfaz gráfica. El estudiante deberá demostrar que comprende cómo una aplicación cliente se comunica con servicios independientes mediante HTTP, endpoints REST, JSON, sesiones, cookies y códigos de respuesta HTTP. La aplicación deberá almacenarse obligatoriamente en: apps/Python_app  y deberá consumir los microservicios existentes en:  services/login  y  services/books

1. Aplicación de escritorio

Desarrolle una aplicación gráfica utilizando Python 3.10 o superior. Puede utilizar PySide6, Tkinter u otra biblioteca para interfaces gráficas que considere apropiada. La aplicación deberá ejecutarse como una aplicación independiente y comunicarse con los microservicios mediante HTTP. No se deberá acceder directamente desde Python a las bases de datos utilizadas por los microservicios.

Toda consulta o modificación de información deberá realizarse mediante los endpoints correspondientes.

2. Autenticación

Al iniciar la aplicación deberá presentarse una pantalla que permita:

    Registrar un nuevo usuario.
    Iniciar sesión mediante correo electrónico y contraseña.
    Detectar credenciales incorrectas.
    Detectar cuentas que todavía no puedan autenticarse.
    Mostrar mensajes comprensibles ante errores del servicio.
    Mantener la información necesaria de la sesión iniciada.

La aplicación deberá utilizar, según corresponda, los servicios:

    POST /register
    GET /verify
    POST /login
    POST /logout
    GET /session
    POST /session/extend
    PATCH /profile

El estudiante deberá determinar qué endpoint corresponde utilizar en cada operación.

3. Persistencia de la sesión

Una vez autenticado, el usuario no deberá introducir nuevamente sus credenciales simplemente por cerrar y volver a ejecutar la aplicación. La aplicación deberá implementar un mecanismo local apropiado para conservar la información necesaria de la sesión.

Sin embargo, recuerde que: recordar localmente a un usuario no significa que la sesión del servidor continúe siendo válida.

Al iniciar nuevamente la aplicación deberá verificarse con el microservicio si la sesión continúa vigente. Si el servidor indica que la sesión expiró, la aplicación deberá regresar de manera controlada a la pantalla de autenticación. Investigue y decida qué información necesita conservar localmente y cuál debe validarse nuevamente con el servidor.

4. Panel principal

Después de una autenticación correcta deberá mostrarse un panel principal desde el cual puedan accederse las diferentes funciones de la aplicación. El diseño visual queda a criterio del estudiante, pero deberá existir una separación clara entre:

    Sesión y perfil.
    Catálogo de libros.
    Administración de libros.
    Estado de los servicios.
    Configuración del servidor.

La aplicación deberá ser funcional y usable en Windows 11.

5. Estado de los microservicios

El panel principal deberá mostrar visualmente el estado de:

Microservicio de Login

Microservicio de Libros

Utilice el endpoint /health correspondiente.

La aplicación deberá diferenciar al menos tres estados:

    🟢 Servicio funcionando correctamente y con acceso a su base de datos.
    🟡 Servicio accesible, pero con alguna dependencia degradada o base de datos no disponible.
    🔴 Servicio inaccesible, con error de conexión o sin respuesta.

Deberá mostrarse también la fecha y hora de la última comprobación. Incluya una forma de realizar nuevamente la comprobación sin reiniciar la aplicación. Además, la aplicación deberá realizar comprobaciones periódicas mientras se encuentra en ejecución.

6. Prueba obligatoria de tolerancia a fallos

Durante las pruebas deberá provocar deliberadamente al menos las siguientes situaciones:

    Caso A: ambos microservicios disponibles.
    Caso B: detener el microservicio de libros mientras la aplicación continúa ejecutándose.
    Caso C: restaurar el microservicio de libros.
    Caso D: intentar utilizar una URL o puerto incorrecto.

La aplicación no deberá cerrarse inesperadamente en ninguno de estos casos. Documente qué ocurrió y cómo reaccionó su aplicación.

7. Perfil del usuario

El usuario autenticado deberá poder consultar la información asociada con su sesión y modificar los datos permitidos por el microservicio. Deberá ser posible trabajar, según las capacidades actuales del servicio, con:

    Nombre.
    Apellidos.
    Correo electrónico.
    Contraseña.

También deberá implementarse la extensión de sesión. Cuando sea posible determinar que una sesión está próxima a expirar, la interfaz deberá advertir al usuario. No se solicita implementar un CRUD administrativo completo de usuarios debido a que el microservicio actual no proporciona todos los endpoints necesarios para ello.

8. Catálogo de libros

Implemente una sección visual para consultar el catálogo remoto. La información deberá obtenerse mediante el microservicio de libros y no mediante acceso directo a su base de datos. Considere: GET /books?format=json  Cada libro deberá visualizarse de forma organizada mostrando la información disponible, incluyendo:

    ISBN.
    Título.
    Autor o autores.
    Género.
    Año.
    Precio.
    Existencia.
    Formato.
    Categoría.
    Imagen.

Cuando existan varias imágenes, el usuario deberá poder consultarlas. Cuando un libro no tenga imagen, la aplicación deberá indicarlo visualmente sin provocar errores.

9. Búsqueda de libros

El usuario deberá poder localizar libros utilizando diferentes criterios. Como mínimo deberán considerarse búsquedas o filtros relacionados con:

    ISBN.
    Título.
    Año.
    Precio mínimo.
    Precio máximo.

Al seleccionar un libro deberá consultarse su información detallada utilizando: GET /books/{isbn}  El detalle deberá incluir también los conceptos o definiciones que el microservicio tenga asociados al libro.

10. CRUD de libros

La aplicación deberá demostrar el consumo de los siguientes métodos HTTP:

    GET
    POST
    PUT
    PATCH
    DELETE

Para ello deberá utilizar los endpoints disponibles:

    GET /books
    GET /books/{isbn}
    POST /books
    PUT /books/{isbn}
    PATCH /books/{isbn}
    DELETE /books/{isbn}

La interfaz deberá permitir realizar las operaciones necesarias sobre los libros. No se considerará suficiente que los botones aparezcan en pantalla: las operaciones deberán comprobarse contra el microservicio remoto y reflejarse posteriormente en el catálogo. Antes de eliminar información deberá solicitarse confirmación al usuario.

11. Diferencia entre PUT y PATCH

Su implementación deberá demostrar que comprende que PUT y PATCH no representan necesariamente la misma operación. Durante la demostración deberá mostrar:

    Una actualización completa de un libro.
    Una actualización parcial modificando únicamente un atributo.

Deberá explicar brevemente qué información fue enviada al servidor en cada caso y por qué utilizó PUT o PATCH.

12. Manejo de respuestas HTTP

La aplicación deberá interpretar apropiadamente las respuestas recibidas. Durante las pruebas deberán mostrarse ejemplos reales de al menos:

    Una operación correcta.
    Credenciales incorrectas.
    ISBN duplicado.
    Libro inexistente.
    Servicio no disponible.
    Sesión expirada o no válida.

Los mensajes presentados al usuario deberán ser comprensibles. No se deberá mostrar únicamente un traceback de Python como respuesta a un error.

13. Configuración del servidor

La aplicación deberá permitir modificar las direcciones utilizadas para conectarse a los servicios sin cambiar manualmente el código fuente. Deberá existir una pantalla de configuración donde puedan establecerse los datos necesarios para conectarse a los microservicios. La configuración deberá:

    Poder modificarse.
    Poder probarse.
    Poder guardarse.
    Persistir después de cerrar la aplicación.
    Permitir restaurar los valores predeterminados.

La solución deberá funcionar tanto con servicios ejecutándose localmente como con los servicios desplegados en la infraestructura utilizada durante el curso. Por ejemplo, durante desarrollo podrán utilizarse:

http://localhost:5000

http://localhost:5001

Pera el ejercicios deberá estar en una instancia y la aplicación deberá construir correctamente las direcciones utilizadas en las peticiones.

14. Prueba local y remota

La misma aplicación deberá poder ejecutarse utilizando:

Escenario 1 – Local

Microservicios ejecutándose en la computadora del estudiante.

Escenario 2 – Remoto

Microservicios desplegados en la instancia remota utilizada por el equipo.

No se permite crear dos versiones diferentes del programa para resolver este requisito.

El cambio deberá realizarse mediante la configuración de la aplicación.

15. Evidencias mediante screenshots

Además del código fuente deberá entregar un documento con screenshots obtenidos de su propia aplicación en ejecución. Como mínimo deberá documentar:

    Pantalla inicial.
    Registro de usuario.
    Login correcto.
    Intento de login incorrecto.
    Panel principal.
    Estado de ambos microservicios.
    Perfil del usuario.
    Catálogo de libros.
    Búsqueda o filtrado.
    Detalle de un libro.
    Registro de un nuevo libro.
    Modificación completa mediante PUT.
    Modificación parcial mediante PATCH.
    Eliminación de un libro.
    Confirmación previa a la eliminación.
    Error producido por un ISBN duplicado.
    Consulta de un ISBN inexistente.
    Microservicio de libros detenido.
    Recuperación del servicio después de iniciarlo nuevamente.
    Pantalla de configuración.
    Funcionamiento con servicios locales.
    Funcionamiento con los servicios remotos.

Los screenshots deberán mostrar suficiente contexto para comprobar que corresponden a la aplicación desarrollada por el estudiante. No entregue únicamente capturas de fragmentos de código.

16. Evidencia individual

Cada estudiante deberá agregar temporalmente al catálogo un libro de prueba utilizando como parte del registro:

Título: PRUEBA INTEGRACION - <MATRÍCULA>

Por ejemplo:

PRUEBA INTEGRACION - 654321

Deberá mostrar mediante screenshots:

POST → GET → PATCH → GET → DELETE → GET

Es decir, deberá demostrar el ciclo completo de creación, consulta, modificación, nueva consulta, eliminación y comprobación final.

El registro utilizado para esta prueba deberá eliminarse al terminar.

17. Bitácora de integración

Incluya una pequeña tabla de pruebas realizadas.

Prueba
	

Acción realizada
	

Endpoint
	

Resultado HTTP
	

Resultado observado

01
	

Inicio de sesión
	

/login
	

...
	

...

02
	

Consultar libros
	

/books
	

...
	

...

03
	

Crear libro
	

...
	

...
	

...

...
	

...
	

...
	

...
	

...

No copie simplemente la lista anterior. Registre las pruebas que realmente realizó durante su implementación.

18. Breve reflexión

Al finalizar la actividad escriba una reflexión personal de aproximadamente 200 a 300 palabras.

No se solicita una definición teórica de REST, Python o microservicios.

Explique, a partir de su propia implementación:

    Qué parte de la integración presentó mayor dificultad.
    Qué problema encontró durante el desarrollo.
    Cómo identificó la causa.
    Qué modificación realizó para resolverlo.
    Qué ocurre en su aplicación cuando un microservicio deja de responder.
    Qué diferencia observó entre ejecutar los servicios localmente y consumirlos remotamente.
    Qué aprendió sobre la relación entre cliente, microservicio y base de datos.

La reflexión deberá corresponder con las evidencias y con el comportamiento observado en su aplicación.

19. README.md

Dentro de apps/Python_app deberá existir un archivo: README.md

El documento deberá permitir que otra persona pueda ejecutar el proyecto sin preguntarle al desarrollador cómo hacerlo. Incluya:

    Versión de Python utilizada.
    Biblioteca gráfica seleccionada.
    Dependencias.
    Instalación.
    Configuración.
    Ejecución.
    Estructura principal de la aplicación.
    Configuración de los microservicios.
    Problemas conocidos.
    Solución de problemas frecuentes.

Incluya también un archivo de dependencias, por ejemplo: requirements.txt

20. Estructura esperada

La solución deberá encontrarse dentro de: apps/Python_app

La organización interna queda a criterio del estudiante.

Sin embargo, durante la revisión deberá ser capaz de identificar dónde se encuentra el código responsable de:

GUI → configuración → comunicación HTTP → autenticación/sesión → libros → comprobación de servicios.

No existe una estructura de archivos única obligatoria.

La organización del software forma parte de las decisiones de diseño del estudiante.

21. Restricciones

No se permite:

    Acceder directamente desde la aplicación Python a PostgreSQL, MongoDB u otra base de datos de los microservicios.
    Reemplazar el consumo REST por consultas directas.
    Colocar todas las funcionalidades en un único archivo sin una justificación técnica.
    Modificar manualmente el código para cambiar entre servidor local y remoto.
    Incluir contraseñas, tokens o credenciales personales dentro del repositorio.
    Entregar únicamente código sin evidencia de ejecución.
    Utilizar screenshots de otro estudiante.
    Presentar funcionalidades visibles en la GUI que no estén realmente implementadas.

22. Validación durante la revisión

Durante la revisión el profesor podrá solicitar al estudiante una modificación menor no anunciada previamente.

Por ejemplo, se podrá solicitar:

    Cambiar un criterio de búsqueda.
    Modificar un campo mostrado en una card.
    Cambiar temporalmente el puerto de un servicio.
    Explicar qué función realiza una petición HTTP determinada.
    Indicar dónde se conserva la configuración.
    Mostrar qué ocurre al recibir un código HTTP determinado.
    Modificar un dato utilizando PATCH.
    Identificar qué componente conserva la sesión.
    Explicar el recorrido de una petición desde que se presiona un botón hasta que se recibe la respuesta.

La modificación deberá realizarse sobre el proyecto entregado. El propósito es comprobar la comprensión de la solución y no solamente su funcionamiento final.

Entregables

Entregue en Blackboard:

    Proyecto completo dentro de apps/Python_app.
    Código fuente organizado.
    README.md.
    Archivo de dependencias.
    Documento PDF con los screenshots solicitados.
    Bitácora de pruebas.
    Reflexión de 200–300 palabras.
    Evidencia de ejecución local.
    Evidencia de ejecución contra los microservicios remotos.
    Evidencia individual del ciclo POST → GET → PATCH → GET → DELETE → GET.

Importante

La evaluación no se limitará a verificar que la interfaz gráfica se vea correctamente. Se evaluará principalmente que el estudiante pueda demostrar, ejecutar y explicar la integración realizada. Una aplicación visualmente completa cuyos componentes no consuman realmente los microservicios no será considerada una integración funcional. De la misma manera, disponer del código fuente no sustituye la demostración de su funcionamiento.

Cada estudiante deberá ser capaz de explicar las decisiones tomadas en su implementación y demostrar el recorrido de la información entre la aplicación Python y los microservicios.