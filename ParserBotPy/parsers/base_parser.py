import requests
import time
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from loguru import logger
from config.settings import settings
from utils.helpers import (
    extract_price_from_text, 
    clean_product_name, 
    get_random_user_agent, 
    safe_request_delay,
    validate_url
)

class BaseParser:
    """Базовый класс для парсинга сайтов"""
    
    def __init__(self, site_config: Dict[str, Any]):
        self.site_config = site_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def get_page_content(self, url: str) -> Optional[str]:
        """
        Получает содержимое страницы
        """
        if not validate_url(url):
            logger.error(f"Некорректный URL: {url}")
            return None
        
        for attempt in range(settings.MAX_RETRIES):
            try:
                logger.info(f"Парсинг {url} (попытка {attempt + 1})")
                
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Меняем User-Agent для следующего запроса
                self.session.headers['User-Agent'] = get_random_user_agent()
                
                return response.text
                
            except requests.RequestException as e:
                logger.warning(f"Ошибка при запросе {url}: {e}")
                if attempt < settings.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # Экспоненциальная задержка
                else:
                    logger.error(f"Не удалось получить страницу {url} после {settings.MAX_RETRIES} попыток")
                    return None
        
        return None
    
    def parse_product_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Парсит страницу товара
        """
        content = self.get_page_content(url)
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Извлекаем цену
            price_element = soup.select_one(self.site_config['price_selector'])
            if not price_element:
                logger.warning(f"Не найден элемент цены на {url}")
                return None
            
            price_text = price_element.get_text(strip=True)
            price = extract_price_from_text(price_text)
            
            if not price:
                logger.warning(f"Не удалось извлечь цену из текста: {price_text}")
                return None
            
            # Извлекаем название товара
            title_element = soup.select_one(self.site_config['title_selector'])
            title = ""
            if title_element:
                title = clean_product_name(title_element.get_text(strip=True))
            
            # Безопасная задержка между запросами
            safe_request_delay()
            
            return {
                'url': url,
                'title': title,
                'price': price,
                'site_name': self.site_config['name'],
                'parsed_at': time.time()
            }
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге {url}: {e}")
            return None
    
    def parse_multiple_products(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Парсит несколько страниц товаров
        """
        results = []
        
        for url in urls:
            result = self.parse_product_page(url)
            if result:
                results.append(result)
        
        logger.info(f"Успешно спарсено {len(results)} из {len(urls)} товаров")
        return results
    
    def get_product_urls(self, category_url: str) -> List[str]:
        """
        Получает список URL товаров с категории
        Переопределяется в наследниках для конкретных сайтов
        """
        logger.warning("Метод get_product_urls не реализован для данного парсера")
        return []
    
    def parse_category(self, category_url: str) -> List[Dict[str, Any]]:
        """
        Парсит всю категорию товаров
        """
        product_urls = self.get_product_urls(category_url)
        if not product_urls:
            logger.warning(f"Не найдено товаров в категории {category_url}")
            return []
        
        return self.parse_multiple_products(product_urls) 