#!/usr/bin/env python3
"""
Система базы данных для TgGIFT Star Bot - PostgreSQL версия
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import asyncpg
from asyncpg import Pool
from config import SUBSCRIPTION_CONFIGS, QUEUE_SETTINGS

logger = logging.getLogger(__name__)

class PostgresDatabaseManager:
    """Менеджер базы данных PostgreSQL"""
    
    def __init__(self, dsn: str = None):
        self.dsn = dsn or "postgresql://tggift:password@localhost/tggift_bot"
        self.pool: Optional[Pool] = None
    
    async def connect(self):
        """Создание пула соединений"""
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=5,
                max_size=20,
                max_inactive_connection_lifetime=60,
                command_timeout=60
            )
            logger.info("PostgreSQL pool создан успешно")
            await self.init_database()
        except Exception as e:
            logger.error(f"Ошибка создания PostgreSQL pool: {e}")
            raise
    
    async def close(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL pool закрыт")
    
    async def init_database(self):
        """Инициализация базы данных"""
        try:
            async with self.pool.acquire() as conn:
                # Таблица пользователей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                ''')
                
                # Таблица подписок
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        subscription_type VARCHAR(50),
                        start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        end_date TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                ''')
                
                # Таблица балансов
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS balances (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                        balance_stars INTEGER DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица транзакций
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        transaction_type VARCHAR(50),
                        amount INTEGER,
                        description TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица очереди покупок
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS purchase_queue (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        position INTEGER,
                        gifts_per_round INTEGER DEFAULT 1,
                        current_gifts_bought INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT TRUE,
                        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица подарков
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS gifts (
                        id SERIAL PRIMARY KEY,
                        gift_id VARCHAR(255) UNIQUE,
                        name VARCHAR(500),
                        price_stars INTEGER,
                        url TEXT,
                        is_available BOOLEAN DEFAULT TRUE,
                        discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица покупок
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS purchases (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        gift_id VARCHAR(255) REFERENCES gifts(gift_id),
                        purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        price_stars INTEGER,
                        status VARCHAR(50) DEFAULT 'completed'
                    )
                ''')
                
                # Создаем индексы
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_user_active ON subscriptions (user_id, is_active)')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions (user_id, timestamp)')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_queue_position ON purchase_queue (position) WHERE is_active = TRUE')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_gifts_available ON gifts (is_available, discovered_date) WHERE is_available = TRUE')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_user_date ON purchases (user_id, purchase_date)')
                
                logger.info("PostgreSQL база данных инициализирована успешно")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации PostgreSQL базы данных: {e}")
            raise
    
    async def register_user(self, user_id: int, username: Optional[str] = None, 
                          first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
        """Регистрация нового пользователя"""
        try:
            async with self.pool.acquire() as conn:
                # Используем INSERT ... ON CONFLICT для атомарной операции
                await conn.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = COALESCE(EXCLUDED.username, users.username),
                        first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                        last_name = COALESCE(EXCLUDED.last_name, users.last_name)
                ''', user_id, username, first_name, last_name)
                
                # Создаем запись баланса если её нет
                await conn.execute('''
                    INSERT INTO balances (user_id, balance_stars)
                    VALUES ($1, 0)
                    ON CONFLICT (user_id) DO NOTHING
                ''', user_id)
                
                logger.info(f"Пользователь {user_id} зарегистрирован")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя {user_id}: {e}")
            return False
    
    async def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Получение информации о пользователе"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT u.*, b.balance_stars, s.subscription_type, s.end_date
                    FROM users u
                    LEFT JOIN balances b ON u.user_id = b.user_id
                    LEFT JOIN subscriptions s ON u.user_id = s.user_id AND s.is_active = TRUE
                    WHERE u.user_id = $1
                ''', user_id)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
            return None
    
    async def activate_subscription(self, user_id: int, subscription_type: str) -> bool:
        """Активация подписки"""
        if subscription_type not in SUBSCRIPTION_CONFIGS:
            logger.error(f"Неизвестный тип подписки: {subscription_type}")
            return False
        
        try:
            config = SUBSCRIPTION_CONFIGS[subscription_type]
            end_date = datetime.now() + timedelta(days=config['duration_days'])
            
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Деактивируем старые подписки
                    await conn.execute('''
                        UPDATE subscriptions 
                        SET is_active = FALSE 
                        WHERE user_id = $1 AND is_active = TRUE
                    ''', user_id)
                    
                    # Активируем новую подписку
                    await conn.execute('''
                        INSERT INTO subscriptions (user_id, subscription_type, end_date)
                        VALUES ($1, $2, $3)
                    ''', user_id, subscription_type, end_date)
                
                logger.info(f"Подписка {subscription_type} активирована для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка активации подписки для пользователя {user_id}: {e}")
            return False
    
    async def update_balance(self, user_id: int, amount: int, 
                           transaction_type: str, description: str = "") -> bool:
        """Обновление баланса пользователя"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Проверяем текущий баланс для отрицательных операций
                    if amount < 0:
                        current_balance = await conn.fetchval(
                            'SELECT balance_stars FROM balances WHERE user_id = $1',
                            user_id
                        )
                        if current_balance is None or current_balance + amount < 0:
                            logger.warning(f"Недостаточно средств у пользователя {user_id}")
                            return False
                    
                    # Обновляем баланс
                    await conn.execute('''
                        UPDATE balances 
                        SET balance_stars = balance_stars + $1, last_updated = CURRENT_TIMESTAMP
                        WHERE user_id = $2
                    ''', amount, user_id)
                    
                    # Записываем транзакцию
                    await conn.execute('''
                        INSERT INTO transactions (user_id, transaction_type, amount, description)
                        VALUES ($1, $2, $3, $4)
                    ''', user_id, transaction_type, amount, description)
                
                logger.info(f"Баланс пользователя {user_id} обновлен на {amount} звезд")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка обновления баланса пользователя {user_id}: {e}")
            return False
    
    async def get_balance(self, user_id: int) -> int:
        """Получение баланса пользователя"""
        try:
            async with self.pool.acquire() as conn:
                balance = await conn.fetchval(
                    'SELECT balance_stars FROM balances WHERE user_id = $1',
                    user_id
                )
                return balance or 0
                
        except Exception as e:
            logger.error(f"Ошибка получения баланса пользователя {user_id}: {e}")
            return 0
    
    async def add_to_purchase_queue(self, user_id: int, gifts_per_round: int = 1) -> bool:
        """Добавление пользователя в очередь покупок"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Проверяем размер очереди
                    queue_size = await conn.fetchval(
                        'SELECT COUNT(*) FROM purchase_queue WHERE is_active = TRUE'
                    )
                    if queue_size >= QUEUE_SETTINGS['max_queue_size']:
                        logger.warning(f"Очередь переполнена: {queue_size}")
                        return False
                    
                    # Проверяем, есть ли уже пользователь в очереди
                    exists = await conn.fetchval('''
                        SELECT EXISTS(
                            SELECT 1 FROM purchase_queue 
                            WHERE user_id = $1 AND is_active = TRUE
                        )
                    ''', user_id)
                    
                    if exists:
                        logger.warning(f"Пользователь {user_id} уже в очереди")
                        return False
                    
                    # Получаем следующую позицию
                    position = await conn.fetchval('''
                        SELECT COALESCE(MAX(position), 0) + 1 
                        FROM purchase_queue 
                        WHERE is_active = TRUE
                    ''')
                    
                    # Добавляем в очередь
                    await conn.execute('''
                        INSERT INTO purchase_queue (user_id, position, gifts_per_round)
                        VALUES ($1, $2, $3)
                    ''', user_id, position, gifts_per_round)
                
                logger.info(f"Пользователь {user_id} добавлен в очередь на позиции {position}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка добавления в очередь пользователя {user_id}: {e}")
            return False
    
    async def get_database_stats(self) -> Dict:
        """Получение статистики базы данных"""
        try:
            async with self.pool.acquire() as conn:
                stats = {}
                
                stats['total_users'] = await conn.fetchval(
                    'SELECT COUNT(*) FROM users WHERE is_active = TRUE'
                )
                stats['active_subscriptions'] = await conn.fetchval(
                    'SELECT COUNT(*) FROM subscriptions WHERE is_active = TRUE'
                )
                stats['queue_size'] = await conn.fetchval(
                    'SELECT COUNT(*) FROM purchase_queue WHERE is_active = TRUE'
                )
                stats['available_gifts'] = await conn.fetchval(
                    'SELECT COUNT(*) FROM gifts WHERE is_available = TRUE'
                )
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики БД: {e}")
            return {}
    
    # Остальные методы аналогично с использованием asyncpg... 