#!/usr/bin/env python3
"""
Health Monitor - система проверки состояния компонентов TgGIFT Bot
"""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass
import psutil

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    """Статусы состояния компонентов"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

@dataclass
class HealthCheck:
    """Результат проверки состояния"""
    component: str
    status: HealthStatus
    message: str
    response_time: float
    timestamp: datetime
    details: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'component': self.component,
            'status': self.status.value,
            'message': self.message,
            'response_time': self.response_time,
            'timestamp': self.timestamp.isoformat(),
            'details': self.details or {}
        }

class HealthMonitor:
    """Монитор состояния системы"""
    
    def __init__(self):
        self.checks = {}  # Зарегистрированные проверки
        self.last_results = {}  # Последние результаты проверок
        self.check_history = {}  # История проверок
        self.thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'response_time': 5.0
        }
        
        # Регистрируем базовые проверки
        self._register_default_checks()
        
        logger.info("Health Monitor инициализирован")
    
    def _register_default_checks(self):
        """Регистрация стандартных проверок"""
        self.register_check("system_resources", self._check_system_resources)
        self.register_check("process_health", self._check_process_health)
    
    def register_check(self, name: str, check_func: Callable, timeout: float = 10.0):
        """Регистрация новой проверки"""
        self.checks[name] = {
            'func': check_func,
            'timeout': timeout,
            'enabled': True
        }
        logger.info(f"Зарегистрирована проверка: {name}")
    
    def disable_check(self, name: str):
        """Отключение проверки"""
        if name in self.checks:
            self.checks[name]['enabled'] = False
            logger.info(f"Проверка отключена: {name}")
    
    def enable_check(self, name: str):
        """Включение проверки"""
        if name in self.checks:
            self.checks[name]['enabled'] = True
            logger.info(f"Проверка включена: {name}")
    
    async def run_check(self, name: str) -> HealthCheck:
        """Выполнение одной проверки"""
        if name not in self.checks:
            return HealthCheck(
                component=name,
                status=HealthStatus.UNKNOWN,
                message="Проверка не найдена",
                response_time=0,
                timestamp=datetime.now()
            )
        
        check_config = self.checks[name]
        if not check_config['enabled']:
            return HealthCheck(
                component=name,
                status=HealthStatus.UNKNOWN,
                message="Проверка отключена",
                response_time=0,
                timestamp=datetime.now()
            )
        
        start_time = time.time()
        try:
            # Выполняем проверку с таймаутом
            result = await asyncio.wait_for(
                check_config['func'](),
                timeout=check_config['timeout']
            )
            
            response_time = time.time() - start_time
            
            # Если функция вернула HealthCheck, используем его
            if isinstance(result, HealthCheck):
                result.response_time = response_time
                result.timestamp = datetime.now()
                return result
            
            # Если функция вернула словарь, создаем HealthCheck
            if isinstance(result, dict):
                return HealthCheck(
                    component=name,
                    status=HealthStatus(result.get('status', 'healthy')),
                    message=result.get('message', 'OK'),
                    response_time=response_time,
                    timestamp=datetime.now(),
                    details=result.get('details')
                )
            
            # По умолчанию считаем успешным
            return HealthCheck(
                component=name,
                status=HealthStatus.HEALTHY,
                message="OK",
                response_time=response_time,
                timestamp=datetime.now()
            )
            
        except asyncio.TimeoutError:
            return HealthCheck(
                component=name,
                status=HealthStatus.CRITICAL,
                message=f"Таймаут проверки ({check_config['timeout']}s)",
                response_time=time.time() - start_time,
                timestamp=datetime.now()
            )
        except Exception as e:
            return HealthCheck(
                component=name,
                status=HealthStatus.CRITICAL,
                message=f"Ошибка проверки: {str(e)}",
                response_time=time.time() - start_time,
                timestamp=datetime.now()
            )
    
    async def run_all_checks(self) -> Dict[str, HealthCheck]:
        """Выполнение всех проверок"""
        tasks = []
        check_names = []
        
        for name, config in self.checks.items():
            if config['enabled']:
                tasks.append(self.run_check(name))
                check_names.append(name)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        check_results = {}
        for name, result in zip(check_names, results):
            if isinstance(result, Exception):
                check_results[name] = HealthCheck(
                    component=name,
                    status=HealthStatus.CRITICAL,
                    message=f"Исключение: {str(result)}",
                    response_time=0,
                    timestamp=datetime.now()
                )
            else:
                check_results[name] = result
        
        # Сохраняем результаты
        self.last_results = check_results
        
        # Добавляем в историю
        for name, result in check_results.items():
            if name not in self.check_history:
                self.check_history[name] = []
            
            self.check_history[name].append(result)
            
            # Ограничиваем размер истории
            if len(self.check_history[name]) > 100:
                self.check_history[name] = self.check_history[name][-100:]
        
        return check_results
    
    def get_overall_status(self) -> HealthStatus:
        """Получение общего статуса системы"""
        if not self.last_results:
            return HealthStatus.UNKNOWN
        
        statuses = [result.status for result in self.last_results.values()]
        
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        elif all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Получение сводки состояния"""
        overall_status = self.get_overall_status()
        
        component_summary = {}
        for name, result in self.last_results.items():
            component_summary[name] = {
                'status': result.status.value,
                'message': result.message,
                'response_time': result.response_time,
                'last_check': result.timestamp.isoformat()
            }
        
        return {
            'overall_status': overall_status.value,
            'timestamp': datetime.now().isoformat(),
            'components': component_summary,
            'total_checks': len(self.checks),
            'enabled_checks': len([c for c in self.checks.values() if c['enabled']])
        }
    
    # Стандартные проверки
    
    async def _check_system_resources(self) -> Dict[str, Any]:
        """Проверка системных ресурсов"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            issues = []
            status = HealthStatus.HEALTHY
            
            if cpu_percent > self.thresholds['cpu_percent']:
                issues.append(f"Высокая нагрузка CPU: {cpu_percent:.1f}%")
                status = HealthStatus.WARNING if cpu_percent < 95 else HealthStatus.CRITICAL
            
            if memory.percent > self.thresholds['memory_percent']:
                issues.append(f"Высокое потребление памяти: {memory.percent:.1f}%")
                status = HealthStatus.WARNING if memory.percent < 95 else HealthStatus.CRITICAL
            
            if disk.percent > self.thresholds['disk_percent']:
                issues.append(f"Мало свободного места: {disk.percent:.1f}%")
                status = HealthStatus.WARNING if disk.percent < 98 else HealthStatus.CRITICAL
            
            message = "Системные ресурсы в норме"
            if issues:
                message = "; ".join(issues)
            
            return {
                'status': status.value,
                'message': message,
                'details': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_available_gb': memory.available / (1024**3),
                    'disk_percent': disk.percent,
                    'disk_free_gb': disk.free / (1024**3)
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL.value,
                'message': f"Ошибка проверки системных ресурсов: {e}"
            }
    
    async def _check_process_health(self) -> Dict[str, Any]:
        """Проверка состояния процесса"""
        try:
            process = psutil.Process()
            
            # Проверяем основные метрики процесса
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
            num_threads = process.num_threads()
            
            issues = []
            status = HealthStatus.HEALTHY
            
            # Проверяем потребление памяти процессом (более 1GB)
            memory_mb = memory_info.rss / (1024**2)
            if memory_mb > 1024:
                issues.append(f"Высокое потребление памяти процессом: {memory_mb:.1f}MB")
                status = HealthStatus.WARNING
            
            # Проверяем количество потоков (более 50)
            if num_threads > 50:
                issues.append(f"Много потоков: {num_threads}")
                status = HealthStatus.WARNING
            
            message = "Процесс работает нормально"
            if issues:
                message = "; ".join(issues)
            
            return {
                'status': status.value,
                'message': message,
                'details': {
                    'memory_rss_mb': memory_mb,
                    'memory_vms_mb': memory_info.vms / (1024**2),
                    'cpu_percent': cpu_percent,
                    'num_threads': num_threads,
                    'pid': process.pid
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL.value,
                'message': f"Ошибка проверки процесса: {e}"
            }
    
    async def check_database(self, db_manager) -> Dict[str, Any]:
        """Проверка состояния базы данных"""
        try:
            start_time = time.time()
            
            # Выполняем простую проверку
            health_result = db_manager.health_check()
            
            response_time = time.time() - start_time
            
            if health_result and response_time < self.thresholds['response_time']:
                status = HealthStatus.HEALTHY
                message = "База данных работает нормально"
            elif response_time >= self.thresholds['response_time']:
                status = HealthStatus.WARNING
                message = f"Медленный ответ БД: {response_time:.2f}s"
            else:
                status = HealthStatus.CRITICAL
                message = "База данных недоступна"
            
            return {
                'status': status.value,
                'message': message,
                'details': {
                    'response_time': response_time,
                    'health_check_result': health_result
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL.value,
                'message': f"Ошибка проверки БД: {e}"
            }
    
    async def check_redis(self, cache_manager) -> Dict[str, Any]:
        """Проверка состояния Redis"""
        try:
            start_time = time.time()
            
            # Выполняем проверку кэша
            health_result = await cache_manager.health_check()
            
            response_time = time.time() - start_time
            
            if health_result.get('status') == 'healthy':
                status = HealthStatus.HEALTHY
                message = "Redis работает нормально"
            elif health_result.get('status') == 'disabled':
                status = HealthStatus.WARNING
                message = "Redis отключен"
            else:
                status = HealthStatus.CRITICAL
                message = f"Проблема с Redis: {health_result.get('message', 'Unknown')}"
            
            return {
                'status': status.value,
                'message': message,
                'details': {
                    'response_time': response_time,
                    **health_result
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL.value,
                'message': f"Ошибка проверки Redis: {e}"
            }

# Глобальный экземпляр монитора
health_monitor = HealthMonitor() 