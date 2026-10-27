# Reflexión: Redis + JWT en la arquitectura de microservicios de *Library*
## Santiago López - 612956

---

El presente estado del proyecto incorpora una diversa variedad de tecnologías. Para las API Rest con conexione a endpoints , cada peticion debe poder atenderse en cualquier instancia sin depender de que la anterior hubiera llegado al mismo proceso. Dentro de este proyecto, postgres es la fuente de la verdad que siempre debería estar disponible para el cliente en dado caso sea necesario, sin embargo, consultarla en cada request para saber si la sesión de un usuario esta viva o si un token de usuario ya ha sido revocado hace que el sistema sea propenso a la sobrecarga y acopla a los servicios entre sí. Redis resuelve eso como una capa compartida de memoria, con tiempos de vida nativos y operaciones simples.

En el estado actual del proyecto, cualquier servicio puede confirmar en microsegundos si una sesión existe, sin golpear a PostgreSQL en cada request, además, un JWT con su token firmado es valido hasta que su tiempo de expiración suceda, aunque el usuario cierre sesión. Con una clave de revocación, el cierre de sesión surte efecto al instante en todos los servicios.

La aplicación de Redis en este proyecto parece que pudiera subir la complejidad del proyecto, sin embargo, es todo lo contrario, nos ayuda a poder administrar las sesiones y tokens de usuarios de una manera más eficiente y sencilla, de este modo, podemos disminuir los recursos que un usuario necesita del servicio. Mediante esta aplicación, he mejorado mi entendimiento de integración, sin mencionar que fue mucho más simple agregar endpoints ahora que comprendo mi arquitectura y puedo manejar la IA mejor.

Los siguientes son resultados de pruebas con un script verificado y revisado por mi, lo genero la IA, pero nos habilita observar como se guardan en caché las sesiones y tokens de usuario, así como la invalidación de catálogo cuando Redis cae. Tambien se muestra la lista de errores que pueden ocurrir en dado caso suceda algo.

## Pruebas Script

`apps/tests/` (21 pruebas, `unittest`, sin Redis/Postgres reales):

* `test_redis_store.py` — caché (guardar/leer/miss), sesión, refresh, revocación
  `jti`, invalidación del catálogo y el comportamiento **fail-open / fail-closed**
  cuando Redis está caído.
* `test_auth.py` — token válido, ausente (401), expirado (401), tipo incorrecto
  (401), firma inválida (401), jti revocado (401), **Redis caído → 503**,
  rol insuficiente (403) y rol admin (200).

Ejecutar:

```bash
cd apps && ./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```
