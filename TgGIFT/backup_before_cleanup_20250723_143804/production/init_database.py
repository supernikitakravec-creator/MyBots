#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных TgGIFT Star Bot
"""

import os
import sys
from dotenv import load_dotenv

def init_database():
    """Инициализация базы данных"""
    print("🗄️ Инициализация базы данных TgGIFT Star Bot")
    print("=" * 50)
    
    try:
        # Загружаем переменные окружения
        load_dotenv()
        
        # Импортируем DatabaseManager
        from database import DatabaseManager
        
        # Получаем путь к базе данных
        db_path = os.getenv('DATABASE_PATH', 'gift_bot.db')
        
        print(f"📁 Путь к базе данных: {db_path}")
        
        # Проверяем, существует ли файл базы данных
        if os.path.exists(db_path):
            print(f"⚠️ Файл базы данных уже существует: {db_path}")
            
            response = input("🗑️ Удалить существующую базу данных? (y/N): ")
            if response.lower() == 'y':
                os.remove(db_path)
                print(f"✅ Существующая база данных удалена")
            else:
                print("❌ Операция отменена")
                return False
        
        # Создаем новую базу данных
        print("🔧 Создание новой базы данных...")
        
        db_manager = DatabaseManager(db_path)
        
        print("✅ База данных успешно инициализирована")
        
        # Проверяем созданные таблицы
        print("\n📋 Созданные таблицы:")
        tables = [
            "users - Пользователи",
            "subscriptions - Подписки", 
            "balances - Балансы",
            "transactions - Транзакции",
            "purchase_queue - Очередь покупок",
            "gifts - Подарки",
            "purchases - Покупки"
        ]
        
        for table in tables:
            print(f"   • {table}")
        
        print(f"\n🎉 База данных готова к использованию!")
        print(f"📁 Файл: {db_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        return False

def add_sample_data():
    """Добавление тестовых данных"""
    print("\n🔧 Добавление тестовых данных...")
    
    try:
        from database import DatabaseManager
        
        db_manager = DatabaseManager()
        
        # Добавляем тестового пользователя
        test_user_id = 123456789
        db_manager.register_user(
            test_user_id,
            username="test_user",
            first_name="Тестовый",
            last_name="Пользователь"
        )
        
        # Активируем VIP подписку
        db_manager.activate_subscription(test_user_id, 'vip')
        
        # Пополняем баланс
        db_manager.update_balance(
            test_user_id,
            1000,
            'test_topup',
            'Тестовое пополнение'
        )
        
        # Добавляем в очередь
        db_manager.add_to_purchase_queue(test_user_id, 2)
        
        # Добавляем тестовые подарки
        test_gifts = [
            {
                'gift_id': 'test_gift_1',
                'name': 'Тестовый подарок 1',
                'price_stars': 500,
                'url': 'https://t.me/addstickers/test1'
            },
            {
                'gift_id': 'test_gift_2', 
                'name': 'Тестовый подарок 2',
                'price_stars': 750,
                'url': 'https://t.me/addstickers/test2'
            }
        ]
        
        for gift in test_gifts:
            db_manager.add_gift(
                gift['gift_id'],
                gift['name'],
                gift['price_stars'],
                gift['url']
            )
        
        print("✅ Тестовые данные добавлены")
        print(f"👤 Тестовый пользователь: {test_user_id}")
        print("💎 VIP подписка активирована")
        print("💰 Баланс: 1000⭐")
        print("📊 Позиция в очереди: 1")
        print("🎁 Тестовые подарки: 2")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка добавления тестовых данных: {e}")
        return False

def main():
    """Основная функция"""
    print("🚀 Инициализация TgGIFT Star Bot")
    print("=" * 50)
    
    # Инициализируем базу данных
    if not init_database():
        print("❌ Ошибка инициализации базы данных")
        sys.exit(1)
    
    # Спрашиваем о добавлении тестовых данных
    response = input("\n🧪 Добавить тестовые данные? (y/N): ")
    if response.lower() == 'y':
        if add_sample_data():
            print("\n✅ Тестовые данные успешно добавлены")
        else:
            print("\n❌ Ошибка добавления тестовых данных")
    
    print("\n" + "=" * 50)
    print("🎉 Инициализация завершена!")
    print("\n💡 Следующие шаги:")
    print("1. Настройте .env файл")
    print("2. Запустите: python check_config.py")
    print("3. Запустите бота: python main_bot.py")

if __name__ == "__main__":
    main() 