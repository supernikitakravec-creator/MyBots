#!/usr/bin/env python3
"""
Enhanced Logging - улучшенная система логирования для TgGIFT Bot
"""

import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import traceback

class JSONFormatter(logging.Formatter):
    """Форматтер для структурированных JSON логов"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Базовые поля
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Добавляем дополнительные поля если есть
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        
        if hasattr(record, 'operation'):
            log_entry['operation'] = record.operation
        
        if hasattr(record, 'duration'):
            log_entry['duration'] = record.duration
        
        if hasattr(record, 'extra_data'):
            log_entry['extra'] = record.extra_data
        
        # Добавляем информацию об исключении
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_entry, ensure_ascii=False)

class ColoredFormatter(logging.Formatter):
    """Цветной форматтер для консольного вывода"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        # Добавляем цвет
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        
        # Форматируем сообщение
        formatted = super().format(record)
        
        # Добавляем дополнительную информацию если есть
        extras = []
        if hasattr(record, 'user_id'):
            extras.append(f"user_id={record.user_id}")
        
        if hasattr(record, 'operation'):
            extras.append(f"op={record.operation}")
        
        if hasattr(record, 'duration'):
            extras.append(f"dur={record.duration:.3f}s")
        
        if extras:
            formatted += f" [{', '.join(extras)}]"
        
        return formatted

class EnhancedLogger:
    """Улучшенная система логирования"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.loggers = {}
        
        # Настройки по умолчанию
        self.log_dir = Path(self.config.get('log_dir', 'logs'))
        self.max_file_size = self.config.get('max_file_size', 50 * 1024 * 1024)  # 50MB
        self.backup_count = self.config.get('backup_count', 5)
        self.console_level = self.config.get('console_level', 'INFO')
        self.file_level = self.config.get('file_level', 'DEBUG')
        self.json_logs = self.config.get('json_logs', True)
        
        # Создаем директорию для логов
        self.log_dir.mkdir(exist_ok=True)
        
        self._setup_root_logger()
    
    def _setup_root_logger(self):
        """Настройка корневого логгера"""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Очищаем существующие обработчики
        root_logger.handlers.clear()
        
        # Консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.console_level.upper()))
        
        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # Файловый обработчик для общих логов
        main_file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'tggift_bot.log',
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        main_file_handler.setLevel(getattr(logging, self.file_level.upper()))
        
        if self.json_logs:
            main_file_handler.setFormatter(JSONFormatter())
        else:
            main_file_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s:%(lineno)-3d | %(message)s'
            ))
        
        root_logger.addHandler(main_file_handler)
        
        # Файловый обработчик для ошибок
        error_file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'errors.log',
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(JSONFormatter() if self.json_logs else logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s:%(lineno)-3d | %(message)s'
        ))
        root_logger.addHandler(error_file_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """Получение логгера с дополнительными возможностями"""
        if name not in self.loggers:
            logger = logging.getLogger(name)
            
            # Добавляем специальные методы
            logger.log_operation = self._create_operation_logger(logger)
            logger.log_user_action = self._create_user_action_logger(logger)
            logger.log_performance = self._create_performance_logger(logger)
            
            self.loggers[name] = logger
        
        return self.loggers[name]
    
    def _create_operation_logger(self, logger):
        """Создание логгера операций"""
        def log_operation(operation: str, level: str = 'INFO', **kwargs):
            extra = {'operation': operation}
            if kwargs:
                extra['extra_data'] = kwargs
            
            getattr(logger, level.lower())(
                f"Operation: {operation}",
                extra=extra
            )
        
        return log_operation
    
    def _create_user_action_logger(self, logger):
        """Создание логгера действий пользователей"""
        def log_user_action(user_id: int, action: str, level: str = 'INFO', **kwargs):
            extra = {'user_id': user_id, 'operation': action}
            if kwargs:
                extra['extra_data'] = kwargs
            
            getattr(logger, level.lower())(
                f"User {user_id} performed: {action}",
                extra=extra
            )
        
        return log_user_action
    
    def _create_performance_logger(self, logger):
        """Создание логгера производительности"""
        def log_performance(operation: str, duration: float, level: str = 'DEBUG', **kwargs):
            extra = {'operation': operation, 'duration': duration}
            if kwargs:
                extra['extra_data'] = kwargs
            
            getattr(logger, level.lower())(
                f"Performance: {operation} took {duration:.3f}s",
                extra=extra
            )
        
        return log_performance
    
    def create_specialized_logger(self, name: str, filename: str) -> logging.Logger:
        """Создание специализированного логгера с отдельным файлом"""
        logger = logging.getLogger(name)
        
        # Файловый обработчик для специализированного логгера
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / filename,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        if self.json_logs:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s'
            ))
        
        logger.addHandler(file_handler)
        logger.setLevel(logging.DEBUG)
        
        return logger
    
    def setup_audit_logging(self) -> logging.Logger:
        """Настройка аудит-логирования"""
        return self.create_specialized_logger('audit', 'audit.log')
    
    def setup_security_logging(self) -> logging.Logger:
        """Настройка логирования безопасности"""
        return self.create_specialized_logger('security', 'security.log')
    
    def setup_payment_logging(self) -> logging.Logger:
        """Настройка логирования платежей"""
        return self.create_specialized_logger('payments', 'payments.log')
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Получение статистики логирования"""
        stats = {
            'log_directory': str(self.log_dir),
            'files': [],
            'total_size': 0
        }
        
        try:
            for log_file in self.log_dir.glob('*.log*'):
                size = log_file.stat().st_size
                stats['files'].append({
                    'name': log_file.name,
                    'size': size,
                    'size_mb': round(size / (1024 * 1024), 2),
                    'modified': datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
                })
                stats['total_size'] += size
            
            stats['total_size_mb'] = round(stats['total_size'] / (1024 * 1024), 2)
            stats['file_count'] = len(stats['files'])
            
        except Exception as e:
            stats['error'] = str(e)
        
        return stats
    
    def cleanup_old_logs(self, days: int = 30):
        """Очистка старых лог-файлов"""
        cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
        cleaned_files = []
        
        try:
            for log_file in self.log_dir.glob('*.log.*'):  # Только ротированные файлы
                if log_file.stat().st_mtime < cutoff_time:
                    size = log_file.stat().st_size
                    log_file.unlink()
                    cleaned_files.append({
                        'name': log_file.name,
                        'size_mb': round(size / (1024 * 1024), 2)
                    })
            
            if cleaned_files:
                total_size = sum(f['size_mb'] for f in cleaned_files)
                logging.info(f"Очищено {len(cleaned_files)} лог-файлов, освобождено {total_size:.2f} MB")
            
        except Exception as e:
            logging.error(f"Ошибка очистки лог-файлов: {e}")
        
        return cleaned_files

# Контекстный менеджер для логирования операций
class LogOperation:
    """Контекстный менеджер для автоматического логирования операций"""
    
    def __init__(self, logger: logging.Logger, operation: str, level: str = 'INFO'):
        self.logger = logger
        self.operation = operation
        self.level = level
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        if hasattr(self.logger, 'log_operation'):
            self.logger.log_operation(f"{self.operation} started", self.level)
        else:
            getattr(self.logger, self.level.lower())(f"Operation started: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            # Успешное завершение
            if hasattr(self.logger, 'log_performance'):
                self.logger.log_performance(f"{self.operation} completed", duration, self.level)
            else:
                getattr(self.logger, self.level.lower())(
                    f"Operation completed: {self.operation} in {duration:.3f}s"
                )
        else:
            # Ошибка
            if hasattr(self.logger, 'log_operation'):
                self.logger.log_operation(
                    f"{self.operation} failed: {exc_val}", 
                    'ERROR',
                    duration=duration,
                    exception_type=exc_type.__name__
                )
            else:
                self.logger.error(
                    f"Operation failed: {self.operation} after {duration:.3f}s - {exc_val}"
                )

# Функция для создания улучшенной системы логирования
def setup_enhanced_logging(config: Dict[str, Any] = None) -> EnhancedLogger:
    """Создание и настройка улучшенной системы логирования"""
    return EnhancedLogger(config or {})

# Глобальный экземпляр (будет создан при первом импорте)
enhanced_logger = None

def get_enhanced_logger(name: str = None) -> logging.Logger:
    """Получение улучшенного логгера"""
    global enhanced_logger
    
    if enhanced_logger is None:
        enhanced_logger = setup_enhanced_logging()
    
    if name:
        return enhanced_logger.get_logger(name)
    else:
        return logging.getLogger() 