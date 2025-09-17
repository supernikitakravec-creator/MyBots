#!/usr/bin/env python3
"""
Тест основных функций бота без запуска Telegram API
"""
import sys
import os
import asyncio
from datetime import datetime

def test_imports():
    """Тест импорта основных модулей"""
    print("🔍 Проверка импорта модулей...")
    
    try:
        # Основные модули
        from config import BOT_TOKEN, ADMIN_ID, SUBSCRIPTION_CONFIGS
        print("✅ config.py - OK")
        
        # Проверяем токен
        if not BOT_TOKEN:
            print("❌ BOT_TOKEN не установлен!")
            return False
        print(f"✅ BOT_TOKEN установлен: {BOT_TOKEN[:10]}...")
        
        # Проверяем админ ID
        if ADMIN_ID == 0:
            print("⚠️ ADMIN_ID не установлен!")
        else:
            print(f"✅ ADMIN_ID установлен: {ADMIN_ID}")
            
        # База данных
        from database_adapter_simple import SimpleDatabaseAdapter
        print("✅ database_adapter_simple.py - OK")
        
        # Мониторинг подарков
        from gift_monitor import GiftMonitor
        print("✅ gift_monitor.py - OK")
        
        # Платежные системы
        from payment_yookassa import YooKassaPaymentHandler
        from payment_ton import TONPaymentHandler
        print("✅ payment_yookassa.py, payment_ton.py - OK")
        
        # Депозитные аккаунты
        from deposit_accounts_manager import DepositAccountsManager
        print("✅ deposit_accounts_manager.py - OK")
        
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

def test_database_connection():
    """Тест подключения к базе данных"""
    print("\n🔍 Проверка подключения к базе данных...")
    
    try:
        from database_adapter_simple import SimpleDatabaseAdapter
        
        db = SimpleDatabaseAdapter()
        db.init_database()
        print("✅ База данных инициализирована")
        
        # Проверяем основные таблицы
        import sqlite3
        conn = sqlite3.connect('gift_bot.db')
        
        # Проверяем пользователей
        users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        print(f"✅ Пользователей в БД: {users_count}")
        
        # Проверяем подписки
        subs_count = conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
        print(f"✅ Активных подписок: {subs_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка работы с БД: {e}")
        return False

def test_bot_class():
    """Тест создания экземпляра бота"""
    print("\n🔍 Проверка класса бота...")
    
    try:
        from main_bot import TgGiftBot
        
        # Создаем экземпляр бота (без запуска)
        bot = TgGiftBot()
        print("✅ Экземпляр TgGiftBot создан")
        
        # Проверяем основные атрибуты
        if hasattr(bot, 'db_manager'):
            print("✅ db_manager инициализирован")
        
        if hasattr(bot, 'gift_monitor'):
            print("✅ gift_monitor инициализирован")
            
        if hasattr(bot, 'yookassa_handler'):
            print("✅ yookassa_handler инициализирован")
            
        if hasattr(bot, 'ton_handler'):
            print("✅ ton_handler инициализирован")
            
        if hasattr(bot, 'deposit_manager'):
            print("✅ deposit_manager инициализирован")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания бота: {e}")
        return False

def test_session_files():
    """Проверка файлов сессий депозитных аккаунтов"""
    print("\n🔍 Проверка файлов сессий...")
    
    session_files = [
        'deposit_account_account_1.session',
        'deposit_account_account_2.session'
    ]
    
    for session_file in session_files:
        if os.path.exists(session_file):
            size = os.path.getsize(session_file)
            print(f"✅ {session_file}: {size} байт")
        else:
            print(f"⚠️ {session_file}: не найден")
    
    return True

def main():
    """Основная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ ОСНОВНЫХ ФУНКЦИЙ БОТА")
    print("=" * 50)
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("Импорт модулей", test_imports),
        ("Подключение к БД", test_database_connection),
        ("Класс бота", test_bot_class),
        ("Файлы сессий", test_session_files)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: ПРОЙДЕН")
            else:
                print(f"❌ {test_name}: ПРОВАЛЕН")
        except Exception as e:
            print(f"❌ {test_name}: ОШИБКА - {e}")
    
    print("\n" + "="*50)
    print(f"📊 РЕЗУЛЬТАТ: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Бот готов к запуску.")
        return True
    else:
        print("⚠️ Есть проблемы, которые нужно исправить.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 