#!/usr/bin/env python3
"""
Production-ready скрипт запуска TgGIFT Star Bot
"""

import os
import sys
import signal
import logging
import asyncio
from datetime import datetime
from config import get_config_summary, HEALTH_CHECK_SETTINGS, SHUTDOWN_SETTINGS
from main_bot import TgGiftBot

# Настройка кодировки для Windows - исправленная версия
if sys.platform == "win32":
    # Устанавливаем кодировку для консоли Windows
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Альтернативный способ для Windows
    try:
        import locale
        locale.setlocale(locale.LC_ALL, '')
    except Exception:
        pass  # Игнорируем ошибки установки локали

# Настройка логирования для запуска с исправлением для Windows
if sys.platform == "win32":
    # Создаем handler для Windows
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    # Настраиваем root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        force=True
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

logger = logging.getLogger(__name__)

class BotRunner:
    """Класс для управления запуском бота"""
    
    def __init__(self):
        self.bot = None
        self.is_running = False
        self.shutdown_requested = False
        
    def signal_handler(self, signum, frame):
        """Обработчик сигналов для graceful shutdown"""
        logger.info(f"Получен сигнал {signum}, начинаем graceful shutdown...")
        self.shutdown_requested = True
        
        if self.bot:
            asyncio.create_task(self._graceful_shutdown())
    
    async def _graceful_shutdown(self):
        """Graceful shutdown бота"""
        try:
            logger.info("Начинаем graceful shutdown...")
            
            # Останавливаем бота
            if self.bot:
                try:
                    # Останавливаем updater
                    if hasattr(self.bot.application, 'updater') and self.bot.application.updater:
                        await self.bot.application.updater.stop()
                        logger.info("Updater остановлен")
                except Exception as e:
                    logger.error(f"Ошибка остановки updater: {e}")
                
                try:
                    await self.bot.application.stop()
                    logger.info("Приложение остановлено")
                except Exception as e:
                    logger.error(f"Ошибка остановки приложения: {e}")
                
                try:
                    await self.bot.application.shutdown()
                    logger.info("Приложение завершено")
                except Exception as e:
                    logger.error(f"Ошибка shutdown приложения: {e}")
                
                # Ждем завершения фоновых задач
                try:
                    await self.bot._shutdown_background_tasks()
                except Exception as e:
                    logger.error(f"Ошибка остановки фоновых задач: {e}")
            
            logger.info("Graceful shutdown завершен")
            
        except Exception as e:
            logger.error(f"Ошибка при graceful shutdown: {e}")
        finally:
            self.is_running = False
    
    def check_environment(self):
        """Проверка окружения перед запуском"""
        logger.info("Проверка окружения...")
        
        # Проверяем конфигурацию
        config_summary = get_config_summary()
        
        if not config_summary['bot_token_set']:
            logger.error("BOT_TOKEN не установлен!")
            return False
        
        logger.info("Конфигурация корректна")
        
        # Проверяем доступность файлов
        required_files = ['main_bot.py', 'config.py', 'database.py']
        for file in required_files:
            if not os.path.exists(file):
                logger.error(f"Файл {file} не найден!")
                return False
        
        logger.info("Все необходимые файлы найдены")
        
        # Проверяем права на запись в директорию
        try:
            test_file = 'test_write.tmp'
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            logger.error(f"Нет прав на запись в директорию: {e}")
            return False
        
        logger.info("Права на запись в директорию есть")
        
        return True
    
    async def health_check(self):
        """Проверка здоровья системы"""
        try:
            if not self.bot:
                return False
            
            # Проверяем подключение к базе данных
            stats = self.bot.db_manager.get_database_stats()
            if not stats:
                logger.warning("Не удалось получить статистику БД")
                return False
            
            # Проверяем подключение к Telegram Bot API
            try:
                await self.bot.application.bot.get_me()
            except Exception as e:
                logger.warning(f"Проблема с подключением к Telegram Bot API: {e}")
                return False
            
            logger.info("Health check пройден")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка health check: {e}")
            return False
    
    async def run_health_monitor(self):
        """Мониторинг здоровья системы"""
        if not HEALTH_CHECK_SETTINGS['enabled']:
            return
        
        logger.info("Запуск мониторинга здоровья...")
        
        while self.is_running and not self.shutdown_requested:
            try:
                await asyncio.sleep(HEALTH_CHECK_SETTINGS['interval'])
                
                if not await self.health_check():
                    logger.warning("Health check не пройден")
                    
            except asyncio.CancelledError:
                logger.info("Мониторинг здоровья отменен")
                break
            except Exception as e:
                logger.error(f"Ошибка мониторинга здоровья: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повтором
    
    async def start_bot(self):
        """Запуск бота"""
        try:
            logger.info("Запуск TgGIFT Star Bot...")
            
            # Создаем экземпляр бота
            self.bot = TgGiftBot()
            
            # Запускаем мониторинг здоровья в фоне
            if HEALTH_CHECK_SETTINGS['enabled']:
                health_task = asyncio.create_task(self.run_health_monitor())
                self.bot._add_background_task(health_task)
            
            # Запускаем бота
            await self.bot.run()
            
        except Exception as e:
            logger.error(f"Критическая ошибка запуска бота: {e}")
            raise
    
    def run(self):
        """Основной метод запуска"""
        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Проверяем окружение
        if not self.check_environment():
            logger.error("Проверка окружения не пройдена")
            sys.exit(1)
        
        # Запускаем бота
        try:
            self.is_running = True
            
            # Универсальный запуск event loop для Windows
            if sys.platform == "win32":
                # Для Windows используем специальную обработку
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            try:
                asyncio.run(self.start_bot())
            except RuntimeError as e:
                if "already running" in str(e):
                    # Если event loop уже запущен, используем его
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Создаем задачу и ждем завершения
                        task = loop.create_task(self.start_bot())
                        loop.run_until_complete(task)
                    else:
                        # Запускаем loop
                        loop.run_until_complete(self.start_bot())
                else:
                    logger.error(f"Критическая ошибка event loop: {e}")
                    raise
            except KeyboardInterrupt:
                logger.info("Получен сигнал прерывания")
                self.shutdown_requested = True
            except Exception as e:
                logger.error(f"Критическая ошибка: {e}")
                raise
                
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            sys.exit(1)
        finally:
            self.is_running = False
            logger.info("Бот завершен")

def main():
    """Главная функция"""
    print("=" * 50)
    print("TgGIFT Star Bot - Production Launcher")
    print("=" * 50)
    print(f"Запуск: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Показываем конфигурацию
    config_summary = get_config_summary()
    print("Конфигурация:")
    for key, value in config_summary.items():
        print(f"  {key}: {value}")
    print()
    
    # Запускаем бота
    runner = BotRunner()
    runner.run()

if __name__ == "__main__":
    main() 