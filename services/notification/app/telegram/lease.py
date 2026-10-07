from __future__ import annotations

import uuid

from redis.asyncio import Redis

_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class Lease:
    def __init__(self, client: Redis, key: str, ttl_ms: int) -> None:
        self._client = client
        self._key = key
        self._ttl_ms = ttl_ms
        self._owner = uuid.uuid4().hex
        self._renew = client.register_script(_RENEW)
        self._release = client.register_script(_RELEASE)

    async def acquire(self) -> bool:
        return bool(await self._client.set(self._key, self._owner, nx=True, px=self._ttl_ms))

    async def renew(self) -> bool:
        return int(await self._renew(keys=[self._key], args=[self._owner, self._ttl_ms])) == 1

    async def release(self) -> None:
        await self._release(keys=[self._key], args=[self._owner])
