#!/usr/bin/env python3
"""
Скрипт миграции данных из SQLite в PostgreSQL
ВНИМАНИЕ: Запускайте только после остановки бота!
"""

import asyncio
import sqlite3
import logging
import json
from datetime import datetime
from typing import Dict, List, Any
from database import DatabaseManager as SQLiteDB
from database_postgres import PostgresDatabaseManager, DatabaseConfig
import os

# Настройка логирования с поддержкой UTF-8
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Настройка кодировки для Windows
import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
logger = logging.getLogger(__name__)

class DataMigrator:
    """Класс для миграции данных"""
    
    def __init__(self, sqlite_db_path: str = "gift_bot.db"):
        self.sqlite_db_path = sqlite_db_path
        self.sqlite_db = SQLiteDB()
        
        # Создаем конфигурацию для PostgreSQL
        config = DatabaseConfig(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database=os.getenv('POSTGRES_DB', 'tggift_db'),
            user=os.getenv('POSTGRES_USER', 'tggift_user'),
            password=os.getenv('POSTGRES_PASSWORD', 'tggift_password_2024')
        )
        self.postgres_db = PostgresDatabaseManager(config)
        
    async def migrate(self):
        """Основной процесс миграции"""
        logger.info("🚀 Начинаем миграцию данных SQLite → PostgreSQL")
        
        try:
            # Подключаемся к PostgreSQL
            await self.postgres_db.connect()
            logger.info("✅ Подключение к PostgreSQL установлено")
            
            # Выполняем миграцию по таблицам
            await self._migrate_users()
            await self._migrate_subscriptions()
            await self._migrate_stars_balances()
            await self._migrate_stars_transactions()
            await self._migrate_payments()
            await self._migrate_auto_purchase_profiles()
            await self._migrate_gift_purchases()
            
            logger.info("🎉 Миграция завершена успешно!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка миграции: {e}")
            raise
        finally:
            await self.postgres_db.disconnect()
    
    async def _migrate_users(self):
        """Миграция пользователей"""
        logger.info("📤 Миграция пользователей...")
        
        # Получаем данные из SQLite
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
            
            migrated = 0
            for user in users:
                try:
                    success = await self.postgres_db.add_user(
                        user_id=user['user_id'],
                        username=user.get('username'),
                        first_name=user.get('first_name'),
                        last_name=user.get('last_name'),
                        language_code=user.get('language_code', 'ru')
                    )
                    if success:
                        migrated += 1
                except Exception as e:
                    logger.error(f"Ошибка миграции пользователя {user['user_id']}: {e}")
        
        logger.info(f"✅ Пользователи: {migrated} записей мигрировано")
    
    async def _migrate_subscriptions(self):
        """Миграция подписок"""
        logger.info("📤 Миграция подписок...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT * FROM subscriptions")
                subscriptions = cursor.fetchall()
                
                migrated = 0
                async with self.postgres_db.get_connection() as pg_conn:
                    for sub in subscriptions:
                        try:
                            await pg_conn.execute('''
                                INSERT INTO subscriptions 
                                (user_id, subscription_type, start_date, end_date, 
                                 is_active, auto_renewal, payment_id, created_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                                ON CONFLICT DO NOTHING
                            ''', 
                                sub['user_id'],
                                sub['subscription_type'],
                                datetime.fromisoformat(sub['start_date']) if sub['start_date'] else None,
                                datetime.fromisoformat(sub['end_date']) if sub['end_date'] else None,
                                bool(sub.get('is_active', True)),
                                bool(sub.get('auto_renewal', False)),
                                sub.get('payment_id'),
                                datetime.fromisoformat(sub['created_at']) if sub['created_at'] else datetime.now()
                            )
                            migrated += 1
                        except Exception as e:
                            logger.error(f"Ошибка миграции подписки {sub['user_id']}: {e}")
                
                logger.info(f"✅ Подписки: {migrated} записей мигрировано")
                
            except sqlite3.OperationalError:
                logger.info("⚠️ Таблица subscriptions не найдена в SQLite, пропускаем")
    
    async def _migrate_stars_balances(self):
        """Миграция балансов Stars"""
        logger.info("📤 Миграция балансов Stars...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Сначала пробуем новую таблицу stars_balances
            try:
                cursor.execute("SELECT * FROM stars_balances")
                balances = cursor.fetchall()
                table_name = "stars_balances"
            except sqlite3.OperationalError:
                # Если нет, пробуем старую internal_balances
                try:
                    cursor.execute("SELECT * FROM internal_balances")
                    balances = cursor.fetchall()
                    table_name = "internal_balances"
                except sqlite3.OperationalError:
                    logger.info("⚠️ Таблицы балансов не найдены, пропускаем")
                    return
            
            migrated = 0
            async with self.postgres_db.get_connection() as pg_conn:
                for balance in balances:
                    try:
                        await pg_conn.execute('''
                            INSERT INTO stars_balances 
                            (user_id, balance, total_earned, total_spent, total_commission, last_updated)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT (user_id) DO UPDATE SET
                                balance = EXCLUDED.balance,
                                total_earned = EXCLUDED.total_earned,
                                total_spent = EXCLUDED.total_spent,
                                total_commission = EXCLUDED.total_commission,
                                last_updated = EXCLUDED.last_updated
                        ''',
                            balance['user_id'],
                            balance.get('balance', 0),
                            balance.get('total_earned', 0),
                            balance.get('total_spent', 0),
                            float(balance.get('total_commission', 0)),
                            datetime.now()
                        )
                        migrated += 1
                    except Exception as e:
                        logger.error(f"Ошибка миграции баланса {balance['user_id']}: {e}")
            
            logger.info(f"✅ Балансы Stars ({table_name}): {migrated} записей мигрировано")
    
    async def _migrate_stars_transactions(self):
        """Миграция транзакций Stars"""
        logger.info("📤 Миграция транзакций Stars...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Пробуем разные названия таблиц
            table_names = ['stars_transactions', 'points_transactions']
            transactions = []
            
            for table_name in table_names:
                try:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    transactions = cursor.fetchall()
                    logger.info(f"Найдена таблица {table_name}")
                    break
                except sqlite3.OperationalError:
                    continue
            
            if not transactions:
                logger.info("⚠️ Таблицы транзакций не найдены, пропускаем")
                return
            
            migrated = 0
            async with self.postgres_db.get_connection() as pg_conn:
                for tx in transactions:
                    try:
                        await pg_conn.execute('''
                            INSERT INTO stars_transactions 
                            (user_id, transaction_type, amount, balance_before, balance_after,
                             description, payment_id, metadata, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ''',
                            tx['user_id'],
                            tx.get('transaction_type', 'topup'),
                            tx.get('amount', 0),
                            tx.get('balance_before', 0),
                            tx.get('balance_after', 0),
                            tx.get('description', ''),
                            tx.get('payment_id'),
                            json.dumps({}),  # Пустые метаданные если их нет
                            datetime.fromisoformat(tx['created_at']) if tx.get('created_at') else datetime.now()
                        )
                        migrated += 1
                    except Exception as e:
                        logger.error(f"Ошибка миграции транзакции {tx.get('id', 'unknown')}: {e}")
            
            logger.info(f"✅ Транзакции Stars: {migrated} записей мигрировано")
    
    async def _migrate_payments(self):
        """Миграция платежей"""
        logger.info("📤 Миграция платежей...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT * FROM payments")
                payments = cursor.fetchall()
                
                migrated = 0
                async with self.postgres_db.get_connection() as pg_conn:
                    for payment in payments:
                        try:
                            await pg_conn.execute('''
                                INSERT INTO payments 
                                (payment_id, user_id, payment_type, amount, currency,
                                 status, payment_method, external_payment_id, payment_url,
                                 metadata, created_at, completed_at, expires_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                                ON CONFLICT (payment_id) DO NOTHING
                            ''',
                                payment['payment_id'],
                                payment['user_id'],
                                payment['payment_type'],
                                float(payment['amount']),
                                payment['currency'],
                                payment.get('status', 'pending'),
                                payment.get('payment_method', 'unknown'),
                                payment.get('external_payment_id'),
                                payment.get('payment_url'),
                                json.dumps({}),
                                datetime.fromisoformat(payment['created_at']) if payment.get('created_at') else datetime.now(),
                                datetime.fromisoformat(payment['completed_at']) if payment.get('completed_at') else None,
                                datetime.fromisoformat(payment['expires_at']) if payment.get('expires_at') else None
                            )
                            migrated += 1
                        except Exception as e:
                            logger.error(f"Ошибка миграции платежа {payment['payment_id']}: {e}")
                
                logger.info(f"✅ Платежи: {migrated} записей мигрировано")
                
            except sqlite3.OperationalError:
                logger.info("⚠️ Таблица payments не найдена, пропускаем")
    
    async def _migrate_auto_purchase_profiles(self):
        """Миграция профилей автопокупки"""
        logger.info("📤 Миграция профилей автопокупки...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT * FROM auto_purchase_profiles")
                profiles = cursor.fetchall()
                
                migrated = 0
                for profile in profiles:
                    try:
                        # Парсим preferred_categories
                        categories = []
                        if profile.get('preferred_categories'):
                            try:
                                categories = json.loads(profile['preferred_categories'])
                            except:
                                categories = profile['preferred_categories'].split(',') if profile['preferred_categories'] else []
                        
                        profile_data = {
                            'enabled': bool(profile.get('enabled', False)),
                            'max_price_stars': profile.get('max_price_stars', 500),
                            'max_edition_size': profile.get('max_edition_size', 1000),
                            'preferred_categories': categories,
                            'auto_buy_cooldown': profile.get('auto_buy_cooldown', 5),
                            'daily_limit': profile.get('daily_limit', 10)
                        }
                        
                        success = await self.postgres_db.update_auto_purchase_profile(
                            profile['user_id'], profile_data
                        )
                        if success:
                            migrated += 1
                    except Exception as e:
                        logger.error(f"Ошибка миграции профиля автопокупки {profile['user_id']}: {e}")
                
                logger.info(f"✅ Профили автопокупки: {migrated} записей мигрировано")
                
            except sqlite3.OperationalError:
                logger.info("⚠️ Таблица auto_purchase_profiles не найдена, пропускаем")
    
    async def _migrate_gift_purchases(self):
        """Миграция покупок подарков"""
        logger.info("📤 Миграция покупок подарков...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT * FROM gift_purchases")
                purchases = cursor.fetchall()
                
                migrated = 0
                async with self.postgres_db.get_connection() as pg_conn:
                    for purchase in purchases:
                        try:
                            await pg_conn.execute('''
                                INSERT INTO gift_purchases 
                                (user_id, gift_id, gift_name, price_stars, price_rub,
                                 edition_size, category, is_auto_purchase, transaction_hash,
                                 purchase_date, metadata)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                            ''',
                                purchase['user_id'],
                                purchase.get('gift_id', ''),
                                purchase.get('gift_name', ''),
                                purchase.get('price_stars', 0),
                                float(purchase.get('price_rub', 0)) if purchase.get('price_rub') else None,
                                purchase.get('edition_size'),
                                purchase.get('category'),
                                bool(purchase.get('is_auto_purchase', False)),
                                purchase.get('transaction_hash'),
                                datetime.fromisoformat(purchase['purchase_date']) if purchase.get('purchase_date') else datetime.now(),
                                json.dumps({})
                            )
                            migrated += 1
                        except Exception as e:
                            logger.error(f"Ошибка миграции покупки {purchase.get('id', 'unknown')}: {e}")
                
                logger.info(f"✅ Покупки подарков: {migrated} записей мигрировано")
                
            except sqlite3.OperationalError:
                logger.info("⚠️ Таблица gift_purchases не найдена, пропускаем")
    
    async def verify_migration(self):
        """Проверка результатов миграции"""
        logger.info("🔍 Проверка результатов миграции...")
        
        await self.postgres_db.connect()
        
        try:
            async with self.postgres_db.get_connection() as conn:
                # Проверяем количество записей в основных таблицах
                tables_to_check = [
                    'users', 'subscriptions', 'stars_balances', 
                    'stars_transactions', 'payments', 'auto_purchase_profiles'
                ]
                
                for table in tables_to_check:
                    try:
                        count = await conn.fetchval(f'SELECT COUNT(*) FROM {table}')
                        logger.info(f"✅ {table}: {count} записей")
                    except Exception as e:
                        logger.error(f"❌ Ошибка проверки таблицы {table}: {e}")
                
                # Проверка целостности данных
                health_ok = await self.postgres_db.health_check()
                logger.info(f"🏥 Health check: {'✅ OK' if health_ok else '❌ FAIL'}")
                
        finally:
            await self.postgres_db.disconnect()

async def main():
    """Главная функция миграции"""
    print("""
    🚀 МИГРАЦИЯ SQLite → PostgreSQL
    
    ⚠️  ВНИМАНИЕ! Перед запуском:
    1. Остановите бота
    2. Создайте резервную копию SQLite базы
    3. Настройте PostgreSQL сервер
    4. Проверьте переменную DATABASE_URL
    
    Продолжить? (y/N): """, end="")
    
    response = input().strip().lower()
    if response != 'y':
        print("❌ Миграция отменена")
        return
    
    migrator = DataMigrator()
    
    try:
        await migrator.migrate()
        await migrator.verify_migration()
        
        print("""
        🎉 МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!
        
        Следующие шаги:
        1. Обновите main_bot.py для использования database_postgres.py
        2. Установите переменную окружения USE_POSTGRES=true  
        3. Запустите бота и проверьте работоспособность
        4. После проверки можно удалить старую SQLite базу
        """)
        
    except Exception as e:
        logger.error(f"❌ Миграция не удалась: {e}")
        print("\n❌ Миграция завершилась с ошибками. Проверьте логи.")

if __name__ == "__main__":
    asyncio.run(main()) 