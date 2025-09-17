#!/usr/bin/env python3
"""
Load Balancer - система балансировки нагрузки для TgGIFT Bot
"""

import logging
import asyncio
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import json
import random
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class LoadBalancingStrategy(Enum):
    """Стратегии балансировки нагрузки"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    CONSISTENT_HASHING = "consistent_hashing"
    LEAST_RESPONSE_TIME = "least_response_time"
    STICKY_SESSION = "sticky_session"

class WorkerStatus(Enum):
    """Статусы воркеров"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"

@dataclass
class WorkerNode:
    """Узел-воркер"""
    id: str
    host: str
    port: int
    weight: int = 100
    max_connections: int = 1000
    current_connections: int = 0
    status: WorkerStatus = WorkerStatus.HEALTHY
    last_health_check: datetime = field(default_factory=datetime.now)
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    total_requests: int = 0
    failed_requests: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"
    
    @property
    def load_factor(self) -> float:
        """Коэффициент загруженности (0.0 - 1.0)"""
        if self.max_connections == 0:
            return 1.0
        return self.current_connections / self.max_connections
    
    @property
    def avg_response_time(self) -> float:
        """Среднее время отклика"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    @property
    def error_rate(self) -> float:
        """Процент ошибок"""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100
    
    def is_available(self) -> bool:
        """Проверка доступности воркера"""
        return (
            self.status in [WorkerStatus.HEALTHY, WorkerStatus.DEGRADED] and
            self.current_connections < self.max_connections
        )
    
    def record_request(self, response_time: float, success: bool = True):
        """Запись статистики запроса"""
        self.response_times.append(response_time)
        self.total_requests += 1
        if not success:
            self.failed_requests += 1

class LoadBalancer:
    """Балансировщик нагрузки"""
    
    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN):
        self.strategy = strategy
        self.workers: Dict[str, WorkerNode] = {}
        self.current_worker_index = 0
        
        # Для consistent hashing
        self.hash_ring: Dict[int, str] = {}
        self.virtual_nodes = 150  # Количество виртуальных узлов на воркер
        
        # Для sticky sessions
        self.session_affinity: Dict[str, str] = {}  # session_id -> worker_id
        self.session_timeout = 3600  # 1 час
        
        # Статистика
        self.request_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0.0
        }
        
        # Health check
        self.health_check_interval = 30  # секунд
        self.health_check_timeout = 5    # секунд
        self.health_check_task = None
        
        logger.info(f"Load Balancer инициализирован со стратегией: {strategy.value}")
    
    def add_worker(self, worker: WorkerNode):
        """Добавление воркера"""
        self.workers[worker.id] = worker
        
        # Обновляем hash ring для consistent hashing
        if self.strategy == LoadBalancingStrategy.CONSISTENT_HASHING:
            self._add_to_hash_ring(worker)
        
        logger.info(f"Добавлен воркер: {worker.id} ({worker.endpoint})")
    
    def remove_worker(self, worker_id: str):
        """Удаление воркера"""
        if worker_id in self.workers:
            worker = self.workers[worker_id]
            
            # Удаляем из hash ring
            if self.strategy == LoadBalancingStrategy.CONSISTENT_HASHING:
                self._remove_from_hash_ring(worker)
            
            # Очищаем session affinity
            sessions_to_remove = [
                session_id for session_id, w_id in self.session_affinity.items()
                if w_id == worker_id
            ]
            for session_id in sessions_to_remove:
                del self.session_affinity[session_id]
            
            del self.workers[worker_id]
            logger.info(f"Удален воркер: {worker_id}")
    
    def _add_to_hash_ring(self, worker: WorkerNode):
        """Добавление воркера в hash ring"""
        for i in range(self.virtual_nodes):
            virtual_key = f"{worker.id}:{i}"
            hash_value = int(hashlib.md5(virtual_key.encode()).hexdigest(), 16)
            self.hash_ring[hash_value] = worker.id
    
    def _remove_from_hash_ring(self, worker: WorkerNode):
        """Удаление воркера из hash ring"""
        keys_to_remove = []
        for hash_value, worker_id in self.hash_ring.items():
            if worker_id == worker.id:
                keys_to_remove.append(hash_value)
        
        for key in keys_to_remove:
            del self.hash_ring[key]
    
    def get_available_workers(self) -> List[WorkerNode]:
        """Получение доступных воркеров"""
        return [worker for worker in self.workers.values() if worker.is_available()]
    
    def select_worker(self, session_id: Optional[str] = None, 
                     routing_key: Optional[str] = None) -> Optional[WorkerNode]:
        """Выбор воркера согласно стратегии"""
        
        available_workers = self.get_available_workers()
        if not available_workers:
            logger.warning("Нет доступных воркеров")
            return None
        
        if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._select_round_robin(available_workers)
        
        elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._select_least_connections(available_workers)
        
        elif self.strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._select_weighted_round_robin(available_workers)
        
        elif self.strategy == LoadBalancingStrategy.CONSISTENT_HASHING:
            return self._select_consistent_hashing(routing_key or session_id or "default")
        
        elif self.strategy == LoadBalancingStrategy.LEAST_RESPONSE_TIME:
            return self._select_least_response_time(available_workers)
        
        elif self.strategy == LoadBalancingStrategy.STICKY_SESSION:
            return self._select_sticky_session(available_workers, session_id)
        
        # Fallback to round robin
        return self._select_round_robin(available_workers)
    
    def _select_round_robin(self, workers: List[WorkerNode]) -> WorkerNode:
        """Round Robin балансировка"""
        worker = workers[self.current_worker_index % len(workers)]
        self.current_worker_index = (self.current_worker_index + 1) % len(workers)
        return worker
    
    def _select_least_connections(self, workers: List[WorkerNode]) -> WorkerNode:
        """Выбор воркера с наименьшим количеством соединений"""
        return min(workers, key=lambda w: w.current_connections)
    
    def _select_weighted_round_robin(self, workers: List[WorkerNode]) -> WorkerNode:
        """Взвешенный Round Robin"""
        # Создаем список с повторениями согласно весам
        weighted_workers = []
        for worker in workers:
            weight_factor = max(1, worker.weight // 10)  # Нормализуем веса
            weighted_workers.extend([worker] * weight_factor)
        
        if not weighted_workers:
            return workers[0]
        
        worker = weighted_workers[self.current_worker_index % len(weighted_workers)]
        self.current_worker_index = (self.current_worker_index + 1) % len(weighted_workers)
        return worker
    
    def _select_consistent_hashing(self, key: str) -> Optional[WorkerNode]:
        """Consistent Hashing"""
        if not self.hash_ring:
            return None
        
        hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
        
        # Находим ближайший узел по часовой стрелке
        sorted_hashes = sorted(self.hash_ring.keys())
        
        for ring_hash in sorted_hashes:
            if hash_value <= ring_hash:
                worker_id = self.hash_ring[ring_hash]
                if worker_id in self.workers and self.workers[worker_id].is_available():
                    return self.workers[worker_id]
        
        # Если не нашли, берем первый
        if sorted_hashes:
            worker_id = self.hash_ring[sorted_hashes[0]]
            if worker_id in self.workers and self.workers[worker_id].is_available():
                return self.workers[worker_id]
        
        return None
    
    def _select_least_response_time(self, workers: List[WorkerNode]) -> WorkerNode:
        """Выбор воркера с наименьшим временем отклика"""
        return min(workers, key=lambda w: w.avg_response_time or float('inf'))
    
    def _select_sticky_session(self, workers: List[WorkerNode], 
                              session_id: Optional[str]) -> WorkerNode:
        """Sticky Session балансировка"""
        if not session_id:
            return self._select_round_robin(workers)
        
        # Проверяем существующую привязку
        if session_id in self.session_affinity:
            worker_id = self.session_affinity[session_id]
            if worker_id in self.workers and self.workers[worker_id].is_available():
                return self.workers[worker_id]
            else:
                # Удаляем недоступную привязку
                del self.session_affinity[session_id]
        
        # Создаем новую привязку
        worker = self._select_least_connections(workers)
        self.session_affinity[session_id] = worker.id
        return worker
    
    async def handle_request(self, request_handler: Callable, 
                           session_id: Optional[str] = None,
                           routing_key: Optional[str] = None,
                           *args, **kwargs) -> Any:
        """Обработка запроса через балансировщик"""
        
        worker = self.select_worker(session_id, routing_key)
        if not worker:
            raise Exception("Нет доступных воркеров")
        
        start_time = time.time()
        worker.current_connections += 1
        success = False
        
        try:
            # Выполняем запрос
            if asyncio.iscoroutinefunction(request_handler):
                result = await request_handler(worker, *args, **kwargs)
            else:
                result = request_handler(worker, *args, **kwargs)
            
            success = True
            return result
            
        except Exception as e:
            logger.error(f"Ошибка запроса к воркеру {worker.id}: {e}")
            raise
            
        finally:
            # Обновляем статистику
            response_time = time.time() - start_time
            worker.record_request(response_time, success)
            worker.current_connections = max(0, worker.current_connections - 1)
            
            # Обновляем общую статистику
            self.request_stats['total_requests'] += 1
            if success:
                self.request_stats['successful_requests'] += 1
            else:
                self.request_stats['failed_requests'] += 1
    
    async def start_health_checks(self):
        """Запуск мониторинга здоровья воркеров"""
        if self.health_check_task:
            return
        
        self.health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Запущен мониторинг здоровья воркеров")
    
    async def stop_health_checks(self):
        """Остановка мониторинга здоровья"""
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
            self.health_check_task = None
        
        logger.info("Остановлен мониторинг здоровья воркеров")
    
    async def _health_check_loop(self):
        """Цикл проверки здоровья воркеров"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                tasks = []
                for worker in self.workers.values():
                    tasks.append(self._check_worker_health(worker))
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле health check: {e}")
    
    async def _check_worker_health(self, worker: WorkerNode):
        """Проверка здоровья воркера"""
        try:
            # Простая проверка доступности (можно расширить)
            start_time = time.time()
            
            # Здесь должна быть реальная проверка здоровья
            # Например, HTTP запрос к /health endpoint
            await asyncio.sleep(0.01)  # Имитация проверки
            
            response_time = time.time() - start_time
            
            # Обновляем статус на основе метрик
            if worker.error_rate > 50:  # Более 50% ошибок
                worker.status = WorkerStatus.UNHEALTHY
            elif worker.error_rate > 20 or worker.load_factor > 0.9:
                worker.status = WorkerStatus.DEGRADED
            else:
                worker.status = WorkerStatus.HEALTHY
            
            worker.last_health_check = datetime.now()
            
        except Exception as e:
            logger.warning(f"Health check failed for worker {worker.id}: {e}")
            worker.status = WorkerStatus.UNHEALTHY
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики балансировщика"""
        
        total_requests = self.request_stats['total_requests']
        success_rate = 0
        if total_requests > 0:
            success_rate = (self.request_stats['successful_requests'] / total_requests) * 100
        
        # Статистика воркеров
        worker_stats = {}
        total_connections = 0
        healthy_workers = 0
        
        for worker_id, worker in self.workers.items():
            worker_stats[worker_id] = {
                'status': worker.status.value,
                'endpoint': worker.endpoint,
                'connections': worker.current_connections,
                'max_connections': worker.max_connections,
                'load_factor': round(worker.load_factor, 3),
                'total_requests': worker.total_requests,
                'error_rate': round(worker.error_rate, 2),
                'avg_response_time': round(worker.avg_response_time * 1000, 2),  # в мс
                'weight': worker.weight,
                'last_health_check': worker.last_health_check.isoformat()
            }
            
            total_connections += worker.current_connections
            if worker.status == WorkerStatus.HEALTHY:
                healthy_workers += 1
        
        return {
            'strategy': self.strategy.value,
            'total_workers': len(self.workers),
            'healthy_workers': healthy_workers,
            'total_connections': total_connections,
            'total_requests': total_requests,
            'success_rate_percent': round(success_rate, 2),
            'active_sessions': len(self.session_affinity),
            'workers': worker_stats
        }
    
    def cleanup_sessions(self):
        """Очистка устаревших сессий"""
        current_time = datetime.now()
        sessions_to_remove = []
        
        # В реальной реализации нужно отслеживать время последнего доступа к сессии
        # Пока просто ограничиваем общее количество
        if len(self.session_affinity) > 10000:
            # Удаляем случайные сессии
            sessions_to_remove = random.sample(
                list(self.session_affinity.keys()), 
                len(self.session_affinity) - 8000
            )
        
        for session_id in sessions_to_remove:
            del self.session_affinity[session_id]
        
        if sessions_to_remove:
            logger.info(f"Очищено {len(sessions_to_remove)} устаревших сессий")

# Утилиты для интеграции

class TelegramLoadBalancer(LoadBalancer):
    """Специализированный балансировщик для Telegram бота"""
    
    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.CONSISTENT_HASHING):
        super().__init__(strategy)
        self.user_sessions: Dict[int, str] = {}  # user_id -> session_id
    
    def get_user_session(self, user_id: int) -> str:
        """Получение или создание сессии пользователя"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = f"user_{user_id}_{int(time.time())}"
        return self.user_sessions[user_id]
    
    async def handle_telegram_update(self, update_handler: Callable, 
                                   user_id: int, update_data: Dict) -> Any:
        """Обработка Telegram обновления"""
        session_id = self.get_user_session(user_id)
        routing_key = f"user_{user_id}"
        
        return await self.handle_request(
            update_handler, 
            session_id=session_id,
            routing_key=routing_key,
            update_data=update_data
        )

# Пример использования с webhook распределением

class WebhookDistributor:
    """Распределитель webhook запросов"""
    
    def __init__(self, load_balancer: LoadBalancer):
        self.load_balancer = load_balancer
    
    async def distribute_webhook(self, webhook_data: Dict) -> Dict[str, Any]:
        """Распределение webhook между воркерами"""
        
        # Извлекаем информацию о пользователе для роутинга
        user_id = None
        if 'message' in webhook_data:
            user_id = webhook_data['message'].get('from', {}).get('id')
        elif 'callback_query' in webhook_data:
            user_id = webhook_data['callback_query'].get('from', {}).get('id')
        
        routing_key = f"user_{user_id}" if user_id else "general"
        
        async def process_webhook(worker: WorkerNode, data: Dict):
            # Здесь должна быть логика отправки webhook на конкретный воркер
            # Например, HTTP POST запрос
            logger.info(f"Обрабатываем webhook на воркере {worker.id}")
            return {"status": "processed", "worker": worker.id}
        
        return await self.load_balancer.handle_request(
            process_webhook,
            routing_key=routing_key,
            data=webhook_data
        )

# Глобальный экземпляр
_global_load_balancer = None

def get_load_balancer() -> Optional[LoadBalancer]:
    """Получение глобального балансировщика"""
    return _global_load_balancer

def set_load_balancer(load_balancer: LoadBalancer):
    """Установка глобального балансировщика"""
    global _global_load_balancer
    _global_load_balancer = load_balancer

def create_worker_from_config(config: Dict[str, Any]) -> WorkerNode:
    """Создание воркера из конфигурации"""
    return WorkerNode(
        id=config['id'],
        host=config['host'],
        port=config['port'],
        weight=config.get('weight', 100),
        max_connections=config.get('max_connections', 1000),
        metadata=config.get('metadata', {})
    ) 