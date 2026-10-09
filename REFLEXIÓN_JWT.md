# Actividad: Integración de autenticación JWT en microservicios login y books
## Santiago López Cervantes #612956

## Qué se implementó

**Servicio login (emisor, puerto 5002):**
`POST /login` ahora devuelve, además de la cookie de sesión de Flask, un par
de tokens firmados con HS256 (`PyJWT`): `access_token` (15 min, `type=access`,
`scope=escribir_libros`) y `refresh_token` (24 h, `type=refresh`, con `jti`
persistido en la tabla `refresh_tokens`). Existe `POST /refresh` con
**rotación**: cada refresh se usa una sola vez; reusarlo devuelve 401
(detección de robo). `POST /logout` revoca el refresh en la base de datos.
`GET /session` acepta `Authorization: Bearer <access_token>` y responde
`"via":"jwt"` (mantiene la cookie como alternativa para compatibilidad).

**Servicio books (verificador, puerto 5001):**
Un `@app.before_request` protege **sólo** `POST/PUT/PATCH/DELETE` exigiendo
`Authorization: Bearer <access_token>`. **La verificación es local**: se
comprueba la firma HMAC con el `JWT_SECRET_KEY` compartido en memoria, **sin
ninguna llamada HTTP al servicio de login** — no se encadena un microservicio
detrás de la autenticación. Rechaza con 401 (`missing_token`, `token_expired`,
`invalid_token`, `wrong_token_type`) y cabecera `WWW-Authenticate: Bearer`.
Los `GET` (`/books`, `/api/books`, `/api/books/{isbn}`, `/books/{isbn}`,
`/api/libros*`, `/uploads/*`) quedan **públicos**, tal como pide el
enunciado. Opcionalmente `JWT_WRITE_ROLES` restringe la escritura por rol.

**App Electron:** sólo hace `fetch` GET al catálogo público, por lo que
**funciona sin cambios ni token**.

**App Python Tk:** `ApiClient` guarda `access_token` + `refresh_token` al
hacer login, envía `Authorization: Bearer` en cada CRUD de escritura y, ante
un 401, renueva con `POST /refresh` y reintenta una sola vez. Los tokens se
persisten en `~/.libreria_cliente_session.json` (nunca la contraseña).

## Evidencia (instancia: Postgres en Docker `freshtrack_db`, servicios en 5001/5002)

Flujo verificado en vivo con `curl` y guardado en
`apps/services/{login,soap}/Evidencias/` (scripts `verificar.sh`):
públicos sin token → 200; POST sin token → 401; POST con token basura → 401;
login `admin@library.com` → par de tokens; POST/PATCH/DELETE con Bearer →
201/200/204; refresh → 200 y reuso → 401; logout revoca → refresh posterior
401; `/session` con Bearer → `{"authenticated":true,"via":"jwt"}`.

## Por qué JWT importa en REST

REST es sin estado: cada petición debe autenticarse sola. Con sesiones de
servidor habría que compartir estado entre instancias (sticky sessions o
almacén común) y cada microservicio tendría que preguntar a otro quién es el
usuario. El JWT es **autocontenido y verificable localmente** (firma HMAC +
`exp` + `type`): el servicio de libros autoriza escrituras sin red adicional,
escala horizontalmente sin estado compartido y mantiene el catálogo público
sin fricción, protegiendo sólo lo que muta datos. El refresh rotado acota la
ventana de exposición del access corto sin pedir la contraseña a cada rato.
