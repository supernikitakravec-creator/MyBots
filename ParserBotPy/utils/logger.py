import os
from loguru import logger
from config.settings import settings

def setup_logger():
    """Настройка логирования"""
    
    # Создаем директорию для логов если её нет
    log_dir = os.path.dirname(settings.LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Удаляем стандартный обработчик
    logger.remove()
    
    # Добавляем обработчик для файла
    logger.add(
        settings.LOG_FILE,
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        rotation="1 day",
        retention="7 days",
        compression="zip"
    )
    
    # Добавляем обработчик для консоли
    logger.add(
        lambda msg: print(msg, end=""),
        level=settings.LOG_LEVEL,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    return logger

# Инициализируем логгер
setup_logger() 