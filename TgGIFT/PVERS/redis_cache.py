#!/usr/bin/env python3
"""
Redis Cache Manager - система кэширования для TgGIFT Bot
"""

import logging
import json
import asyncio
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
import redis.asyncio as redis
from config import REDIS_CONFIG, CACHE_CONFIG

logger = logging.getLogger(__name__)

class RedisCacheManager:
    """Менеджер Redis кэша"""
    
    def __init__(self):
        self.redis_pool = None
        self.enabled = CACHE_CONFIG['enabled']
        self.default_ttl = CACHE_CONFIG['default_ttl']
        
        logger.info(f"Redis Cache {'включен' if self.enabled else 'отключен'}")
    
    async def connect(self):
        """Подключение к Redis"""
        if not self.enabled:
            logger.info("Кэш отключен, пропускаем подключение к Redis")
            return
        
        try:
            # Создаем пул соединений
            self.redis_pool = redis.ConnectionPool(
                host=REDIS_CONFIG['host'],
                port=REDIS_CONFIG['port'],
                db=REDIS_CONFIG['db'],
                password=REDIS_CONFIG['password'],
                decode_responses=REDIS_CONFIG['decode_responses'],
                socket_timeout=REDIS_CONFIG['socket_timeout'],
                socket_connect_timeout=REDIS_CONFIG['socket_connect_timeout'],
                retry_on_timeout=REDIS_CONFIG['retry_on_timeout'],
                health_check_interval=REDIS_CONFIG['health_check_interval'],
                max_connections=REDIS_CONFIG['max_connections']
            )
            
            # Тестируем подключение
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            await redis_client.ping()
            await redis_client.close()
            
            logger.info(f"✅ Подключение к Redis установлено: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Redis: {e}")
            self.enabled = False
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis_pool:
            await self.redis_pool.disconnect()
            logger.info("Redis соединение закрыто")
    
    async def _get_client(self):
        """Получение клиента Redis"""
        if not self.enabled or not self.redis_pool:
            return None
        return redis.Redis(connection_pool=self.redis_pool)
    
    def _make_key(self, prefix: str, *args) -> str:
        """Создание ключа для кэша"""
        parts = [str(arg) for arg in args if arg is not None]
        return f"tggift:{prefix}:{':'.join(parts)}"
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Получение значения из кэша"""
        if not self.enabled:
            return default
        
        client = await self._get_client()
        if not client:
            return default
        
        try:
            value = await client.get(key)
            if value is None:
                return default
            
            # Пытаемся десериализовать JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            logger.error(f"Ошибка получения из кэша {key}: {e}")
            return default
        finally:
            await client.close()
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Сохранение значения в кэш"""
        if not self.enabled:
            return False
        
        client = await self._get_client()
        if not client:
            return False
        
        try:
            # Сериализуем в JSON если нужно
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            ttl = ttl or self.default_ttl
            await client.setex(key, ttl, value)
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения в кэш {key}: {e}")
            return False
        finally:
            await client.close()
    
    async def delete(self, key: str) -> bool:
        """Удаление значения из кэша"""
        if not self.enabled:
            return False
        
        client = await self._get_client()
        if not client:
            return False
        
        try:
            result = await client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Ошибка удаления из кэша {key}: {e}")
            return False
        finally:
            await client.close()
    
    async def exists(self, key: str) -> bool:
        """Проверка существования ключа"""
        if not self.enabled:
            return False
        
        client = await self._get_client()
        if not client:
            return False
        
        try:
            result = await client.exists(key)
            return result > 0
        except Exception as e:
            logger.error(f"Ошибка проверки существования {key}: {e}")
            return False
        finally:
            await client.close()
    
    async def clear_pattern(self, pattern: str) -> int:
        """Очистка кэша по шаблону"""
        if not self.enabled:
            return 0
        
        client = await self._get_client()
        if not client:
            return 0
        
        try:
            keys = await client.keys(pattern)
            if keys:
                deleted = await client.delete(*keys)
                logger.info(f"Очищено {deleted} ключей по шаблону {pattern}")
                return deleted
            return 0
        except Exception as e:
            logger.error(f"Ошибка очистки кэша по шаблону {pattern}: {e}")
            return 0
        finally:
            await client.close()
    
    # Специализированные методы для разных типов данных
    
    async def get_user_data(self, user_id: int) -> Optional[Dict]:
        """Получение данных пользователя"""
        key = self._make_key("user", user_id)
        return await self.get(key)
    
    async def set_user_data(self, user_id: int, data: Dict) -> bool:
        """Сохранение данных пользователя"""
        key = self._make_key("user", user_id)
        return await self.set(key, data, CACHE_CONFIG['user_data_ttl'])
    
    async def get_subscription(self, user_id: int) -> Optional[Dict]:
        """Получение подписки пользователя"""
        key = self._make_key("subscription", user_id)
        return await self.get(key)
    
    async def set_subscription(self, user_id: int, subscription: Dict) -> bool:
        """Сохранение подписки пользователя"""
        key = self._make_key("subscription", user_id)
        return await self.set(key, subscription, CACHE_CONFIG['subscription_ttl'])
    
    async def invalidate_user(self, user_id: int):
        """Инвалидация всех данных пользователя"""
        pattern = self._make_key("*", user_id)
        await self.clear_pattern(pattern)
    
    async def get_gift_data(self, gift_id: str) -> Optional[Dict]:
        """Получение данных подарка"""
        key = self._make_key("gift", gift_id)
        return await self.get(key)
    
    async def set_gift_data(self, gift_id: str, data: Dict) -> bool:
        """Сохранение данных подарка"""
        key = self._make_key("gift", gift_id)
        return await self.set(key, data, CACHE_CONFIG['gift_data_ttl'])
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния Redis"""
        if not self.enabled:
            return {"status": "disabled", "message": "Кэш отключен"}
        
        client = await self._get_client()
        if not client:
            return {"status": "error", "message": "Нет подключения к Redis"}
        
        try:
            # Тест ping
            ping_result = await client.ping()
            
            # Получаем статистику
            info = await client.info()
            
            return {
                "status": "healthy" if ping_result else "error",
                "ping": ping_result,
                "connected_clients": info.get('connected_clients', 0),
                "used_memory": info.get('used_memory_human', 'Unknown'),
                "uptime": info.get('uptime_in_seconds', 0)
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            await client.close()

# Глобальный экземпляр кэша
cache_manager = RedisCacheManager() 