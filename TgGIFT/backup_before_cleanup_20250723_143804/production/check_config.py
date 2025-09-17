#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации TgGIFT Star Bot
"""

import os
import sys
from dotenv import load_dotenv

def check_env_file():
    """Проверка файла .env"""
    print("🔍 Проверка файла .env...")
    
    if not os.path.exists('.env'):
        print("❌ Файл .env не найден!")
        print("💡 Создайте файл .env на основе env_example.txt")
        return False
    
    print("✅ Файл .env найден")
    return True

def check_required_variables():
    """Проверка обязательных переменных"""
    print("\n🔍 Проверка обязательных переменных...")
    
    load_dotenv()
    
    required_vars = {
        'BOT_TOKEN': 'Токен Telegram бота',
        'API_ID': 'API ID для Telegram Client',
        'API_HASH': 'API Hash для Telegram Client',
        'PHONE_NUMBER': 'Номер телефона для управляемого аккаунта'
    }
    
    missing_vars = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value or value == f'your_{var.lower()}_here':
            missing_vars.append(f"{var} ({description})")
            print(f"❌ {var}: не установлен")
        else:
            print(f"✅ {var}: установлен")
    
    if missing_vars:
        print(f"\n❌ Отсутствуют обязательные переменные:")
        for var in missing_vars:
            print(f"   • {var}")
        return False
    
    print("✅ Все обязательные переменные установлены")
    return True

def check_optional_variables():
    """Проверка опциональных переменных"""
    print("\n🔍 Проверка опциональных переменных...")
    
    optional_vars = {
        'DATABASE_PATH': 'gift_bot.db',
        'MONITORING_INTERVAL': '60',
        'GIFT_CHECK_INTERVAL': '30',
        'TEST_MODE': 'false'
    }
    
    for var, default_value in optional_vars.items():
        value = os.getenv(var, default_value)
        print(f"✅ {var}: {value}")
    
    print("✅ Опциональные переменные настроены")

def check_dependencies():
    """Проверка зависимостей"""
    print("\n🔍 Проверка зависимостей...")
    
    required_packages = [
        'telegram',
        'pyrogram',
        'python-dotenv',
        'requests'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package}: установлен")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package}: не установлен")
    
    if missing_packages:
        print(f"\n❌ Отсутствуют зависимости:")
        for package in missing_packages:
            print(f"   • {package}")
        print("\n💡 Установите зависимости:")
        print("   pip install -r requirements.txt")
        return False
    
    print("✅ Все зависимости установлены")
    return True

def check_database():
    """Проверка базы данных"""
    print("\n🔍 Проверка базы данных...")
    
    try:
        from database import DatabaseManager
        
        db_manager = DatabaseManager()
        print("✅ База данных инициализирована")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        return False

def check_config():
    """Проверка конфигурации"""
    print("\n🔍 Проверка конфигурации...")
    
    try:
        from config import (
            BOT_TOKEN, API_ID, API_HASH, PHONE_NUMBER,
            SUBSCRIPTION_CONFIGS, COMMISSION_PERCENT
        )
        
        print("✅ Конфигурация загружена")
        print(f"✅ Комиссия: {COMMISSION_PERCENT}%")
        print(f"✅ Подписки: {len(SUBSCRIPTION_CONFIGS)} типов")
        
        for sub_type, config in SUBSCRIPTION_CONFIGS.items():
            print(f"   • {config['name']}: {config['stars']}⭐")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        return False

def main():
    """Основная функция проверки"""
    print("🔧 Проверка конфигурации TgGIFT Star Bot")
    print("=" * 50)
    
    checks = [
        check_env_file,
        check_required_variables,
        check_optional_variables,
        check_dependencies,
        check_database,
        check_config
    ]
    
    all_passed = True
    
    for check in checks:
        try:
            if not check():
                all_passed = False
        except Exception as e:
            print(f"❌ Ошибка в проверке {check.__name__}: {e}")
            all_passed = False
    
    print("\n" + "=" * 50)
    
    if all_passed:
        print("🎉 Все проверки пройдены! Бот готов к запуску.")
        print("\n💡 Для запуска выполните:")
        print("   python main_bot.py")
    else:
        print("❌ Обнаружены проблемы в конфигурации.")
        print("\n💡 Исправьте ошибки и запустите проверку снова.")
        sys.exit(1)

if __name__ == "__main__":
    main() 