"""Pruebas de ``common.redis_store`` sin un servidor Redis real.

Se sustituye ``get_redis`` por un ``FakeRedis`` (operaciones reales) o por
``None`` (Redis caído) para verificar las dos reglas del diseño:

* lecturas cacheadas  -> fail-open (devuelven ``None`` sin Redis);
* sesión / revocación -> fail-closed (``False``/``None`` sin Redis).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Auto-arranque del path: funciona sin importar el directorio de ejecución.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import FakeRedis  # noqa: E402
from common import redis_store  # noqa: E402


class RedisCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeRedis()
        self._orig = redis_store.get_redis
        redis_store.get_redis = lambda: self.fake
        redis_store.metricas.update({"hits": 0, "misses": 0, "errores": 0})

    def tearDown(self) -> None:
        redis_store.get_redis = self._orig

    def test_guardar_y_leer_cache(self) -> None:
        redis_store.guardar_cache("books:list:x", {"libros": [1, 2]}, 60)
        self.assertEqual(redis_store.leer_cache("books:list:x"), {"libros": [1, 2]})

    def test_cache_miss_devuelve_none(self) -> None:
        self.assertIsNone(redis_store.leer_cache("books:list:inexistente"))

    def test_invalidar_catalogo_borra_lista_y_detalle(self) -> None:
        redis_store.guardar_cache("books:list:a", {"x": 1}, 60)
        redis_store.guardar_cache("books:978", {"y": 2}, 120)
        redis_store.invalidar_catalogo("978")
        self.assertIsNone(redis_store.leer_cache("books:list:a"))
        self.assertIsNone(redis_store.leer_cache("books:978"))

    def test_clave_lista_estable_por_filtros(self) -> None:
        k1 = redis_store.clave_lista({"page": 1, "limit": 8})
        k2 = redis_store.clave_lista({"page": 1, "limit": 8})
        k3 = redis_store.clave_lista({"page": 2, "limit": 8})
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)
        self.assertTrue(k1.startswith("books:list:"))


class RedisSesionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeRedis()
        self._orig = redis_store.get_redis
        redis_store.get_redis = lambda: self.fake
        redis_store.metricas.update({"hits": 0, "misses": 0, "errores": 0})

    def tearDown(self) -> None:
        redis_store.get_redis = self._orig

    def test_sesion_roundtrip(self) -> None:
        self.assertTrue(redis_store.guardar_sesion("7", "jti-a", {"rol": "admin"}, 1200))
        self.assertEqual(redis_store.leer_sesion("7", "jti-a"), {"rol": "admin"})

    def test_borrar_sesion(self) -> None:
        redis_store.guardar_sesion("7", "jti-a", {"rol": "admin"}, 1200)
        redis_store.borrar_sesion("7", "jti-a")
        self.assertIsNone(redis_store.leer_sesion("7", "jti-a"))

    def test_refresh_valido_y_borrado(self) -> None:
        redis_store.guardar_refresh("r-1", "7", 86400)
        self.assertTrue(redis_store.refresh_valido("r-1"))
        redis_store.borrar_refresh("r-1")
        self.assertFalse(redis_store.refresh_valido("r-1"))

    def test_revocacion_jti(self) -> None:
        self.assertFalse(redis_store.esta_revocado("jti-a"))  # no revocado -> False
        self.assertTrue(redis_store.revocar_jti("jti-a", 900))
        self.assertTrue(redis_store.esta_revocado("jti-a"))   # revocado -> True


class RedisCaidoTests(unittest.TestCase):
    """Con Redis caído: cache fail-open, sesión/revocación fail-closed."""

    def setUp(self) -> None:
        self._orig = redis_store.get_redis
        redis_store.get_redis = lambda: None
        redis_store.metricas.update({"hits": 0, "misses": 0, "errores": 0})

    def tearDown(self) -> None:
        redis_store.get_redis = self._orig

    def test_cache_fail_open(self) -> None:
        # Escribir/leer caché no debe lanzar: devuelve None (miss).
        redis_store.guardar_cache("books:list:x", {"a": 1}, 60)
        self.assertIsNone(redis_store.leer_cache("books:list:x"))

    def test_sesion_fail_closed(self) -> None:
        self.assertFalse(redis_store.guardar_sesion("7", "jti-a", {}, 1200))
        self.assertIsNone(redis_store.leer_sesion("7", "jti-a"))

    def test_revocacion_fail_closed_devuelve_none(self) -> None:
        # None => el servicio debe responder 503 (no dejar pasar el token).
        self.assertIsNone(redis_store.esta_revocado("jti-a"))
        self.assertFalse(redis_store.revocar_jti("jti-a", 900))

    def test_redis_health_down(self) -> None:
        self.assertEqual(redis_store.redis_health(), "down")


if __name__ == "__main__":
    unittest.main()
