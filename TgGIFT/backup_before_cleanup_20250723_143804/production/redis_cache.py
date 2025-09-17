#!/usr/bin/env python3
"""
Redis кеш и очереди для TgGIFT Star Bot
"""

import redis.asyncio as redis
import json
import logging
from typing import Optional, Dict, List, Any
from datetime import timedelta
from datetime import datetime

logger = logging.getLogger(__name__)

class RedisManager:
    """Менеджер Redis для кеша и очередей"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None
        
    async def connect(self):
        """Подключение к Redis"""
        try:
            self.redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
            await self.redis.ping()
            logger.info("Подключение к Redis установлено")
        except Exception as e:
            logger.error(f"Ошибка подключения к Redis: {e}")
            raise
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis:
            await self.redis.close()
            logger.info("Соединение с Redis закрыто")
    
    # === Методы кеша ===
    
    async def get_cached(self, key: str) -> Optional[Any]:
        """Получить значение из кеша"""
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения из кеша {key}: {e}")
            return None
    
    async def set_cached(self, key: str, value: Any, ttl: int = 300):
        """Сохранить значение в кеше с TTL в секундах"""
        try:
            await self.redis.setex(
                key,
                ttl,
                json.dumps(value, ensure_ascii=False)
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения в кеш {key}: {e}")
    
    async def delete_cached(self, key: str):
        """Удалить значение из кеша"""
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Ошибка удаления из кеша {key}: {e}")
    
    async def clear_cache_pattern(self, pattern: str):
        """Очистить кеш по паттерну"""
        try:
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Ошибка очистки кеша по паттерну {pattern}: {e}")
    
    # === Методы для кеширования пользователей ===
    
    async def cache_user_info(self, user_id: int, user_info: Dict):
        """Кешировать информацию о пользователе"""
        await self.set_cached(f"user:{user_id}", user_info, ttl=600)  # 10 минут
    
    async def get_cached_user_info(self, user_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе из кеша"""
        return await self.get_cached(f"user:{user_id}")
    
    async def cache_user_balance(self, user_id: int, balance: int):
        """Кешировать баланс пользователя"""
        await self.set_cached(f"balance:{user_id}", balance, ttl=60)  # 1 минута
    
    async def get_cached_balance(self, user_id: int) -> Optional[int]:
        """Получить баланс из кеша"""
        return await self.get_cached(f"balance:{user_id}")
    
    async def invalidate_user_cache(self, user_id: int):
        """Инвалидировать весь кеш пользователя"""
        await self.delete_cached(f"user:{user_id}")
        await self.delete_cached(f"balance:{user_id}")
        await self.delete_cached(f"subscription:{user_id}")
    
    # === Методы для очередей ===
    
    async def add_to_notification_queue(self, user_id: int, message: Dict):
        """Добавить уведомление в очередь"""
        try:
            await self.redis.lpush(
                "queue:notifications",
                json.dumps({
                    "user_id": user_id,
                    "message": message,
                    "timestamp": datetime.now().isoformat()
                })
            )
        except Exception as e:
            logger.error(f"Ошибка добавления в очередь уведомлений: {e}")
    
    async def get_notification_from_queue(self) -> Optional[Dict]:
        """Получить уведомление из очереди"""
        try:
            data = await self.redis.rpop("queue:notifications")
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения из очереди уведомлений: {e}")
            return None
    
    async def add_to_purchase_priority_queue(self, user_id: int, gift_id: str, priority: int = 0):
        """Добавить в приоритетную очередь покупок"""
        try:
            await self.redis.zadd(
                "queue:priority_purchases",
                {json.dumps({"user_id": user_id, "gift_id": gift_id}): priority}
            )
        except Exception as e:
            logger.error(f"Ошибка добавления в приоритетную очередь: {e}")
    
    async def get_from_priority_queue(self) -> Optional[Dict]:
        """Получить элемент с наивысшим приоритетом"""
        try:
            items = await self.redis.zrange("queue:priority_purchases", 0, 0, withscores=True)
            if items:
                data, score = items[0]
                await self.redis.zrem("queue:priority_purchases", data)
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения из приоритетной очереди: {e}")
            return None
    
    # === Методы для подарков ===
    
    async def cache_gift_list(self, gifts: List[Dict]):
        """Кешировать список подарков"""
        await self.set_cached("gifts:available", gifts, ttl=300)  # 5 минут
    
    async def get_cached_gifts(self) -> Optional[List[Dict]]:
        """Получить список подарков из кеша"""
        return await self.get_cached("gifts:available")
    
    async def cache_gift_details(self, gift_id: str, details: Dict):
        """Кешировать детали подарка"""
        await self.set_cached(f"gift:{gift_id}", details, ttl=3600)  # 1 час
    
    # === Методы для rate limiting ===
    
    async def check_rate_limit(self, key: str, limit: int, window: int) -> bool:
        """Проверить rate limit"""
        try:
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, window)
            return current <= limit
        except Exception as e:
            logger.error(f"Ошибка проверки rate limit: {e}")
            return True  # В случае ошибки разрешаем операцию
    
    async def get_rate_limit_remaining(self, key: str, limit: int) -> int:
        """Получить оставшееся количество запросов"""
        try:
            current = await self.redis.get(key)
            if current:
                return max(0, limit - int(current))
            return limit
        except Exception as e:
            logger.error(f"Ошибка получения rate limit: {e}")
            return limit
    
    # === Методы для статистики ===
    
    async def increment_stat(self, stat_name: str, amount: int = 1):
        """Увеличить счетчик статистики"""
        try:
            await self.redis.hincrby("stats", stat_name, amount)
        except Exception as e:
            logger.error(f"Ошибка увеличения статистики {stat_name}: {e}")
    
    async def get_stats(self) -> Dict[str, int]:
        """Получить всю статистику"""
        try:
            stats = await self.redis.hgetall("stats")
            return {k: int(v) for k, v in stats.items()}
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}
    
    # === Методы для распределенных блокировок ===
    
    async def acquire_lock(self, lock_name: str, timeout: int = 10) -> bool:
        """Получить распределенную блокировку"""
        try:
            return await self.redis.set(
                f"lock:{lock_name}",
                "1",
                nx=True,
                ex=timeout
            )
        except Exception as e:
            logger.error(f"Ошибка получения блокировки {lock_name}: {e}")
            return False
    
    async def release_lock(self, lock_name: str):
        """Освободить блокировку"""
        try:
            await self.redis.delete(f"lock:{lock_name}")
        except Exception as e:
            logger.error(f"Ошибка освобождения блокировки {lock_name}: {e}")
    
    # === Методы для сессий ===
    
    async def save_session(self, session_id: str, data: Dict, ttl: int = 86400):
        """Сохранить сессию пользователя"""
        await self.set_cached(f"session:{session_id}", data, ttl)
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Получить сессию пользователя"""
        return await self.get_cached(f"session:{session_id}")
    
    async def delete_session(self, session_id: str):
        """Удалить сессию"""
        await self.delete_cached(f"session:{session_id}") 