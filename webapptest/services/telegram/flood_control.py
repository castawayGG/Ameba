import time
import asyncio
import redis
from core.config import Config

class FloodControl:
    def __init__(self):
        self.redis = redis.from_url(Config.REDIS_URL, decode_responses=True)

    async def wait_if_needed(self, account_id: str, max_actions_per_minute: int = 30):
        key = f"flood_control:{account_id}"
        now = time.time()
        
        pipe = self.redis.pipeline()
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
        self.redis.zadd(key, {str(current_time): current_time})
        self.redis.expire(key, 65)

flood_controller = FloodControl()