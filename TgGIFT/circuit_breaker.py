#!/usr/bin/env python3
"""
Circuit Breaker - паттерн для предотвращения каскадных сбоев в TgGIFT Bot
"""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
from dataclasses import dataclass
from enum import Enum
import json
from functools import wraps

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    """Состояния Circuit Breaker"""
    CLOSED = "closed"        # Нормальная работа
    OPEN = "open"           # Сбои, запросы блокируются
    HALF_OPEN = "half_open" # Тестирование восстановления

@dataclass
class CircuitBreakerConfig:
    """Конфигурация Circuit Breaker"""
    name: str
    failure_threshold: int = 5          # Количество сбоев для открытия
    success_threshold: int = 3          # Количество успехов для закрытия
    timeout: float = 60.0               # Таймаут в открытом состоянии (секунды)
    expected_exception: type = Exception # Ожидаемый тип исключения
    fallback_func: Optional[Callable] = None  # Fallback функция

@dataclass
class CallResult:
    """Результат вызова через Circuit Breaker"""
    success: bool
    result: Any = None
    error: Exception = None
    duration: float = 0.0
    timestamp: datetime = None

class CircuitBreaker:
    """Реализация Circuit Breaker паттерна"""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        
        # Счетчики
        self.failure_count = 0
        self.success_count = 0
        self.total_calls = 0
        
        # Временные метки
        self.last_failure_time = None
        self.last_success_time = None
        self.state_changed_time = datetime.now()
        
        # История вызовов (для анализа)
        self.call_history = []
        self.max_history = 100
        
        logger.info(f"Circuit Breaker '{self.config.name}' инициализирован")
    
    async def call(self, func: Callable, *args, **kwargs) -> CallResult:
        """Выполнение функции через Circuit Breaker"""
        
        self.total_calls += 1
        call_start = time.time()
        
        # Проверяем состояние и возможность выполнения
        if not self._can_execute():
            # Пытаемся использовать fallback
            if self.config.fallback_func:
                try:
                    result = await self._execute_fallback(*args, **kwargs)
                    return CallResult(
                        success=True,
                        result=result,
                        duration=time.time() - call_start,
                        timestamp=datetime.now()
                    )
                except Exception as e:
                    logger.error(f"Ошибка fallback для {self.config.name}: {e}")
            
            # Возвращаем ошибку circuit breaker
            error = CircuitBreakerOpenException(
                f"Circuit breaker '{self.config.name}' is {self.state.value}"
            )
            
            call_result = CallResult(
                success=False,
                error=error,
                duration=time.time() - call_start,
                timestamp=datetime.now()
            )
            
            self._record_call(call_result)
            return call_result
        
        # Выполняем функцию
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Успешный вызов
            call_result = CallResult(
                success=True,
                result=result,
                duration=time.time() - call_start,
                timestamp=datetime.now()
            )
            
            self._on_success()
            
        except self.config.expected_exception as e:
            # Ожидаемое исключение (сбой)
            call_result = CallResult(
                success=False,
                error=e,
                duration=time.time() - call_start,
                timestamp=datetime.now()
            )
            
            self._on_failure()
            
        except Exception as e:
            # Неожиданное исключение (не считается сбоем circuit breaker)
            call_result = CallResult(
                success=False,
                error=e,
                duration=time.time() - call_start,
                timestamp=datetime.now()
            )
            
            logger.warning(f"Неожиданное исключение в {self.config.name}: {e}")
        
        self._record_call(call_result)
        return call_result
    
    def _can_execute(self) -> bool:
        """Проверка возможности выполнения запроса"""
        
        if self.state == CircuitState.CLOSED:
            return True
        
        elif self.state == CircuitState.OPEN:
            # Проверяем, не пора ли перейти в half-open
            if self._should_attempt_reset():
                self._transition_to_half_open()
                return True
            return False
        
        elif self.state == CircuitState.HALF_OPEN:
            return True
        
        return False
    
    def _should_attempt_reset(self) -> bool:
        """Проверка, пора ли попытаться восстановиться"""
        if not self.last_failure_time:
            return True
        
        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure.total_seconds() >= self.config.timeout
    
    def _on_success(self):
        """Обработка успешного вызова"""
        self.last_success_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
        
        elif self.state == CircuitState.CLOSED:
            # Сбрасываем счетчик неудач при успехе
            self.failure_count = 0
    
    def _on_failure(self):
        """Обработка неудачного вызова"""
        self.last_failure_time = datetime.now()
        self.failure_count += 1
        
        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()
        
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
    
    def _transition_to_open(self):
        """Переход в открытое состояние"""
        self.state = CircuitState.OPEN
        self.state_changed_time = datetime.now()
        self.success_count = 0
        
        logger.warning(f"Circuit breaker '{self.config.name}' открыт (failures: {self.failure_count})")
    
    def _transition_to_half_open(self):
        """Переход в полуоткрытое состояние"""
        self.state = CircuitState.HALF_OPEN
        self.state_changed_time = datetime.now()
        self.success_count = 0
        
        logger.info(f"Circuit breaker '{self.config.name}' в режиме тестирования")
    
    def _transition_to_closed(self):
        """Переход в закрытое состояние"""
        self.state = CircuitState.CLOSED
        self.state_changed_time = datetime.now()
        self.failure_count = 0
        self.success_count = 0
        
        logger.info(f"Circuit breaker '{self.config.name}' закрыт (восстановлен)")
    
    async def _execute_fallback(self, *args, **kwargs):
        """Выполнение fallback функции"""
        if asyncio.iscoroutinefunction(self.config.fallback_func):
            return await self.config.fallback_func(*args, **kwargs)
        else:
            return self.config.fallback_func(*args, **kwargs)
    
    def _record_call(self, call_result: CallResult):
        """Запись результата вызова в историю"""
        self.call_history.append(call_result)
        
        # Ограничиваем размер истории
        if len(self.call_history) > self.max_history:
            self.call_history = self.call_history[-self.max_history:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики Circuit Breaker"""
        
        # Анализ последних вызовов
        recent_calls = self.call_history[-50:] if self.call_history else []
        success_rate = 0
        avg_duration = 0
        
        if recent_calls:
            successful_calls = [c for c in recent_calls if c.success]
            success_rate = len(successful_calls) / len(recent_calls) * 100
            avg_duration = sum(c.duration for c in recent_calls) / len(recent_calls)
        
        return {
            'name': self.config.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'total_calls': self.total_calls,
            'success_rate_percent': round(success_rate, 2),
            'avg_response_time_ms': round(avg_duration * 1000, 2),
            'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
            'state_changed_at': self.state_changed_time.isoformat(),
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'success_threshold': self.config.success_threshold,
                'timeout_seconds': self.config.timeout,
                'has_fallback': self.config.fallback_func is not None
            }
        }
    
    def reset(self):
        """Принудительный сброс Circuit Breaker"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.state_changed_time = datetime.now()
        
        logger.info(f"Circuit breaker '{self.config.name}' принудительно сброшен")

class CircuitBreakerOpenException(Exception):
    """Исключение когда Circuit Breaker открыт"""
    pass

class CircuitBreakerManager:
    """Менеджер множественных Circuit Breaker"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        logger.info("Circuit Breaker Manager инициализирован")
    
    def create_circuit_breaker(self, config: CircuitBreakerConfig) -> CircuitBreaker:
        """Создание нового Circuit Breaker"""
        circuit_breaker = CircuitBreaker(config)
        self.circuit_breakers[config.name] = circuit_breaker
        return circuit_breaker
    
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Получение Circuit Breaker по имени"""
        return self.circuit_breakers.get(name)
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Получение статистики всех Circuit Breaker"""
        stats = {}
        
        for name, cb in self.circuit_breakers.items():
            stats[name] = cb.get_stats()
        
        # Общая статистика
        total_breakers = len(self.circuit_breakers)
        open_breakers = len([cb for cb in self.circuit_breakers.values() 
                           if cb.state == CircuitState.OPEN])
        half_open_breakers = len([cb for cb in self.circuit_breakers.values() 
                                if cb.state == CircuitState.HALF_OPEN])
        
        return {
            'circuit_breakers': stats,
            'summary': {
                'total_breakers': total_breakers,
                'open_breakers': open_breakers,
                'half_open_breakers': half_open_breakers,
                'healthy_breakers': total_breakers - open_breakers - half_open_breakers
            }
        }
    
    def reset_all(self):
        """Сброс всех Circuit Breaker"""
        for cb in self.circuit_breakers.values():
            cb.reset()
        
        logger.info("Все Circuit Breaker сброшены")

# Декораторы для удобного использования

def circuit_breaker(name: str, failure_threshold: int = 5, success_threshold: int = 3,
                   timeout: float = 60.0, expected_exception: type = Exception,
                   fallback_func: Optional[Callable] = None):
    """Декоратор Circuit Breaker"""
    
    config = CircuitBreakerConfig(
        name=name,
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timeout,
        expected_exception=expected_exception,
        fallback_func=fallback_func
    )
    
    # Получаем или создаем Circuit Breaker
    cb = _global_circuit_manager.get_circuit_breaker(name)
    if not cb:
        cb = _global_circuit_manager.create_circuit_breaker(config)
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await cb.call(func, *args, **kwargs)
            
            if result.success:
                return result.result
            else:
                raise result.error
        
        # Добавляем метаданные к функции
        wrapper._circuit_breaker = cb
        wrapper._circuit_breaker_name = name
        
        return wrapper
    
    return decorator

# Предопределенные fallback функции

async def empty_fallback(*args, **kwargs):
    """Пустая fallback функция"""
    logger.warning("Используется пустая fallback функция")
    return None

async def cached_fallback(cache_key: str, cache_manager=None):
    """Fallback с использованием кэша"""
    if cache_manager:
        try:
            cached_result = await cache_manager.get(cache_key)
            if cached_result:
                logger.info(f"Используется кэшированный результат для {cache_key}")
                return cached_result
        except Exception as e:
            logger.error(f"Ошибка получения кэша для fallback: {e}")
    
    logger.warning("Кэшированный результат недоступен для fallback")
    return None

async def default_value_fallback(default_value):
    """Fallback с возвратом значения по умолчанию"""
    logger.info("Используется значение по умолчанию для fallback")
    return default_value

# Интеграция с компонентами системы

def setup_database_circuit_breaker(db_manager, config: Dict[str, Any] = None) -> CircuitBreaker:
    """Настройка Circuit Breaker для базы данных"""
    
    config = config or {}
    
    circuit_config = CircuitBreakerConfig(
        name="database",
        failure_threshold=config.get('failure_threshold', 3),
        success_threshold=config.get('success_threshold', 2),
        timeout=config.get('timeout', 30.0),
        expected_exception=Exception,  # Любые исключения БД
        fallback_func=lambda *args, **kwargs: None  # Простая fallback
    )
    
    return _global_circuit_manager.create_circuit_breaker(circuit_config)

def setup_cache_circuit_breaker(cache_manager, config: Dict[str, Any] = None) -> CircuitBreaker:
    """Настройка Circuit Breaker для кэша"""
    
    config = config or {}
    
    async def cache_fallback(*args, **kwargs):
        logger.warning("Cache недоступен, работаем без кэша")
        return None
    
    circuit_config = CircuitBreakerConfig(
        name="cache",
        failure_threshold=config.get('failure_threshold', 5),
        success_threshold=config.get('success_threshold', 3),
        timeout=config.get('timeout', 60.0),
        expected_exception=Exception,
        fallback_func=cache_fallback
    )
    
    return _global_circuit_manager.create_circuit_breaker(circuit_config)

def setup_external_api_circuit_breaker(api_name: str, config: Dict[str, Any] = None) -> CircuitBreaker:
    """Настройка Circuit Breaker для внешнего API"""
    
    config = config or {}
    
    async def api_fallback(*args, **kwargs):
        logger.warning(f"API {api_name} недоступен")
        return {'status': 'unavailable', 'fallback': True}
    
    circuit_config = CircuitBreakerConfig(
        name=f"api_{api_name}",
        failure_threshold=config.get('failure_threshold', 3),
        success_threshold=config.get('success_threshold', 2),
        timeout=config.get('timeout', 120.0),
        expected_exception=(ConnectionError, TimeoutError, Exception),
        fallback_func=api_fallback
    )
    
    return _global_circuit_manager.create_circuit_breaker(circuit_config)

# Примеры использования

@circuit_breaker("payment_service", failure_threshold=3, timeout=30.0)
async def process_payment(amount: float, user_id: int):
    """Пример защищенной функции обработки платежей"""
    # Имитация обращения к платежному сервису
    await asyncio.sleep(0.1)
    
    # Имитация случайных сбоев
    import random
    if random.random() < 0.3:  # 30% сбоев
        raise ConnectionError("Payment service unavailable")
    
    return {"payment_id": f"pay_{user_id}_{int(time.time())}", "status": "success"}

@circuit_breaker("notification_service", failure_threshold=5, timeout=60.0,
                fallback_func=lambda *args: {"status": "queued"})
async def send_notification(user_id: int, message: str):
    """Пример защищенной функции отправки уведомлений"""
    await asyncio.sleep(0.05)
    
    import random
    if random.random() < 0.2:  # 20% сбоев
        raise TimeoutError("Notification service timeout")
    
    return {"notification_id": f"notif_{user_id}", "status": "sent"}

# Глобальный менеджер Circuit Breaker
_global_circuit_manager = CircuitBreakerManager()

def get_circuit_manager() -> CircuitBreakerManager:
    """Получение глобального менеджера Circuit Breaker"""
    return _global_circuit_manager 