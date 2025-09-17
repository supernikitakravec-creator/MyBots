"""
Упрощенный Database Adapter - использует SQLite интерфейс с PostgreSQL
"""
import os
import logging
import asyncio
import json
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class SimpleDatabaseAdapter:
    """Упрощенный адаптер, который предоставляет SQLite интерфейс"""
    
    def __init__(self):
        self.is_postgres = os.getenv('USE_POSTGRES', 'false').lower() == 'true'
        
        if self.is_postgres:
            from database_postgres import PostgresDatabaseManager, DatabaseConfig
            config = DatabaseConfig(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', '5432')),
                database=os.getenv('POSTGRES_DB', 'tggift_db'),
                user=os.getenv('POSTGRES_USER', 'tggift_user'),
                password=os.getenv('POSTGRES_PASSWORD', 'tggift_password_2024')
            )
            self.postgres_db = PostgresDatabaseManager(config)
            logger.info("🐘 Используется PostgreSQL")
        else:
            from database import DatabaseManager
            self.sqlite_db = DatabaseManager()
            logger.info("🗄️ Используется SQLite")
    

    
    def _run_postgres_sync(self, coro, *args, **kwargs):
        """Запуск PostgreSQL корутины синхронно"""
        import concurrent.futures
        
        def run_in_thread():
            # Создаем новый loop и новое подключение для каждого запроса
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                # Создаем временное подключение для этого потока
                from database_postgres import PostgresDatabaseManager, DatabaseConfig
                config = DatabaseConfig(
                    host=os.getenv('POSTGRES_HOST', 'localhost'),
                    port=int(os.getenv('POSTGRES_PORT', '5432')),
                    database=os.getenv('POSTGRES_DB', 'tggift_db'),
                    user=os.getenv('POSTGRES_USER', 'tggift_user'),
                    password=os.getenv('POSTGRES_PASSWORD', 'tggift_password_2024')
                )
                temp_db = PostgresDatabaseManager(config)
                new_loop.run_until_complete(temp_db.connect())
                result = new_loop.run_until_complete(coro(temp_db, *args, **kwargs))
                new_loop.run_until_complete(temp_db.disconnect())
                return result
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result(timeout=10)  # Уменьшаем таймаут
    
    # Основные методы базы данных
    def init_database(self):
        """Инициализация базы данных"""
        if self.is_postgres:
            # Для PostgreSQL просто проверяем подключение
            try:
                async def _test_connection(db):
                    return await db.health_check()
                result = self._run_postgres_sync(_test_connection)
                logger.info(f"PostgreSQL готов к работе: {result}")
                return True
            except Exception as e:
                logger.error(f"Ошибка инициализации PostgreSQL: {e}")
                return False
        else:
            return self.sqlite_db.init_database()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение пользователя"""
        if self.is_postgres:
            async def _get_user(db, user_id):
                return await db.get_user(user_id)
            return self._run_postgres_sync(_get_user, user_id)
        else:
            return self.sqlite_db.get_user(user_id)
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, 
                last_name: str = None, language_code: str = 'ru') -> bool:
        """Добавление пользователя"""
        if self.is_postgres:
            async def _add_user(db, user_id, username, first_name, last_name, language_code):
                return await db.add_user(user_id, username, first_name, last_name, language_code)
            return self._run_postgres_sync(_add_user, user_id, username, first_name, last_name, language_code)
        else:
            return self.sqlite_db.add_user(user_id, username, first_name, last_name, language_code)
    
    def register_user(self, user_id: int, username: str = None, first_name: str = None, 
                     last_name: str = None, language_code: str = 'ru') -> bool:
        """Регистрация пользователя (алиас)"""
        return self.add_user(user_id, username, first_name, last_name, language_code)
    
    def get_stars_balance(self, user_id: int) -> int:
        """Получение баланса Stars"""
        if self.is_postgres:
            async def _get_balance(db, user_id):
                return await db.get_stars_balance(user_id)
            return self._run_postgres_sync(_get_balance, user_id)
        else:
            return self.sqlite_db.get_stars_balance(user_id)
    
    def add_stars_with_commission(self, user_id: int, stars_requested: int, 
                                commission_rate: float, source: str, 
                                description: str = "", metadata: dict = None) -> dict:
        """Добавление Stars с комиссией"""
        if self.is_postgres:
            async def _add_stars(db, user_id, stars_requested, commission_rate, source, description, metadata):
                return await db.add_stars_with_commission(user_id, stars_requested, commission_rate, source, description, metadata)
            return self._run_postgres_sync(_add_stars, user_id, stars_requested, commission_rate, source, description, metadata)
        else:
            return self.sqlite_db.add_stars_with_commission(user_id, stars_requested, commission_rate, source, description, metadata)
    
    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """Получение подписки пользователя"""
        if self.is_postgres:
            async def _get_subscription(db, user_id):
                result = await db.get_user_subscription(user_id)
                # Исправляем совместимость полей для PostgreSQL
                if result and 'subscription_type' in result:
                    result['type'] = result['subscription_type']  # Добавляем поле 'type' для совместимости
                return result
            return self._run_postgres_sync(_get_subscription, user_id)
        else:
            return self.sqlite_db.get_user_subscription(user_id)
    
    def get_auto_purchase_profile(self, user_id: int) -> Optional[Dict]:
        """Получение профиля автопокупки"""
        if self.is_postgres:
            async def _get_profile(db, user_id):
                return await db.get_auto_purchase_profile(user_id)
            return self._run_postgres_sync(_get_profile, user_id)
        else:
            return self.sqlite_db.get_auto_purchase_profile(user_id)
    
    def update_auto_purchase_profile(self, user_id: int, profile_data: dict = None, **kwargs) -> bool:
        """Обновление профиля автопокупки"""
        if self.is_postgres:
            async def _update_profile(db, user_id, **kwargs):
                return await db.update_auto_purchase_profile(user_id, **kwargs)
            # Используем kwargs для PostgreSQL
            update_kwargs = profile_data if profile_data else kwargs
            return self._run_postgres_sync(_update_profile, user_id, **update_kwargs)
        else:
            # Для SQLite используем profile_data
            if profile_data:
                return self.sqlite_db.update_auto_purchase_profile(user_id, profile_data)
            else:
                return self.sqlite_db.update_auto_purchase_profile(user_id, kwargs)
    
    def toggle_auto_purchase_profile(self, user_id: int) -> bool:
        """Переключение статуса автопокупки"""
        if self.is_postgres:
            async def _toggle_profile(db, user_id):
                return await db.toggle_auto_purchase_profile(user_id)
            return self._run_postgres_sync(_toggle_profile, user_id)
        else:
            return self.sqlite_db.toggle_auto_purchase_profile(user_id)
    
    def get_autopurchase_statistics(self, user_id: int) -> Dict:
        """Получение статистики автопокупок"""
        if self.is_postgres:
            async def _get_stats(db, user_id):
                return await db.get_autopurchase_statistics(user_id)
            return self._run_postgres_sync(_get_stats, user_id)
        else:
            return self.sqlite_db.get_autopurchase_statistics(user_id)
    
    @contextmanager
    def get_connection(self):
        """Получение соединения с базой данных"""
        if self.is_postgres:
            # Для PostgreSQL создаем временное подключение
            import asyncio
            
            def get_postgres_connection():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    config = self.postgres_db.config
                    temp_db = type(self.postgres_db)(config)
                    loop.run_until_complete(temp_db.connect())
                    return temp_db, loop
                except:
                    loop.close()
                    raise
            
            temp_db, loop = get_postgres_connection()
            try:
                yield temp_db
            finally:
                try:
                    loop.run_until_complete(temp_db.disconnect())
                finally:
                    loop.close()
        else:
            with self.sqlite_db.get_connection() as conn:
                yield conn
    
    # Методы совместимости
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Алиас для get_user"""
        return self.get_user(user_id)
    
    def get_balance(self, user_id: int) -> int:
        """Алиас для get_stars_balance"""
        return self.get_stars_balance(user_id)
    
    def get_pending_payments(self, currency: str = None) -> List[Dict]:
        """Получение ожидающих платежей"""
        if self.is_postgres:
            # Для PostgreSQL возвращаем пустой список пока не реализовано
            return []
        else:
            if hasattr(self.sqlite_db, 'get_pending_payments'):
                try:
                    return self.sqlite_db.get_pending_payments(currency)
                except TypeError:
                    # Если метод не принимает аргумент currency
                    return self.sqlite_db.get_pending_payments()
            else:
                return []
    
    def get_reserved_points(self, user_id: int) -> int:
        """Получение зарезервированных поинтов"""
        if self.is_postgres:
            # Для PostgreSQL возвращаем 0 пока не реализовано
            return 0
        else:
            return self.sqlite_db.get_reserved_points(user_id) if hasattr(self.sqlite_db, 'get_reserved_points') else 0
    
    def save_payment_info(self, user_id: int = None, payment_id: str = None, payment_type: str = None, 
                         amount: float = None, currency: str = None, status: str = 'pending', 
                         metadata: Dict = None, **kwargs) -> bool:
        """Сохранение информации о платеже"""
        if self.is_postgres:
            async def _save_payment_info(db, user_id, payment_id, payment_type, amount, currency, status, metadata):
                try:
                    async with db.get_connection() as conn:
                        await conn.execute('''
                            INSERT INTO payments 
                            (user_id, payment_id, payment_type, amount, currency, status, metadata, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
                            ON CONFLICT (payment_id) DO UPDATE SET
                                status = $6,
                                metadata = $7
                        ''', user_id, payment_id, payment_type, amount, currency, status, 
                             json.dumps(metadata) if metadata else None)
                        return True
                except Exception as e:
                    logger.error(f"Ошибка сохранения информации о платеже PostgreSQL: {e}")
                    return False
            
            return self._run_postgres_sync(_save_payment_info, user_id, payment_id, payment_type, 
                                         amount, currency, status, metadata)
        else:
            if hasattr(self.sqlite_db, 'save_payment_info'):
                # Для SQLite пробуем разные варианты вызова
                try:
                    return self.sqlite_db.save_payment_info(
                        user_id=user_id, payment_id=payment_id, payment_type=payment_type,
                        amount=amount, currency=currency, status=status, metadata=metadata, **kwargs
                    )
                except TypeError:
                    # Если метод принимает другие аргументы, возвращаем True
                    return True
            else:
                return True
    
    def activate_subscription(self, user_id: int, subscription_type: str, days: int = 30) -> bool:
        """Активация подписки пользователя"""
        if self.is_postgres:
            async def _activate_subscription(db, user_id, subscription_type, days):
                from datetime import datetime, timedelta
                try:
                    async with db.get_connection() as conn:
                        start_date = datetime.now()
                        end_date = start_date + timedelta(days=days)
                        
                        await conn.execute('''
                            INSERT INTO subscriptions 
                            (user_id, subscription_type, start_date, end_date, is_active, auto_renewal)
                            VALUES ($1, $2, $3, $4, TRUE, FALSE)
                            ON CONFLICT (user_id) DO UPDATE SET
                                subscription_type = $2,
                                start_date = $3,
                                end_date = $4,
                                is_active = TRUE,
                                auto_renewal = FALSE
                        ''', user_id, subscription_type, start_date, end_date)
                        
                        return True
                except Exception as e:
                    logger.error(f"Ошибка активации подписки PostgreSQL: {e}")
                    return False
            
            return self._run_postgres_sync(_activate_subscription, user_id, subscription_type, days)
        else:
            if hasattr(self.sqlite_db, 'activate_subscription'):
                return self.sqlite_db.activate_subscription(user_id, subscription_type, days)
            else:
                return True
    
    def save_auto_purchase_profile(self, user_id: int, profile_data: Dict) -> bool:
        """Сохранение профиля автопокупки"""
        if self.is_postgres:
            async def _save_profile(db, user_id, profile_data):
                try:
                    async with db.get_connection() as conn:
                        await conn.execute('''
                            INSERT INTO auto_purchase_profiles 
                            (user_id, profile_name, max_price, cooldown_minutes, is_active, filters)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT (user_id, profile_name) DO UPDATE SET
                                max_price = $3,
                                cooldown_minutes = $4,
                                is_active = $5,
                                filters = $6,
                                updated_at = CURRENT_TIMESTAMP
                        ''', user_id, profile_data.get('name', 'default'), 
                             profile_data.get('max_price', 1000),
                             profile_data.get('cooldown', 60),
                             profile_data.get('is_active', True),
                             json.dumps(profile_data.get('filters', {})))
                        return True
                except Exception as e:
                    logger.error(f"Ошибка сохранения профиля автопокупки PostgreSQL: {e}")
                    return False
            
            return self._run_postgres_sync(_save_profile, user_id, profile_data)
        else:
            if hasattr(self.sqlite_db, 'save_auto_purchase_profile'):
                return self.sqlite_db.save_auto_purchase_profile(user_id, profile_data)
            else:
                return True

    def get_auto_purchase_profiles(self, user_id: int) -> List[Dict]:
        """Получение профилей автопокупки пользователя"""
        if self.is_postgres:
            async def _get_profiles(db, user_id):
                try:
                    async with db.get_connection() as conn:
                        rows = await conn.fetch('''
                            SELECT profile_name, max_price, cooldown_minutes, is_active, filters, created_at
                            FROM auto_purchase_profiles 
                            WHERE user_id = $1
                            ORDER BY created_at DESC
                        ''', user_id)
                        
                        profiles = []
                        for row in rows:
                            profiles.append({
                                'name': row['profile_name'],
                                'max_price': row['max_price'],
                                'cooldown': row['cooldown_minutes'],
                                'is_active': row['is_active'],
                                'filters': json.loads(row['filters']) if row['filters'] else {},
                                'created_at': row['created_at']
                            })
                        return profiles
                except Exception as e:
                    logger.error(f"Ошибка получения профилей автопокупки PostgreSQL: {e}")
                    return []
            
            return self._run_postgres_sync(_get_profiles, user_id)
        else:
            if hasattr(self.sqlite_db, 'get_auto_purchase_profiles'):
                return self.sqlite_db.get_auto_purchase_profiles(user_id)
            else:
                return []

    def toggle_auto_purchase_profile(self, user_id: int, profile_name: str) -> bool:
        """Переключение активности профиля автопокупки"""
        if self.is_postgres:
            async def _toggle_profile(db, user_id, profile_name):
                try:
                    async with db.get_connection() as conn:
                        # Сначала деактивируем все профили пользователя
                        await conn.execute('''
                            UPDATE auto_purchase_profiles 
                            SET is_active = FALSE 
                            WHERE user_id = $1
                        ''', user_id)
                        
                        # Затем активируем выбранный профиль
                        result = await conn.execute('''
                            UPDATE auto_purchase_profiles 
                            SET is_active = TRUE 
                            WHERE user_id = $1 AND profile_name = $2
                        ''', user_id, profile_name)
                        
                        return result != 'UPDATE 0'
                except Exception as e:
                    logger.error(f"Ошибка переключения профиля автопокупки PostgreSQL: {e}")
                    return False
            
            return self._run_postgres_sync(_toggle_profile, user_id, profile_name)
        else:
            if hasattr(self.sqlite_db, 'toggle_auto_purchase_profile'):
                return self.sqlite_db.toggle_auto_purchase_profile(user_id, profile_name)
            else:
                return True

    def get_payment_info(self, payment_id: str) -> Optional[Dict]:
        """Получение информации о платеже"""
        if self.is_postgres:
            async def _get_payment_info(db, payment_id):
                try:
                    async with db.get_connection() as conn:
                        row = await conn.fetchrow('''
                            SELECT user_id, payment_id, payment_type, amount, currency, status, metadata, created_at
                            FROM payments 
                            WHERE payment_id = $1
                        ''', payment_id)
                        
                        if row:
                            return {
                                'user_id': row['user_id'],
                                'payment_id': row['payment_id'],
                                'payment_type': row['payment_type'],
                                'amount': row['amount'],
                                'currency': row['currency'],
                                'status': row['status'],
                                'metadata': json.loads(row['metadata']) if row['metadata'] else {},
                                'created_at': row['created_at']
                            }
                        return None
                except Exception as e:
                    logger.error(f"Ошибка получения информации о платеже PostgreSQL: {e}")
                    return None
            
            return self._run_postgres_sync(_get_payment_info, payment_id)
        else:
            if hasattr(self.sqlite_db, 'get_payment_info'):
                return self.sqlite_db.get_payment_info(payment_id)
            else:
                return None

    def health_check(self) -> bool:
        """Проверка здоровья базы данных"""
        if self.is_postgres:
            async def _health_check(db):
                return await db.health_check()
            try:
                return self._run_postgres_sync(_health_check)
            except:
                return False
        else:
            return self.sqlite_db.health_check()
    
    def get_connection_stats(self) -> Dict:
        """Получение статистики подключений"""
        if self.is_postgres:
            async def _get_stats(db):
                return await db.get_connection_stats()
            try:
                return self._run_postgres_sync(_get_stats)
            except:
                return {'active': 0, 'idle': 0, 'total': 0}
        else:
            return self.sqlite_db.get_connection_stats()
    
    # Проксирование недостающих методов
    def __getattr__(self, name):
        """Проксирование к оригинальному менеджеру"""
        if self.is_postgres:
            # Для PostgreSQL возвращаем заглушки для отсутствующих методов
            def default_method(*args, **kwargs):
                logger.warning(f"Метод {name} не реализован для PostgreSQL, возвращаем значение по умолчанию")
                if 'get_' in name:
                    if 'list' in name.lower() or 'history' in name.lower() or 'all_' in name.lower():
                        return []
                    elif 'balance' in name.lower() or 'count' in name.lower() or 'points' in name.lower():
                        return 0
                    elif 'stats' in name.lower() or 'statistics' in name.lower():
                        return {'total': 0}
                    else:
                        return None
                else:
                    return True  # Для методов типа save_, update_, etc.
            return default_method
        else:
            return getattr(self.sqlite_db, name) 