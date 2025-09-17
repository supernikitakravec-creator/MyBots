#!/usr/bin/env python3
"""
Production конфигурация для TgGIFT Star Bot
"""

import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# === База данных ===
DATABASE_CONFIG = {
    'type': os.getenv('DB_TYPE', 'postgresql'),  # postgresql или sqlite
    'postgresql': {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'tggift_bot'),
        'user': os.getenv('DB_USER', 'tggift'),
        'password': os.getenv('DB_PASSWORD', 'password'),
        'pool_size': int(os.getenv('DB_POOL_SIZE', 20)),
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', 40))
    },
    'sqlite': {
        'path': os.getenv('SQLITE_PATH', 'gift_bot.db')
    }
}

# === Redis ===
REDIS_CONFIG = {
    'enabled': os.getenv('REDIS_ENABLED', 'true').lower() == 'true',
    'url': os.getenv('REDIS_URL', 'redis://localhost:6379'),
    'max_connections': int(os.getenv('REDIS_MAX_CONNECTIONS', 50)),
    'decode_responses': True,
    'socket_timeout': int(os.getenv('REDIS_SOCKET_TIMEOUT', 5)),
    'socket_connect_timeout': int(os.getenv('REDIS_CONNECT_TIMEOUT', 5))
}

# === Prometheus метрики ===
METRICS_CONFIG = {
    'enabled': os.getenv('METRICS_ENABLED', 'true').lower() == 'true',
    'port': int(os.getenv('METRICS_PORT', 8000)),
    'path': os.getenv('METRICS_PATH', '/metrics'),
    'update_interval': int(os.getenv('METRICS_UPDATE_INTERVAL', 30))
}

# === Алерты ===
ALERTS_CONFIG = {
    'enabled': os.getenv('ALERTS_ENABLED', 'true').lower() == 'true',
    'webhook_url': os.getenv('ALERTS_WEBHOOK_URL'),
    'telegram_chat_id': os.getenv('ALERTS_TELEGRAM_CHAT_ID'),
    'telegram_bot_token': os.getenv('ALERTS_TELEGRAM_BOT_TOKEN'),
    'thresholds': {
        'memory_percent': float(os.getenv('ALERT_MEMORY_PERCENT', 80)),
        'cpu_percent': float(os.getenv('ALERT_CPU_PERCENT', 80)),
        'error_rate_per_minute': int(os.getenv('ALERT_ERROR_RATE', 10)),
        'response_time_ms': int(os.getenv('ALERT_RESPONSE_TIME_MS', 1000)),
        'queue_size': int(os.getenv('ALERT_QUEUE_SIZE', 1000)),
        'min_balance': int(os.getenv('ALERT_MIN_BALANCE', 100)),
        'database_size_mb': int(os.getenv('ALERT_DB_SIZE_MB', 500)),
        'log_size_mb': int(os.getenv('ALERT_LOG_SIZE_MB', 100))
    }
}

# === Масштабирование ===
SCALING_CONFIG = {
    'enabled': os.getenv('SCALING_ENABLED', 'false').lower() == 'true',
    'min_workers': int(os.getenv('MIN_WORKERS', 1)),
    'max_workers': int(os.getenv('MAX_WORKERS', 4)),
    'scale_up_threshold': float(os.getenv('SCALE_UP_THRESHOLD', 80)),  # CPU %
    'scale_down_threshold': float(os.getenv('SCALE_DOWN_THRESHOLD', 20)),  # CPU %
    'scale_check_interval': int(os.getenv('SCALE_CHECK_INTERVAL', 300))  # секунды
}

# === CDN для статических ресурсов (если будут) ===
CDN_CONFIG = {
    'enabled': os.getenv('CDN_ENABLED', 'false').lower() == 'true',
    'base_url': os.getenv('CDN_BASE_URL', 'https://cdn.example.com'),
    'cache_control': os.getenv('CDN_CACHE_CONTROL', 'public, max-age=86400')
}

# === A/B тестирование ===
AB_TESTING_CONFIG = {
    'enabled': os.getenv('AB_TESTING_ENABLED', 'false').lower() == 'true',
    'experiments': {
        'new_ui': {
            'enabled': os.getenv('AB_NEW_UI_ENABLED', 'false').lower() == 'true',
            'percentage': int(os.getenv('AB_NEW_UI_PERCENTAGE', 10))
        },
        'fast_queue': {
            'enabled': os.getenv('AB_FAST_QUEUE_ENABLED', 'false').lower() == 'true',
            'percentage': int(os.getenv('AB_FAST_QUEUE_PERCENTAGE', 20))
        }
    }
}

# === Кеширование ===
CACHE_CONFIG = {
    'user_info_ttl': int(os.getenv('CACHE_USER_INFO_TTL', 600)),  # 10 минут
    'balance_ttl': int(os.getenv('CACHE_BALANCE_TTL', 60)),  # 1 минута
    'gifts_list_ttl': int(os.getenv('CACHE_GIFTS_LIST_TTL', 300)),  # 5 минут
    'gift_details_ttl': int(os.getenv('CACHE_GIFT_DETAILS_TTL', 3600)),  # 1 час
    'stats_ttl': int(os.getenv('CACHE_STATS_TTL', 60))  # 1 минута
}

# === Rate Limiting (расширенный) ===
RATE_LIMIT_CONFIG = {
    'enabled': os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true',
    'global_limit': int(os.getenv('RATE_LIMIT_GLOBAL', 1000)),  # запросов в минуту
    'per_user_limit': int(os.getenv('RATE_LIMIT_PER_USER', 60)),  # запросов в минуту
    'burst_limit': int(os.getenv('RATE_LIMIT_BURST', 10)),  # burst запросов
    'window_seconds': int(os.getenv('RATE_LIMIT_WINDOW', 60))
}

# === Очереди (расширенные) ===
QUEUE_CONFIG = {
    'max_size': int(os.getenv('QUEUE_MAX_SIZE', 10000)),
    'priority_enabled': os.getenv('QUEUE_PRIORITY_ENABLED', 'true').lower() == 'true',
    'batch_size': int(os.getenv('QUEUE_BATCH_SIZE', 10)),
    'processing_interval': int(os.getenv('QUEUE_PROCESSING_INTERVAL', 30)),
    'max_retries': int(os.getenv('QUEUE_MAX_RETRIES', 3)),
    'retry_delay': int(os.getenv('QUEUE_RETRY_DELAY', 60))
}

# === Мониторинг подарков (оптимизированный) ===
MONITORING_CONFIG = {
    'interval': int(os.getenv('MONITORING_INTERVAL', 15)),
    'dynamic_interval': os.getenv('MONITORING_DYNAMIC_INTERVAL', 'true').lower() == 'true',
    'min_interval': int(os.getenv('MONITORING_MIN_INTERVAL', 15)),
    'max_interval': int(os.getenv('MONITORING_MAX_INTERVAL', 300)),
    'parallel_checks': int(os.getenv('MONITORING_PARALLEL_CHECKS', 5)),
    'timeout': int(os.getenv('MONITORING_TIMEOUT', 30))
}

# === Логирование (расширенное) ===
LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': os.getenv('LOG_FILE', '/var/log/tggift-bot/bot.log'),
    'max_size': int(os.getenv('LOG_MAX_SIZE', 50 * 1024 * 1024)),  # 50MB
    'backup_count': int(os.getenv('LOG_BACKUP_COUNT', 10)),
    'enable_syslog': os.getenv('LOG_ENABLE_SYSLOG', 'true').lower() == 'true',
    'enable_json': os.getenv('LOG_ENABLE_JSON', 'true').lower() == 'true',
    'enable_elk': os.getenv('LOG_ENABLE_ELK', 'false').lower() == 'true',
    'elk_host': os.getenv('LOG_ELK_HOST', 'localhost'),
    'elk_port': int(os.getenv('LOG_ELK_PORT', 9200))
}

# === Безопасность (усиленная) ===
SECURITY_CONFIG = {
    'enable_encryption': os.getenv('SECURITY_ENCRYPTION', 'true').lower() == 'true',
    'encryption_key': os.getenv('SECURITY_ENCRYPTION_KEY'),
    'enable_audit_log': os.getenv('SECURITY_AUDIT_LOG', 'true').lower() == 'true',
    'enable_ip_whitelist': os.getenv('SECURITY_IP_WHITELIST', 'false').lower() == 'true',
    'ip_whitelist': os.getenv('SECURITY_IP_LIST', '').split(','),
    'enable_2fa': os.getenv('SECURITY_2FA', 'false').lower() == 'true',
    'session_timeout': int(os.getenv('SECURITY_SESSION_TIMEOUT', 86400))  # 24 часа
}

# === Производительность ===
PERFORMANCE_CONFIG = {
    'enable_profiling': os.getenv('PERF_PROFILING', 'false').lower() == 'true',
    'profile_requests': os.getenv('PERF_PROFILE_REQUESTS', 'false').lower() == 'true',
    'slow_query_threshold': int(os.getenv('PERF_SLOW_QUERY_MS', 100)),
    'enable_query_cache': os.getenv('PERF_QUERY_CACHE', 'true').lower() == 'true',
    'query_cache_size': int(os.getenv('PERF_QUERY_CACHE_SIZE', 1000)),
    'enable_connection_pool': os.getenv('PERF_CONNECTION_POOL', 'true').lower() == 'true',
    'pool_size': int(os.getenv('PERF_POOL_SIZE', 20)),
    'pool_recycle': int(os.getenv('PERF_POOL_RECYCLE', 3600))  # 1 час
}

# === Резервное копирование ===
BACKUP_CONFIG = {
    'enabled': os.getenv('BACKUP_ENABLED', 'true').lower() == 'true',
    'interval': int(os.getenv('BACKUP_INTERVAL', 86400)),  # 24 часа
    'retention_days': int(os.getenv('BACKUP_RETENTION_DAYS', 30)),
    'compression': os.getenv('BACKUP_COMPRESSION', 'true').lower() == 'true',
    'encryption': os.getenv('BACKUP_ENCRYPTION', 'true').lower() == 'true',
    'storage_type': os.getenv('BACKUP_STORAGE_TYPE', 'local'),  # local, s3, gcs
    'storage_path': os.getenv('BACKUP_STORAGE_PATH', '/backup/tggift-bot'),
    's3_bucket': os.getenv('BACKUP_S3_BUCKET'),
    's3_region': os.getenv('BACKUP_S3_REGION', 'us-east-1'),
    's3_access_key': os.getenv('BACKUP_S3_ACCESS_KEY'),
    's3_secret_key': os.getenv('BACKUP_S3_SECRET_KEY')
}

# === Функция для получения DSN PostgreSQL ===
def get_postgres_dsn():
    """Получить DSN для подключения к PostgreSQL"""
    if DATABASE_CONFIG['type'] == 'postgresql':
        cfg = DATABASE_CONFIG['postgresql']
        return f"postgresql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    return None

# === Функция для проверки production готовности ===
def check_production_ready():
    """Проверить готовность к production"""
    issues = []
    
    # Проверяем критические настройки
    if not os.getenv('BOT_TOKEN'):
        issues.append("BOT_TOKEN не установлен")
    
    if DATABASE_CONFIG['type'] == 'sqlite':
        issues.append("Рекомендуется использовать PostgreSQL вместо SQLite для production")
    
    if not REDIS_CONFIG['enabled']:
        issues.append("Redis отключен - рекомендуется включить для производительности")
    
    if not METRICS_CONFIG['enabled']:
        issues.append("Метрики отключены - рекомендуется включить для мониторинга")
    
    if not ALERTS_CONFIG['enabled']:
        issues.append("Алерты отключены - рекомендуется включить для оповещений")
    
    if not BACKUP_CONFIG['enabled']:
        issues.append("Резервное копирование отключено - критично для production")
    
    if not SECURITY_CONFIG['enable_encryption']:
        issues.append("Шифрование отключено - рекомендуется включить")
    
    return issues 