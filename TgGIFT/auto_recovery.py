#!/usr/bin/env python3
"""
Auto Recovery - система автовосстановления для TgGIFT Bot
"""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class RecoveryAction(Enum):
    """Типы действий восстановления"""
    RESTART_COMPONENT = "restart_component"
    RECONNECT_SERVICE = "reconnect_service"
    CLEAR_CACHE = "clear_cache"
    RESET_STATE = "reset_state"
    FALLBACK_MODE = "fallback_mode"
    ESCALATE = "escalate"

class FailureType(Enum):
    """Типы сбоев"""
    CONNECTION_LOST = "connection_lost"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class FailureEvent:
    """События сбоя"""
    component: str
    failure_type: FailureType
    timestamp: datetime
    error_message: str
    context: Dict[str, Any] = None
    recovery_attempted: bool = False
    recovery_successful: bool = False

@dataclass
class RecoveryStrategy:
    """Стратегия восстановления"""
    name: str
    failure_types: List[FailureType]
    actions: List[RecoveryAction]
    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    initial_delay: float = 1.0
    timeout: float = 30.0
    enabled: bool = True

class AutoRecoveryManager:
    """Менеджер автовосстановления"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Настройки
        self.max_failure_history = self.config.get('max_failure_history', 1000)
        self.failure_window_minutes = self.config.get('failure_window_minutes', 60)
        self.max_failures_per_window = self.config.get('max_failures_per_window', 10)
        
        # Состояние
        self.failure_history = []
        self.recovery_strategies = {}
        self.component_states = {}
        self.active_recoveries = {}
        
        # Статистика
        self.recovery_stats = {
            'total_failures': 0,
            'successful_recoveries': 0,
            'failed_recoveries': 0,
            'escalations': 0
        }
        
        # Регистрируем стандартные стратегии
        self._register_default_strategies()
        
        logger.info("Auto Recovery Manager инициализирован")
    
    def _register_default_strategies(self):
        """Регистрация стандартных стратегий восстановления"""
        
        # Стратегия для потери соединения
        self.register_strategy(RecoveryStrategy(
            name="connection_recovery",
            failure_types=[FailureType.CONNECTION_LOST],
            actions=[
                RecoveryAction.RECONNECT_SERVICE,
                RecoveryAction.RESTART_COMPONENT,
                RecoveryAction.ESCALATE
            ],
            max_attempts=3,
            initial_delay=2.0
        ))
        
        # Стратегия для таймаутов
        self.register_strategy(RecoveryStrategy(
            name="timeout_recovery",
            failure_types=[FailureType.TIMEOUT],
            actions=[
                RecoveryAction.CLEAR_CACHE,
                RecoveryAction.RESTART_COMPONENT,
                RecoveryAction.FALLBACK_MODE
            ],
            max_attempts=2,
            initial_delay=1.0
        ))
        
        # Стратегия для исчерпания ресурсов
        self.register_strategy(RecoveryStrategy(
            name="resource_recovery",
            failure_types=[FailureType.RESOURCE_EXHAUSTED],
            actions=[
                RecoveryAction.CLEAR_CACHE,
                RecoveryAction.RESET_STATE,
                RecoveryAction.RESTART_COMPONENT
            ],
            max_attempts=2,
            initial_delay=5.0
        ))
        
        # Стратегия для rate limiting
        self.register_strategy(RecoveryStrategy(
            name="rate_limit_recovery",
            failure_types=[FailureType.RATE_LIMITED],
            actions=[
                RecoveryAction.FALLBACK_MODE
            ],
            max_attempts=1,
            initial_delay=60.0  # Ждем минуту
        ))
    
    def register_strategy(self, strategy: RecoveryStrategy):
        """Регистрация стратегии восстановления"""
        self.recovery_strategies[strategy.name] = strategy
        logger.info(f"Зарегистрирована стратегия восстановления: {strategy.name}")
    
    def register_component(self, component_name: str, 
                         restart_func: Optional[Callable[[], Awaitable[bool]]] = None,
                         reconnect_func: Optional[Callable[[], Awaitable[bool]]] = None,
                         clear_cache_func: Optional[Callable[[], Awaitable[bool]]] = None,
                         reset_state_func: Optional[Callable[[], Awaitable[bool]]] = None,
                         fallback_func: Optional[Callable[[], Awaitable[bool]]] = None):
        """Регистрация компонента для автовосстановления"""
        
        self.component_states[component_name] = {
            'status': 'healthy',
            'last_failure': None,
            'failure_count': 0,
            'recovery_functions': {
                RecoveryAction.RESTART_COMPONENT: restart_func,
                RecoveryAction.RECONNECT_SERVICE: reconnect_func,
                RecoveryAction.CLEAR_CACHE: clear_cache_func,
                RecoveryAction.RESET_STATE: reset_state_func,
                RecoveryAction.FALLBACK_MODE: fallback_func
            }
        }
        
        logger.info(f"Зарегистрирован компонент для автовосстановления: {component_name}")
    
    async def report_failure(self, component: str, failure_type: FailureType, 
                           error_message: str, context: Dict[str, Any] = None) -> bool:
        """Сообщение о сбое компонента"""
        
        failure_event = FailureEvent(
            component=component,
            failure_type=failure_type,
            timestamp=datetime.now(),
            error_message=error_message,
            context=context or {}
        )
        
        # Добавляем в историю
        self.failure_history.append(failure_event)
        if len(self.failure_history) > self.max_failure_history:
            self.failure_history = self.failure_history[-self.max_failure_history:]
        
        # Обновляем статистику
        self.recovery_stats['total_failures'] += 1
        
        # Обновляем состояние компонента
        if component in self.component_states:
            self.component_states[component]['status'] = 'failed'
            self.component_states[component]['last_failure'] = failure_event.timestamp
            self.component_states[component]['failure_count'] += 1
        
        logger.error(f"Сбой компонента {component}: {failure_type.value} - {error_message}")
        
        # Проверяем, не слишком ли много сбоев
        if self._is_failure_storm(component):
            logger.critical(f"Обнаружен шторм сбоев для компонента {component}")
            await self._handle_failure_storm(component)
            return False
        
        # Запускаем автовосстановление
        recovery_success = await self._attempt_recovery(failure_event)
        
        # Обновляем статистику
        failure_event.recovery_attempted = True
        failure_event.recovery_successful = recovery_success
        
        if recovery_success:
            self.recovery_stats['successful_recoveries'] += 1
            if component in self.component_states:
                self.component_states[component]['status'] = 'recovered'
        else:
            self.recovery_stats['failed_recoveries'] += 1
        
        return recovery_success
    
    async def _attempt_recovery(self, failure_event: FailureEvent) -> bool:
        """Попытка автовосстановления"""
        component = failure_event.component
        failure_type = failure_event.failure_type
        
        # Проверяем, не идет ли уже восстановление
        if component in self.active_recoveries:
            logger.warning(f"Восстановление {component} уже в процессе")
            return False
        
        # Находим подходящую стратегию
        strategy = self._find_recovery_strategy(failure_type)
        if not strategy or not strategy.enabled:
            logger.warning(f"Нет подходящей стратегии для {failure_type.value}")
            return False
        
        logger.info(f"Начинаем восстановление {component} по стратегии {strategy.name}")
        
        self.active_recoveries[component] = {
            'strategy': strategy.name,
            'started_at': datetime.now(),
            'attempt': 0
        }
        
        try:
            recovery_success = False
            
            for attempt in range(strategy.max_attempts):
                self.active_recoveries[component]['attempt'] = attempt + 1
                
                logger.info(f"Попытка восстановления {component} #{attempt + 1}")
                
                # Выполняем действия восстановления
                for action in strategy.actions:
                    if action == RecoveryAction.ESCALATE:
                        await self._escalate_failure(failure_event)
                        self.recovery_stats['escalations'] += 1
                        break
                    
                    success = await self._execute_recovery_action(component, action)
                    
                    if success:
                        logger.info(f"Действие {action.value} для {component} выполнено успешно")
                        recovery_success = True
                        break
                    else:
                        logger.warning(f"Действие {action.value} для {component} не удалось")
                
                if recovery_success:
                    break
                
                # Ждем перед следующей попыткой (exponential backoff)
                if attempt < strategy.max_attempts - 1:
                    delay = strategy.initial_delay * (strategy.backoff_multiplier ** attempt)
                    logger.info(f"Ждем {delay:.1f}s перед следующей попыткой")
                    await asyncio.sleep(delay)
            
            if recovery_success:
                logger.info(f"Восстановление {component} завершено успешно")
            else:
                logger.error(f"Восстановление {component} не удалось")
            
            return recovery_success
            
        except Exception as e:
            logger.error(f"Критическая ошибка при восстановлении {component}: {e}")
            return False
        
        finally:
            # Убираем из активных восстановлений
            if component in self.active_recoveries:
                del self.active_recoveries[component]
    
    async def _execute_recovery_action(self, component: str, action: RecoveryAction) -> bool:
        """Выполнение действия восстановления"""
        
        if component not in self.component_states:
            logger.error(f"Компонент {component} не зарегистрирован")
            return False
        
        recovery_func = self.component_states[component]['recovery_functions'].get(action)
        
        if not recovery_func:
            logger.warning(f"Функция восстановления {action.value} не определена для {component}")
            return False
        
        try:
            logger.info(f"Выполняем {action.value} для {component}")
            result = await recovery_func()
            return bool(result)
        
        except Exception as e:
            logger.error(f"Ошибка выполнения {action.value} для {component}: {e}")
            return False
    
    def _find_recovery_strategy(self, failure_type: FailureType) -> Optional[RecoveryStrategy]:
        """Поиск подходящей стратегии восстановления"""
        
        for strategy in self.recovery_strategies.values():
            if failure_type in strategy.failure_types:
                return strategy
        
        return None
    
    def _is_failure_storm(self, component: str) -> bool:
        """Проверка на шторм сбоев"""
        cutoff_time = datetime.now() - timedelta(minutes=self.failure_window_minutes)
        
        recent_failures = [
            f for f in self.failure_history 
            if f.component == component and f.timestamp > cutoff_time
        ]
        
        return len(recent_failures) >= self.max_failures_per_window
    
    async def _handle_failure_storm(self, component: str):
        """Обработка шторма сбоев"""
        logger.critical(f"Обнаружен шторм сбоев для {component}, переводим в fallback режим")
        
        # Пытаемся перевести в fallback режим
        if component in self.component_states:
            fallback_func = self.component_states[component]['recovery_functions'].get(
                RecoveryAction.FALLBACK_MODE
            )
            
            if fallback_func:
                try:
                    await fallback_func()
                    logger.info(f"Компонент {component} переведен в fallback режим")
                except Exception as e:
                    logger.error(f"Ошибка перевода {component} в fallback режим: {e}")
    
    async def _escalate_failure(self, failure_event: FailureEvent):
        """Эскалация сбоя"""
        logger.critical(f"Эскалация сбоя: {failure_event.component} - {failure_event.error_message}")
        
        # Здесь можно отправить критическое уведомление администратору
        # Интеграция с системой алертов
        try:
            from alert_system import AlertLevel
            # Предполагаем, что есть глобальная система алертов
            # alert_system.trigger_alert(
            #     failure_event.component,
            #     AlertLevel.CRITICAL,
            #     f"Автовосстановление не удалось: {failure_event.error_message}",
            #     failure_event.context
            # )
        except:
            pass
    
    def get_component_status(self, component: str) -> Dict[str, Any]:
        """Получение статуса компонента"""
        if component not in self.component_states:
            return {'error': f'Компонент {component} не зарегистрирован'}
        
        state = self.component_states[component]
        
        # Считаем недавние сбои
        cutoff_time = datetime.now() - timedelta(hours=1)
        recent_failures = [
            f for f in self.failure_history 
            if f.component == component and f.timestamp > cutoff_time
        ]
        
        return {
            'component': component,
            'status': state['status'],
            'last_failure': state['last_failure'].isoformat() if state['last_failure'] else None,
            'total_failures': state['failure_count'],
            'recent_failures_1h': len(recent_failures),
            'recovery_in_progress': component in self.active_recoveries,
            'registered_functions': [
                action.value for action, func in state['recovery_functions'].items() 
                if func is not None
            ]
        }
    
    def get_recovery_stats(self) -> Dict[str, Any]:
        """Получение статистики восстановления"""
        
        # Статистика по типам сбоев
        failure_types_stats = {}
        for failure in self.failure_history:
            failure_type = failure.failure_type.value
            if failure_type not in failure_types_stats:
                failure_types_stats[failure_type] = {
                    'count': 0,
                    'recovered': 0
                }
            
            failure_types_stats[failure_type]['count'] += 1
            if failure.recovery_successful:
                failure_types_stats[failure_type]['recovered'] += 1
        
        # Общая статистика
        total_failures = self.recovery_stats['total_failures']
        success_rate = 0
        if total_failures > 0:
            success_rate = (self.recovery_stats['successful_recoveries'] / total_failures) * 100
        
        return {
            'total_failures': total_failures,
            'successful_recoveries': self.recovery_stats['successful_recoveries'],
            'failed_recoveries': self.recovery_stats['failed_recoveries'],
            'escalations': self.recovery_stats['escalations'],
            'success_rate_percent': round(success_rate, 2),
            'active_recoveries': len(self.active_recoveries),
            'registered_components': len(self.component_states),
            'registered_strategies': len(self.recovery_strategies),
            'failure_types_breakdown': failure_types_stats
        }
    
    def get_failure_history(self, component: str = None, hours: int = 24) -> List[Dict[str, Any]]:
        """Получение истории сбоев"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        filtered_failures = [
            f for f in self.failure_history 
            if f.timestamp > cutoff_time and (component is None or f.component == component)
        ]
        
        return [
            {
                'component': f.component,
                'failure_type': f.failure_type.value,
                'timestamp': f.timestamp.isoformat(),
                'error_message': f.error_message,
                'context': f.context,
                'recovery_attempted': f.recovery_attempted,
                'recovery_successful': f.recovery_successful
            }
            for f in filtered_failures
        ]
    
    def export_recovery_report(self, file_path: str = None) -> str:
        """Экспорт отчета о восстановлении"""
        report = {
            'generated_at': datetime.now().isoformat(),
            'recovery_stats': self.get_recovery_stats(),
            'component_statuses': {
                comp: self.get_component_status(comp) 
                for comp in self.component_states.keys()
            },
            'recent_failures': self.get_failure_history(hours=24),
            'active_recoveries': {
                comp: {
                    'strategy': info['strategy'],
                    'started_at': info['started_at'].isoformat(),
                    'attempt': info['attempt']
                }
                for comp, info in self.active_recoveries.items()
            }
        }
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                logger.info(f"Отчет о восстановлении сохранен в {file_path}")
            except Exception as e:
                logger.error(f"Ошибка сохранения отчета: {e}")
        
        return json.dumps(report, indent=2, ensure_ascii=False)

# Утилиты для интеграции

async def database_reconnect(db_manager) -> bool:
    """Переподключение к базе данных"""
    try:
        logger.info("Переподключение к базе данных")
        
        if hasattr(db_manager, 'reconnect'):
            return await db_manager.reconnect()
        elif hasattr(db_manager, 'connect'):
            return await db_manager.connect()
        else:
            # Пытаемся выполнить простой запрос
            result = db_manager.health_check()
            return bool(result)
    except Exception as e:
        logger.error(f"Ошибка переподключения к БД: {e}")
        return False

async def cache_reconnect(cache_manager) -> bool:
    """Переподключение к кэшу"""
    try:
        logger.info("Переподключение к Redis")
        
        if hasattr(cache_manager, 'connect'):
            await cache_manager.connect()
            return True
        else:
            # Проверяем соединение
            health = await cache_manager.health_check()
            return health.get('status') == 'healthy'
    except Exception as e:
        logger.error(f"Ошибка переподключения к Redis: {e}")
        return False

async def clear_application_cache(cache_manager) -> bool:
    """Очистка кэша приложения"""
    try:
        logger.info("Очистка кэша приложения")
        
        if hasattr(cache_manager, 'clear_cache'):
            cleared = await cache_manager.clear_cache()
            return cleared > 0
        else:
            return True
    except Exception as e:
        logger.error(f"Ошибка очистки кэша: {e}")
        return False

def setup_auto_recovery(app_components: Dict[str, Any], 
                       config: Dict[str, Any] = None) -> AutoRecoveryManager:
    """Настройка автовосстановления для приложения"""
    
    recovery_manager = AutoRecoveryManager(config)
    
    # Регистрируем компоненты
    
    if 'db_manager' in app_components:
        recovery_manager.register_component(
            'database',
            reconnect_func=lambda: database_reconnect(app_components['db_manager'])
        )
    
    if 'cache_manager' in app_components:
        recovery_manager.register_component(
            'cache',
            reconnect_func=lambda: cache_reconnect(app_components['cache_manager']),
            clear_cache_func=lambda: clear_application_cache(app_components['cache_manager'])
        )
    
    return recovery_manager

# Глобальный экземпляр
_global_recovery_manager = None

def get_recovery_manager() -> Optional[AutoRecoveryManager]:
    """Получение глобального менеджера восстановления"""
    return _global_recovery_manager

def set_recovery_manager(manager: AutoRecoveryManager):
    """Установка глобального менеджера восстановления"""
    global _global_recovery_manager
    _global_recovery_manager = manager 