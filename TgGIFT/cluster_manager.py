#!/usr/bin/env python3
"""
Главный менеджер кластера для TgGIFT Bot
"""

import asyncio
import logging
import os
import signal
from typing import Dict, Any, Optional

from load_balancer import LoadBalancer, LoadBalancingStrategy, WorkerNode
from message_queue import create_telegram_message_queue, create_worker_pool
from worker_manager import WorkerManager, create_bot_worker_config, create_queue_worker_config

logger = logging.getLogger(__name__)

class ClusterManager:
    """Менеджер кластера TgGIFT Bot"""
    
    def __init__(self):
        # Load Balancer
        strategy = LoadBalancingStrategy(os.getenv('LOAD_BALANCER_STRATEGY', 'consistent_hashing'))
        self.load_balancer = LoadBalancer(strategy)
        
        # Message Queue
        redis_config = {
            'host': os.getenv('REDIS_QUEUE_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_QUEUE_PORT', 6379)),
            'db': int(os.getenv('REDIS_QUEUE_DB', 1)),
            'password': os.getenv('REDIS_QUEUE_PASSWORD') or None,
            'key_prefix': os.getenv('QUEUE_KEY_PREFIX', 'tggift:queue')
        }
        self.message_queue = create_telegram_message_queue(redis_config)
        
        # Worker Manager
        worker_config = {
            'max_workers': int(os.getenv('MAX_WORKERS', 8)),
            'auto_scale': os.getenv('AUTO_SCALE_WORKERS', 'true').lower() == 'true',
            'monitor_interval': int(os.getenv('WORKER_MONITOR_INTERVAL', 10))
        }
        self.worker_manager = WorkerManager(worker_config)
        
        # Queue workers
        self.queue_workers = []
        
        logger.info("Cluster Manager инициализирован")
    
    async def start_cluster(self):
        """Запуск кластера"""
        logger.info("🚀 Запуск кластера TgGIFT Bot")
        
        try:
            # Запускаем Worker Manager
            await self.worker_manager.start()
            
            # Добавляем конфигурации воркеров
            self._setup_workers()
            
            # Запускаем воркеров
            await self.worker_manager.start_all_workers()
            
            # Настраиваем Load Balancer
            self._setup_load_balancer()
            
            # Запускаем health checks
            await self.load_balancer.start_health_checks()
            
            # Создаем пул queue воркеров
            self.queue_workers = create_worker_pool([self.message_queue], worker_count=4)
            for worker in self.queue_workers:
                await worker.start()
            
            logger.info("✅ Кластер запущен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска кластера: {e}")
            await self.stop_cluster()
            raise
    
    async def stop_cluster(self):
        """Остановка кластера"""
        logger.info("🛑 Остановка кластера")
        
        try:
            # Останавливаем queue workers
            for worker in self.queue_workers:
                await worker.stop()
            
            # Останавливаем health checks
            await self.load_balancer.stop_health_checks()
            
            # Останавливаем worker manager
            await self.worker_manager.stop()
            
            logger.info("✅ Кластер остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки кластера: {e}")
    
    def _setup_workers(self):
        """Настройка воркеров"""
        min_workers = int(os.getenv('MIN_WORKERS_PER_TYPE', 2))
        
        # Bot handlers
        for i in range(min_workers):
            config = create_bot_worker_config(f"bot_handler_{i+1}")
            self.worker_manager.add_worker_config(config)
        
        # Queue workers
        for i in range(min_workers):
            config = create_queue_worker_config(f"queue_worker_{i+1}", ["telegram", "payments"])
            self.worker_manager.add_worker_config(config)
    
    def _setup_load_balancer(self):
        """Настройка балансировщика нагрузки"""
        # Добавляем воркеров в балансировщик
        for worker_id, worker_process in self.worker_manager.workers.items():
            if worker_process.config.worker_type.value == 'bot_handler':
                worker_node = WorkerNode(
                    id=worker_id,
                    host='localhost',
                    port=8000 + int(worker_id.split('_')[-1]),  # Динамические порты
                    weight=100,
                    max_connections=1000
                )
                self.load_balancer.add_worker(worker_node)
    
    def get_cluster_status(self):
        """Получение статуса кластера"""
        return {
            'load_balancer': self.load_balancer.get_stats(),
            'workers': self.worker_manager.get_all_workers_status(),
            'message_queue_stats': asyncio.create_task(self.message_queue.get_stats())
        }

# Глобальный экземпляр
_global_cluster_manager = None

def get_cluster_manager() -> Optional[ClusterManager]:
    """Получение глобального менеджера кластера"""
    return _global_cluster_manager

def set_cluster_manager(manager: ClusterManager):
    """Установка глобального менеджера кластера"""
    global _global_cluster_manager
    _global_cluster_manager = manager

# Главная функция запуска кластера
async def main():
    """Главная функция запуска кластера"""
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    cluster = ClusterManager()
    set_cluster_manager(cluster)
    
    # Обработчик сигналов для graceful shutdown
    stop_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, остановка кластера...")
        stop_event.set()
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        await cluster.start_cluster()
        
        logger.info("Кластер запущен, ожидание сигнала остановки...")
        await stop_event.wait()
        
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await cluster.stop_cluster()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nЗавершение работы...") 