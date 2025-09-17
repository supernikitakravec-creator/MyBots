# Быстрое развертывание TgGIFT Bot

## 🔧 Исправленные проблемы

✅ **Исправлены зависимости в requirements.txt:**
- Удалены встроенные модули (sqlite3, base64)
- Обновлена версия cryptography до 42.0.8
- Добавлены asyncpg==0.29.0 и yookassa==3.0.0

✅ **Добавлены PostgreSQL переменные окружения в docker-compose.yml**

✅ **Добавлен метод get_pending_payments в database_postgres.py**

✅ **Исправлен healthcheck для PostgreSQL**

✅ **Создан скрипт clear_webhook.py для очистки Telegram webhook**

✅ **Создан полный env_example.txt на основе production версии**

## 📋 Предварительные требования

1. **Docker и Docker Compose** установлены на сервере
2. **Telegram Bot Token** (получите у @BotFather)
3. **Telegram API данные** (api_id, api_hash от https://my.telegram.org)
4. **TON кошелек** для приема платежей
5. **Депозитный Telegram аккаунт** для покупки подарков

## 🚀 Шаги развертывания

### 1. Подготовка файлов
```bash
# Скопируйте файлы проекта на сервер
cd /opt/tggift

# Создайте .env файл на основе примера
cp env_example.txt .env
```

### 2. Настройка переменных окружения
Отредактируйте `.env` файл и обязательно заполните:

**Основные настройки бота:**
```bash
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz  # От @BotFather
BOT_USERNAME=your_bot_username                    # Без @
```

**База данных:**
```bash
POSTGRES_PASSWORD=very_secure_password_here       # Придумайте надежный пароль
```

**Депозитный аккаунт:**
```bash
DEPOSIT_ACCOUNT_1_API_ID=12345678                # От my.telegram.org
DEPOSIT_ACCOUNT_1_API_HASH=abcdef1234567890      # От my.telegram.org  
DEPOSIT_ACCOUNT_1_PHONE=+79001234567             # Номер аккаунта
```

**TON кошелек:**
```bash
TON_WALLET_1_ADDRESS=UQD6zqW_AfYdaV...           # Адрес TON кошелька
```

**YooKassa (опционально):**
```bash
YOOKASSA_SHOP_ID=1234567
YOOKASSA_SECRET_KEY=live_aBcDeFgHiJkLmNoPqRsTuVwXyZ
```

### 3. Создание необходимых папок
```bash
mkdir -p logs data backups
chmod 777 logs data backups
```

### 4. Очистка Telegram webhook (если нужно)
```bash
# Остановите старые контейнеры
docker-compose down --remove-orphans

# Очистите webhook
docker-compose run --rm tggift-bot python clear_webhook.py
```

### 5. Запуск проекта
```bash
# Соберите контейнеры
docker-compose build --no-cache

# Запустите PostgreSQL сначала
docker-compose up -d postgres

# Дождитесь готовности PostgreSQL (30-60 секунд)
docker-compose logs postgres

# Запустите бота
docker-compose up -d tggift-bot

# Проверьте логи
docker-compose logs -f tggift-bot
```

## 🔍 Проверка работы

### Проверка статуса контейнеров
```bash
docker-compose ps
```

### Проверка подключения к PostgreSQL
```bash
docker-compose exec postgres pg_isready -U tggift -d tggift
```

### Тест подключения к базе данных
```bash
docker-compose run --rm tggift-bot python -c "
import asyncio
import asyncpg
import os

async def test_db():
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'tggift-postgres'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            database=os.getenv('POSTGRES_DB', 'tggift'),
            user=os.getenv('POSTGRES_USER', 'tggift'),
            password=os.getenv('POSTGRES_PASSWORD', 'tggift_password')
        )
        result = await conn.fetchval('SELECT 1')
        await conn.close()
        print('✅ PostgreSQL подключение работает')
        return True
    except Exception as e:
        print(f'❌ Ошибка подключения к PostgreSQL: {e}')
        return False

asyncio.run(test_db())
"
```

### Проверка переменных окружения
```bash
docker-compose run --rm tggift-bot python -c "
import os
print('BOT_TOKEN:', 'Установлен' if os.getenv('BOT_TOKEN') else 'НЕ УСТАНОВЛЕН')
print('POSTGRES_HOST:', os.getenv('POSTGRES_HOST', 'НЕ УСТАНОВЛЕН'))
print('USE_POSTGRES:', os.getenv('USE_POSTGRES', 'НЕ УСТАНОВЛЕН'))
print('DEPOSIT_ACCOUNT_1_API_ID:', 'Установлен' if os.getenv('DEPOSIT_ACCOUNT_1_API_ID') else 'НЕ УСТАНОВЛЕН')
"
```

## 🚨 Решение проблем

### Если бот не запускается:

**1. Проверьте переменные окружения:**
```bash
docker-compose run --rm tggift-bot env | grep -E "(BOT_TOKEN|POSTGRES|DEPOSIT)"
```

**2. Проверьте логи бота:**
```bash
docker-compose logs --tail=50 tggift-bot
```

**3. Проверьте логи PostgreSQL:**
```bash
docker-compose logs postgres
```

### Если есть конфликт Telegram API:
```bash
# Остановите все контейнеры
docker-compose down

# Очистите webhook
docker-compose run --rm tggift-bot python clear_webhook.py

# Запустите заново
docker-compose up -d
```

### Если проблемы с правами доступа:
```bash
sudo chmod -R 777 logs/
sudo chmod -R 777 data/
sudo chown -R $USER:$USER logs/ data/
```

### Если PostgreSQL не запускается:
```bash
# Проверьте логи PostgreSQL
docker-compose logs postgres

# Пересоздайте volume PostgreSQL
docker-compose down -v
docker volume rm tggift_postgres_data
docker-compose up -d postgres
```

### Если ошибка "ModuleNotFoundError":
```bash
# Пересоберите контейнер
docker-compose build --no-cache tggift-bot
```

## 📊 Мониторинг

### Просмотр логов в реальном времени
```bash
docker-compose logs -f tggift-bot
```

### Проверка использования ресурсов
```bash
docker stats
```

### Проверка здоровья сервисов
```bash
docker-compose ps
docker-compose exec tggift-bot python -c "print('Bot is running')"
```

### Мониторинг базы данных
```bash
# Подключение к PostgreSQL
docker-compose exec postgres psql -U tggift -d tggift

# Проверка таблиц
\dt

# Выход
\q
```

## 🔄 Обновление и обслуживание

### Перезапуск бота
```bash
docker-compose restart tggift-bot
```

### Обновление кода
```bash
# Остановите бота
docker-compose stop tggift-bot

# Обновите код
# (скопируйте новые файлы)

# Пересоберите и запустите
docker-compose build --no-cache tggift-bot
docker-compose up -d tggift-bot
```

### Бэкап базы данных
```bash
docker-compose exec postgres pg_dump -U tggift tggift > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Восстановление из бэкапа
```bash
docker-compose exec -T postgres psql -U tggift -d tggift < backup_file.sql
```

## 📞 Поддержка

Если у вас возникли проблемы:

1. Проверьте все переменные окружения в `.env`
2. Убедитесь что все порты свободны
3. Проверьте логи всех сервисов
4. Убедитесь что Docker имеет достаточно ресурсов

**Важные логи для диагностики:**
- `docker-compose logs tggift-bot` - логи бота
- `docker-compose logs postgres` - логи базы данных
- `docker system df` - использование дискового пространства
- `docker system prune` - очистка неиспользуемых ресурсов 
 
 
 