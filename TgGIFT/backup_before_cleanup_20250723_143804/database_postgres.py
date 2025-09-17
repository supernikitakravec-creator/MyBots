#!/usr/bin/env python3
"""
Улучшенная система базы данных для TgGIFT Star Bot - PostgreSQL версия для продакшена
Полная совместимость с существующим database.py + оптимизации для масштабирования
"""

import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, Dict, List, Any, Tuple
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "tggift_db"
    user: str = "tggift_user"
    password: str = "tggift_password_2024"
    min_connections: int = 10
    max_connections: int = 20
    command_timeout: int = 60

class PostgresDatabaseManager:
    """PostgreSQL Database Manager для TgGIFT Bot"""
    
    def __init__(self, config: DatabaseConfig = None):
        self.config = config or DatabaseConfig()
        self.pool: Optional[asyncpg.Pool] = None
        self._is_connected = False
        
    async def connect(self):
        """Подключение к PostgreSQL"""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                min_size=self.config.min_connections,
                max_size=self.config.max_connections,
                command_timeout=self.config.command_timeout
            )
            self._is_connected = True
            logger.info("✅ Подключение к PostgreSQL установлено")
            await self.init_database()
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            raise
            
    async def disconnect(self):
        """Отключение от PostgreSQL"""
        if self.pool:
            await self.pool.close()
            self._is_connected = False
            logger.info("PostgreSQL подключение закрыто")
            
    @asynccontextmanager
    async def get_connection(self):
        """Получение соединения из пула"""
        if not self.pool:
            raise RuntimeError("База данных не подключена")
        async with self.pool.acquire() as connection:
            yield connection
            
    async def init_database(self):
        """Инициализация схемы базы данных"""
        try:
            async with self.get_connection() as conn:
                # Создание таблиц
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        language_code TEXT DEFAULT 'ru',
                        is_premium BOOLEAN DEFAULT FALSE,
                        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_banned BOOLEAN DEFAULT FALSE,
                        ban_reason TEXT,
                        referrer_id BIGINT,
                        total_referrals INTEGER DEFAULT 0,
                        FOREIGN KEY (referrer_id) REFERENCES users (user_id)
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        user_id BIGINT PRIMARY KEY,
                        subscription_type TEXT NOT NULL CHECK (subscription_type IN ('basic', 'vip')),
                        start_date TIMESTAMP NOT NULL,
                        end_date TIMESTAMP NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        auto_renewal BOOLEAN DEFAULT FALSE,
                        payment_method TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS stars_balances (
                        user_id BIGINT PRIMARY KEY,
                        balance_stars INTEGER DEFAULT 0 CHECK (balance_stars >= 0),
                        total_earned INTEGER DEFAULT 0,
                        total_spent INTEGER DEFAULT 0,
                        total_commission INTEGER DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS stars_transactions (
                        transaction_id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        type TEXT NOT NULL CHECK (type IN ('topup', 'purchase', 'refund', 'bonus', 'commission')),
                        amount INTEGER NOT NULL,
                        balance_after INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        description TEXT,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        payment_id TEXT PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        payment_type TEXT NOT NULL CHECK (payment_type IN ('subscription', 'points_topup', 'stars_topup')),
                        amount DECIMAL(10,2) NOT NULL,
                        currency TEXT NOT NULL,
                        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS auto_purchase_profiles (
                        user_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        max_price_stars INTEGER DEFAULT 1000,
                        max_edition_size INTEGER DEFAULT 10000,
                        daily_limit INTEGER DEFAULT 5,
                        auto_buy_cooldown INTEGER DEFAULT 300,
                        preferred_categories TEXT[] DEFAULT '{}',
                        last_purchase TIMESTAMP,
                        total_purchases INTEGER DEFAULT 0,
                        total_spent INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS autopurchase_stats (
                        user_id BIGINT NOT NULL,
                        date DATE NOT NULL,
                        purchases_count INTEGER DEFAULT 0,
                        total_spent INTEGER DEFAULT 0,
                        PRIMARY KEY (user_id, date),
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS gift_purchases (
                        purchase_id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        gift_name TEXT NOT NULL,
                        gift_price INTEGER NOT NULL,
                        purchase_type TEXT NOT NULL CHECK (purchase_type IN ('manual', 'auto')),
                        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
                        deposit_account TEXT,
                        transaction_hash TEXT,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS gift_monitoring (
                        gift_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        price INTEGER NOT NULL,
                        edition_size INTEGER,
                        sold_count INTEGER DEFAULT 0,
                        category TEXT,
                        description TEXT,
                        image_url TEXT,
                        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        metadata JSONB
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS system_logs (
                        log_id SERIAL PRIMARY KEY,
                        level TEXT NOT NULL,
                        module TEXT NOT NULL,
                        message TEXT NOT NULL,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Создание индексов
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)",
                    "CREATE INDEX IF NOT EXISTS idx_users_registration_date ON users (registration_date)",
                    "CREATE INDEX IF NOT EXISTS idx_subscriptions_end_date ON subscriptions (end_date)",
                    "CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON subscriptions (is_active)",
                    "CREATE INDEX IF NOT EXISTS idx_stars_transactions_user_id ON stars_transactions (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_stars_transactions_created_at ON stars_transactions (created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments (status)",
                    "CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments (created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_gift_purchases_user_id ON gift_purchases (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_gift_purchases_created_at ON gift_purchases (created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_gift_monitoring_active ON gift_monitoring (is_active)",
                    "CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs (created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs (level)"
                ]
                
                for index in indexes:
                    await conn.execute(index)
                
                logger.info("✅ PostgreSQL схема инициализирована")
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации PostgreSQL схемы: {e}")
            raise
    
    # Методы совместимости с существующим интерфейсом
    async def add_user(self, user_id: int, username: str = None, first_name: str = None, 
                      last_name: str = None, language_code: str = 'ru') -> bool:
        """Добавление пользователя"""
        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, language_code)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = $2,
                        first_name = $3,
                        last_name = $4,
                        last_activity = CURRENT_TIMESTAMP
                ''', user_id, username, first_name, last_name, language_code)
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return False
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение данных пользователя"""
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None
    
    async def get_stars_balance(self, user_id: int) -> int:
        """Получение баланса Stars"""
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow(
                    'SELECT balance_stars FROM stars_balances WHERE user_id = $1', 
                    user_id
                )
                return row['balance_stars'] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения баланса Stars: {e}")
            return 0
    
    async def add_stars_with_commission(self, user_id: int, stars_requested: int, 
                                      commission_rate: float, source: str, 
                                      description: str = "", metadata: dict = None) -> dict:
        """Добавление Stars с комиссией"""
        try:
            commission_amount = int(stars_requested * commission_rate)
            total_charged = stars_requested + commission_amount
            
            async with self.get_connection() as conn:
                async with conn.transaction():
                    # Обновляем баланс
                    await conn.execute('''
                        INSERT INTO stars_balances (user_id, balance_stars, total_earned, total_commission)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (user_id) DO UPDATE SET
                            balance_stars = stars_balances.balance_stars + $2,
                            total_earned = stars_balances.total_earned + $3,
                            total_commission = stars_balances.total_commission + $4,
                            last_updated = CURRENT_TIMESTAMP
                    ''', user_id, stars_requested, stars_requested, commission_amount)
                    
                    # Получаем новый баланс
                    new_balance = await self.get_stars_balance(user_id)
                    
                    # Записываем транзакцию
                    await conn.execute('''
                        INSERT INTO stars_transactions 
                        (user_id, type, amount, balance_after, source, description, metadata)
                        VALUES ($1, 'topup', $2, $3, $4, $5, $6)
                    ''', user_id, stars_requested, new_balance, source, description, 
                         json.dumps({
                             'stars_requested': stars_requested,
                             'commission_amount': commission_amount,
                             'total_charged': total_charged,
                             'commission_rate': commission_rate,
                             **(metadata or {})
                         }))
                    
                    return {
                        'success': True,
                        'stars_added': stars_requested,
                        'commission_amount': commission_amount,
                        'total_charged': total_charged,
                        'new_balance': new_balance
                    }
                    
        except Exception as e:
            logger.error(f"Ошибка добавления Stars: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_auto_purchase_profile(self, user_id: int) -> Optional[Dict]:
        """Получение профиля автопокупки"""
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow(
                    'SELECT * FROM auto_purchase_profiles WHERE user_id = $1', 
                    user_id
                )
                if row:
                    profile = dict(row)
                    # Конвертируем массив в список
                    if 'preferred_categories' in profile:
                        profile['preferred_categories'] = list(profile['preferred_categories'] or [])
                    return profile
                return None
        except Exception as e:
            logger.error(f"Ошибка получения профиля автопокупки: {e}")
            return None
    
    async def update_auto_purchase_profile(self, user_id: int, **kwargs) -> bool:
        """Обновление профиля автопокупки"""
        try:
            # Сначала создаем профиль если его нет
            await self.create_auto_purchase_profile(user_id)
            
            # Подготавливаем поля для обновления
            fields = []
            values = []
            param_num = 1
            
            for key, value in kwargs.items():
                if key == 'preferred_categories' and isinstance(value, list):
                    fields.append(f"{key} = ${param_num}")
                    values.append(value)
                elif key in ['enabled', 'max_price_stars', 'max_edition_size', 'daily_limit', 'auto_buy_cooldown']:
                    fields.append(f"{key} = ${param_num}")
                    values.append(value)
                param_num += 1
            
            if fields:
                values.append(user_id)
                query = f'''
                    UPDATE auto_purchase_profiles 
                    SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ${param_num}
                '''
                
                async with self.get_connection() as conn:
                    await conn.execute(query, *values)
                    
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления профиля автопокупки: {e}")
            return False
    
    async def create_auto_purchase_profile(self, user_id: int) -> bool:
        """Создание профиля автопокупки"""
        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO auto_purchase_profiles (user_id)
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                ''', user_id)
                return True
        except Exception as e:
            logger.error(f"Ошибка создания профиля автопокупки: {e}")
            return False
    
    async def toggle_auto_purchase_profile(self, user_id: int) -> bool:
        """Переключение статуса автопокупки"""
        try:
            async with self.get_connection() as conn:
                # Создаем профиль если его нет
                await self.create_auto_purchase_profile(user_id)
                
                # Переключаем статус
                await conn.execute('''
                    UPDATE auto_purchase_profiles 
                    SET enabled = NOT enabled, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $1
                ''', user_id)
                
                # Получаем новый статус
                row = await conn.fetchrow(
                    'SELECT enabled FROM auto_purchase_profiles WHERE user_id = $1', 
                    user_id
                )
                return row['enabled'] if row else False
        except Exception as e:
            logger.error(f"Ошибка переключения автопокупки: {e}")
            return False
    
    async def get_autopurchase_statistics(self, user_id: int) -> Dict:
        """Получение статистики автопокупок"""
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow('''
                    SELECT 
                        COALESCE(total_purchases, 0) as total_purchases,
                        COALESCE(total_spent, 0) as total_spent
                    FROM auto_purchase_profiles 
                    WHERE user_id = $1
                ''', user_id)
                
                if row:
                    return {
                        'total_purchases': row['total_purchases'],
                        'total_spent': row['total_spent']
                    }
                return {'total_purchases': 0, 'total_spent': 0}
        except Exception as e:
            logger.error(f"Ошибка получения статистики автопокупок: {e}")
            return {'total_purchases': 0, 'total_spent': 0}
    
    async def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """Получение подписки пользователя"""
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow('''
                    SELECT * FROM subscriptions 
                    WHERE user_id = $1 AND is_active = TRUE AND end_date > CURRENT_TIMESTAMP
                ''', user_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения подписки: {e}")
            return None
    
    async def get_connection_stats(self) -> Dict:
        """Получение статистики подключений"""
        if not self.pool:
            return {'active': 0, 'idle': 0, 'total': 0}
        
        return {
            'active': self.pool.get_size(),
            'idle': self.pool.get_idle_size(),
            'total': self.pool.get_max_size()
        }
    
    async def health_check(self) -> bool:
        """Проверка здоровья базы данных"""
        try:
            async with self.get_connection() as conn:
                await conn.fetchval('SELECT 1')
                return True
        except Exception as e:
            logger.error(f"Ошибка проверки здоровья БД: {e}")
            return False

# Алиас для совместимости
DatabaseManager = PostgresDatabaseManager 