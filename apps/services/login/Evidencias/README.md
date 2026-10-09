# Evidencias del microservicio de autenticacion

Para validar los cinco endpoints y guardar la evidencia:

```bash
bash apps/services/login/verificar.sh
```

El script deja aqui un archivo `.txt` por endpoint con la peticion y la respuesta
recibida, en XML y en JSON.

Para las capturas de pantalla: abre <http://localhost:5000/apidocs/>, ejecuta cada
endpoint desde "Try it out" y captura la respuesta de cada uno, mas la de
`http://localhost:5000/health` con el mensaje de base de datos conectada.

Requisito previo: la base `library` debe existir y `library_user` debe poder
autenticarse (ver el README de este servicio).
