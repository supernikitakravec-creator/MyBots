#!/usr/bin/env python3
"""
Главный файл приложения - Парсер цен для Telegram-бота
"""

import asyncio
import signal
import sys
from loguru import logger
from config.settings import settings
from parsers.base_parser import BaseParser
from parsers.webasyst_api import WebasystAPI
from bot.telegram_bot import TelegramBot
from utils.logger import setup_logger

class ParserManager:
    """Менеджер парсинга"""
    
    def __init__(self, webasyst_api):
        self.webasyst_api = webasyst_api
        self.parsers = {}
        self.last_parsing_time = None
        self.statistics = {
            'total_runs': 0,
            'total_products': 0,
            'total_updates': 0,
            'today_runs': 0,
            'today_products': 0,
            'today_updates': 0,
            'avg_time': 0
        }
        self._init_parsers()
    
    def _init_parsers(self):
        """Инициализация парсеров для каждого сайта"""
        for site_config in settings.TARGET_SITES:
            if site_config.get('enabled', True):
                parser = BaseParser(site_config)
                self.parsers[site_config['name']] = parser
                logger.info(f"Инициализирован парсер для {site_config['name']}")
    
    async def run_parsing(self) -> list:
        """Запуск парсинга всех сайтов"""
        import time
        start_time = time.time()
        
        logger.info("Запуск парсинга всех сайтов")
        results = []
        
        for site_name, parser in self.parsers.items():
            try:
                logger.info(f"Парсинг сайта: {site_name}")
                
                # Здесь нужно будет добавить URL товаров для парсинга
                # Пока используем заглушку
                product_urls = self._get_product_urls_for_site(site_name)
                
                if product_urls:
                    parsed_products = parser.parse_multiple_products(product_urls)
                    updated_prices = await self._update_prices(parsed_products)
                    
                    results.append({
                        'site_name': site_name,
                        'products': parsed_products,
                        'updated_prices': updated_prices
                    })
                    
                    logger.info(f"Сайт {site_name}: спарсено {len(parsed_products)} товаров, обновлено {updated_prices} цен")
                else:
                    logger.warning(f"Нет URL товаров для сайта {site_name}")
                    
            except Exception as e:
                logger.error(f"Ошибка при парсинге сайта {site_name}: {e}")
                results.append({
                    'site_name': site_name,
                    'error': str(e),
                    'products': [],
                    'updated_prices': 0
                })
        
        # Обновляем статистику
        self._update_statistics(len(results), sum(len(r.get('products', [])) for r in results), 
                               sum(r.get('updated_prices', 0) for r in results), time.time() - start_time)
        
        self.last_parsing_time = time.strftime("%H:%M:%S")
        
        return results
    
    def _get_product_urls_for_site(self, site_name: str) -> list:
        """
        Получает список URL товаров для парсинга
        В реальном приложении здесь будет логика получения URL из базы данных или конфигурации
        """
        # Заглушка - возвращаем тестовые URL
        # В реальном приложении здесь будет получение URL из базы данных
        test_urls = {
            'example_site_1': [
                'https://example1.com/product1',
                'https://example1.com/product2'
            ],
            'example_site_2': [
                'https://example2.com/product1',
                'https://example2.com/product2'
            ]
        }
        
        return test_urls.get(site_name, [])
    
    async def _update_prices(self, parsed_products: list) -> int:
        """Обновляет цены в Webasyst на основе спарсенных данных"""
        updated_count = 0
        
        for product in parsed_products:
            try:
                # Ищем соответствующий товар в Webasyst
                matching_product = await self.webasyst_api.find_matching_product(
                    product['title'], product['price']
                )
                
                if matching_product:
                    product_id = matching_product.get('id')
                    current_price = float(matching_product.get('price', 0))
                    
                    if product_id and current_price > 0:
                        # Рассчитываем новую цену
                        from utils.helpers import calculate_new_price
                        new_price = calculate_new_price(current_price, product['price'])
                        
                        # Обновляем цену если она изменилась
                        if abs(new_price - current_price) > 0.01:  # Минимальное изменение
                            success = await self.webasyst_api.update_product_price(product_id, new_price)
                            if success:
                                updated_count += 1
                                logger.info(f"Обновлена цена товара {product_id}: {current_price} -> {new_price}")
                
            except Exception as e:
                logger.error(f"Ошибка при обновлении цены для товара {product.get('title', 'Unknown')}: {e}")
        
        return updated_count
    
    def get_last_parsing_time(self) -> str:
        """Возвращает время последнего парсинга"""
        return self.last_parsing_time or "Не выполнялся"
    
    def is_auto_parsing_enabled(self) -> bool:
        """Проверяет, включен ли автоматический парсинг"""
        return True  # В реальном приложении это может быть настройка
    
    def get_statistics(self) -> dict:
        """Возвращает статистику работы"""
        return self.statistics.copy()
    
    def _update_statistics(self, runs: int, products: int, updates: int, time_taken: float):
        """Обновляет статистику"""
        self.statistics['total_runs'] += runs
        self.statistics['total_products'] += products
        self.statistics['total_updates'] += updates
        self.statistics['today_runs'] += runs
        self.statistics['today_products'] += products
        self.statistics['today_updates'] += updates
        
        # Обновляем среднее время
        if self.statistics['total_runs'] > 0:
            self.statistics['avg_time'] = (
                (self.statistics['avg_time'] * (self.statistics['total_runs'] - runs) + time_taken) / 
                self.statistics['total_runs']
            )

class Application:
    """Основной класс приложения"""
    
    def __init__(self):
        self.webasyst_api = None
        self.parser_manager = None
        self.telegram_bot = None
        self.running = False
    
    async def start(self):
        """Запуск приложения"""
        try:
            logger.info("Запуск приложения Парсер цен")
            
            # Инициализируем Webasyst API
            self.webasyst_api = WebasystAPI()
            logger.info("Webasyst API инициализирован")
            
            # Инициализируем менеджер парсинга
            self.parser_manager = ParserManager(self.webasyst_api)
            logger.info("Менеджер парсинга инициализирован")
            
            # Инициализируем Telegram-бота
            self.telegram_bot = TelegramBot(self.parser_manager, self.webasyst_api)
            logger.info("Telegram-бот инициализирован")
            
            # Запускаем бота
            self.running = True
            await self.telegram_bot.start()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске приложения: {e}")
            raise
    
    async def stop(self):
        """Остановка приложения"""
        logger.info("Остановка приложения")
        self.running = False
        
        if self.telegram_bot:
            await self.telegram_bot.stop()
        
        logger.info("Приложение остановлено")

async def main():
    """Главная функция"""
    app = Application()
    
    # Обработчик сигналов для корректного завершения
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, завершение работы...")
        asyncio.create_task(app.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)
    finally:
        await app.stop()

if __name__ == "__main__":
    # Настраиваем логирование
    setup_logger()
    
    # Запускаем приложение
    asyncio.run(main()) 