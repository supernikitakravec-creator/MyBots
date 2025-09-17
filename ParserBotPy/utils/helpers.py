import re
import random
import time
from typing import Optional, Dict, Any
from loguru import logger
from config.settings import settings

def extract_price_from_text(text: str) -> Optional[float]:
    """
    Извлекает цену из текста
    """
    if not text:
        return None
    
    # Убираем лишние символы
    text = text.strip()
    
    # Ищем числа с возможными разделителями
    price_patterns = [
        r'(\d+[\s.,]?\d*)\s*(?:руб|₽|р\.|рублей)',
        r'(\d+[\s.,]?\d*)\s*(?:USD|\$)',
        r'(\d+[\s.,]?\d*)\s*(?:EUR|€)',
        r'(\d+[\s.,]?\d*)'
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price_str = match.group(1)
            # Заменяем запятые на точки и убираем пробелы
            price_str = price_str.replace(',', '.').replace(' ', '')
            try:
                return float(price_str)
            except ValueError:
                continue
    
    return None

def clean_product_name(name: str) -> str:
    """
    Очищает название товара от лишних символов
    """
    if not name:
        return ""
    
    # Убираем лишние пробелы и символы
    name = re.sub(r'\s+', ' ', name.strip())
    name = re.sub(r'[^\w\s\-\.\(\)]', '', name)
    
    return name

def get_random_user_agent() -> str:
    """
    Возвращает случайный User-Agent
    """
    return random.choice(settings.USER_AGENTS)

def safe_request_delay():
    """
    Безопасная задержка между запросами
    """
    delay = settings.REQUEST_DELAY_SECONDS + random.uniform(0, 1)
    time.sleep(delay)

def calculate_new_price(current_price: float, competitor_price: float) -> float:
    """
    Рассчитывает новую цену на основе цены конкурента
    """
    if competitor_price <= 0:
        return current_price
    
    # Минимальная наценка
    min_price = competitor_price * (1 + settings.MIN_PRICE_MARGIN)
    
    # Максимальное снижение цены
    max_drop = current_price * (1 - settings.MAX_PRICE_DROP)
    
    # Выбираем лучшую цену
    new_price = max(min_price, max_drop)
    
    logger.info(f"Текущая цена: {current_price}, цена конкурента: {competitor_price}, новая цена: {new_price}")
    
    return round(new_price, 2)

def format_price_message(site_name: str, product_name: str, old_price: float, new_price: float) -> str:
    """
    Форматирует сообщение об изменении цены
    """
    change_percent = ((new_price - old_price) / old_price) * 100
    change_symbol = "📈" if change_percent > 0 else "📉" if change_percent < 0 else "➡️"
    
    return (
        f"{change_symbol} <b>Изменение цены</b>\n\n"
        f"🏪 <b>Сайт:</b> {site_name}\n"
        f"📦 <b>Товар:</b> {product_name}\n"
        f"💰 <b>Старая цена:</b> {old_price} ₽\n"
        f"💵 <b>Новая цена:</b> {new_price} ₽\n"
        f"📊 <b>Изменение:</b> {change_percent:+.1f}%"
    )

def validate_url(url: str) -> bool:
    """
    Проверяет корректность URL
    """
    url_pattern = re.compile(
        r'^https?://'  # http:// или https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # домен
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # порт
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url)) 