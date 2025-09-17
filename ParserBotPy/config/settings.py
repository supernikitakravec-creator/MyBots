import os
from typing import List, Dict, Any
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class Settings:
    """Настройки приложения"""
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ADMIN_ID: str = os.getenv("TELEGRAM_ADMIN_ID", "")
    
    # Webasyst API
    WEBASYST_API_URL: str = os.getenv("WEBASYST_API_URL", "https://your-shop.webasyst.net/api/")
    WEBASYST_API_TOKEN: str = os.getenv("WEBASYST_API_TOKEN", "")
    WEBASYST_SHOP_ID: str = os.getenv("WEBASYST_SHOP_ID", "")
    
    # Парсинг
    PARSING_INTERVAL_MINUTES: int = int(os.getenv("PARSING_INTERVAL_MINUTES", "30"))
    REQUEST_DELAY_SECONDS: float = float(os.getenv("REQUEST_DELAY_SECONDS", "2.0"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    
    # User-Agents для парсинга
    USER_AGENTS: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ]
    
    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/parser_bot.log")
    
    # Настройки цен
    MIN_PRICE_MARGIN: float = float(os.getenv("MIN_PRICE_MARGIN", "0.05"))  # 5% минимальная наценка
    MAX_PRICE_DROP: float = float(os.getenv("MAX_PRICE_DROP", "0.20"))  # Максимальное снижение цены 20%
    
    # Сайты для парсинга (пример)
    TARGET_SITES: List[Dict[str, Any]] = [
        {
            "name": "example_site_1",
            "url": "https://example1.com",
            "price_selector": ".price",
            "title_selector": ".product-title",
            "enabled": True
        },
        {
            "name": "example_site_2", 
            "url": "https://example2.com",
            "price_selector": "[data-price]",
            "title_selector": "h1",
            "enabled": True
        }
    ]

# Создаем экземпляр настроек
settings = Settings() 