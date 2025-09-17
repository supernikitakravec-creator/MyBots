import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# Параметры ЮКассы
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID', '')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY', '')

# Режимы
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'
PAYMENT_DEMO_MODE = os.getenv('PAYMENT_DEMO_MODE', 'false').lower() == 'true'

# Цены подписок (месяц: цена)
SUBSCRIPTION_PRICES = {
    1: int(os.getenv('SUBSCRIPTION_PRICE_MONTH', '2990'))
}

# Простейшая валидация, чтобы не запускать с пустыми секретами
def validate_config() -> bool:
    errors = []
    if not BOT_TOKEN:
        errors.append('BOT_TOKEN is not set')
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        errors.append('YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY are not set')
    if errors:
        for e in errors:
            print(f"[config] {e}")
        return False
    return True

if __name__ == '__main__':
    # Для локальной проверки
    print('Config valid:', validate_config())