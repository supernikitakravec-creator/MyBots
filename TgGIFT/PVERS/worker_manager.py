#!/usr/bin/env python3
"""
Worker Manager - система управления worker процессами для TgGIFT Bot
"""

import logging
import asyncio
import multiprocessing
import signal
import os
import sys
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import subprocess

logger = logging.getLogger(__name__)

class WorkerType(Enum):
    """Типы воркеров"""
    BOT_HANDLER = "bot_handler"      # Обработка Telegram сообщений
    QUEUE_WORKER = "queue_worker"    # Обработка очередей
    BACKGROUND_TASK = "background_task"  # Фоновые задачи
    API_SERVER = "api_server"        # API сервер
    WEBHOOK_HANDLER = "webhook_handler"  # Webhook обработчик

class WorkerState(Enum):
    """Состояния воркеров"""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    RESTARTING = "restarting"

@dataclass
class WorkerConfig:
    """Конфигурация воркера"""
    worker_type: WorkerType
    worker_id: str
    module_path: str  # Путь к модулю для запуска
    function_name: str = "main"  # Функция для запуска
    args: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    max_memory_mb: int = 512
    max_cpu_percent: float = 80.0
    restart_on_failure: bool = True
    max_restarts: int = 5
    restart_delay: int = 5
    health_check_interval: int = 30
    graceful_shutdown_timeout: int = 30

@dataclass
class WorkerProcess:
    """Информация о worker процессе"""
    config: WorkerConfig
    process: Optional[subprocess.Popen] = None
    pid: Optional[int] = None
    state: WorkerState = WorkerState.STOPPED
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    restart_count: int = 0
    last_restart: Optional[datetime] = None
    cpu_usage: float = 0.0
    memory_usage_mb: float = 0.0
    error_message: Optional[str] = None
    
    @property
    def uptime_seconds(self) -> float:
        """Время работы в секундах"""
        if self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return 0.0
    
    @property
    def is_healthy(self) -> bool:
        """Проверка здоровья воркера"""
        if self.state != WorkerState.RUNNING:
            return False
        
        # Проверяем heartbeat
        if self.last_heartbeat:
            heartbeat_age = (datetime.now() - self.last_heartbeat).total_seconds()
            if heartbeat_age > self.config.health_check_interval * 2:
                return False
        
        # Проверяем ресурсы
        if self.memory_usage_mb > self.config.max_memory_mb:
            return False
        
        if self.cpu_usage > self.config.max_cpu_percent:
            return False
        
        return True

class WorkerManager:
    """Менеджер worker процессов"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.workers: Dict[str, WorkerProcess] = {}
        self.running = False
        
        # Настройки
        self.monitor_interval = self.config.get('monitor_interval', 10)
        self.max_workers = self.config.get('max_workers', multiprocessing.cpu_count() * 2)
        self.auto_scale = self.config.get('auto_scale', True)
        
        # Статистика
        self.stats = {
            'total_started': 0,
            'total_stopped': 0,
            'total_restarts': 0,
            'total_failures': 0
        }
        
        # Задачи мониторинга
        self.monitor_task = None
        
        logger.info(f"Worker Manager инициализирован (max_workers: {self.max_workers})")
    
    async def start(self):
        """Запуск менеджера"""
        if self.running:
            return
        
        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        
        # Настраиваем обработчики сигналов
        self._setup_signal_handlers()
        
        logger.info("Worker Manager запущен")
    
    async def stop(self):
        """Остановка менеджера"""
        if not self.running:
            return
        
        self.running = False
        
        # Останавливаем мониторинг
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # Останавливаем все воркеры
        await self.stop_all_workers()
        
        logger.info("Worker Manager остановлен")
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        def signal_handler(signum, frame):
            logger.info(f"Получен сигнал {signum}, останавливаем воркеры")
            # Создаем задачу остановки
            loop = asyncio.get_event_loop()
            loop.create_task(self.stop())
        
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        else:
            signal.signal(signal.SIGINT, signal_handler)
    
    def add_worker_config(self, config: WorkerConfig):
        """Добавление конфигурации воркера"""
        if config.worker_id in self.workers:
            raise ValueError(f"Воркер {config.worker_id} уже существует")
        
        worker = WorkerProcess(config=config)
        self.workers[config.worker_id] = worker
        
        logger.info(f"Добавлен воркер: {config.worker_id} ({config.worker_type.value})")
    
    async def start_worker(self, worker_id: str) -> bool:
        """Запуск воркера"""
        if worker_id not in self.workers:
            logger.error(f"Воркер {worker_id} не найден")
            return False
        
        worker = self.workers[worker_id]
        
        if worker.state in [WorkerState.RUNNING, WorkerState.STARTING]:
            logger.warning(f"Воркер {worker_id} уже запущен или запускается")
            return True
        
        try:
            logger.info(f"Запуск воркера {worker_id}")
            worker.state = WorkerState.STARTING
            
            # Подготавливаем команду
            cmd = self._build_worker_command(worker.config)
            
            # Подготавливаем окружение
            env = os.environ.copy()
            env.update(worker.config.env_vars)
            env['WORKER_ID'] = worker_id
            env['WORKER_TYPE'] = worker.config.worker_type.value
            
            # Запускаем процесс
            worker.process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if sys.platform != 'win32' else None
            )
            
            worker.pid = worker.process.pid
            worker.started_at = datetime.now()
            worker.state = WorkerState.RUNNING
            worker.last_heartbeat = datetime.now()
            
            self.stats['total_started'] += 1
            
            logger.info(f"Воркер {worker_id} запущен с PID {worker.pid}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска воркера {worker_id}: {e}")
            worker.state = WorkerState.FAILED
            worker.error_message = str(e)
            self.stats['total_failures'] += 1
            return False
    
    async def stop_worker(self, worker_id: str, force: bool = False) -> bool:
        """Остановка воркера"""
        if worker_id not in self.workers:
            logger.error(f"Воркер {worker_id} не найден")
            return False
        
        worker = self.workers[worker_id]
        
        if worker.state in [WorkerState.STOPPED, WorkerState.STOPPING]:
            logger.warning(f"Воркер {worker_id} уже остановлен или останавливается")
            return True
        
        try:
            logger.info(f"Остановка воркера {worker_id}")
            worker.state = WorkerState.STOPPING
            
            if worker.process and worker.process.poll() is None:
                if force:
                    # Принудительная остановка
                    if sys.platform != 'win32':
                        os.killpg(os.getpgid(worker.process.pid), signal.SIGKILL)
                    else:
                        worker.process.kill()
                else:
                    # Graceful остановка
                    if sys.platform != 'win32':
                        os.killpg(os.getpgid(worker.process.pid), signal.SIGTERM)
                    else:
                        worker.process.terminate()
                    
                    # Ждем graceful завершения
                    try:
                        worker.process.wait(timeout=worker.config.graceful_shutdown_timeout)
                    except subprocess.TimeoutExpired:
                        # Принудительная остановка если не завершился
                        logger.warning(f"Принудительная остановка воркера {worker_id}")
                        if sys.platform != 'win32':
                            os.killpg(os.getpgid(worker.process.pid), signal.SIGKILL)
                        else:
                            worker.process.kill()
                        worker.process.wait()
            
            worker.state = WorkerState.STOPPED
            worker.process = None
            worker.pid = None
            
            self.stats['total_stopped'] += 1
            
            logger.info(f"Воркер {worker_id} остановлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки воркера {worker_id}: {e}")
            worker.error_message = str(e)
            return False
    
    async def restart_worker(self, worker_id: str) -> bool:
        """Перезапуск воркера"""
        if worker_id not in self.workers:
            logger.error(f"Воркер {worker_id} не найден")
            return False
        
        worker = self.workers[worker_id]
        
        # Проверяем лимит перезапусков
        if worker.restart_count >= worker.config.max_restarts:
            logger.error(f"Превышен лимит перезапусков для воркера {worker_id}")
            return False
        
        logger.info(f"Перезапуск воркера {worker_id}")
        worker.state = WorkerState.RESTARTING
        
        # Останавливаем
        await self.stop_worker(worker_id)
        
        # Ждем задержку перед перезапуском
        await asyncio.sleep(worker.config.restart_delay)
        
        # Запускаем
        success = await self.start_worker(worker_id)
        
        if success:
            worker.restart_count += 1
            worker.last_restart = datetime.now()
            self.stats['total_restarts'] += 1
        
        return success
    
    async def start_all_workers(self):
        """Запуск всех воркеров"""
        logger.info("Запуск всех воркеров")
        
        tasks = []
        for worker_id in self.workers:
            tasks.append(self.start_worker(worker_id))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful = sum(1 for r in results if r is True)
            logger.info(f"Запущено {successful}/{len(tasks)} воркеров")
    
    async def stop_all_workers(self):
        """Остановка всех воркеров"""
        logger.info("Остановка всех воркеров")
        
        tasks = []
        for worker_id in self.workers:
            tasks.append(self.stop_worker(worker_id))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful = sum(1 for r in results if r is True)
            logger.info(f"Остановлено {successful}/{len(tasks)} воркеров")
    
    def _build_worker_command(self, config: WorkerConfig) -> List[str]:
        """Построение команды для запуска воркера"""
        cmd = [sys.executable, "-c"]
        
        # Создаем код для запуска
        startup_code = f"""
import sys
sys.path.insert(0, '.')

try:
    from {config.module_path} import {config.function_name}
    {config.function_name}({', '.join(repr(arg) for arg in config.args)})
except Exception as e:
    import logging
    logging.error(f"Ошибка запуска воркера: {{e}}")
    sys.exit(1)
"""
        
        cmd.append(startup_code)
        return cmd
    
    async def _monitor_loop(self):
        """Цикл мониторинга воркеров"""
        while self.running:
            try:
                await asyncio.sleep(self.monitor_interval)
                await self._check_workers_health()
                await self._update_worker_stats()
                
                if self.auto_scale:
                    await self._auto_scale_workers()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
    
    async def _check_workers_health(self):
        """Проверка здоровья воркеров"""
        for worker_id, worker in self.workers.items():
            if worker.state == WorkerState.RUNNING:
                # Проверяем, что процесс еще жив
                if worker.process and worker.process.poll() is not None:
                    logger.warning(f"Воркер {worker_id} завершился неожиданно")
                    worker.state = WorkerState.FAILED
                    worker.error_message = "Process terminated unexpectedly"
                    
                    # Перезапускаем если нужно
                    if worker.config.restart_on_failure:
                        await self.restart_worker(worker_id)
                
                # Проверяем здоровье
                elif not worker.is_healthy:
                    logger.warning(f"Воркер {worker_id} нездоров")
                    
                    # Перезапускаем нездоровый воркер
                    if worker.config.restart_on_failure:
                        await self.restart_worker(worker_id)
    
    async def _update_worker_stats(self):
        """Обновление статистики воркеров"""
        for worker in self.workers.values():
            if worker.pid:
                try:
                    process = psutil.Process(worker.pid)
                    
                    # Обновляем статистику ресурсов
                    worker.cpu_usage = process.cpu_percent()
                    worker.memory_usage_mb = process.memory_info().rss / (1024 * 1024)
                    
                except psutil.NoSuchProcess:
                    # Процесс завершился
                    worker.state = WorkerState.FAILED
                    worker.error_message = "Process not found"
                except Exception as e:
                    logger.error(f"Ошибка обновления статистики воркера {worker.config.worker_id}: {e}")
    
    async def _auto_scale_workers(self):
        """Автоматическое масштабирование воркеров"""
        # Простая логика масштабирования
        # В реальной реализации можно добавить более сложные алгоритмы
        
        running_workers = [w for w in self.workers.values() if w.state == WorkerState.RUNNING]
        
        # Проверяем загрузку системы
        system_load = psutil.cpu_percent(interval=1)
        memory_usage = psutil.virtual_memory().percent
        
        # Если система перегружена, не добавляем новых воркеров
        if system_load > 90 or memory_usage > 90:
            logger.warning("Система перегружена, автомасштабирование отключено")
            return
        
        # Проверяем нужно ли добавить воркеров
        if len(running_workers) < self.max_workers:
            avg_cpu = sum(w.cpu_usage for w in running_workers) / len(running_workers) if running_workers else 0
            
            # Если средняя загрузка воркеров высокая, добавляем новый
            if avg_cpu > 70:
                logger.info("Высокая загрузка воркеров, рассматриваем масштабирование")
                # Здесь можно добавить логику создания новых воркеров
    
    def get_worker_status(self, worker_id: str) -> Dict[str, Any]:
        """Получение статуса воркера"""
        if worker_id not in self.workers:
            return {'error': f'Воркер {worker_id} не найден'}
        
        worker = self.workers[worker_id]
        
        return {
            'worker_id': worker_id,
            'worker_type': worker.config.worker_type.value,
            'state': worker.state.value,
            'pid': worker.pid,
            'uptime_seconds': worker.uptime_seconds,
            'cpu_usage': worker.cpu_usage,
            'memory_usage_mb': worker.memory_usage_mb,
            'restart_count': worker.restart_count,
            'is_healthy': worker.is_healthy,
            'last_heartbeat': worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
            'error_message': worker.error_message
        }
    
    def get_all_workers_status(self) -> Dict[str, Any]:
        """Получение статуса всех воркеров"""
        workers_status = {}
        
        for worker_id in self.workers:
            workers_status[worker_id] = self.get_worker_status(worker_id)
        
        # Общая статистика
        running_count = len([w for w in self.workers.values() if w.state == WorkerState.RUNNING])
        total_cpu = sum(w.cpu_usage for w in self.workers.values() if w.state == WorkerState.RUNNING)
        total_memory = sum(w.memory_usage_mb for w in self.workers.values() if w.state == WorkerState.RUNNING)
        
        return {
            'workers': workers_status,
            'summary': {
                'total_workers': len(self.workers),
                'running_workers': running_count,
                'avg_cpu_usage': total_cpu / running_count if running_count > 0 else 0,
                'total_memory_mb': total_memory,
                'stats': self.stats
            }
        }
    
    def scale_workers(self, worker_type: WorkerType, target_count: int):
        """Масштабирование воркеров определенного типа"""
        current_workers = [
            w for w in self.workers.values() 
            if w.config.worker_type == worker_type
        ]
        
        current_count = len(current_workers)
        
        if target_count > current_count:
            # Добавляем воркеров
            for i in range(target_count - current_count):
                worker_id = f"{worker_type.value}_{len(self.workers) + 1}"
                # Здесь нужно создать конфигурацию для нового воркера
                logger.info(f"Нужно добавить воркер {worker_id}")
        
        elif target_count < current_count:
            # Удаляем воркеров
            workers_to_stop = current_workers[target_count:]
            for worker in workers_to_stop:
                asyncio.create_task(self.stop_worker(worker.config.worker_id))

# Утилиты для создания воркеров

def create_bot_worker_config(worker_id: str, **kwargs) -> WorkerConfig:
    """Создание конфигурации для bot worker"""
    return WorkerConfig(
        worker_type=WorkerType.BOT_HANDLER,
        worker_id=worker_id,
        module_path="main_bot",
        function_name="run_bot_worker",
        max_memory_mb=kwargs.get('max_memory_mb', 256),
        **kwargs
    )

def create_queue_worker_config(worker_id: str, queue_names: List[str], **kwargs) -> WorkerConfig:
    """Создание конфигурации для queue worker"""
    return WorkerConfig(
        worker_type=WorkerType.QUEUE_WORKER,
        worker_id=worker_id,
        module_path="queue_worker",
        function_name="run_queue_worker",
        args=queue_names,
        max_memory_mb=kwargs.get('max_memory_mb', 128),
        **kwargs
    )

def create_webhook_worker_config(worker_id: str, port: int, **kwargs) -> WorkerConfig:
    """Создание конфигурации для webhook worker"""
    return WorkerConfig(
        worker_type=WorkerType.WEBHOOK_HANDLER,
        worker_id=worker_id,
        module_path="webhook_server",
        function_name="run_webhook_server",
        args=[str(port)],
        env_vars={'WEBHOOK_PORT': str(port)},
        max_memory_mb=kwargs.get('max_memory_mb', 192),
        **kwargs
    )

# Глобальный экземпляр
_global_worker_manager = None

def get_worker_manager() -> Optional[WorkerManager]:
    """Получение глобального менеджера воркеров"""
    return _global_worker_manager

def set_worker_manager(manager: WorkerManager):
    """Установка глобального менеджера воркеров"""
    global _global_worker_manager
    _global_worker_manager = manager 