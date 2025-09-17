#!/usr/bin/env python3
"""
Message Queue - система очередей сообщений для TgGIFT Bot
"""

import logging
import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import pickle
import redis.asyncio as redis
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class MessagePriority(Enum):
    """Приоритеты сообщений"""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20

class MessageStatus(Enum):
    """Статусы сообщений"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"

@dataclass
class QueueMessage:
    """Сообщение в очереди"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    queue_name: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 300.0  # 5 минут
    error_message: Optional[str] = None
    worker_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Проверка истечения времени обработки"""
        if not self.started_at:
            return False
        return (datetime.now() - self.started_at).total_seconds() > self.timeout
    
    @property
    def should_retry(self) -> bool:
        """Проверка возможности повторной попытки"""
        return self.retry_count < self.max_retries and self.status == MessageStatus.FAILED
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        data = asdict(self)
        # Конвертируем datetime в ISO строки
        for field_name in ['created_at', 'scheduled_at', 'started_at', 'completed_at']:
            if data[field_name]:
                data[field_name] = data[field_name].isoformat()
        # Конвертируем enum в значения
        data['priority'] = data['priority'].value
        data['status'] = data['status'].value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueMessage':
        """Создание из словаря"""
        # Конвертируем ISO строки в datetime
        for field_name in ['created_at', 'scheduled_at', 'started_at', 'completed_at']:
            if data.get(field_name):
                data[field_name] = datetime.fromisoformat(data[field_name])
        
        # Конвертируем значения в enum
        if 'priority' in data:
            data['priority'] = MessagePriority(data['priority'])
        if 'status' in data:
            data['status'] = MessageStatus(data['status'])
        
        return cls(**data)

class MessageQueueBackend(ABC):
    """Абстрактный бэкенд для очереди сообщений"""
    
    @abstractmethod
    async def enqueue(self, message: QueueMessage) -> bool:
        """Добавление сообщения в очередь"""
        pass
    
    @abstractmethod
    async def dequeue(self, queue_name: str, worker_id: str) -> Optional[QueueMessage]:
        """Извлечение сообщения из очереди"""
        pass
    
    @abstractmethod
    async def ack(self, message_id: str) -> bool:
        """Подтверждение обработки сообщения"""
        pass
    
    @abstractmethod
    async def nack(self, message_id: str, error: str = None) -> bool:
        """Отклонение сообщения"""
        pass
    
    @abstractmethod
    async def get_queue_stats(self, queue_name: str) -> Dict[str, Any]:
        """Получение статистики очереди"""
        pass

class RedisMessageQueueBackend(MessageQueueBackend):
    """Redis бэкенд для очередей сообщений"""
    
    def __init__(self, redis_config: Dict[str, Any]):
        self.redis_config = redis_config
        self.redis_client = None
        self.key_prefix = redis_config.get('key_prefix', 'tggift:queue')
        
    async def connect(self):
        """Подключение к Redis"""
        if not self.redis_client:
            self.redis_client = redis.Redis(
                host=self.redis_config.get('host', 'localhost'),
                port=self.redis_config.get('port', 6379),
                db=self.redis_config.get('db', 0),
                password=self.redis_config.get('password'),
                decode_responses=False  # Работаем с байтами для pickle
            )
        
        try:
            await self.redis_client.ping()
            logger.info("Подключение к Redis для очередей успешно")
        except Exception as e:
            logger.error(f"Ошибка подключения к Redis: {e}")
            raise
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
    
    def _queue_key(self, queue_name: str) -> str:
        """Ключ для очереди"""
        return f"{self.key_prefix}:{queue_name}"
    
    def _priority_queue_key(self, queue_name: str, priority: MessagePriority) -> str:
        """Ключ для приоритетной очереди"""
        return f"{self.key_prefix}:{queue_name}:p{priority.value}"
    
    def _processing_key(self, queue_name: str) -> str:
        """Ключ для обрабатываемых сообщений"""
        return f"{self.key_prefix}:{queue_name}:processing"
    
    def _message_key(self, message_id: str) -> str:
        """Ключ для сообщения"""
        return f"{self.key_prefix}:message:{message_id}"
    
    def _scheduled_key(self) -> str:
        """Ключ для отложенных сообщений"""
        return f"{self.key_prefix}:scheduled"
    
    async def enqueue(self, message: QueueMessage) -> bool:
        """Добавление сообщения в очередь"""
        try:
            if not self.redis_client:
                await self.connect()
            
            # Сериализуем сообщение
            message_data = pickle.dumps(message.to_dict())
            
            # Сохраняем сообщение
            message_key = self._message_key(message.id)
            await self.redis_client.setex(
                message_key, 
                int(message.timeout + 3600),  # TTL с запасом
                message_data
            )
            
            # Если сообщение отложенное
            if message.scheduled_at and message.scheduled_at > datetime.now():
                scheduled_key = self._scheduled_key()
                await self.redis_client.zadd(
                    scheduled_key,
                    {message.id: message.scheduled_at.timestamp()}
                )
            else:
                # Добавляем в приоритетную очередь
                priority_queue_key = self._priority_queue_key(message.queue_name, message.priority)
                await self.redis_client.lpush(priority_queue_key, message.id)
            
            logger.debug(f"Сообщение {message.id} добавлено в очередь {message.queue_name}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления сообщения в очередь: {e}")
            return False
    
    async def dequeue(self, queue_name: str, worker_id: str) -> Optional[QueueMessage]:
        """Извлечение сообщения из очереди"""
        try:
            if not self.redis_client:
                await self.connect()
            
            # Сначала обрабатываем отложенные сообщения
            await self._process_scheduled_messages()
            
            # Пытаемся получить сообщение по приоритетам (от высокого к низкому)
            priorities = sorted(MessagePriority, key=lambda p: p.value, reverse=True)
            
            for priority in priorities:
                priority_queue_key = self._priority_queue_key(queue_name, priority)
                message_id = await self.redis_client.rpop(priority_queue_key)
                
                if message_id:
                    message_id = message_id.decode('utf-8')
                    
                    # Получаем данные сообщения
                    message_key = self._message_key(message_id)
                    message_data = await self.redis_client.get(message_key)
                    
                    if message_data:
                        try:
                            message_dict = pickle.loads(message_data)
                            message = QueueMessage.from_dict(message_dict)
                            
                            # Обновляем статус
                            message.status = MessageStatus.PROCESSING
                            message.started_at = datetime.now()
                            message.worker_id = worker_id
                            
                            # Сохраняем обновленное сообщение
                            updated_data = pickle.dumps(message.to_dict())
                            await self.redis_client.setex(message_key, int(message.timeout + 3600), updated_data)
                            
                            # Добавляем в список обрабатываемых
                            processing_key = self._processing_key(queue_name)
                            await self.redis_client.zadd(
                                processing_key,
                                {message_id: time.time()}
                            )
                            
                            return message
                            
                        except Exception as e:
                            logger.error(f"Ошибка десериализации сообщения {message_id}: {e}")
                            # Удаляем поврежденное сообщение
                            await self.redis_client.delete(message_key)
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка извлечения сообщения из очереди: {e}")
            return None
    
    async def ack(self, message_id: str) -> bool:
        """Подтверждение обработки сообщения"""
        try:
            if not self.redis_client:
                await self.connect()
            
            # Получаем сообщение для определения очереди
            message_key = self._message_key(message_id)
            message_data = await self.redis_client.get(message_key)
            
            if message_data:
                message_dict = pickle.loads(message_data)
                message = QueueMessage.from_dict(message_dict)
                
                # Обновляем статус
                message.status = MessageStatus.COMPLETED
                message.completed_at = datetime.now()
                
                # Сохраняем финальное состояние
                final_data = pickle.dumps(message.to_dict())
                await self.redis_client.setex(message_key, 3600, final_data)  # Храним час для статистики
                
                # Удаляем из обрабатываемых
                processing_key = self._processing_key(message.queue_name)
                await self.redis_client.zrem(processing_key, message_id)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка подтверждения сообщения {message_id}: {e}")
            return False
    
    async def nack(self, message_id: str, error: str = None) -> bool:
        """Отклонение сообщения"""
        try:
            if not self.redis_client:
                await self.connect()
            
            message_key = self._message_key(message_id)
            message_data = await self.redis_client.get(message_key)
            
            if message_data:
                message_dict = pickle.loads(message_data)
                message = QueueMessage.from_dict(message_dict)
                
                # Обновляем информацию об ошибке
                message.retry_count += 1
                message.error_message = error
                message.worker_id = None
                
                # Определяем следующий статус
                if message.should_retry:
                    message.status = MessageStatus.RETRYING
                    # Возвращаем в очередь с задержкой (exponential backoff)
                    delay = min(300, 2 ** message.retry_count)  # Максимум 5 минут
                    message.scheduled_at = datetime.now() + timedelta(seconds=delay)
                    
                    # Добавляем в отложенные
                    scheduled_key = self._scheduled_key()
                    await self.redis_client.zadd(
                        scheduled_key,
                        {message_id: message.scheduled_at.timestamp()}
                    )
                else:
                    message.status = MessageStatus.DEAD
                    message.completed_at = datetime.now()
                
                # Сохраняем обновленное сообщение
                updated_data = pickle.dumps(message.to_dict())
                await self.redis_client.setex(message_key, 3600, updated_data)
                
                # Удаляем из обрабатываемых
                processing_key = self._processing_key(message.queue_name)
                await self.redis_client.zrem(processing_key, message_id)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка отклонения сообщения {message_id}: {e}")
            return False
    
    async def _process_scheduled_messages(self):
        """Обработка отложенных сообщений"""
        try:
            scheduled_key = self._scheduled_key()
            current_time = time.time()
            
            # Получаем сообщения, время которых пришло
            ready_messages = await self.redis_client.zrangebyscore(
                scheduled_key, 0, current_time, withscores=True
            )
            
            for message_id_bytes, score in ready_messages:
                message_id = message_id_bytes.decode('utf-8')
                
                # Получаем данные сообщения
                message_key = self._message_key(message_id)
                message_data = await self.redis_client.get(message_key)
                
                if message_data:
                    message_dict = pickle.loads(message_data)
                    message = QueueMessage.from_dict(message_dict)
                    
                    # Возвращаем в обычную очередь
                    priority_queue_key = self._priority_queue_key(message.queue_name, message.priority)
                    await self.redis_client.lpush(priority_queue_key, message_id)
                    
                    # Удаляем из отложенных
                    await self.redis_client.zrem(scheduled_key, message_id)
                    
                    # Обновляем статус
                    message.status = MessageStatus.PENDING
                    message.scheduled_at = None
                    
                    updated_data = pickle.dumps(message.to_dict())
                    await self.redis_client.setex(message_key, int(message.timeout + 3600), updated_data)
            
        except Exception as e:
            logger.error(f"Ошибка обработки отложенных сообщений: {e}")
    
    async def get_queue_stats(self, queue_name: str) -> Dict[str, Any]:
        """Получение статистики очереди"""
        try:
            if not self.redis_client:
                await self.connect()
            
            stats = {
                'queue_name': queue_name,
                'pending_by_priority': {},
                'processing': 0,
                'scheduled': 0
            }
            
            # Считаем сообщения по приоритетам
            for priority in MessagePriority:
                priority_queue_key = self._priority_queue_key(queue_name, priority)
                count = await self.redis_client.llen(priority_queue_key)
                stats['pending_by_priority'][priority.name] = count
            
            # Считаем обрабатываемые сообщения
            processing_key = self._processing_key(queue_name)
            stats['processing'] = await self.redis_client.zcard(processing_key)
            
            # Считаем отложенные (только для этой очереди)
            scheduled_key = self._scheduled_key()
            all_scheduled = await self.redis_client.zrange(scheduled_key, 0, -1)
            queue_scheduled = 0
            
            for message_id_bytes in all_scheduled:
                message_id = message_id_bytes.decode('utf-8')
                message_key = self._message_key(message_id)
                message_data = await self.redis_client.get(message_key)
                
                if message_data:
                    try:
                        message_dict = pickle.loads(message_data)
                        if message_dict.get('queue_name') == queue_name:
                            queue_scheduled += 1
                    except:
                        pass
            
            stats['scheduled'] = queue_scheduled
            stats['total_pending'] = sum(stats['pending_by_priority'].values())
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики очереди: {e}")
            return {}

class MessageQueue:
    """Основной класс очереди сообщений"""
    
    def __init__(self, backend: MessageQueueBackend, name: str = "default"):
        self.backend = backend
        self.name = name
        self.handlers: Dict[str, Callable] = {}
        self.middleware: List[Callable] = []
        
        logger.info(f"Очередь сообщений '{name}' инициализирована")
    
    def register_handler(self, message_type: str, handler: Callable):
        """Регистрация обработчика сообщений"""
        self.handlers[message_type] = handler
        logger.info(f"Зарегистрирован обработчик для типа '{message_type}'")
    
    def add_middleware(self, middleware: Callable):
        """Добавление middleware"""
        self.middleware.append(middleware)
        logger.info("Добавлен middleware")
    
    async def enqueue(self, message_type: str, payload: Dict[str, Any],
                     priority: MessagePriority = MessagePriority.NORMAL,
                     delay: Optional[timedelta] = None,
                     max_retries: int = 3,
                     timeout: float = 300.0) -> str:
        """Добавление сообщения в очередь"""
        
        message = QueueMessage(
            queue_name=self.name,
            payload={
                'type': message_type,
                'data': payload
            },
            priority=priority,
            scheduled_at=datetime.now() + delay if delay else None,
            max_retries=max_retries,
            timeout=timeout
        )
        
        success = await self.backend.enqueue(message)
        if success:
            logger.info(f"Сообщение {message.id} типа '{message_type}' добавлено в очередь")
            return message.id
        else:
            raise Exception("Не удалось добавить сообщение в очередь")
    
    async def process_messages(self, worker_id: str, max_messages: int = 100):
        """Обработка сообщений из очереди"""
        processed = 0
        
        while processed < max_messages:
            message = await self.backend.dequeue(self.name, worker_id)
            if not message:
                break
            
            try:
                # Проверяем таймаут
                if message.is_expired:
                    await self.backend.nack(message.id, "Message timeout")
                    continue
                
                # Извлекаем тип сообщения
                message_type = message.payload.get('type')
                if not message_type or message_type not in self.handlers:
                    await self.backend.nack(message.id, f"No handler for message type: {message_type}")
                    continue
                
                # Выполняем middleware
                for middleware in self.middleware:
                    try:
                        if asyncio.iscoroutinefunction(middleware):
                            await middleware(message)
                        else:
                            middleware(message)
                    except Exception as e:
                        logger.error(f"Ошибка middleware: {e}")
                
                # Выполняем обработчик
                handler = self.handlers[message_type]
                
                if asyncio.iscoroutinefunction(handler):
                    await handler(message.payload.get('data', {}), message)
                else:
                    handler(message.payload.get('data', {}), message)
                
                # Подтверждаем обработку
                await self.backend.ack(message.id)
                processed += 1
                
                logger.debug(f"Сообщение {message.id} обработано успешно")
                
            except Exception as e:
                logger.error(f"Ошибка обработки сообщения {message.id}: {e}")
                await self.backend.nack(message.id, str(e))
        
        return processed
    
    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики очереди"""
        return await self.backend.get_stats(self.name)

class MessageQueueWorker:
    """Воркер для обработки очередей"""
    
    def __init__(self, queues: List[MessageQueue], worker_id: str = None):
        self.queues = queues
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.running = False
        self.task = None
        
        logger.info(f"Воркер {self.worker_id} инициализирован для {len(queues)} очередей")
    
    async def start(self, poll_interval: float = 1.0):
        """Запуск воркера"""
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._worker_loop(poll_interval))
        logger.info(f"Воркер {self.worker_id} запущен")
    
    async def stop(self):
        """Остановка воркера"""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"Воркер {self.worker_id} остановлен")
    
    async def _worker_loop(self, poll_interval: float):
        """Основной цикл воркера"""
        while self.running:
            try:
                total_processed = 0
                
                # Обрабатываем все очереди
                for queue in self.queues:
                    processed = await queue.process_messages(self.worker_id, max_messages=10)
                    total_processed += processed
                
                # Если ничего не обработали, ждем
                if total_processed == 0:
                    await asyncio.sleep(poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле воркера {self.worker_id}: {e}")
                await asyncio.sleep(poll_interval)

# Утилиты для интеграции

def create_telegram_message_queue(redis_config: Dict[str, Any]) -> MessageQueue:
    """Создание очереди для Telegram сообщений"""
    backend = RedisMessageQueueBackend(redis_config)
    queue = MessageQueue(backend, "telegram")
    
    # Регистрируем стандартные обработчики
    @queue.register_handler("user_message")
    async def handle_user_message(data: Dict[str, Any], message: QueueMessage):
        logger.info(f"Обработка сообщения пользователя: {data}")
    
    @queue.register_handler("payment_notification")
    async def handle_payment_notification(data: Dict[str, Any], message: QueueMessage):
        logger.info(f"Обработка уведомления о платеже: {data}")
    
    @queue.register_handler("subscription_renewal")
    async def handle_subscription_renewal(data: Dict[str, Any], message: QueueMessage):
        logger.info(f"Обработка продления подписки: {data}")
    
    return queue

# Middleware для логирования
async def logging_middleware(message: QueueMessage):
    """Middleware для логирования сообщений"""
    logger.info(f"Обработка сообщения {message.id} типа {message.payload.get('type')}")

# Middleware для метрик
async def metrics_middleware(message: QueueMessage):
    """Middleware для сбора метрик"""
    try:
        from metrics_collector import metrics_collector
        metrics_collector.increment(f"queue.{message.queue_name}.processed")
        metrics_collector.timer(f"queue.{message.queue_name}.processing_time", 
                              (datetime.now() - message.started_at).total_seconds())
    except ImportError:
        pass

# Глобальные экземпляры
_global_message_queues: Dict[str, MessageQueue] = {}
_global_workers: List[MessageQueueWorker] = []

def get_message_queue(name: str) -> Optional[MessageQueue]:
    """Получение очереди по имени"""
    return _global_message_queues.get(name)

def register_message_queue(queue: MessageQueue):
    """Регистрация очереди"""
    _global_message_queues[queue.name] = queue

def create_worker_pool(queues: List[MessageQueue], worker_count: int = 4) -> List[MessageQueueWorker]:
    """Создание пула воркеров"""
    workers = []
    for i in range(worker_count):
        worker = MessageQueueWorker(queues, f"worker_{i+1}")
        workers.append(worker)
    
    _global_workers.extend(workers)
    return workers 