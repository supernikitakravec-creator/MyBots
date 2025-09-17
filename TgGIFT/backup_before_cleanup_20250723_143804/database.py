#!/usr/bin/env python3
"""
Оптимизированная система базы данных для TgGIFT Star Bot
"""

import sqlite3
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from contextlib import contextmanager
from config import DATABASE_PATH, SUBSCRIPTION_CONFIGS, QUEUE_SETTINGS
import json

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Оптимизированный менеджер базы данных"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()  # Рекурсивный lock для избежания deadlock
        self._connection_pool = []
        self._pool_size = 5
        self._init_pool()
        self.init_database()
    
    def _init_pool(self):
        """Инициализация пула соединений"""
        try:
            for _ in range(self._pool_size):
                conn = sqlite3.connect(
                    self.db_path, 
                    timeout=30.0,
                    check_same_thread=False
                )
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
                conn.execute("PRAGMA temp_store = MEMORY")
                self._connection_pool.append(conn)
        except Exception as e:
            logger.error(f"Ошибка инициализации пула соединений: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения соединения из пула"""
        conn = None
        try:
            with self._lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                else:
                    # Создаем новое соединение если пул пуст
                    conn = sqlite3.connect(
                        self.db_path, 
                        timeout=30.0,
                        check_same_thread=False
                    )
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA journal_mode = WAL")
            
            yield conn
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка SQLite: {e}")
            if conn:
                conn.rollback()
            raise
        except Exception as e:
            logger.error(f"Ошибка соединения с БД: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                try:
                    conn.commit()
                    with self._lock:
                        if len(self._connection_pool) < self._pool_size:
                            self._connection_pool.append(conn)
                        else:
                            conn.close()
                except Exception as e:
                    logger.error(f"Ошибка возврата соединения в пул: {e}")
                    try:
                        conn.close()
                    except:
                        pass
    
    def init_database(self):
        """Инициализация базы данных с индексами"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Таблица пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                ''')
                
                # Таблица подписок
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        subscription_type TEXT NOT NULL,
                        start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        end_date TIMESTAMP NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица балансов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS balances (
                        user_id INTEGER PRIMARY KEY,
                        balance_stars INTEGER DEFAULT 0 CHECK (balance_stars >= 0),
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица транзакций
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        transaction_type TEXT NOT NULL,
                        amount INTEGER NOT NULL,
                        description TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица очереди покупок
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS purchase_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        gift_id TEXT NOT NULL,
                        priority INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'pending',
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица подарков
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gifts (
                        gift_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        price_stars INTEGER NOT NULL CHECK (price_stars > 0),
                        url TEXT,
                        source TEXT,
                        is_available BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица покупок
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS purchases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        gift_id TEXT NOT NULL,
                        price_stars INTEGER NOT NULL,
                        purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'completed',
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                        FOREIGN KEY (gift_id) REFERENCES gifts (gift_id)
                    )
                ''')
                
                # Таблица уведомлений
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        message TEXT NOT NULL,
                        notification_type TEXT DEFAULT 'info',
                        is_sent BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        sent_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')

                # Новые таблицы для системы баллов и платежей
                
                # Таблица балансов Telegram Stars
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS stars_balances (
                        user_id INTEGER PRIMARY KEY,
                        balance_stars INTEGER DEFAULT 0 CHECK (balance_stars >= 0),
                        total_earned INTEGER DEFAULT 0,
                        total_spent INTEGER DEFAULT 0,
                        total_commission INTEGER DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица транзакций со Stars
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS stars_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        type TEXT NOT NULL CHECK (type IN ('topup', 'spend', 'bonus', 'refund')),
                        amount INTEGER NOT NULL,
                        balance_after INTEGER NOT NULL,
                        source TEXT,
                        description TEXT,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица истории конвертаций
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS conversion_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        source_currency TEXT NOT NULL,
                        source_amount REAL NOT NULL,
                        points_amount INTEGER NOT NULL,
                        conversion_rate REAL NOT NULL,
                        bonus_percent REAL DEFAULT 0,
                        bonus_points INTEGER DEFAULT 0,
                        payment_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица платежей (ЮКасса, TON и др.)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        payment_id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        payment_type TEXT NOT NULL CHECK (payment_type IN ('subscription', 'points_topup', 'stars_topup')),
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL,
                        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица профилей автопокупки для VIP
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS auto_purchase_profiles (
                        user_id INTEGER PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        max_price_stars INTEGER DEFAULT 500,
                        max_edition_size INTEGER DEFAULT 1000,
                        preferred_categories TEXT,
                        auto_buy_cooldown INTEGER DEFAULT 5,
                        daily_limit INTEGER DEFAULT 10,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица резервирования баллов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS points_reservations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        points_amount INTEGER NOT NULL,
                        purpose TEXT NOT NULL,
                        status TEXT DEFAULT 'active' CHECK (status IN ('active', 'confirmed', 'cancelled')),
                        expires_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Таблица покупок подарков с расширенной информацией
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gift_purchases_extended (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        recipient_id INTEGER,
                        gift_id TEXT NOT NULL,
                        gift_name TEXT,
                        points_spent INTEGER NOT NULL,
                        stars_spent INTEGER NOT NULL,
                        commission_amount INTEGER NOT NULL,
                        telegram_gift_id TEXT,
                        purchase_method TEXT DEFAULT 'auto',
                        status TEXT DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')

                # Обновляем существующие таблицы
                
                # Добавляем новые поля к таблице подписок
                try:
                    cursor.execute('ALTER TABLE subscriptions ADD COLUMN payment_method TEXT DEFAULT "stars"')
                except:
                    pass  # Поле уже существует
                
                try:
                    cursor.execute('ALTER TABLE subscriptions ADD COLUMN price_paid REAL DEFAULT 0')
                except:
                    pass
                
                try:
                    cursor.execute('ALTER TABLE subscriptions ADD COLUMN currency TEXT DEFAULT "stars"')
                except:
                    pass
                
                # Миграция: удаляем ограничение CHECK для payment_type в таблице payments
                # Создаем новую таблицу с обновленным ограничением
                try:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS payments_new (
                            payment_id TEXT PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            payment_type TEXT NOT NULL CHECK (payment_type IN ('subscription', 'points_topup', 'stars_topup')),
                            amount REAL NOT NULL,
                            currency TEXT NOT NULL,
                            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
                            metadata TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            completed_at TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                        )
                    ''')
                    
                    # Копируем данные из старой таблицы
                    cursor.execute('''
                        INSERT OR IGNORE INTO payments_new 
                        SELECT * FROM payments
                    ''')
                    
                    # Удаляем старую таблицу и переименовываем новую
                    cursor.execute('DROP TABLE IF EXISTS payments_old')
                    cursor.execute('ALTER TABLE payments RENAME TO payments_old')
                    cursor.execute('ALTER TABLE payments_new RENAME TO payments')
                except Exception as e:
                    logger.warning(f"Миграция таблицы payments не выполнена: {e}")
                
                # Создаем индексы для оптимизации
                self._create_indexes(cursor)
                
                logger.info("База данных инициализирована успешно")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise
    
    def _create_indexes(self, cursor):
        """Создание индексов для оптимизации запросов"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON subscriptions(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_end_date ON subscriptions(end_date)",
            "CREATE INDEX IF NOT EXISTS idx_balances_user_id ON balances(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type)",
            "CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_purchase_queue_user_id ON purchase_queue(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_gifts_available ON gifts(is_available)",
            "CREATE INDEX IF NOT EXISTS idx_gifts_price ON gifts(price_stars)",
            "CREATE INDEX IF NOT EXISTS idx_purchases_user_id ON purchases(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_sent ON notifications(is_sent)",
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except sqlite3.Error as e:
                logger.warning(f"Не удалось создать индекс: {e}")
    
    def _validate_user_id(self, user_id: int) -> bool:
        """Валидация ID пользователя"""
        return isinstance(user_id, int) and 1 <= user_id <= 9999999999  # Telegram user ID limits
    
    def _validate_amount(self, amount: int) -> bool:
        """Валидация суммы"""
        return isinstance(amount, int) and 0 < amount <= 1000000000  # Reasonable limits
    
    def _validate_string(self, value: str, max_length: int = 255) -> bool:
        """Валидация строковых значений"""
        return isinstance(value, str) and 0 < len(value.strip()) <= max_length
    
    def _sanitize_string(self, value: str) -> str:
        """Санитизация строковых значений"""
        if not isinstance(value, str):
            return ""
        # Удаляем потенциально опасные символы
        import re
        return re.sub(r'[<>"\';\\]', '', value.strip())[:255]
    
    def register_user(self, user_id: int, username: str = None, 
                     first_name: str = None, last_name: str = None) -> bool:
        """Регистрация нового пользователя"""
        if not self._validate_user_id(user_id):
            logger.error(f"Некорректный user_id: {user_id}")
            return False
        
        # Санитизация входных данных
        username = self._sanitize_string(username) if username else None
        first_name = self._sanitize_string(first_name) if first_name else None
        last_name = self._sanitize_string(last_name) if last_name else None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли пользователь
                cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
                if cursor.fetchone():
                    logger.debug(f"Пользователь {user_id} уже существует")
                    return True
                
                # Регистрируем нового пользователя
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                
                # Создаем запись баланса
                cursor.execute('''
                    INSERT INTO balances (user_id, balance_stars)
                    VALUES (?, 0)
                ''', (user_id,))
                
                # Создаем запись внутреннего баланса
                cursor.execute('''
                    INSERT INTO internal_balances (user_id, balance_points)
                    VALUES (?, 0)
                ''', (user_id,))
                
                logger.info(f"Пользователь {user_id} зарегистрирован")
                return True
                
        except sqlite3.IntegrityError as e:
            logger.warning(f"Пользователь {user_id} уже существует: {e}")
            return True  # Пользователь уже существует - не ошибка
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя {user_id}: {e}")
            return False
    
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Получение информации о пользователе"""
        if not self._validate_user_id(user_id):
            return None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name, 
                           registration_date, is_active
                    FROM users 
                    WHERE user_id = ?
                ''', (user_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'user_id': row[0],
                        'username': row[1],
                        'first_name': row[2],
                        'last_name': row[3],
                        'registration_date': row[4],
                        'is_active': row[5]
                    }
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
            return None
    
    def activate_subscription(self, user_id: int, subscription_type: str) -> bool:
        """Активация подписки"""
        if not self._validate_user_id(user_id):
            return False
        
        if subscription_type not in SUBSCRIPTION_CONFIGS:
            logger.error(f"Неизвестный тип подписки: {subscription_type}")
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Деактивируем старые подписки
                cursor.execute('''
                    UPDATE subscriptions 
                    SET is_active = FALSE 
                    WHERE user_id = ? AND is_active = TRUE
                ''', (user_id,))
                
                # Создаем новую подписку
                duration_days = SUBSCRIPTION_CONFIGS[subscription_type]['duration_days']
                end_date = datetime.now() + timedelta(days=duration_days)
                
                cursor.execute('''
                    INSERT INTO subscriptions (user_id, subscription_type, end_date)
                    VALUES (?, ?, ?)
                ''', (user_id, subscription_type, end_date))
                
                logger.info(f"Подписка {subscription_type} активирована для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка активации подписки для пользователя {user_id}: {e}")
            return False
    
    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """Получение активной подписки пользователя"""
        if not self._validate_user_id(user_id):
            return None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT subscription_type, start_date, end_date, is_active
                    FROM subscriptions
                    WHERE user_id = ? AND is_active = TRUE AND end_date > ?
                    ORDER BY end_date DESC
                    LIMIT 1
                ''', (user_id, datetime.now()))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'type': row[0],
                        'start_date': row[1],
                        'end_date': row[2],
                        'is_active': row[3]
                    }
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения подписки пользователя {user_id}: {e}")
            return None
    
    def get_balance(self, user_id: int) -> int:
        """Получение баланса пользователя"""
        if not self._validate_user_id(user_id):
            return 0
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT balance_stars FROM balances WHERE user_id = ?', (user_id,))
                row = cursor.fetchone()
                return row[0] if row else 0
                
        except Exception as e:
            logger.error(f"Ошибка получения баланса пользователя {user_id}: {e}")
            return 0
    
    def update_balance(self, user_id: int, amount: int, 
                      transaction_type: str, description: str = "") -> bool:
        """Обновление баланса пользователя с транзакцией"""
        if not self._validate_user_id(user_id):
            return False
        
        if not isinstance(amount, int) or amount == 0:
            logger.error(f"Некорректная сумма: {amount}")
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем текущий баланс
                cursor.execute('SELECT balance_stars FROM balances WHERE user_id = ?', (user_id,))
                row = cursor.fetchone()
                current_balance = row[0] if row else 0
                
                # Проверяем, что баланс не станет отрицательным
                new_balance = current_balance + amount
                if new_balance < 0:
                    logger.warning(f"Недостаточно средств у пользователя {user_id}: {current_balance} + {amount} = {new_balance}")
                    return False
                
                # Обновляем баланс
                cursor.execute('''
                    UPDATE balances 
                    SET balance_stars = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (new_balance, user_id))
                
                # Записываем транзакцию
                cursor.execute('''
                    INSERT INTO transactions (user_id, transaction_type, amount, description)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, transaction_type, amount, description))
                
                logger.info(f"Баланс пользователя {user_id} обновлен на {amount} звезд")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка обновления баланса пользователя {user_id}: {e}")
            return False
    
    def add_transaction(self, user_id: int, transaction_type: str, 
                       amount: int, description: str = "") -> bool:
        """Добавление транзакции"""
        if not self._validate_user_id(user_id):
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO transactions (user_id, transaction_type, amount, description)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, transaction_type, amount, description))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка добавления транзакции: {e}")
            return False
    
    def cleanup_expired_subscriptions(self) -> int:
        """Очистка истекших подписок"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subscriptions 
                    SET is_active = FALSE 
                    WHERE is_active = TRUE AND end_date <= ?
                ''', (datetime.now(),))
                
                count = cursor.rowcount
                logger.info(f"Деактивировано {count} истекших подписок")
                return count
                
        except Exception as e:
            logger.error(f"Ошибка очистки истекших подписок: {e}")
            return 0
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Получение статистики базы данных"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Количество пользователей
                cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = TRUE')
                stats['users'] = cursor.fetchone()[0]
                
                # Активные подписки
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions 
                    WHERE is_active = TRUE AND end_date > ?
                ''', (datetime.now(),))
                stats['active_subscriptions'] = cursor.fetchone()[0]
                
                # Транзакции
                cursor.execute('SELECT COUNT(*) FROM transactions')
                stats['transactions'] = cursor.fetchone()[0]
                
                # Подарки
                cursor.execute('SELECT COUNT(*) FROM gifts WHERE is_available = TRUE')
                stats['gifts'] = cursor.fetchone()[0]
                
                # Размер базы данных
                cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                stats['db_size'] = cursor.fetchone()[0]
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики БД: {e}")
            return {}
    
    def add_notification(self, user_id: int, message: str, notification_type: str = 'info') -> bool:
        """Добавление уведомления"""
        if not self._validate_user_id(user_id):
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO notifications (user_id, message, notification_type)
                    VALUES (?, ?, ?)
                ''', (user_id, message, notification_type))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка добавления уведомления: {e}")
            return False
    
    def get_pending_notifications(self, user_id: int) -> List[Dict]:
        """Получение неотправленных уведомлений"""
        if not self._validate_user_id(user_id):
            return []
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, message, notification_type, created_at
                    FROM notifications
                    WHERE user_id = ? AND is_sent = FALSE
                    ORDER BY created_at ASC
                    LIMIT 10
                ''', (user_id,))
                
                notifications = []
                for row in cursor.fetchall():
                    notifications.append({
                        'id': row[0],
                        'message': row[1],
                        'type': row[2],
                        'created_at': row[3]
                    })
                
                return notifications
                
        except Exception as e:
            logger.error(f"Ошибка получения уведомлений: {e}")
            return []
    
    def mark_notification_sent(self, notification_id: int) -> bool:
        """Отметка уведомления как отправленного"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE notifications 
                    SET is_sent = TRUE, sent_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (notification_id,))
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Ошибка отметки уведомления как отправленного: {e}")
            return False
    
    def mark_notification_failed(self, notification_id: int) -> bool:
        """Отметка уведомления как неудачного"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE notifications 
                    SET is_sent = TRUE, sent_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (notification_id,))
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Ошибка отметки уведомления как неудачного: {e}")
            return False
    
    def get_all_active_users(self) -> List[Dict]:
        """Получение всех активных пользователей"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, username, first_name
                    FROM users
                    WHERE is_active = TRUE
                    ORDER BY registration_date DESC
                ''')
                
                users = []
                for row in cursor.fetchall():
                    users.append({
                        'user_id': row[0],
                        'username': row[1],
                        'first_name': row[2]
                    })
                
                return users
                
        except Exception as e:
            logger.error(f"Ошибка получения активных пользователей: {e}")
            return []
    
    def get_available_gifts(self) -> List[Dict]:
        """Получение доступных подарков"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT gift_id, name, price_stars, url, 'telegram' as source
                    FROM gifts
                    WHERE is_available = TRUE
                    ORDER BY price_stars ASC
                ''')
                
                gifts = []
                for row in cursor.fetchall():
                    gifts.append({
                        'gift_id': row[0],
                        'name': row[1],
                        'price_stars': row[2],
                        'url': row[3],
                        'source': row[4]
                    })
                
                return gifts
                
        except Exception as e:
            logger.error(f"Ошибка получения доступных подарков: {e}")
            return []
    
    def add_gift(self, gift_id: str, name: str, price_stars: int, 
                url: str = None, source: str = None) -> bool:
        """Добавление подарка"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO gifts (gift_id, name, price_stars, url, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (gift_id, name, price_stars, url, source))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка добавления подарка: {e}")
            return False
    
    def record_purchase(self, user_id: int, gift_id: str, price_stars: int) -> bool:
        """Запись покупки"""
        if not self._validate_user_id(user_id):
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Списываем средства с баланса
                if not self.update_balance(user_id, -price_stars, 'gift_purchase', f'Покупка подарка {gift_id}'):
                    return False
                
                # Записываем покупку
                cursor.execute('''
                    INSERT INTO purchases (user_id, gift_id, price_stars)
                    VALUES (?, ?, ?)
                ''', (user_id, gift_id, price_stars))
                
                logger.info(f"Покупка записана: пользователь {user_id}, подарок {gift_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка записи покупки: {e}")
            return False
    
    def get_purchase_queue(self) -> List[Dict]:
        """Получение очереди покупок"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT pq.user_id, pq.gift_id, pq.priority, b.balance_stars,
                           u.first_name, s.subscription_type
                    FROM purchase_queue pq
                    JOIN users u ON pq.user_id = u.user_id
                    JOIN balances b ON pq.user_id = b.user_id
                    LEFT JOIN subscriptions s ON pq.user_id = s.user_id 
                        AND s.is_active = TRUE AND s.end_date > ?
                    WHERE pq.status = 'pending'
                    ORDER BY pq.priority DESC, pq.created_at ASC
                ''', (datetime.now(),))
                
                queue = []
                for row in cursor.fetchall():
                    queue.append({
                        'user_id': row[0],
                        'gift_id': row[1],
                        'priority': row[2],
                        'balance_stars': row[3],
                        'first_name': row[4],
                        'subscription_type': row[5],
                        'current_gifts_bought': 0,  # TODO: Вычислить из покупок
                        'gifts_per_round': QUEUE_SETTINGS.get('gifts_per_round', 1)
                    })
                
                return queue
                
        except Exception as e:
            logger.error(f"Ошибка получения очереди покупок: {e}")
            return []
    
    def add_to_queue(self, user_id: int, gift_id: str, priority: int = 0) -> int:
        """Добавление в очередь покупок"""
        if not self._validate_user_id(user_id):
            return 0
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO purchase_queue (user_id, gift_id, priority)
                    VALUES (?, ?, ?)
                ''', (user_id, gift_id, priority))
                
                # Получаем позицию в очереди
                cursor.execute('''
                    SELECT COUNT(*) FROM purchase_queue
                    WHERE status = 'pending' AND (
                        priority > ? OR 
                        (priority = ? AND created_at <= (
                            SELECT created_at FROM purchase_queue 
                            WHERE user_id = ? AND gift_id = ? AND status = 'pending'
                            ORDER BY created_at DESC LIMIT 1
                        ))
                    )
                ''', (priority, priority, user_id, gift_id))
                
                position = cursor.fetchone()[0]
                logger.info(f"Пользователь {user_id} добавлен в очередь на позицию {position}")
                return position
                
        except Exception as e:
            logger.error(f"Ошибка добавления в очередь: {e}")
            return 0
    
    def __del__(self):
        """Деструктор для закрытия соединений"""
        try:
            for conn in self._connection_pool:
                conn.close()
        except:
            pass 

    def cleanup_old_data(self, days: int = 30):
        """Очистка старых данных"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Удаляем старые уведомления
                cursor.execute(
                    'DELETE FROM notifications WHERE created_at < ? AND is_sent = TRUE',
                    (cutoff_date,)
                )
                
                # Удаляем старые транзакции (кроме важных)
                cursor.execute(
                    'DELETE FROM transactions WHERE timestamp < ? AND transaction_type NOT IN ("subscription_purchase", "gift_purchase")',
                    (cutoff_date,)
                )
                
                deleted_notifications = cursor.rowcount
                logger.info(f"Очищено {deleted_notifications} старых записей")
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых данных: {e}")

    # Новые методы для системы баллов
    
    def get_stars_balance(self, user_id: int) -> int:
        """Получение баланса в Stars"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT balance_stars FROM stars_balances WHERE user_id = ?',
                    (user_id,)
                )
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения баланса Stars: {e}")
            return 0
    
    def get_reserved_points(self, user_id: int) -> int:
        """Получение суммы зарезервированных баллов"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COALESCE(SUM(points_amount), 0) 
                    FROM points_reservations 
                    WHERE user_id = ? AND status = "active" AND expires_at > CURRENT_TIMESTAMP
                ''', (user_id,))
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения зарезервированных баллов: {e}")
            return 0
    
    def add_stars_with_commission(self, user_id: int, stars_requested: int, 
                                  commission_rate: float, source: str, 
                                  description: str = "", metadata: dict = None) -> dict:
        """Добавление баллов пользователю"""
        if not self._validate_user_id(user_id):
            logger.error(f"Некорректный user_id: {user_id}")
            return False
        
        if not self._validate_amount(stars_requested):
            logger.error(f"Некорректная сумма Stars: {stars_requested}")
            return {'success': False, 'error': 'Некорректная сумма'}
        
        if not self._validate_string(source, 50):
            logger.error(f"Некорректный источник: {source}")
            return {'success': False, 'error': 'Некорректный источник'}
        
        # Санитизация данных
        source = self._sanitize_string(source)
        description = self._sanitize_string(description) if description else ""
        
        try:
            # Рассчитываем комиссию
            commission_amount = int(stars_requested * commission_rate)
            total_charged = stars_requested + commission_amount
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем текущий баланс
                current_balance = self.get_stars_balance(user_id)
                new_balance = current_balance + stars_requested
                
                # Проверяем максимальный баланс (защита от переполнения)
                if new_balance > 1000000000:  # 1 миллиард Stars максимум
                    logger.error(f"Превышен максимальный баланс для пользователя {user_id}")
                    return {'success': False, 'error': 'Превышен максимальный баланс'}
                
                # Обновляем или создаем запись баланса
                cursor.execute('''
                    INSERT INTO stars_balances (user_id, balance_stars, total_earned, total_commission)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        balance_stars = balance_stars + ?,
                        total_earned = total_earned + ?,
                        total_commission = total_commission + ?,
                        last_updated = CURRENT_TIMESTAMP
                ''', (user_id, stars_requested, stars_requested, commission_amount, 
                      stars_requested, stars_requested, commission_amount))
                
                # Записываем транзакцию
                cursor.execute('''
                    INSERT INTO stars_transactions 
                    (user_id, type, amount, balance_after, source, description, metadata)
                    VALUES (?, 'topup', ?, ?, ?, ?, ?)
                ''', (user_id, stars_requested, new_balance, source, description, 
                      json.dumps({
                          'stars_requested': stars_requested,
                          'commission_amount': commission_amount,
                          'total_charged': total_charged,
                          'commission_rate': commission_rate,
                          **(metadata or {})
                      })))
                
                logger.info(f"Добавлено {stars_requested} Stars пользователю {user_id}, комиссия {commission_amount}")
                
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
    
    def spend_points(self, user_id: int, amount: int, description: str = "") -> bool:
        """Списание баллов"""
        if not self._validate_user_id(user_id):
            logger.error(f"Некорректный user_id: {user_id}")
            return False
        
        if not self._validate_amount(amount):
            logger.error(f"Некорректная сумма баллов: {amount}")
            return False
        
        # Санитизация данных
        description = self._sanitize_string(description) if description else ""
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем баланс
                current_balance = self.get_points_balance(user_id)
                if current_balance < amount:
                    logger.warning(f"Недостаточно баллов у пользователя {user_id}: {current_balance} < {amount}")
                    return False
                
                new_balance = current_balance - amount
                
                # Обновляем баланс
                cursor.execute('''
                    UPDATE internal_balances 
                    SET balance_points = ?,
                        total_spent = total_spent + ?,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (new_balance, amount, user_id))
                
                # Записываем транзакцию
                cursor.execute('''
                    INSERT INTO points_transactions 
                    (user_id, type, amount, balance_after, source, description)
                    VALUES (?, 'spend', ?, ?, 'internal', ?)
                ''', (user_id, -amount, new_balance, description))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка списания баллов: {e}")
            return False
    
    def reserve_points(self, user_id: int, amount: int, purpose: str) -> Optional[int]:
        """Резервирование баллов на время покупки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем баланс
                current_balance = self.get_points_balance(user_id)
                if current_balance < amount:
                    return None
                
                # Создаем резервирование
                expires_at = datetime.now() + timedelta(minutes=10)  # 10 минут на покупку
                
                cursor.execute('''
                    INSERT INTO points_reservations 
                    (user_id, points_amount, purpose, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, amount, purpose, expires_at))
                
                reservation_id = cursor.lastrowid
                
                # Блокируем баллы
                new_balance = current_balance - amount
                cursor.execute('''
                    UPDATE internal_balances 
                    SET balance_points = ?,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (new_balance, user_id))
                
                logger.info(f"Зарезервировано {amount} баллов для пользователя {user_id}")
                return reservation_id
                
        except Exception as e:
            logger.error(f"Ошибка резервирования баллов: {e}")
            return None
    
    def confirm_points_reservation(self, reservation_id: int) -> bool:
        """Подтверждение резервирования (списание баллов)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о резервировании
                cursor.execute(
                    'SELECT user_id, points_amount, purpose FROM points_reservations WHERE id = ? AND status = "active"',
                    (reservation_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return False
                
                user_id, amount, purpose = row
                
                # Подтверждаем резервирование
                cursor.execute(
                    'UPDATE points_reservations SET status = "confirmed" WHERE id = ?',
                    (reservation_id,)
                )
                
                # Записываем транзакцию списания
                current_balance = self.get_points_balance(user_id)
                cursor.execute('''
                    INSERT INTO points_transactions 
                    (user_id, type, amount, balance_after, source, description)
                    VALUES (?, 'spend', ?, ?, 'reservation', ?)
                ''', (user_id, -amount, current_balance, purpose))
                
                # Обновляем статистику
                cursor.execute('''
                    UPDATE internal_balances 
                    SET total_spent = total_spent + ?,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (amount, user_id))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка подтверждения резервирования: {e}")
            return False
    
    def cancel_points_reservation(self, reservation_id: int) -> bool:
        """Отмена резервирования (возврат баллов)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о резервировании
                cursor.execute(
                    'SELECT user_id, points_amount FROM points_reservations WHERE id = ? AND status = "active"',
                    (reservation_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return False
                
                user_id, amount = row
                
                # Отменяем резервирование
                cursor.execute(
                    'UPDATE points_reservations SET status = "cancelled" WHERE id = ?',
                    (reservation_id,)
                )
                
                # Возвращаем баллы
                cursor.execute('''
                    UPDATE internal_balances 
                    SET balance_points = balance_points + ?,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (amount, user_id))
                
                return True
                
        except Exception as e:
            logger.error(f"Ошибка отмены резервирования: {e}")
            return False
    
    # Методы для работы с платежами
    
    def save_payment_info(self, user_id: int, payment_id: str, payment_type: str, 
                         amount: float, currency: str, status: str = 'pending', 
                         metadata: dict = None) -> bool:
        """Сохранение информации о платеже"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO payments 
                    (payment_id, user_id, payment_type, amount, currency, status, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (payment_id, user_id, payment_type, amount, currency, status,
                      json.dumps(metadata) if metadata else None))
                
                logger.info(f"Сохранен платеж {payment_id} для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка сохранения платежа: {e}")
            return False
    
    def get_payment_info(self, payment_id: str) -> Optional[dict]:
        """Получение информации о платеже"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM payments WHERE payment_id = ?',
                    (payment_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    columns = [description[0] for description in cursor.description]
                    payment_info = dict(zip(columns, row))
                    
                    # Парсим metadata
                    if payment_info['metadata']:
                        try:
                            payment_info['metadata'] = json.loads(payment_info['metadata'])
                        except:
                            payment_info['metadata'] = {}
                    else:
                        payment_info['metadata'] = {}
                    
                    return payment_info
                
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения платежа: {e}")
            return None
    
    def update_payment_status(self, payment_id: str, status: str) -> bool:
        """Обновление статуса платежа"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                completed_at = datetime.now() if status == 'completed' else None
                
                cursor.execute('''
                    UPDATE payments 
                    SET status = ?, completed_at = ?
                    WHERE payment_id = ?
                ''', (status, completed_at, payment_id))
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Ошибка обновления статуса платежа: {e}")
            return False
    
    def get_pending_payments(self, currency: str = None) -> List[dict]:
        """Получение pending платежей"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if currency:
                    cursor.execute(
                        'SELECT * FROM payments WHERE status = "pending" AND currency = ?',
                        (currency,)
                    )
                else:
                    cursor.execute('SELECT * FROM payments WHERE status = "pending"')
                
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                
                payments = []
                for row in rows:
                    payment = dict(zip(columns, row))
                    
                    # Парсим metadata
                    if payment['metadata']:
                        try:
                            payment['metadata'] = json.loads(payment['metadata'])
                        except:
                            payment['metadata'] = {}
                    else:
                        payment['metadata'] = {}
                    
                    payments.append(payment)
                
                return payments
                
        except Exception as e:
            logger.error(f"Ошибка получения pending платежей: {e}")
            return []
    
    # Методы для автопокупки
    
    def get_auto_purchase_profile(self, user_id: int) -> Optional[dict]:
        """Получение профиля автопокупки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM auto_purchase_profiles WHERE user_id = ?',
                    (user_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    columns = [description[0] for description in cursor.description]
                    profile = dict(zip(columns, row))
                    
                    # Парсим preferred_categories
                    if profile['preferred_categories']:
                        try:
                            profile['preferred_categories'] = json.loads(profile['preferred_categories'])
                        except:
                            profile['preferred_categories'] = []
                    else:
                        profile['preferred_categories'] = []
                    
                    return profile
                
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения профиля автопокупки: {e}")
            return None
    
    def save_auto_purchase_profile(self, user_id: int, profile_data: dict) -> bool:
        """Сохранение профиля автопокупки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Подготавливаем данные
                preferred_categories = json.dumps(profile_data.get('preferred_categories', []))
                
                cursor.execute('''
                    INSERT INTO auto_purchase_profiles 
                    (user_id, enabled, max_price_stars, max_edition_size, 
                     preferred_categories, auto_buy_cooldown, daily_limit, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        enabled = excluded.enabled,
                        max_price_stars = excluded.max_price_stars,
                        max_edition_size = excluded.max_edition_size,
                        preferred_categories = excluded.preferred_categories,
                        auto_buy_cooldown = excluded.auto_buy_cooldown,
                        daily_limit = excluded.daily_limit,
                        updated_at = CURRENT_TIMESTAMP
                ''', (
                    user_id,
                    profile_data.get('enabled', False),
                    profile_data.get('max_price_stars', 500),
                    profile_data.get('max_edition_size', 1000),
                    preferred_categories,
                    profile_data.get('auto_buy_cooldown', 5),
                    profile_data.get('daily_limit', 10)
                ))
                
                logger.info(f"Сохранен профиль автопокупки для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка сохранения профиля автопокупки: {e}")
            return False
    
    def get_vip_users_with_auto_buy(self) -> List[dict]:
        """Получение VIP пользователей с включенной автопокупкой"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT s.user_id, s.subscription_type, ap.* 
                    FROM subscriptions s
                    JOIN auto_purchase_profiles ap ON s.user_id = ap.user_id
                    WHERE s.is_active = TRUE 
                    AND s.subscription_type = 'vip'
                    AND s.end_date > CURRENT_TIMESTAMP
                    AND ap.enabled = TRUE
                ''')
                
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                
                users = []
                for row in rows:
                    user_data = dict(zip(columns, row))
                    
                    # Парсим preferred_categories
                    if user_data['preferred_categories']:
                        try:
                            user_data['preferred_categories'] = json.loads(user_data['preferred_categories'])
                        except:
                            user_data['preferred_categories'] = []
                    else:
                        user_data['preferred_categories'] = []
                    
                    users.append(user_data)
                
                return users
                
        except Exception as e:
            logger.error(f"Ошибка получения VIP пользователей: {e}")
            return []
    
    def record_gift_purchase(self, user_id: int, recipient_id: int, gift_id: str,
                           gift_name: str, points_spent: int, stars_spent: int,
                           commission_amount: int, telegram_gift_id: str = None,
                           purchase_method: str = 'auto') -> bool:
        """Запись покупки подарка"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO gift_purchases_extended 
                    (user_id, recipient_id, gift_id, gift_name, points_spent, 
                     stars_spent, commission_amount, telegram_gift_id, purchase_method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, recipient_id, gift_id, gift_name, points_spent,
                      stars_spent, commission_amount, telegram_gift_id, purchase_method))
                
                logger.info(f"Записана покупка подарка {gift_name} для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка записи покупки подарка: {e}")
            return False

    def get_points_transactions_history(self, user_id: int, limit: int = 20) -> List[dict]:
        """Получение истории пополнений баллов"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT type, amount, balance_after, source, description, 
                           created_at, metadata
                    FROM points_transactions 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                
                transactions = []
                for row in cursor.fetchall():
                    transaction = {
                        'type': row[0],
                        'amount': row[1],
                        'balance_after': row[2],
                        'source': row[3],
                        'description': row[4],
                        'created_at': row[5],
                        'metadata': json.loads(row[6]) if row[6] else {}
                    }
                    transactions.append(transaction)
                
                return transactions
                
        except Exception as e:
            logger.error(f"Ошибка получения истории пополнений: {e}")
            return []

    def get_gift_purchases_history(self, user_id: int, limit: int = 20) -> List[dict]:
        """Получение истории покупок подарков"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT gift_name, points_spent, stars_spent, commission_amount,
                           purchase_method, status, created_at, telegram_gift_id
                    FROM gift_purchases_extended 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                
                purchases = []
                for row in cursor.fetchall():
                    purchase = {
                        'gift_name': row[0],
                        'points_spent': row[1],
                        'stars_spent': row[2],
                        'commission_amount': row[3],
                        'purchase_method': row[4],
                        'status': row[5],
                        'created_at': row[6],
                        'telegram_gift_id': row[7]
                    }
                    purchases.append(purchase)
                
                return purchases
                
        except Exception as e:
            logger.error(f"Ошибка получения истории покупок подарков: {e}")
            return []

    def get_user_statistics(self, user_id: int) -> dict:
        """Получение статистики пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Баланс и общая статистика баллов
                cursor.execute('''
                    SELECT balance_points, total_earned, total_spent 
                    FROM internal_balances 
                    WHERE user_id = ?
                ''', (user_id,))
                row = cursor.fetchone()
                
                if row:
                    stats['balance_points'] = row[0]
                    stats['total_earned'] = row[1]
                    stats['total_spent'] = row[2]
                else:
                    stats['balance_points'] = 0
                    stats['total_earned'] = 0
                    stats['total_spent'] = 0
                
                # Количество пополнений
                cursor.execute('''
                    SELECT COUNT(*) FROM points_transactions 
                    WHERE user_id = ? AND type = 'topup'
                ''', (user_id,))
                stats['topups_count'] = cursor.fetchone()[0]
                
                # Количество покупок подарков
                cursor.execute('''
                    SELECT COUNT(*) FROM gift_purchases_extended 
                    WHERE user_id = ?
                ''', (user_id,))
                stats['gifts_purchased'] = cursor.fetchone()[0]
                
                # Общая сумма потраченная на подарки (в рублях)
                cursor.execute('''
                    SELECT SUM(points_spent + commission_amount) 
                    FROM gift_purchases_extended 
                    WHERE user_id = ?
                ''', (user_id,))
                row = cursor.fetchone()
                stats['total_spent_on_gifts'] = row[0] if row[0] else 0
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователя: {e}")
            return {} 

    def get_balance_leaderboard(self, limit: int = 10) -> List[dict]:
        """Получение топа пользователей по балансу"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT u.user_id, u.first_name, u.username, 
                           COALESCE(ib.balance_points, 0) as balance_points,
                           COALESCE(ib.total_earned, 0) as total_earned,
                           COALESCE(s.type, 'basic') as subscription_type,
                           CASE WHEN s.is_active = 1 AND s.end_date > CURRENT_TIMESTAMP 
                                THEN 1 ELSE 0 END as has_active_subscription
                    FROM users u
                    LEFT JOIN internal_balances ib ON u.user_id = ib.user_id
                    LEFT JOIN subscriptions s ON u.user_id = s.user_id 
                    WHERE u.is_active = 1
                    ORDER BY balance_points DESC, total_earned DESC
                    LIMIT ?
                ''', (limit,))
                
                leaderboard = []
                for i, row in enumerate(cursor.fetchall(), 1):
                    user_data = {
                        'position': i,
                        'user_id': row[0],
                        'first_name': row[1] or 'Неизвестно',
                        'username': row[2],
                        'balance_points': row[3],
                        'total_earned': row[4],
                        'subscription_type': row[5],
                        'has_active_subscription': bool(row[6])
                    }
                    leaderboard.append(user_data)
                
                return leaderboard
                
        except Exception as e:
            logger.error(f"Ошибка получения топа по балансу: {e}")
            return []

    def get_user_autopurchase_profiles(self, user_id: int) -> List[dict]:
        """Получение всех профилей автопокупки пользователя"""
        try:
            # Пока у нас один профиль на пользователя, но можно расширить
            profile = self.get_auto_purchase_profile(user_id)
            if profile:
                # Добавляем дополнительную информацию
                profile['id'] = 1  # Временный ID
                profile['name'] = f"Профиль {user_id}"
                return [profile]
            return []
                
        except Exception as e:
            logger.error(f"Ошибка получения профилей автопокупки: {e}")
            return []

    def update_auto_purchase_profile(self, user_id: int, profile_data: dict) -> bool:
        """Обновление профиля автопокупки (алиас для save_auto_purchase_profile)"""
        return self.save_auto_purchase_profile(user_id, profile_data)

    def delete_auto_purchase_profile(self, user_id: int) -> bool:
        """Удаление профиля автопокупки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM auto_purchase_profiles WHERE user_id = ?', (user_id,))
                
                logger.info(f"Профиль автопокупки удален для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка удаления профиля автопокупки: {e}")
            return False

    def toggle_auto_purchase_profile(self, user_id: int) -> bool:
        """Включение/выключение профиля автопокупки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем текущий статус
                cursor.execute('SELECT enabled FROM auto_purchase_profiles WHERE user_id = ?', (user_id,))
                row = cursor.fetchone()
                
                if not row:
                    return False
                
                new_status = not bool(row[0])
                
                # Обновляем статус
                cursor.execute('''
                    UPDATE auto_purchase_profiles 
                    SET enabled = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                ''', (new_status, user_id))
                
                logger.info(f"Профиль автопокупки {'включен' if new_status else 'выключен'} для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка переключения профиля автопокупки: {e}")
            return False

    def get_autopurchase_statistics(self, user_id: int) -> dict:
        """Получение статистики автопокупки пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Общее количество автопокупок
                cursor.execute('''
                    SELECT COUNT(*) FROM gift_purchases_extended 
                    WHERE user_id = ? AND purchase_method = 'auto'
                ''', (user_id,))
                stats['auto_purchases_count'] = cursor.fetchone()[0]
                
                # Потрачено на автопокупки
                cursor.execute('''
                    SELECT SUM(points_spent + commission_amount) 
                    FROM gift_purchases_extended 
                    WHERE user_id = ? AND purchase_method = 'auto'
                ''', (user_id,))
                row = cursor.fetchone()
                stats['auto_purchases_spent'] = row[0] if row[0] else 0
                
                # Автопокупки за последние 24 часа
                cursor.execute('''
                    SELECT COUNT(*) FROM gift_purchases_extended 
                    WHERE user_id = ? AND purchase_method = 'auto'
                    AND created_at > datetime('now', '-24 hours')
                ''', (user_id,))
                stats['auto_purchases_today'] = cursor.fetchone()[0]
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики автопокупки: {e}")
            return {} 