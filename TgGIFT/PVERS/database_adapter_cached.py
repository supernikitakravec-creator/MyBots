#!/usr/bin/env python3
"""
Cached Database Adapter - обертка с кэшированием для database_adapter_simple
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from database_adapter_simple import DatabaseAdapterSimple
from redis_cache import cache_manager

logger = logging.getLogger(__name__)

class CachedDatabaseAdapter:
    """Кэширующая обертка для базы данных"""
    
    def __init__(self, db_adapter: DatabaseAdapterSimple):
        self.db_adapter = db_adapter
        self.cache = cache_manager
        
        logger.info("Кэширующий адаптер базы данных инициализирован")
    
    async def init_cache(self):
        """Инициализация кэша"""
        await self.cache.connect()
    
    async def close_cache(self):
        """Закрытие кэша"""
        await self.cache.disconnect()
    
    # Кэшируемые методы для пользователей
    
    def register_user(self, user_id: int, username: str = None, first_name: str = None) -> bool:
        """Регистрация пользователя (инвалидирует кэш)"""
        result = self.db_adapter.register_user(user_id, username, first_name)
        if result:
            # Асинхронно инвалидируем кэш пользователя
            asyncio.create_task(self.cache.invalidate_user(user_id))
        return result
    
    def get_user_data(self, user_id: int) -> Optional[Dict]:
        """Получение данных пользователя с кэшированием"""
        # Пытаемся получить из кэша
        cached_data = asyncio.create_task(self.cache.get_user_data(user_id))
        
        try:
            # Получаем результат из кэша (если доступен)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если цикл уже запущен, создаем новую задачу
                future = asyncio.ensure_future(cached_data)
                # Ждем немного, если кэш быстро отвечает
                try:
                    cached_result = loop.run_until_complete(asyncio.wait_for(future, timeout=0.1))
                    if cached_result:
                        logger.debug(f"Данные пользователя {user_id} получены из кэша")
                        return cached_result
                except asyncio.TimeoutError:
                    pass
        except:
            pass
        
        # Получаем из базы данных
        data = self.db_adapter.get_user_data(user_id)
        
        # Сохраняем в кэш асинхронно
        if data:
            asyncio.create_task(self.cache.set_user_data(user_id, data))
            
        return data
    
    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """Получение подписки пользователя с кэшированием"""
        # Пытаемся получить из кэша
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.ensure_future(self.cache.get_subscription(user_id))
                try:
                    cached_result = loop.run_until_complete(asyncio.wait_for(future, timeout=0.1))
                    if cached_result:
                        logger.debug(f"Подписка пользователя {user_id} получена из кэша")
                        return cached_result
                except asyncio.TimeoutError:
                    pass
        except:
            pass
        
        # Получаем из базы данных
        subscription = self.db_adapter.get_user_subscription(user_id)
        
        # Сохраняем в кэш асинхронно
        if subscription:
            asyncio.create_task(self.cache.set_subscription(user_id, subscription))
            
        return subscription
    
    def activate_subscription(self, user_id: int, subscription_type: str, days: int = 30) -> bool:
        """Активация подписки (инвалидирует кэш)"""
        result = self.db_adapter.activate_subscription(user_id, subscription_type, days)
        if result:
            # Инвалидируем кэш подписки
            asyncio.create_task(self._invalidate_subscription_cache(user_id))
        return result
    
    async def _invalidate_subscription_cache(self, user_id: int):
        """Инвалидация кэша подписки"""
        subscription_key = self.cache._make_key("subscription", user_id)
        await self.cache.delete(subscription_key)
    
    # Методы для работы с подарками (кэшируются на короткое время)
    
    def get_available_gifts(self) -> List[Dict]:
        """Получение доступных подарков с кэшированием"""
        cache_key = "available_gifts"
        
        # Пытаемся получить из кэша
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.ensure_future(self.cache.get(cache_key))
                try:
                    cached_result = loop.run_until_complete(asyncio.wait_for(future, timeout=0.1))
                    if cached_result:
                        logger.debug("Список подарков получен из кэша")
                        return cached_result
                except asyncio.TimeoutError:
                    pass
        except:
            pass
        
        # Получаем из базы данных
        gifts = self.db_adapter.get_available_gifts() if hasattr(self.db_adapter, 'get_available_gifts') else []
        
        # Кэшируем на короткое время (5 минут)
        if gifts:
            asyncio.create_task(self.cache.set(cache_key, gifts, 300))
            
        return gifts
    
    # Проксирование остальных методов без кэширования
    
    def __getattr__(self, name):
        """Проксирование методов к оригинальному адаптеру"""
        attr = getattr(self.db_adapter, name)
        
        # Если это метод, который изменяет данные пользователя, добавляем инвалидацию кэша
        if callable(attr) and any(keyword in name.lower() for keyword in ['save', 'update', 'delete', 'add', 'remove']):
            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                
                # Пытаемся извлечь user_id для инвалидации
                user_id = None
                if args and isinstance(args[0], int):
                    user_id = args[0]
                elif 'user_id' in kwargs:
                    user_id = kwargs['user_id']
                
                if user_id and result:
                    asyncio.create_task(self.cache.invalidate_user(user_id))
                
                return result
            return wrapper
        
        return attr
    
    # Методы для мониторинга кэша
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""
        return await self.cache.health_check()
    
    async def clear_cache(self, pattern: str = "tggift:*") -> int:
        """Очистка кэша"""
        return await self.cache.clear_pattern(pattern)
    
    async def warm_up_cache(self, user_ids: List[int] = None):
        """Прогрев кэша для указанных пользователей"""
        if not user_ids:
            return
        
        logger.info(f"Прогрев кэша для {len(user_ids)} пользователей")
        
        for user_id in user_ids:
            try:
                # Загружаем данные пользователя
                user_data = self.db_adapter.get_user_data(user_id)
                if user_data:
                    await self.cache.set_user_data(user_id, user_data)
                
                # Загружаем подписку
                subscription = self.db_adapter.get_user_subscription(user_id)
                if subscription:
                    await self.cache.set_subscription(user_id, subscription)
                    
            except Exception as e:
                logger.error(f"Ошибка прогрева кэша для пользователя {user_id}: {e}")
        
        logger.info("Прогрев кэша завершен") 