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
                
                # Аккаунты пользователей для покупок с их баланса
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_accounts (
                        user_id BIGINT PRIMARY KEY,
                        phone TEXT,
                        is_connected BOOLEAN DEFAULT FALSE,
                        session_path TEXT,
                        session_string_enc TEXT,
                        purchase_mode TEXT DEFAULT 'deposit' CHECK (purchase_mode IN ('deposit','user')),
                        stars_balance INTEGER DEFAULT 0,
                        last_login TIMESTAMP,
                        last_balance_check TIMESTAMP,
                        last_error TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                # Миграция для старых схем: добавляем недостающие столбцы
                try:
                    await conn.execute("ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS session_string_enc TEXT")
                except Exception:
                    pass
                
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
                    "CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs (level)",
                    "CREATE INDEX IF NOT EXISTS idx_user_accounts_connected ON user_accounts (is_connected)",
                    "CREATE INDEX IF NOT EXISTS idx_user_accounts_mode ON user_accounts (purchase_mode)"
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

    async def get_available_gifts(self) -> List[Dict]:
        """Получение доступных подарков из gift_monitoring"""
        try:
            async with self.get_connection() as conn:
                result = await conn.fetch(
                    """
                    SELECT gift_id, name, price, description, first_seen, last_seen, is_active, metadata
                    FROM gift_monitoring
                    WHERE is_active = TRUE
                    ORDER BY last_seen DESC
                    """
                )

                gifts: List[Dict] = []
                for row in result:
                    meta = row["metadata"] if row["metadata"] else None
                    url = None
                    try:
                        if isinstance(meta, dict):
                            url = meta.get("url")
                        else:
                            # asyncpg может вернуть str, если JSONB как текст
                            import json as _json
                            url = _json.loads(meta).get("url") if meta else None
                    except Exception:
                        url = None
                    gifts.append({
                        "gift_id": row["gift_id"],
                        "name": row["name"],
                        "price_stars": row["price"],
                        "url": url,
                        "created_at": row["first_seen"],
                        "last_seen": row["last_seen"],
                        "is_active": row["is_active"],
                    })
                return gifts
        except Exception as e:
            logger.error(f"Ошибка получения доступных подарков: {e}")
            return []

    async def add_gift(self, gift_id: str, name: str, price_stars: int, url: str = None) -> bool:
        """Сохранить/обновить информацию о подарке в gift_monitoring"""
        try:
            async with self.get_connection() as conn:
                import json as _json
                await conn.execute(
                    """
                    INSERT INTO gift_monitoring (gift_id, name, price, metadata, first_seen, last_seen, is_active)
                    VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, TRUE)
                    ON CONFLICT (gift_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        price = EXCLUDED.price,
                        metadata = EXCLUDED.metadata,
                        last_seen = CURRENT_TIMESTAMP,
                        is_active = TRUE
                    """,
                    gift_id, name, price_stars, _json.dumps({"url": url}) if url else None
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения подарка {gift_id}: {e}")
            return False

    async def get_active_subscribers(self) -> List[int]:
        """Список user_id с активной подпиской"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_id
                    FROM subscriptions
                    WHERE is_active = TRUE AND end_date > CURRENT_TIMESTAMP
                    """
                )
                return [r["user_id"] for r in rows]
        except Exception as e:
            logger.error(f"Ошибка получения активных подписчиков: {e}")
            return []

    async def get_all_active_users(self) -> List[int]:
        """Список всех активных пользователей (без бана)"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_id
                    FROM users
                    WHERE is_banned = FALSE
                    ORDER BY last_activity DESC
                    """
                )
                return [r["user_id"] for r in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    async def get_users_with_autobuy_enabled(self) -> List[Dict]:
        """Пользователи с включённой автопокупкой + их настройки и баланс"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT u.user_id,
                           COALESCE(sb.balance_stars, 0) AS balance_stars,
                           ap.enabled,
                           ap.max_price_stars,
                           ap.max_edition_size,
                           ap.daily_limit,
                           ap.auto_buy_cooldown,
                           ap.preferred_categories
                    FROM users u
                    JOIN auto_purchase_profiles ap ON ap.user_id = u.user_id AND ap.enabled = TRUE
                    LEFT JOIN stars_balances sb ON sb.user_id = u.user_id
                    WHERE u.is_banned = FALSE
                    ORDER BY COALESCE(sb.balance_stars, 0) DESC, u.last_activity DESC
                    """
                )
                users: List[Dict] = []
                for r in rows:
                    users.append({
                        "user_id": r["user_id"],
                        "subscription_type": "free",
                        "max_price_stars": r["max_price_stars"],
                        "max_edition_size": r["max_edition_size"],
                        "daily_limit": r["daily_limit"],
                        "auto_buy_cooldown": r["auto_buy_cooldown"],
                        "preferred_categories": list(r["preferred_categories"]) if r["preferred_categories"] is not None else [],
                        "balance_stars": r["balance_stars"],
                    })
                return users
        except Exception as e:
            logger.error(f"Ошибка получения пользователей с автопокупкой: {e}")
            return []

    # ==== User accounts methods ====
    async def upsert_user_account(self, user_id: int, phone: str = None, session_path: str = None,
                                  is_connected: bool = None, purchase_mode: str = None,
                                  stars_balance: int = None, last_error: str = None) -> bool:
        try:
            async with self.get_connection() as conn:
                # Сначала обеспечим наличие строки
                await conn.execute('''
                    INSERT INTO user_accounts (user_id)
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                ''', user_id)

                # Динамический апдейт
                fields = []
                values: List[Any] = []
                if phone is not None:
                    fields.append("phone = $" + str(len(values)+1))
                    values.append(phone)
                if session_path is not None:
                    fields.append("session_path = $" + str(len(values)+1))
                    values.append(session_path)
                if is_connected is not None:
                    fields.append("is_connected = $" + str(len(values)+1))
                    values.append(is_connected)
                if purchase_mode is not None:
                    fields.append("purchase_mode = $" + str(len(values)+1))
                    values.append(purchase_mode)
                if stars_balance is not None:
                    fields.append("stars_balance = $" + str(len(values)+1))
                    values.append(stars_balance)
                if last_error is not None:
                    fields.append("last_error = $" + str(len(values)+1))
                    values.append(last_error)

                if fields:
                    values.append(user_id)
                    q = f"UPDATE user_accounts SET {', '.join(fields)}, last_login = COALESCE(last_login, CURRENT_TIMESTAMP) WHERE user_id = $" + str(len(values))
                    await conn.execute(q, *values)
                return True
        except Exception as e:
            logger.error(f"Ошибка upsert user_account: {e}")
            return False

    async def get_user_account(self, user_id: int) -> Optional[Dict]:
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow('SELECT * FROM user_accounts WHERE user_id = $1', user_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения user_account: {e}")
            return None

    async def set_user_purchase_mode(self, user_id: int, mode: str) -> bool:
        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    UPDATE user_accounts SET purchase_mode = $1 WHERE user_id = $2
                ''', mode, user_id)
                return True
        except Exception as e:
            logger.error(f"Ошибка установки purchase_mode: {e}")
            return False

    async def set_user_session_connected(self, user_id: int, connected: bool, session_path: str = None) -> bool:
        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    UPDATE user_accounts SET is_connected = $1, session_path = COALESCE($2, session_path), last_login = CURRENT_TIMESTAMP WHERE user_id = $3
                ''', connected, session_path, user_id)
                return True
        except Exception as e:
            logger.error(f"Ошибка установки is_connected: {e}")
            return False

    async def set_user_session_string(self, user_id: int, session_string_enc: str) -> bool:
        try:
            async with self.get_connection() as conn:
                await conn.execute('''
                    UPDATE user_accounts SET session_string_enc = $1 WHERE user_id = $2
                ''', session_string_enc, user_id)
                return True
        except Exception as e:
            logger.error(f"Ошибка записи session_string_enc: {e}")
            return False

    async def get_user_session_string(self, user_id: int) -> Optional[str]:
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow('SELECT session_string_enc FROM user_accounts WHERE user_id = $1', user_id)
                return row['session_string_enc'] if row else None
        except Exception as e:
            logger.error(f"Ошибка чтения session_string_enc: {e}")
            return None

    async def list_connected_user_accounts(self, limit: int = 100) -> List[Dict]:
        """Список подключённых пользовательских аккаунтов"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch(
                    '''
                    SELECT user_id, phone, session_path, purchase_mode, stars_balance, last_login, last_error
                    FROM user_accounts
                    WHERE is_connected = TRUE
                    ORDER BY last_login DESC NULLS LAST
                    LIMIT $1
                    ''',
                    limit,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка подключённых user-аккаунтов: {e}")
            return []

    async def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Получение информации о пользователе"""
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT user_id, username, first_name, last_name, created_at, is_active
                    FROM users
                    WHERE user_id = $1
                """, user_id)

                if result:
                    return dict(result)
                return None

        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
            return None

    async def get_pending_payments(self, currency: str = None) -> List[Dict]:
        """Получение ожидающих платежей"""
        try:
            async with self.get_connection() as conn:
                if currency:
                    result = await conn.fetch("""
                        SELECT payment_id, user_id, amount, currency, status, created_at
                        FROM payments
                        WHERE status = 'pending' AND currency = $1
                        ORDER BY created_at ASC
                    """, currency)
                else:
                    result = await conn.fetch("""
                        SELECT payment_id, user_id, amount, currency, status, created_at
                        FROM payments
                        WHERE status = 'pending'
                        ORDER BY created_at ASC
                    """)

                payments = []
                for row in result:
                    payments.append(dict(row))

                return payments

        except Exception as e:
            logger.error(f"Ошибка получения ожидающих платежей: {e}")
            return []

# Алиас для совместимости