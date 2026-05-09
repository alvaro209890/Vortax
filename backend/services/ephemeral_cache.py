import asyncio
import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_TTL_BY_COMPLEXITY: dict[str, float] = {"SIMPLE": 600.0, "MODERATE": 300.0, "COMPLEX": 0.0}


class EphemeralCache:
    """Cache in-memory cross-task para resultados de pesquisa, com TTL por complexidade.

    SIMPLE: 10 min | MODERATE: 5 min | COMPLEX: nunca cacheia.
    Entradas expiradas são removidas lazy no acesso e proativamente via purge_loop().
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]

    async def get(self, query: str) -> Any | None:
        key = self._key(query)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            payload, expires_at = entry
            if time.monotonic() < expires_at:
                logger.debug("[ephemeral_cache HIT] query=%s", query[:80])
                return payload
            del self._store[key]
            return None

    async def set(self, query: str, payload: Any, complexity: str) -> None:
        ttl = _TTL_BY_COMPLEXITY.get(complexity, 0.0)
        if ttl <= 0:
            return
        key = self._key(query)
        async with self._lock:
            self._store[key] = (payload, time.monotonic() + ttl)
        logger.debug("[ephemeral_cache SET] complexity=%s ttl=%.0fs query=%s", complexity, ttl, query[:80])

    async def purge_expired(self) -> int:
        now = time.monotonic()
        async with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in expired:
                del self._store[k]
        return len(expired)

    async def purge_loop(self, interval: float = 300.0) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                n = await self.purge_expired()
                if n:
                    logger.debug("[ephemeral_cache] removidas %d entradas expiradas", n)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[ephemeral_cache] erro no loop de purge")


ephemeral_cache = EphemeralCache()
