#!/usr/bin/env python3
"""
Конфигурация для PostgreSQL версии TgGIFT Bot
"""

import os
from config import *  # Импортируем все из основной конфигурации

# Переопределяем настройки базы данных для PostgreSQL
DATABASE_CONFIG = {
    'type': 'postgresql',
    'dsn': os.getenv('DATABASE_URL', 'postgresql://tggift:tggift_password@localhost:5432/tggift_db'),
    'pool_min_size': int(os.getenv('DB_POOL_MIN_SIZE', '10')),
    'pool_max_size': int(os.getenv('DB_POOL_MAX_SIZE', '50')),
    'command_timeout': int(os.getenv('DB_COMMAND_TIMEOUT', '60')),
}

# Redis конфигурация для кэширования
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', '6379')),
    'db': int(os.getenv('REDIS_DB', '0')),
    'password': os.getenv('REDIS_PASSWORD', None),
    'decode_responses': True,
    'max_connections': int(os.getenv('REDIS_MAX_CONNECTIONS', '20')),
}

# Настройки производительности
PERFORMANCE_CONFIG = {
    'enable_caching': True,
    'cache_ttl': {
        'user_balance': 60,        # Кэш баланса на 1 минуту
        'user_profile': 300,       # Кэш профиля на 5 минут
        'subscriptions': 600,      # Кэш подписок на 10 минут
        'ton_transactions': 30,    # Кэш транзакций на 30 секунд
    },
    'batch_size': {
        'notifications': 100,      # Размер батча для уведомлений
        'gift_processing': 50,     # Размер батча для обработки подарков
    }
}

# Мониторинг и метрики
MONITORING_CONFIG = {
    'enable_metrics': True,
    'metrics_port': int(os.getenv('METRICS_PORT', '8000')),
    'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    'sentry_dsn': os.getenv('SENTRY_DSN', None),
}

# Настройки очередей задач
QUEUE_CONFIG = {
    'broker_url': os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    'result_backend': os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2'),
    'task_routes': {
        'gift_purchase': {'queue': 'high_priority'},
        'notifications': {'queue': 'normal'},
        'statistics': {'queue': 'low_priority'},
    }
}

# Проверка обязательных переменных окружения для продакшена
REQUIRED_ENV_VARS = [
    'BOT_TOKEN',
    'DATABASE_URL',
    'ADMIN_ID',
]

def check_production_config():
    """Проверка конфигурации для продакшена"""
    missing_vars = []
    for var in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
    
    print("✅ Конфигурация для продакшена проверена")

if __name__ == "__main__":
    check_production_config() 