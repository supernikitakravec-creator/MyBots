#!/usr/bin/env python3
"""
Тестирование новой системы баллов и платежей
"""

import logging
import asyncio
from database import DatabaseManager
from payment_yookassa import YooKassaPaymentHandler
from payment_ton import TONPaymentHandler
from deposit_accounts_manager import DepositAccountsManager
from config import ADMIN_ID, STARS_SYSTEM

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_database_system():
    """Тестирование системы базы данных"""
    logger.info("🧪 Тестирование системы базы данных...")
    
    db_manager = DatabaseManager()
    test_user_id = 123456789
    
    # Тест регистрации пользователя
    db_manager.register_user(test_user_id, "testuser", "Test", "User")
    logger.info("✅ Пользователь зарегистрирован")
    
    # Тест активации подписки
    success = db_manager.activate_subscription(test_user_id, 'vip')
    logger.info(f"{'✅' if success else '❌'} Активация подписки: {success}")
    
    # Тест добавления баллов
    success = db_manager.add_points(test_user_id, 5000, 'test', 'Тестовые баллы')
    balance = db_manager.get_points_balance(test_user_id)
    logger.info(f"{'✅' if success else '❌'} Добавление баллов: {success}, баланс: {balance}")
    
    # Тест резервирования баллов
    reservation_id = db_manager.reserve_points(test_user_id, 1000, 'Тест резервирования')
    logger.info(f"{'✅' if reservation_id else '❌'} Резервирование баллов: {reservation_id}")
    
    if reservation_id:
        # Тест подтверждения резервирования
        success = db_manager.confirm_points_reservation(reservation_id)
        logger.info(f"{'✅' if success else '❌'} Подтверждение резервирования: {success}")
        
        # Проверяем новый баланс
        new_balance = db_manager.get_points_balance(test_user_id)
        logger.info(f"💰 Новый баланс: {new_balance}")
    
    # Тест профиля автопокупки
    profile_data = {
        'enabled': True,
        'max_price_stars': 500,
        'max_edition_size': 1000,
        'preferred_categories': ['test'],
        'daily_limit': 5
    }
    
    success = db_manager.save_auto_purchase_profile(test_user_id, profile_data)
    logger.info(f"{'✅' if success else '❌'} Сохранение профиля автопокупки: {success}")
    
    # Получение профиля
    profile = db_manager.get_auto_purchase_profile(test_user_id)
    logger.info(f"{'✅' if profile else '❌'} Получение профиля: {profile is not None}")
    
    logger.info("✅ Тестирование базы данных завершено")

async def test_payment_systems():
    """Тестирование платежных систем"""
    logger.info("💳 Тестирование платежных систем...")
    
    db_manager = DatabaseManager()
    yookassa_handler = YooKassaPaymentHandler(db_manager)
    ton_handler = TONPaymentHandler(db_manager)
    
    test_user_id = 123456789
    
    # Тест создания платежа ЮКассы для подписки
    logger.info("📋 Тест создания платежа ЮКассы для подписки...")
    result = await yookassa_handler.create_subscription_payment(test_user_id, 'vip')
    logger.info(f"{'✅' if result['success'] else '❌'} ЮКасса подписка: {result.get('payment_id', result.get('error'))}")
    
    # Тест создания платежа ЮКассы для баллов
    logger.info("💰 Тест создания платежа ЮКассы для баллов...")
    result = await yookassa_handler.create_points_topup_payment(test_user_id, 1000.0)
    logger.info(f"{'✅' if result['success'] else '❌'} ЮКасса баллы: {result.get('payment_id', result.get('error'))}")
    
    # Тест создания TON платежа для подписки
    logger.info("💎 Тест создания TON платежа для подписки...")
    result = await ton_handler.create_subscription_payment(test_user_id, 'vip')
    logger.info(f"{'✅' if result['success'] else '❌'} TON подписка: {result.get('payment_id', result.get('error'))}")
    
    # Тест создания TON платежа для баллов
    logger.info("💰 Тест создания TON платежа для баллов...")
    result = await ton_handler.create_points_topup_payment(test_user_id, 1000.0)
    logger.info(f"{'✅' if result['success'] else '❌'} TON баллы: {result.get('payment_id', result.get('error'))}")
    
    logger.info("✅ Тестирование платежных систем завершено")

async def test_deposit_accounts():
    """Тестирование депозитных аккаунтов"""
    logger.info("🏦 Тестирование депозитных аккаунтов...")
    
    db_manager = DatabaseManager()
    deposit_manager = DepositAccountsManager(db_manager)
    
    # Получаем статус аккаунтов
    status = deposit_manager.get_accounts_status()
    logger.info(f"📊 Статус аккаунтов:")
    for account_key, account_status in status.items():
        logger.info(f"  {account_key}: {'🟢' if account_status['is_active'] else '🔴'} {account_status['name']}")
    
    # Тест покупки подарка (симуляция)
    test_gift = {
        'gift_id': 'test_gift_001',
        'name': 'Тестовый подарок',
        'price_stars': 100,
        'url': 'https://t.me/test'
    }
    
    test_user_id = 123456789
    
    logger.info("🎁 Тест покупки подарка...")
    result = await deposit_manager.purchase_gift(test_gift, test_user_id)
    logger.info(f"{'✅' if result['success'] else '❌'} Покупка подарка: {result.get('telegram_gift_id', result.get('error'))}")
    
    logger.info("✅ Тестирование депозитных аккаунтов завершено")

async def test_points_calculations():
    """Тестирование расчетов баллов"""
    logger.info("🧮 Тестирование расчетов баллов...")
    
    # Тест конвертации валют
    test_amounts = [100, 1000, 5000, 10000, 50000]
    
    for amount_rub in test_amounts:
        # Базовые баллы
        conversion_rate = STARS_SYSTEM['conversion_rates']['RUB']
        base_points = int(amount_rub * conversion_rate)
        
        # Вычисляем бонус
        bonus_percent = 0
        for threshold, bonus in sorted(STARS_SYSTEM['topup_bonuses'].items()):
            if base_points >= threshold:
                bonus_percent = bonus
        
        bonus_points = int(base_points * bonus_percent)
        total_points = base_points + bonus_points
        
        logger.info(f"💰 {amount_rub}₽ → {total_points} баллов (базовые: {base_points}, бонус: {bonus_points}, {int(bonus_percent*100)}%)")
    
    # Тест TON конвертации
    ton_rate = STARS_SYSTEM['conversion_rates']['TON']
    amount_ton = 1.0
    points_from_ton = int(amount_ton * ton_rate)
    logger.info(f"💎 {amount_ton} TON → {points_from_ton} баллов")
    
    logger.info("✅ Тестирование расчетов завершено")

async def run_all_tests():
    """Запуск всех тестов"""
    logger.info("🚀 Запуск полного тестирования новой системы TgGIFT...")
    
    try:
        # Тестирование компонентов
        await test_database_system()
        await test_payment_systems()
        await test_points_calculations()
        
        # Тестирование депозитных аккаунтов (может не работать без реальных аккаунтов)
        try:
            await test_deposit_accounts()
        except Exception as e:
            logger.warning(f"⚠️ Тест депозитных аккаунтов пропущен: {e}")
        
        logger.info("✅ Все тесты завершены успешно!")
        
        # Рекомендации
        logger.info("\n📋 Рекомендации для production:")
        logger.info("1. Настройте webhook для ЮКассы")
        logger.info("2. Добавьте мониторинг TON транзакций")
        logger.info("3. Настройте депозитные аккаунты Telegram")
        logger.info("4. Протестируйте реальные платежи")
        logger.info("5. Настройте уведомления админу")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка тестирования: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(run_all_tests()) 