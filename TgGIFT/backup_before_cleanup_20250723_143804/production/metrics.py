#!/usr/bin/env python3
"""
Prometheus метрики для TgGIFT Star Bot
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from prometheus_client.exposition import start_http_server
import time
import logging
from functools import wraps
from typing import Callable

logger = logging.getLogger(__name__)

# Создаем реестр метрик
registry = CollectorRegistry()

# === Счетчики ===

# Команды бота
bot_commands_total = Counter(
    'bot_commands_total',
    'Общее количество команд',
    ['command', 'status'],
    registry=registry
)

# Транзакции
transactions_total = Counter(
    'transactions_total',
    'Общее количество транзакций',
    ['type', 'status'],
    registry=registry
)

# Подписки
subscriptions_total = Counter(
    'subscriptions_total',
    'Общее количество активаций подписок',
    ['type'],
    registry=registry
)

# Покупки подарков
gift_purchases_total = Counter(
    'gift_purchases_total',
    'Общее количество покупок подарков',
    ['status'],
    registry=registry
)

# Ошибки
errors_total = Counter(
    'errors_total',
    'Общее количество ошибок',
    ['error_type', 'module'],
    registry=registry
)

# === Гистограммы ===

# Время выполнения команд
command_duration_seconds = Histogram(
    'command_duration_seconds',
    'Время выполнения команд в секундах',
    ['command'],
    registry=registry
)

# Время запросов к БД
db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Время выполнения запросов к БД в секундах',
    ['operation'],
    registry=registry
)

# Время обработки подарков
gift_processing_duration_seconds = Histogram(
    'gift_processing_duration_seconds',
    'Время обработки подарков в секундах',
    ['action'],
    registry=registry
)

# === Измерители (Gauges) ===

# Активные пользователи
active_users_gauge = Gauge(
    'active_users_total',
    'Количество активных пользователей',
    registry=registry
)

# Размер очереди
queue_size_gauge = Gauge(
    'queue_size_total',
    'Размер очереди покупок',
    registry=registry
)

# Доступные подарки
available_gifts_gauge = Gauge(
    'available_gifts_total',
    'Количество доступных подарков',
    registry=registry
)

# Баланс системы
system_balance_gauge = Gauge(
    'system_balance_stars',
    'Общий баланс системы в звездах',
    registry=registry
)

# Использование памяти
memory_usage_gauge = Gauge(
    'memory_usage_bytes',
    'Использование памяти в байтах',
    ['type'],  # rss, vms
    registry=registry
)

# Использование CPU
cpu_usage_gauge = Gauge(
    'cpu_usage_percent',
    'Использование CPU в процентах',
    registry=registry
)

# Количество потоков
threads_gauge = Gauge(
    'threads_total',
    'Количество потоков',
    registry=registry
)

# Размер БД
database_size_gauge = Gauge(
    'database_size_bytes',
    'Размер базы данных в байтах',
    registry=registry
)

# Состояние подключений
connections_gauge = Gauge(
    'connections_active',
    'Активные подключения',
    ['type'],  # telegram, database, redis
    registry=registry
)

# === Декораторы для метрик ===

def track_command_time(command_name: str):
    """Декоратор для отслеживания времени выполнения команд"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                bot_commands_total.labels(command=command_name, status='success').inc()
                return result
            except Exception as e:
                bot_commands_total.labels(command=command_name, status='error').inc()
                errors_total.labels(error_type=type(e).__name__, module='commands').inc()
                raise
            finally:
                duration = time.time() - start_time
                command_duration_seconds.labels(command=command_name).observe(duration)
        return wrapper
    return decorator

def track_db_time(operation: str):
    """Декоратор для отслеживания времени запросов к БД"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                errors_total.labels(error_type=type(e).__name__, module='database').inc()
                raise
            finally:
                duration = time.time() - start_time
                db_query_duration_seconds.labels(operation=operation).observe(duration)
        return wrapper
    return decorator

# === Класс для управления метриками ===

class MetricsManager:
    """Менеджер метрик Prometheus"""
    
    def __init__(self, port: int = 8000):
        self.port = port
        self.server_started = False
    
    def start_metrics_server(self):
        """Запуск HTTP сервера для метрик"""
        if not self.server_started:
            try:
                start_http_server(self.port, registry=registry)
                self.server_started = True
                logger.info(f"Prometheus метрики доступны на порту {self.port}")
            except Exception as e:
                logger.error(f"Ошибка запуска сервера метрик: {e}")
    
    def update_system_metrics(self, stats: dict):
        """Обновление системных метрик"""
        try:
            # Обновляем gauges
            if 'active_users' in stats:
                active_users_gauge.set(stats['active_users'])
            
            if 'queue_size' in stats:
                queue_size_gauge.set(stats['queue_size'])
            
            if 'available_gifts' in stats:
                available_gifts_gauge.set(stats['available_gifts'])
            
            if 'system_balance' in stats:
                system_balance_gauge.set(stats['system_balance'])
            
            if 'memory_rss' in stats:
                memory_usage_gauge.labels(type='rss').set(stats['memory_rss'])
            
            if 'memory_vms' in stats:
                memory_usage_gauge.labels(type='vms').set(stats['memory_vms'])
            
            if 'cpu_percent' in stats:
                cpu_usage_gauge.set(stats['cpu_percent'])
            
            if 'threads' in stats:
                threads_gauge.set(stats['threads'])
            
            if 'database_size' in stats:
                database_size_gauge.set(stats['database_size'])
            
        except Exception as e:
            logger.error(f"Ошибка обновления системных метрик: {e}")
    
    def update_connection_metrics(self, connection_type: str, count: int):
        """Обновление метрик подключений"""
        connections_gauge.labels(type=connection_type).set(count)
    
    def track_transaction(self, transaction_type: str, status: str = 'success'):
        """Отслеживание транзакции"""
        transactions_total.labels(type=transaction_type, status=status).inc()
    
    def track_subscription(self, subscription_type: str):
        """Отслеживание активации подписки"""
        subscriptions_total.labels(type=subscription_type).inc()
    
    def track_gift_purchase(self, status: str = 'success'):
        """Отслеживание покупки подарка"""
        gift_purchases_total.labels(status=status).inc()
    
    def track_error(self, error_type: str, module: str):
        """Отслеживание ошибки"""
        errors_total.labels(error_type=error_type, module=module).inc()
    
    def get_metrics(self) -> bytes:
        """Получить метрики в формате Prometheus"""
        return generate_latest(registry)

# Глобальный экземпляр менеджера метрик
metrics_manager = MetricsManager() 