#!/usr/bin/env python3
"""
Metrics Collector - система сбора метрик для TgGIFT Bot
"""

import logging
import time
import psutil
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import threading
import json

logger = logging.getLogger(__name__)

@dataclass
class Metric:
    """Структура метрики"""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = None
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'tags': self.tags or {}
        }

class MetricsCollector:
    """Сборщик метрик производительности"""
    
    def __init__(self, max_metrics: int = 10000):
        self.metrics = deque(maxlen=max_metrics)
        self.counters = defaultdict(int)
        self.gauges = defaultdict(float)
        self.timers = defaultdict(list)
        self.histograms = defaultdict(list)
        
        # Статистика по операциям
        self.operation_stats = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0,
            'errors': 0
        })
        
        self._lock = threading.RLock()
        self.start_time = datetime.now()
        
        logger.info("Сборщик метрик инициализирован")
    
    def increment(self, name: str, value: int = 1, tags: Dict[str, str] = None):
        """Увеличение счетчика"""
        with self._lock:
            key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
            self.counters[key] += value
            
            metric = Metric(name, self.counters[key], datetime.now(), tags)
            self.metrics.append(metric)
    
    def gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """Установка значения gauge"""
        with self._lock:
            key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
            self.gauges[key] = value
            
            metric = Metric(name, value, datetime.now(), tags)
            self.metrics.append(metric)
    
    def timer(self, name: str, value: float, tags: Dict[str, str] = None):
        """Запись времени выполнения"""
        with self._lock:
            key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
            self.timers[key].append(value)
            
            # Ограничиваем размер буфера
            if len(self.timers[key]) > 1000:
                self.timers[key] = self.timers[key][-1000:]
            
            metric = Metric(name, value, datetime.now(), tags)
            self.metrics.append(metric)
    
    def histogram(self, name: str, value: float, tags: Dict[str, str] = None):
        """Запись значения в гистограмму"""
        with self._lock:
            key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
            self.histograms[key].append(value)
            
            # Ограничиваем размер буфера
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]
            
            metric = Metric(name, value, datetime.now(), tags)
            self.metrics.append(metric)
    
    def record_operation(self, operation: str, duration: float, success: bool = True, tags: Dict[str, str] = None):
        """Запись статистики операции"""
        with self._lock:
            key = f"{operation}:{json.dumps(tags or {}, sort_keys=True)}"
            stats = self.operation_stats[key]
            
            stats['count'] += 1
            stats['total_time'] += duration
            stats['min_time'] = min(stats['min_time'], duration)
            stats['max_time'] = max(stats['max_time'], duration)
            
            if not success:
                stats['errors'] += 1
            
            # Записываем как timer
            self.timer(f"{operation}.duration", duration, tags)
            self.increment(f"{operation}.count", 1, tags)
            
            if not success:
                self.increment(f"{operation}.errors", 1, tags)
    
    def get_operation_stats(self, operation: str, tags: Dict[str, str] = None) -> Dict[str, Any]:
        """Получение статистики операции"""
        with self._lock:
            key = f"{operation}:{json.dumps(tags or {}, sort_keys=True)}"
            stats = self.operation_stats[key].copy()
            
            if stats['count'] > 0:
                stats['avg_time'] = stats['total_time'] / stats['count']
                stats['error_rate'] = stats['errors'] / stats['count'] * 100
            else:
                stats['avg_time'] = 0
                stats['error_rate'] = 0
            
            return stats
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Получение системных метрик"""
        try:
            # CPU и память
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Сетевые соединения
            connections = len(psutil.net_connections())
            
            # Процесс
            process = psutil.Process()
            process_memory = process.memory_info()
            process_cpu = process.cpu_percent()
            
            return {
                'system': {
                    'cpu_percent': cpu_percent,
                    'memory_total': memory.total,
                    'memory_available': memory.available,
                    'memory_percent': memory.percent,
                    'disk_total': disk.total,
                    'disk_free': disk.free,
                    'disk_percent': disk.percent,
                    'connections_count': connections
                },
                'process': {
                    'memory_rss': process_memory.rss,
                    'memory_vms': process_memory.vms,
                    'cpu_percent': process_cpu,
                    'num_threads': process.num_threads(),
                    'num_fds': process.num_fds() if hasattr(process, 'num_fds') else 0
                },
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds()
            }
        except Exception as e:
            logger.error(f"Ошибка получения системных метрик: {e}")
            return {}
    
    def get_summary(self, minutes: int = 5) -> Dict[str, Any]:
        """Получение сводки метрик за последние N минут"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        with self._lock:
            recent_metrics = [m for m in self.metrics if m.timestamp > cutoff_time]
            
            # Группируем по именам
            grouped = defaultdict(list)
            for metric in recent_metrics:
                grouped[metric.name].append(metric.value)
            
            summary = {}
            for name, values in grouped.items():
                if values:
                    summary[name] = {
                        'count': len(values),
                        'min': min(values),
                        'max': max(values),
                        'avg': sum(values) / len(values),
                        'sum': sum(values)
                    }
            
            return {
                'period_minutes': minutes,
                'total_metrics': len(recent_metrics),
                'unique_metrics': len(grouped),
                'metrics': summary,
                'system': self.get_system_metrics()
            }
    
    def get_top_operations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение топа операций по времени выполнения"""
        with self._lock:
            operations = []
            for key, stats in self.operation_stats.items():
                operation_name = key.split(':')[0]
                if stats['count'] > 0:
                    operations.append({
                        'operation': operation_name,
                        'count': stats['count'],
                        'total_time': stats['total_time'],
                        'avg_time': stats['total_time'] / stats['count'],
                        'min_time': stats['min_time'],
                        'max_time': stats['max_time'],
                        'errors': stats['errors'],
                        'error_rate': stats['errors'] / stats['count'] * 100
                    })
            
            # Сортируем по среднему времени выполнения
            operations.sort(key=lambda x: x['avg_time'], reverse=True)
            return operations[:limit]
    
    def clear_old_metrics(self, hours: int = 24):
        """Очистка старых метрик"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            # Очищаем основные метрики
            self.metrics = deque(
                (m for m in self.metrics if m.timestamp > cutoff_time),
                maxlen=self.metrics.maxlen
            )
            
            # Очищаем буферы таймеров и гистограмм
            for key in list(self.timers.keys()):
                if len(self.timers[key]) > 100:
                    self.timers[key] = self.timers[key][-100:]
            
            for key in list(self.histograms.keys()):
                if len(self.histograms[key]) > 100:
                    self.histograms[key] = self.histograms[key][-100:]
            
            logger.info(f"Очищены метрики старше {hours} часов")
    
    def export_metrics(self, format: str = 'json') -> str:
        """Экспорт метрик в различных форматах"""
        summary = self.get_summary(60)  # За последний час
        
        if format == 'json':
            return json.dumps(summary, indent=2, ensure_ascii=False)
        elif format == 'prometheus':
            # Простой формат Prometheus
            lines = []
            for name, data in summary['metrics'].items():
                safe_name = name.replace('.', '_').replace('-', '_')
                lines.append(f"# HELP {safe_name} Metric {name}")
                lines.append(f"# TYPE {safe_name} gauge")
                lines.append(f"{safe_name}_count {data['count']}")
                lines.append(f"{safe_name}_sum {data['sum']}")
                lines.append(f"{safe_name}_avg {data['avg']}")
            return '\n'.join(lines)
        else:
            return str(summary)

# Декоратор для автоматического измерения времени выполнения
def measure_time(operation_name: str, tags: Dict[str, str] = None):
    """Декоратор для измерения времени выполнения функции"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration = time.time() - start_time
                metrics_collector.record_operation(
                    operation_name, duration, success, tags
                )
        return wrapper
    return decorator

# Асинхронная версия декоратора
def measure_time_async(operation_name: str, tags: Dict[str, str] = None):
    """Асинхронный декоратор для измерения времени выполнения"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration = time.time() - start_time
                metrics_collector.record_operation(
                    operation_name, duration, success, tags
                )
        return wrapper
    return decorator

# Глобальный экземпляр сборщика метрик
metrics_collector = MetricsCollector() 