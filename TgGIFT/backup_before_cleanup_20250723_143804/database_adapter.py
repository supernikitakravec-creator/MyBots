"""
Database Adapter - Адаптер для совместимости между SQLite и PostgreSQL
"""
import asyncio
import logging
import os
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

class DatabaseAdapter:
    """Адаптер для совместимости между синхронным и асинхронным API базы данных"""
    
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
            self.db_manager = PostgresDatabaseManager(config)
            logger.info("🐘 Используется PostgreSQL")
        else:
            from database import DatabaseManager
            self.db_manager = DatabaseManager()
            logger.info("🗄️ Используется SQLite")
    
    async def connect(self):
        """Подключение к базе данных"""
        if self.is_postgres:
            await self.db_manager.connect()
        else:
            self.db_manager.init_database()
    
    async def disconnect(self):
        """Отключение от базы данных"""
        if self.is_postgres and hasattr(self.db_manager, 'disconnect'):
            await self.db_manager.disconnect()
    
    def _run_sync(self, coro_or_method, *args, **kwargs):
        """Запуск асинхронного метода в синхронном контексте"""
        if self.is_postgres:
            # Для PostgreSQL запускаем асинхронно
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Если цикл уже запущен, создаем задачу и ждем ее выполнения
                    import asyncio
                    import threading
                    import concurrent.futures
                    
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(coro_or_method(*args, **kwargs))
                        finally:
                            new_loop.close()
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_in_thread)
                        return future.result(timeout=30)  # 30 секунд таймаут
                else:
                    return loop.run_until_complete(coro_or_method(*args, **kwargs))
            except RuntimeError:
                # Если нет цикла событий, создаем новый
                return asyncio.run(coro_or_method(*args, **kwargs))
        else:
            # Для SQLite вызываем синхронно
            return coro_or_method(*args, **kwargs)
    
    # Синхронные методы-обертки для совместимости
    def get_user(self, user_id: int) -> Optional[Dict]:
        if self.is_postgres:
            return self._run_sync(self.db_manager.get_user, user_id)
        else:
            return self.db_manager.get_user(user_id)
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, 
                last_name: str = None, language_code: str = 'ru') -> bool:
        if self.is_postgres:
            return self._run_sync(self.db_manager.add_user, user_id, username, first_name, last_name, language_code)
        else:
            return self.db_manager.add_user(user_id, username, first_name, last_name, language_code)
    
    def get_stars_balance(self, user_id: int) -> int:
        if self.is_postgres:
            return self._run_sync(self.db_manager.get_stars_balance, user_id)
        else:
            return self.db_manager.get_stars_balance(user_id)
    
    def add_stars_with_commission(self, user_id: int, stars_requested: int, 
                                commission_rate: float, source: str, 
                                description: str = "", metadata: dict = None) -> dict:
        if self.is_postgres:
            return self._run_sync(self.db_manager.add_stars_with_commission, 
                                user_id, stars_requested, commission_rate, source, description, metadata)
        else:
            return self.db_manager.add_stars_with_commission(
                user_id, stars_requested, commission_rate, source, description, metadata)
    
    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        if self.is_postgres:
            return self._run_sync(self.db_manager.get_user_subscription, user_id)
        else:
            return self.db_manager.get_user_subscription(user_id)
    
    def get_auto_purchase_profile(self, user_id: int) -> Optional[Dict]:
        if self.is_postgres:
            return self._run_sync(self.db_manager.get_auto_purchase_profile, user_id)
        else:
            return self.db_manager.get_auto_purchase_profile(user_id)
    
    def update_auto_purchase_profile(self, user_id: int, profile_data: dict = None, **kwargs) -> bool:
        if self.is_postgres:
            # PostgreSQL использует kwargs
            return self._run_sync(self.db_manager.update_auto_purchase_profile, user_id, **kwargs)
        else:
            # SQLite использует profile_data dict
            if profile_data:
                return self.db_manager.update_auto_purchase_profile(user_id, profile_data)
            else:
                # Преобразуем kwargs в profile_data для SQLite
                return self.db_manager.update_auto_purchase_profile(user_id, kwargs)
    
    def toggle_auto_purchase_profile(self, user_id: int) -> bool:
        if self.is_postgres:
            return self._run_sync(self.db_manager.toggle_auto_purchase_profile, user_id)
        else:
            return self.db_manager.toggle_auto_purchase_profile(user_id)
    
    def get_autopurchase_statistics(self, user_id: int) -> Dict:
        if self.is_postgres:
            return self._run_sync(self.db_manager.get_autopurchase_statistics, user_id)
        else:
            return self.db_manager.get_autopurchase_statistics(user_id)
    
    def get_connection_stats(self) -> Dict:
        if self.is_postgres:
            return self._run_sync(self.db_manager.get_connection_stats)
        else:
            return self.db_manager.get_connection_stats()
    
    def health_check(self) -> bool:
        if self.is_postgres:
            return self._run_sync(self.db_manager.health_check)
        else:
            return self.db_manager.health_check()
    
    # Методы, которые могут отсутствовать в PostgreSQL версии
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Получение информации о пользователе (алиас для get_user)"""
        return self.get_user(user_id)
    
    def get_balance(self, user_id: int) -> int:
        """Получение баланса (алиас для get_stars_balance)"""
        return self.get_stars_balance(user_id)
    
    def get_database_stats(self) -> Dict:
        """Получение статистики базы данных"""
        if hasattr(self.db_manager, 'get_database_stats'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_database_stats)
            else:
                return self.db_manager.get_database_stats()
        else:
            return {'users': 0, 'subscriptions': 0, 'transactions': 0}
    
    def get_pending_payments(self) -> List[Dict]:
        """Получение ожидающих платежей"""
        if hasattr(self.db_manager, 'get_pending_payments'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_pending_payments)
            else:
                return self.db_manager.get_pending_payments()
        else:
            return []
    
    def get_reserved_points(self, user_id: int) -> int:
        """Получение зарезервированных поинтов"""
        if hasattr(self.db_manager, 'get_reserved_points'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_reserved_points, user_id)
            else:
                return self.db_manager.get_reserved_points(user_id)
        else:
            return 0
    
    def get_points_transactions_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получение истории транзакций"""
        if hasattr(self.db_manager, 'get_points_transactions_history'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_points_transactions_history, user_id, limit)
            else:
                return self.db_manager.get_points_transactions_history(user_id, limit)
        else:
            return []
    
    def get_gift_purchases_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получение истории покупок подарков"""
        if hasattr(self.db_manager, 'get_gift_purchases_history'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_gift_purchases_history, user_id, limit)
            else:
                return self.db_manager.get_gift_purchases_history(user_id, limit)
        else:
            return []
    
    def get_user_statistics(self, user_id: int) -> Dict:
        """Получение статистики пользователя"""
        if hasattr(self.db_manager, 'get_user_statistics'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_user_statistics, user_id)
            else:
                return self.db_manager.get_user_statistics(user_id)
        else:
            return {'total_spent': 0, 'total_purchases': 0}
    
    def get_all_active_users(self) -> List[Dict]:
        """Получение всех активных пользователей"""
        if hasattr(self.db_manager, 'get_all_active_users'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_all_active_users)
            else:
                return self.db_manager.get_all_active_users()
        else:
            return []
    
    def get_pending_notifications(self, user_id: int) -> List[Dict]:
        """Получение ожидающих уведомлений"""
        if hasattr(self.db_manager, 'get_pending_notifications'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_pending_notifications, user_id)
            else:
                return self.db_manager.get_pending_notifications(user_id)
        else:
            return []
    
    def get_balance_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Получение топа по балансу"""
        if hasattr(self.db_manager, 'get_balance_leaderboard'):
            if self.is_postgres:
                return self._run_sync(self.db_manager.get_balance_leaderboard, limit)
            else:
                return self.db_manager.get_balance_leaderboard(limit)
        else:
            return []
    
    def get_connection(self):
        """Получение соединения с базой данных"""
        if self.is_postgres:
            # Для PostgreSQL возвращаем контекстный менеджер
            return self.db_manager.get_connection()
        else:
            # Для SQLite возвращаем обычное соединение
            return self.db_manager.get_connection()
    
    def register_user(self, user_id: int, username: str = None, first_name: str = None, 
                     last_name: str = None, language_code: str = 'ru') -> bool:
        """Регистрация пользователя (алиас для add_user)"""
        return self.add_user(user_id, username, first_name, last_name, language_code)
    
    def init_database(self):
        """Инициализация базы данных (для совместимости с SQLite)"""
        if not self.is_postgres:
            return self.db_manager.init_database()
        # Для PostgreSQL инициализация происходит при подключении
        return True
    
    # Прямое обращение к оригинальному менеджеру для методов, которые не нужно адаптировать
    def __getattr__(self, name):
        """Проксирование недостающих методов к оригинальному менеджеру"""
        attr = getattr(self.db_manager, name)
        if callable(attr) and self.is_postgres:
            # Для PostgreSQL оборачиваем в синхронный вызов если это корутина
            import inspect
            if inspect.iscoroutinefunction(attr):
                def sync_wrapper(*args, **kwargs):
                    return self._run_sync(attr, *args, **kwargs)
                return sync_wrapper
        return attr 