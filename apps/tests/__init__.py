"""Utilidades compartidas por los tests.

Añade la carpeta ``apps`` al ``sys.path`` para poder importar el paquete
``common`` (``common.redis_store`` y ``common.auth``) sin instalar nada.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap: pone ``apps`` en el path para importar ``common`` y ``tests``
# sin importar desde qué directorio se ejecute ``unittest``.
APPS_DIR = Path(__file__).resolve().parents[1]
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))


class FakeRedis:
    """Redis en memoria con el subconjunto de API que usa ``redis_store``.

    Soporta: ``setex``, ``get``, ``delete``, ``exists``, ``scan_iter`` y
    ``ping``. Permite probar la lógica de sesión/refresh/revocación/caché sin
    un servidor Redis real.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def ping(self) -> bool:
        return True

    def setex(self, key: str, ttl: int, value: str) -> bool:
        # El TTL se ignora en el doble de prueba (no expira en memoria).
        self.store[key] = value
        return True

    def get(self, key: str):
        return self.store.get(key)

    def delete(self, *keys: str) -> int:
        borrados = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                borrados += 1
        return borrados

    def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    def scan_iter(self, match: str = "*", count: int = 10):
        import fnmatch

        return [k for k in list(self.store) if fnmatch.fnmatch(k, match)]
