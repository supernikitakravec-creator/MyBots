#!/usr/bin/env python3
"""
Graceful Shutdown - система корректного завершения работы TgGIFT Bot
"""

import logging
import asyncio
import signal
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum
import threading

logger = logging.getLogger(__name__)

class ShutdownPhase(Enum):
    """Фазы корректного завершения"""
    RUNNING = "running"
    GRACEFUL_STOP = "graceful_stop"
    FORCE_STOP = "force_stop"
    STOPPED = "stopped"

@dataclass
class ShutdownTask:
    """Задача для выполнения при завершении"""
    name: str
    func: Callable[[], Awaitable[None]]
    timeout: float
    priority: int = 0  # Чем выше число, тем раньше выполняется
    required: bool = True  # Обязательная ли задача

class GracefulShutdownManager:
    """Менеджер корректного завершения работы"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Настройки таймаутов
        self.graceful_timeout = self.config.get('graceful_timeout', 30)  # 30 секунд
        self.force_timeout = self.config.get('force_timeout', 10)  # 10 секунд
        
        # Состояние
        self.phase = ShutdownPhase.RUNNING
        self.shutdown_tasks = []
        self.shutdown_event = asyncio.Event()
        self.shutdown_start_time = None
        
        # Статистика
        self.shutdown_stats = {
            'initiated_at': None,
            'completed_at': None,
            'duration': None,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'forced': False
        }
        
        # Обработчики сигналов
        self._setup_signal_handlers()
        
        logger.info("Graceful Shutdown Manager инициализирован")
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков системных сигналов"""
        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            logger.info(f"Получен сигнал {signal_name}, начинаем корректное завершение")
            
            # Запускаем завершение в новом потоке если мы не в asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.initiate_shutdown(f"Сигнал {signal_name}"))
            except RuntimeError:
                # Нет активного event loop, создаем новый
                asyncio.create_task(self.initiate_shutdown(f"Сигнал {signal_name}"))
        
        # Регистрируем обработчики для разных сигналов
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGHUP, signal_handler)
        else:
            # Windows поддерживает только SIGINT
            signal.signal(signal.SIGINT, signal_handler)
    
    def register_shutdown_task(self, name: str, func: Callable[[], Awaitable[None]], 
                             timeout: float = 10.0, priority: int = 0, 
                             required: bool = True):
        """Регистрация задачи для выполнения при завершении"""
        task = ShutdownTask(
            name=name,
            func=func,
            timeout=timeout,
            priority=priority,
            required=required
        )
        
        self.shutdown_tasks.append(task)
        
        # Сортируем по приоритету (высокий приоритет первым)
        self.shutdown_tasks.sort(key=lambda x: x.priority, reverse=True)
        
        logger.info(f"Зарегистрирована shutdown задача: {name} (приоритет: {priority})")
    
    async def initiate_shutdown(self, reason: str = "Manual shutdown"):
        """Инициация корректного завершения"""
        if self.phase != ShutdownPhase.RUNNING:
            logger.warning("Завершение уже инициировано")
            return
        
        self.phase = ShutdownPhase.GRACEFUL_STOP
        self.shutdown_start_time = datetime.now()
        self.shutdown_stats['initiated_at'] = self.shutdown_start_time.isoformat()
        
        logger.info(f"🛑 Начинаем корректное завершение работы: {reason}")
        logger.info(f"⏱️ Таймаут graceful shutdown: {self.graceful_timeout}s")
        
        try:
            # Выполняем graceful shutdown с таймаутом
            await asyncio.wait_for(
                self._execute_shutdown_tasks(),
                timeout=self.graceful_timeout
            )
            
            self.phase = ShutdownPhase.STOPPED
            logger.info("✅ Корректное завершение выполнено успешно")
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Превышен таймаут graceful shutdown ({self.graceful_timeout}s)")
            await self._force_shutdown()
        
        except Exception as e:
            logger.error(f"❌ Ошибка при корректном завершении: {e}")
            await self._force_shutdown()
        
        finally:
            self._finalize_shutdown()
            self.shutdown_event.set()
    
    async def _execute_shutdown_tasks(self):
        """Выполнение задач завершения"""
        logger.info(f"📋 Выполняем {len(self.shutdown_tasks)} задач завершения")
        
        for task in self.shutdown_tasks:
            if self.phase == ShutdownPhase.FORCE_STOP:
                logger.warning(f"⏭️ Пропускаем задачу {task.name} (принудительное завершение)")
                break
            
            try:
                logger.info(f"🔄 Выполняем: {task.name} (таймаут: {task.timeout}s)")
                
                start_time = time.time()
                await asyncio.wait_for(task.func(), timeout=task.timeout)
                duration = time.time() - start_time
                
                logger.info(f"✅ Завершена: {task.name} за {duration:.2f}s")
                self.shutdown_stats['tasks_completed'] += 1
                
            except asyncio.TimeoutError:
                logger.error(f"⏰ Таймаут задачи: {task.name}")
                self.shutdown_stats['tasks_failed'] += 1
                
                if task.required:
                    raise  # Прерываем выполнение для обязательных задач
            
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче {task.name}: {e}")
                self.shutdown_stats['tasks_failed'] += 1
                
                if task.required:
                    raise  # Прерываем выполнение для обязательных задач
    
    async def _force_shutdown(self):
        """Принудительное завершение"""
        self.phase = ShutdownPhase.FORCE_STOP
        self.shutdown_stats['forced'] = True
        
        logger.warning(f"🚨 Принудительное завершение (таймаут: {self.force_timeout}s)")
        
        try:
            # Даем еще немного времени на критически важные операции
            await asyncio.sleep(self.force_timeout)
        except:
            pass
        
        logger.warning("💥 Принудительное завершение завершено")
    
    def _finalize_shutdown(self):
        """Финализация завершения"""
        end_time = datetime.now()
        duration = (end_time - self.shutdown_start_time).total_seconds()
        
        self.shutdown_stats.update({
            'completed_at': end_time.isoformat(),
            'duration': duration
        })
        
        logger.info(f"📊 Статистика завершения:")
        logger.info(f"   ⏱️ Длительность: {duration:.2f}s")
        logger.info(f"   ✅ Выполнено задач: {self.shutdown_stats['tasks_completed']}")
        logger.info(f"   ❌ Ошибок: {self.shutdown_stats['tasks_failed']}")
        logger.info(f"   🚨 Принудительное: {self.shutdown_stats['forced']}")
    
    async def wait_for_shutdown(self):
        """Ожидание завершения"""
        await self.shutdown_event.wait()
    
    def is_shutting_down(self) -> bool:
        """Проверка, идет ли процесс завершения"""
        return self.phase != ShutdownPhase.RUNNING
    
    def get_shutdown_stats(self) -> Dict[str, Any]:
        """Получение статистики завершения"""
        return self.shutdown_stats.copy()

class ShutdownContext:
    """Контекстный менеджер для автоматической регистрации shutdown задач"""
    
    def __init__(self, shutdown_manager: GracefulShutdownManager, 
                 name: str, timeout: float = 10.0, priority: int = 0):
        self.shutdown_manager = shutdown_manager
        self.name = name
        self.timeout = timeout
        self.priority = priority
        self.cleanup_func = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cleanup_func:
            self.shutdown_manager.register_shutdown_task(
                self.name, self.cleanup_func, self.timeout, self.priority
            )
    
    def set_cleanup(self, func: Callable[[], Awaitable[None]]):
        """Установка функции очистки"""
        self.cleanup_func = func

# Предопределенные shutdown задачи

async def shutdown_database(db_manager):
    """Корректное завершение работы с базой данных"""
    logger.info("Закрываем соединения с базой данных")
    try:
        if hasattr(db_manager, 'close'):
            await db_manager.close()
        elif hasattr(db_manager, 'disconnect'):
            await db_manager.disconnect()
        logger.info("База данных отключена")
    except Exception as e:
        logger.error(f"Ошибка отключения базы данных: {e}")

async def shutdown_cache(cache_manager):
    """Корректное завершение работы с кэшем"""
    logger.info("Закрываем соединения с Redis")
    try:
        if hasattr(cache_manager, 'disconnect'):
            await cache_manager.disconnect()
        logger.info("Redis отключен")
    except Exception as e:
        logger.error(f"Ошибка отключения Redis: {e}")

async def shutdown_telegram_bot(application):
    """Корректное завершение Telegram бота"""
    logger.info("Останавливаем Telegram бота")
    try:
        if hasattr(application, 'stop'):
            await application.stop()
        if hasattr(application, 'shutdown'):
            await application.shutdown()
        logger.info("Telegram бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка остановки Telegram бота: {e}")

async def save_application_state(state_data: Dict[str, Any], file_path: str = "app_state.json"):
    """Сохранение состояния приложения"""
    logger.info("Сохраняем состояние приложения")
    try:
        import json
        from pathlib import Path
        
        state_file = Path(file_path)
        
        # Добавляем метаданные
        full_state = {
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'data': state_data
        }
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(full_state, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Состояние сохранено в {state_file}")
    except Exception as e:
        logger.error(f"Ошибка сохранения состояния: {e}")

async def cleanup_temp_files(temp_dirs: List[str] = None):
    """Очистка временных файлов"""
    logger.info("Очищаем временные файлы")
    try:
        import tempfile
        import shutil
        from pathlib import Path
        
        # Стандартные временные директории
        dirs_to_clean = temp_dirs or [
            tempfile.gettempdir() + "/tggift_*",
            "./temp",
            "./cache"
        ]
        
        cleaned_count = 0
        for pattern in dirs_to_clean:
            if "*" in pattern:
                # Glob pattern
                base_dir = Path(pattern).parent
                pattern_name = Path(pattern).name
                for item in base_dir.glob(pattern_name):
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    cleaned_count += 1
            else:
                # Обычный путь
                path = Path(pattern)
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    cleaned_count += 1
        
        logger.info(f"Очищено {cleaned_count} временных файлов/директорий")
    except Exception as e:
        logger.error(f"Ошибка очистки временных файлов: {e}")

# Утилиты для интеграции

def setup_graceful_shutdown(app_components: Dict[str, Any], 
                          config: Dict[str, Any] = None) -> GracefulShutdownManager:
    """Настройка graceful shutdown для приложения"""
    
    shutdown_manager = GracefulShutdownManager(config)
    
    # Регистрируем стандартные задачи завершения
    
    # Высокий приоритет (выполняются первыми)
    if 'telegram_bot' in app_components:
        shutdown_manager.register_shutdown_task(
            "telegram_bot",
            lambda: shutdown_telegram_bot(app_components['telegram_bot']),
            timeout=15.0,
            priority=100
        )
    
    # Средний приоритет
    if 'cache_manager' in app_components:
        shutdown_manager.register_shutdown_task(
            "cache",
            lambda: shutdown_cache(app_components['cache_manager']),
            timeout=10.0,
            priority=50
        )
    
    if 'db_manager' in app_components:
        shutdown_manager.register_shutdown_task(
            "database",
            lambda: shutdown_database(app_components['db_manager']),
            timeout=20.0,
            priority=50
        )
    
    # Низкий приоритет (выполняются последними)
    if 'app_state' in app_components:
        shutdown_manager.register_shutdown_task(
            "save_state",
            lambda: save_application_state(app_components['app_state']),
            timeout=5.0,
            priority=10,
            required=False
        )
    
    shutdown_manager.register_shutdown_task(
        "cleanup_temp",
        lambda: cleanup_temp_files(),
        timeout=5.0,
        priority=1,
        required=False
    )
    
    return shutdown_manager

# Глобальный экземпляр (будет создан при первом использовании)
_global_shutdown_manager = None

def get_shutdown_manager() -> Optional[GracefulShutdownManager]:
    """Получение глобального менеджера завершения"""
    return _global_shutdown_manager

def set_shutdown_manager(manager: GracefulShutdownManager):
    """Установка глобального менеджера завершения"""
    global _global_shutdown_manager
    _global_shutdown_manager = manager 