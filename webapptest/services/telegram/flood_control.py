import time
import asyncio
import redis
from core.config import Config
from core.logger import log


class FloodControl:
    def __init__(self):
        self._redis = None
        self._redis_available = True

    def _get_redis(self):
        if not self._redis_available:
            return None
        if self._redis is None:
            try:
                self._redis = redis.from_url(Config.REDIS_URL, decode_responses=True)
                self._redis.ping()
            except (redis.RedisError, OSError) as e:
                log.warning(f"FloodControl: Redis unavailable, flood control disabled: {e}")
                self._redis = None
                self._redis_available = False
        return self._redis

    async def wait_if_needed(self, account_id: str, max_actions_per_minute: int = 30):
        r = self._get_redis()
        if r is None:
            return

        key = f"flood_control:{account_id}"
        now = time.time()

        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - 60)
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            results = pipe.execute()

            count = results[1]
            oldest_data = results[2]

            if count >= max_actions_per_minute:
                if oldest_data:
                    wait_time = 60 - (now - oldest_data[0][1])
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)

            current_time = time.time()
            r.zadd(key, {str(current_time): current_time})
            r.expire(key, 65)
        except (redis.RedisError, OSError) as e:
            log.warning(f"FloodControl: Redis error during wait_if_needed: {e}")
            self._redis = None
            self._redis_available = False


flood_controller = FloodControl()