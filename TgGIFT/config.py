#!/usr/bin/env python3
"""
Конфигурация для TgGIFT Star Bot
"""

import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("⚠️ ВНИМАНИЕ: BOT_TOKEN не установлен!")
    print("Создайте файл .env и добавьте: BOT_TOKEN=your_token_here")
    sys.exit(1)

# Админ ID
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
if ADMIN_ID == 0:
    print("⚠️ ВНИМАНИЕ: ADMIN_ID не установлен!")
    print("Добавьте в .env: ADMIN_ID=your_telegram_id")

# Обязательная подписка на канал
REQUIRED_CHANNEL = os.getenv('REQUIRED_CHANNEL', '').strip()  # пример: @gifthunt
REQUIRED_CHANNEL_LINK = os.getenv('REQUIRED_CHANNEL_LINK', '').strip()  # ссылка-приглашение/публичная ссылка
CHECK_MEMBERSHIP_ENABLED = os.getenv('CHECK_MEMBERSHIP_ENABLED', 'true').lower() == 'true'

# Пользовательские аккаунты (покупка с аккаунта пользователя)
USER_API_ID = int(os.getenv('USER_API_ID', os.getenv('DEPOSIT_ACCOUNT_1_API_ID', '0') or '0'))
USER_API_HASH = os.getenv('USER_API_HASH', os.getenv('DEPOSIT_ACCOUNT_1_API_HASH', ''))
USER_SESSIONS_DIR = os.getenv('USER_SESSIONS_DIR', 'user_sessions')
SESSION_ENC_KEY = os.getenv('SESSION_ENC_KEY', '')  # ключ шифрования сессий (опционально)

# Fragment.com интеграция для покупки Stars
FRAGMENT_CONFIG = {
    'enabled': True,
    'base_url': 'https://fragment.com',
    'stars_packages': {
        50: {'ton': 0.2301, 'usd': 0.75},
        75: {'ton': 0.3452, 'usd': 1.12},
        100: {'ton': 0.4603, 'usd': 1.50},
        150: {'ton': 0.6905, 'usd': 2.25},
        250: {'ton': 1.1508, 'usd': 3.75},
        350: {'ton': 1.611, 'usd': 5.25},
        500: {'ton': 2.30, 'usd': 7.50},   # Расчетные значения
        1000: {'ton': 4.60, 'usd': 15.0}   # для больших пакетов
    },
    'min_stars_purchase': 50,
    'max_stars_purchase': 100000,
    'savings_vs_telegram': 0.25,  # 25% экономия по сравнению с Telegram
    'notification_settings': {
        'admin_chat_id': ADMIN_ID,
        'urgent_threshold': 1000,  # Если нужно > 1000 Stars - срочное уведомление
        'timeout_minutes': 60      # Таймаут ожидания покупки админом
    }
}

# Настройки TON кошельков
TON_WALLETS = {}

# Загружаем кошельки из переменных окружения
for i in range(1, 5):  # Поддержка до 4 кошельков
    address = os.getenv(f'TON_WALLET_{i}_ADDRESS')
    if address:
        name = os.getenv(f'TON_WALLET_{i}_NAME', f'Кошелек {i}')
        is_active = os.getenv(f'TON_WALLET_{i}_ACTIVE', 'true').lower() == 'true'
        
        TON_WALLETS[f'wallet_{i}'] = {
            'address': address,
            'name': name,
            'is_active': is_active,
            'memo': 'TgGIFT_Stars',
            'min_amount': 0.1,
            'max_amount': 100.0
        }

# Если нет кошельков в переменных окружения, используем тестовый
if not TON_WALLETS:
    TON_WALLETS = {
        'main': {
            'address': 'UQTest123_for_development_only',
            'name': 'Тестовый кошелек (настройте TON_WALLET_1_ADDRESS в .env)',
            'is_active': True,
            'memo': 'TgGIFT_Stars',
            'min_amount': 0.1,
            'max_amount': 100.0
        }
    }

# Обновленные настройки ЮКассы (только подписки)
YOOKASSA_CONFIG = {
    'shop_id': os.getenv('YOOKASSA_SHOP_ID'),
    'secret_key': os.getenv('YOOKASSA_SECRET_KEY'),
    'webhook_url': os.getenv('YOOKASSA_WEBHOOK_URL'),
    'return_url': os.getenv('YOOKASSA_RETURN_URL', 'https://t.me/your_bot'),
    'allowed_payment_types': ['subscription'],  # Только подписки
    'currency': 'RUB',
    'test_mode': os.getenv('YOOKASSA_TEST_MODE', 'false').lower() == 'true'
}

# Проверяем обязательные настройки ЮКассы
if not YOOKASSA_CONFIG['shop_id'] or not YOOKASSA_CONFIG['secret_key']:
    print("⚠️ ВНИМАНИЕ: Настройки ЮКассы не установлены!")
    print("Добавьте в .env: YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")

# Проверяем настройки TON кошельков
if not TON_WALLETS:
    print("⚠️ ВНИМАНИЕ: TON кошельки не настроены!")
    print("Добавьте в .env: TON_WALLET_1_ADDRESS=ваш_ton_адрес")
else:
    # Проверяем, что есть хотя бы один активный кошелек
    active_wallets = [w for w in TON_WALLETS.values() if w['is_active']]
    if not active_wallets:
        print("⚠️ ВНИМАНИЕ: Нет активных TON кошельков!")
        print("Проверьте настройки TON_WALLET_*_ACTIVE в .env")

# ========== REDIS КОНФИГУРАЦИЯ ==========
# Настройки Redis для кэширования
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', '6379')),
    'db': int(os.getenv('REDIS_DB', '0')),
    'password': os.getenv('REDIS_PASSWORD'),
    'decode_responses': True,
    'socket_timeout': 5,
    'socket_connect_timeout': 5,
    'retry_on_timeout': True,
    'health_check_interval': 30,
    'max_connections': 20
}

# Настройки кэша
CACHE_CONFIG = {
    'default_ttl': int(os.getenv('CACHE_DEFAULT_TTL', '3600')),  # 1 час
    'user_data_ttl': int(os.getenv('CACHE_USER_DATA_TTL', '1800')),  # 30 минут
    'subscription_ttl': int(os.getenv('CACHE_SUBSCRIPTION_TTL', '900')),  # 15 минут
    'gift_data_ttl': int(os.getenv('CACHE_GIFT_DATA_TTL', '300')),  # 5 минут
    'enabled': os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
}

# TON Кошельки - ТОЛЬКО из переменных окружения
# DEPOSIT_ACCOUNTS = {} # Удалено, так как пополнение баллов теперь через TON

# if not TON_WALLETS:
#     print("⚠️ ВНИМАНИЕ: TON кошельки не настроены!")
#     print("Добавьте в .env: TON_WALLET_1_ADDRESS=...")

# Депозитные аккаунты - для покупки подарков
DEPOSIT_ACCOUNTS = {}

# Загружаем депозитные аккаунты из переменных окружения
for i in range(1, 6):  # Поддержка до 5 депозитных аккаунтов
    api_id_key = f'DEPOSIT_ACCOUNT_{i}_API_ID'
    api_hash_key = f'DEPOSIT_ACCOUNT_{i}_API_HASH'
    phone_key = f'DEPOSIT_ACCOUNT_{i}_PHONE'
    
    if os.getenv(api_id_key) and os.getenv(api_hash_key) and os.getenv(phone_key):
            DEPOSIT_ACCOUNTS[f'account_{i}'] = {
            'api_id': int(os.getenv(api_id_key)),
            'api_hash': os.getenv(api_hash_key),
            'phone': os.getenv(phone_key),
            'session_name': f'deposit_account_{i}',
            'is_active': True,
            'max_daily_purchases': 50,
            'cooldown_seconds': 5
        }

if not DEPOSIT_ACCOUNTS:
    print("⚠️ ВНИМАНИЕ: Депозитные аккаунты не настроены!")
    print("Добавьте в .env настройки для депозитных аккаунтов:")
    print("DEPOSIT_ACCOUNT_1_API_ID=your_api_id")
    print("DEPOSIT_ACCOUNT_1_API_HASH=your_api_hash") 
    print("DEPOSIT_ACCOUNT_1_PHONE=+1234567890")

# Обновленные настройки подписок (только ЮКасса)
SUBSCRIPTION_CONFIGS = {
    'basic': {
        'name': 'Базовая подписка',
        'price_rub': 699,           # Цена в рублях через ЮКассу
        'price_ton': 1.4,           # Цена в TON (примерно $7 при TON=$5)
        'duration_days': 30,
        'features': [
            'Мониторинг новых подарков',
            'Уведомления о новых подарках',
            'Просмотр каталога подарков',
            'Базовая поддержка'
        ],
        'can_buy_stars': False      # Basic не может покупать Stars
    },
    'vip': {
        'name': 'VIP подписка',
        'price_rub': 1299,          # Цена в рублях через ЮКассу
        'price_ton': 2.6,           # Цена в TON (примерно $13 при TON=$5)
        'duration_days': 30,
        'features': [
            'Все функции базовой подписки',
            'Покупка Telegram Stars за TON',
            'Автоматическая покупка подарков',
            'Настройка профилей автопокупки',
            'Приоритетная поддержка',
            'Скидка 20% на все покупки подарков'
        ],
        'can_buy_stars': True,      # VIP может покупать Stars за TON
        'stars_discount': 0.20      # 20% скидка на покупки
    }
}

# Система Telegram Stars (прямая работа со звездами)
STARS_SYSTEM = {
    'conversion_rates': {
        'TON': 250.0,    # 1 TON = 250 Stars (выгоднее Fragment на 15%)
        'RUB': 10.0,     # 1 RUB = 10 Stars (для совместимости со старым кодом)
    },
    'commission_rate': 0.10,     # Комиссия 10% при пополнении
    'min_topup_stars': 50,       # Минимальное пополнение 50 Stars
    'max_topup_stars': 50000,    # Максимальное пополнение 50,000 Stars
    'min_topup_ton': 0.1,        # Минимальное пополнение 0.1 TON
    'max_topup_ton': 100.0,      # Максимальное пополнение 100 TON
    'min_topup_rub': 100,        # Минимальное пополнение 100₽ (для совместимости)
    'max_topup_rub': 50000,      # Максимальное пополнение 50,000₽ (для совместимости)
    'topup_bonuses': {           # Бонусы при пополнении (для совместимости)
        1000: 0.05,              # 5% бонус при пополнении от 1000 Stars
        5000: 0.10,              # 10% бонус при пополнении от 5000 Stars
        10000: 0.15,             # 15% бонус при пополнении от 10000 Stars
    }
}

# Настройки автопокупки для VIP
AUTO_PURCHASE_SETTINGS = {
    'enabled': True,
    'max_price_stars_default': 500,      # Максимальная цена по умолчанию
    'max_edition_size_default': 1000,    # Максимальный тираж по умолчанию
    'cooldown_between_purchases': 5,     # Пауза между покупками (сек)
    'max_purchases_per_minute': 10,      # Максимум покупок в минуту
    'balance_reserve': 1000              # Резерв Stars на депозитном аккаунте
}

# Настройки комиссии
COMMISSION_PERCENT = 10  # 10% комиссия (для совместимости)

# Настройки базы данных
DATABASE_PATH = os.getenv('DATABASE_PATH', 'gift_bot.db')

# Настройки мониторинга
MONITORING_INTERVAL = int(os.getenv('MONITORING_INTERVAL', 15))  # 15 секунд
GIFT_CHECK_INTERVAL = int(os.getenv('GIFT_CHECK_INTERVAL', 15))  # 15 секунд

# Настройки логирования для production
LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': os.getenv('LOG_FILE', 'bot.log'),
    'max_size': int(os.getenv('LOG_MAX_SIZE', 10 * 1024 * 1024)),  # 10MB
    'backup_count': int(os.getenv('LOG_BACKUP_COUNT', 5))
}

# Настройки уведомлений
NOTIFICATION_SETTINGS = {
    'enabled': os.getenv('NOTIFICATIONS_ENABLED', 'true').lower() == 'true',
    'max_notifications_per_hour': int(os.getenv('MAX_NOTIFICATIONS_PER_HOUR', 50)),
    'notification_cooldown': int(os.getenv('NOTIFICATION_COOLDOWN', 3600)),  # 1 час
    'batch_size': int(os.getenv('NOTIFICATION_BATCH_SIZE', 10))  # Размер пакета уведомлений
}

# Настройки очереди
QUEUE_SETTINGS = {
    'max_queue_size': int(os.getenv('MAX_QUEUE_SIZE', 1000)),
    'auto_purchase_enabled': os.getenv('AUTO_PURCHASE_ENABLED', 'true').lower() == 'true',
    'min_balance_for_purchase': int(os.getenv('MIN_BALANCE_FOR_PURCHASE', 100)),  # минимальный баланс для покупки
    'max_purchases_per_round': int(os.getenv('MAX_PURCHASES_PER_ROUND', 5)),  # максимум покупок за раз
    'queue_processing_interval': int(os.getenv('QUEUE_PROCESSING_INTERVAL', 30))  # интервал обработки очереди
}

# Каналы для мониторинга подарков в Telegram
GIFT_CHANNELS = [
    '@gifts',  # Официальный канал подарков
    '@premium_gifts',  # Премиум подарки  
    '@telegram_gifts',  # Альтернативный канал
    '@fragment_news',  # Новости Fragment
    # Дополнительные каналы мониторинга (по запросу)
    '@GiftChangesUpdates',
    '@GiftChanges',
    '@Gift_Alerts',
    '@gifts_detector',
    '@new_gifts_alert_news',
    '@giftstracker'
]

# URL для мониторинга подарков (оставляем для совместимости)
MONITORING_URLS = []

# Настройки безопасности
SECURITY_SETTINGS = {
    'max_requests_per_minute': int(os.getenv('MAX_REQUESTS_PER_MINUTE', 60)),
    'rate_limit_window': int(os.getenv('RATE_LIMIT_WINDOW', 60)),  # секунды
    'max_concurrent_connections': int(os.getenv('MAX_CONCURRENT_CONNECTIONS', 10)),
    'request_timeout': int(os.getenv('REQUEST_TIMEOUT', 30)),  # секунды
    'enable_rate_limiting': os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true'
}

# Настройки мониторинга и health check
HEALTH_CHECK_SETTINGS = {
    'enabled': os.getenv('HEALTH_CHECK_ENABLED', 'true').lower() == 'true',
    'interval': int(os.getenv('HEALTH_CHECK_INTERVAL', 300)),  # 5 минут
    'timeout': int(os.getenv('HEALTH_CHECK_TIMEOUT', 30)),  # секунды
    'max_failures': int(os.getenv('HEALTH_CHECK_MAX_FAILURES', 3))
}

# Настройки производительности
PERFORMANCE_SETTINGS = {
    'max_background_tasks': int(os.getenv('MAX_BACKGROUND_TASKS', 20)),
    'task_timeout': int(os.getenv('TASK_TIMEOUT', 300)),  # 5 минут
    'connection_pool_size': int(os.getenv('CONNECTION_POOL_SIZE', 5)),
    'enable_connection_pooling': os.getenv('ENABLE_CONNECTION_POOLING', 'true').lower() == 'true'
}

# Настройки тестирования
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true'

# Настройки graceful shutdown
SHUTDOWN_SETTINGS = {
    'graceful_timeout': int(os.getenv('GRACEFUL_TIMEOUT', 30)),  # секунды
    'force_shutdown_timeout': int(os.getenv('FORCE_SHUTDOWN_TIMEOUT', 60)),  # секунды
    'save_state_on_shutdown': os.getenv('SAVE_STATE_ON_SHUTDOWN', 'true').lower() == 'true'
}

# Валидация критических настроек
def validate_config():
    """Валидация конфигурации"""
    errors = []
    
    # Проверяем обязательные настройки
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN обязателен")
    
    # Проверяем корректность числовых значений
    if MONITORING_INTERVAL < 10:
        errors.append("MONITORING_INTERVAL должен быть не менее 10 секунд")
    
    if QUEUE_SETTINGS['max_queue_size'] <= 0:
        errors.append("MAX_QUEUE_SIZE должен быть положительным числом")
    
    if COMMISSION_PERCENT < 0 or COMMISSION_PERCENT > 100:
        errors.append("COMMISSION_PERCENT должен быть от 0 до 100")
    
    if NOTIFICATION_SETTINGS['max_notifications_per_hour'] <= 0:
        errors.append("MAX_NOTIFICATIONS_PER_HOUR должен быть положительным числом")
    
    # Проверяем настройки безопасности
    if SECURITY_SETTINGS['max_requests_per_minute'] <= 0:
        errors.append("MAX_REQUESTS_PER_MINUTE должен быть положительным числом")
    
    if PERFORMANCE_SETTINGS['max_background_tasks'] <= 0:
        errors.append("MAX_BACKGROUND_TASKS должен быть положительным числом")
    
    if errors:
        print("❌ Ошибки в конфигурации:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    return True

# Выполняем валидацию при импорте
if not validate_config():
    sys.exit(1)

# Функция для получения конфигурации в удобном виде
def get_config_summary():
    """Получение сводки конфигурации"""
    return {
        'bot_token_set': bool(BOT_TOKEN),
        'database_path': DATABASE_PATH,
        'monitoring_interval': MONITORING_INTERVAL,
        'queue_max_size': QUEUE_SETTINGS['max_queue_size'],
        'notifications_enabled': NOTIFICATION_SETTINGS['enabled'],
        'security_enabled': SECURITY_SETTINGS['enable_rate_limiting'],
        'health_check_enabled': HEALTH_CHECK_SETTINGS['enabled'],
        'test_mode': TEST_MODE
    } 