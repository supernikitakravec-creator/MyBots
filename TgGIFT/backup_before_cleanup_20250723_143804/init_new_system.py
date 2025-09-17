#!/usr/bin/env python3
"""
Скрипт инициализации новой системы баллов и платежей
"""

import logging
import asyncio
from database import DatabaseManager
from config import ADMIN_ID

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def init_new_system():
    """Инициализация новой системы"""
    logger.info("🚀 Инициализация новой системы TgGIFT...")
    
    # Инициализация базы данных
    logger.info("📊 Инициализация базы данных...")
    db_manager = DatabaseManager()
    db_manager.init_database()
    
    # Создание профиля автопокупки для админа (тестовый)
    logger.info(f"👤 Создание тестового профиля автопокупки для админа ({ADMIN_ID})...")
    
    # Регистрируем админа
    db_manager.register_user(
        user_id=ADMIN_ID,
        username="admin",
        first_name="Admin",
        last_name="TgGift"
    )
    
    # Активируем VIP подписку для админа
    success = db_manager.activate_subscription(ADMIN_ID, 'vip')
    if success:
        logger.info("✅ VIP подписка активирована для админа")
    else:
        logger.error("❌ Ошибка активации подписки")
    
    # Добавляем тестовые баллы админу
    success = db_manager.add_points(
        user_id=ADMIN_ID,
        amount=10000,
        source='init',
        description='Начальные баллы для тестирования'
    )
    if success:
        logger.info("✅ Тестовые баллы добавлены админу")
    else:
        logger.error("❌ Ошибка добавления баллов")
    
    # Создаем профиль автопокупки для админа
    profile_data = {
        'enabled': True,
        'max_price_stars': 1000,
        'max_edition_size': 5000,
        'preferred_categories': ['premium', 'rare'],
        'auto_buy_cooldown': 3,
        'daily_limit': 20
    }
    
    success = db_manager.save_auto_purchase_profile(ADMIN_ID, profile_data)
    if success:
        logger.info("✅ Профиль автопокупки создан для админа")
    else:
        logger.error("❌ Ошибка создания профиля автопокупки")
    
    # Проверяем статистику
    logger.info("📊 Проверка системы...")
    
    balance = db_manager.get_points_balance(ADMIN_ID)
    logger.info(f"💰 Баланс админа: {balance} баллов")
    
    subscription = db_manager.get_user_subscription(ADMIN_ID)
    if subscription:
        logger.info(f"⭐ Подписка админа: {subscription['type']} до {subscription['end_date']}")
    else:
        logger.warning("⚠️ Подписка не найдена")
    
    profile = db_manager.get_auto_purchase_profile(ADMIN_ID)
    if profile:
        logger.info(f"⚙️ Автопокупка: {'включена' if profile['enabled'] else 'отключена'}")
    else:
        logger.warning("⚠️ Профиль автопокупки не найден")
    
    logger.info("✅ Инициализация новой системы завершена!")
    logger.info("\n📋 Следующие шаги:")
    logger.info("1. Запустите бота: python main_bot.py")
    logger.info("2. Проверьте команды: /points, /autopurchase, /payments")
    logger.info("3. Протестируйте платежи через ЮКассу и TON")
    logger.info("4. Настройте webhook для ЮКассы")

if __name__ == "__main__":
    asyncio.run(init_new_system()) 