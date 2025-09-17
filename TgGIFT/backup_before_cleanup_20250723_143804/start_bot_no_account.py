#!/usr/bin/env python3
"""
Запуск TgGIFT Star Bot без управляемого аккаунта
(для случаев когда SMS авторизация не работает)
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/bot_no_account.log')
    ]
)
logger = logging.getLogger(__name__)

class BotRunnerNoAccount:
    """Запуск бота без управляемого аккаунта"""
    
    def __init__(self):
        self.bot = None
        self.gift_monitor = None
        self.shutdown_event = asyncio.Event()
        
    async def start_bot(self):
        """Запуск основного бота"""
        try:
            from main_bot import TgGiftBot
            
            self.bot = TgGiftBot()
            await self.bot.start()
            
            logger.info("✅ Telegram бот запущен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            return False
    
    async def start_gift_monitor(self):
        """Запуск мониторинга подарков (без автопокупки)"""
        try:
            from gift_monitor import GiftMonitor
            
            # Создаем мониторинг без управляемого аккаунта
            self.gift_monitor = GiftMonitor(account_manager=None)
            
            # Запускаем только мониторинг (без автопокупки)
            monitor_task = asyncio.create_task(self.gift_monitor.start_monitoring())
            
            logger.info("✅ Мониторинг подарков запущен (без автопокупки)")
            return monitor_task
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска мониторинга: {e}")
            return None
    
    async def setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        def signal_handler(signum, frame):
            logger.info(f"Получен сигнал {signum}, завершение работы...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def run(self):
        """Главный цикл работы"""
        logger.info("🚀 Запуск TgGIFT Star Bot (без управляемого аккаунта)")
        logger.info("⚠️ Автопокупка подарков отключена")
        
        # Настройка обработчиков сигналов
        await self.setup_signal_handlers()
        
        # Запуск основного бота
        if not await self.start_bot():
            logger.error("❌ Не удалось запустить бота")
            return
        
        # Запуск мониторинга
        monitor_task = await self.start_gift_monitor()
        
        # Создаем список задач
        tasks = []
        if monitor_task:
            tasks.append(monitor_task)
        
        logger.info("✅ Все системы запущены")
        logger.info("📋 Доступные функции:")
        logger.info("  - Telegram бот: @GIFT_SCROLL_bot")
        logger.info("  - Мониторинг подарков: ✅")
        logger.info("  - Пополнение баланса: ✅")
        logger.info("  - Система подписок: ✅")
        logger.info("  - Автопокупка: ❌ (отключена)")
        logger.info("  - Отправка подарков: ❌ (отключена)")
        
        try:
            # Ждем сигнала завершения
            await self.shutdown_event.wait()
            
        except KeyboardInterrupt:
            logger.info("Получен сигнал прерывания")
        
        finally:
            logger.info("🔄 Завершение работы...")
            
            # Отменяем задачи
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Останавливаем бота
            if self.bot:
                await self.bot.stop()
            
            logger.info("✅ Бот остановлен")

async def main():
    """Точка входа"""
    runner = BotRunnerNoAccount()
    await runner.run()

if __name__ == "__main__":
    # Создаем директорию для логов
    import os
    os.makedirs('logs', exist_ok=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа завершена пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1) 