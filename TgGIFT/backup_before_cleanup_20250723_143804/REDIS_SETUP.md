# Установка и настройка Redis для TgGIFT Bot

## 🚀 Установка Redis

### Windows:
1. Скачайте Redis для Windows с GitHub: https://github.com/microsoftarchive/redis/releases
2. Установите Redis
3. Запустите Redis сервер:
   ```cmd
   redis-server
   ```

### Linux (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### macOS:
```bash
brew install redis
brew services start redis
```

### Docker:
```bash
docker run -d --name redis -p 6379:6379 redis:latest
```

## ⚙️ Конфигурация

### 1. Добавьте в .env файл:
```env
# Redis настройки
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # Оставьте пустым если пароль не установлен

# Настройки кэша
CACHE_ENABLED=true
CACHE_DEFAULT_TTL=3600
CACHE_USER_DATA_TTL=1800
CACHE_SUBSCRIPTION_TTL=900
CACHE_GIFT_DATA_TTL=300
```

### 2. Установите Python зависимости:
```bash
pip install -r requirements_redis.txt
```

## 🔧 Интеграция с ботом

### 1. Обновите main_bot.py:
```python
from database_adapter_cached import CachedDatabaseAdapter

# Вместо:
# self.db_manager = DatabaseAdapterSimple()

# Используйте:
base_adapter = DatabaseAdapterSimple()
self.db_manager = CachedDatabaseAdapter(base_adapter)

# В методе инициализации добавьте:
await self.db_manager.init_cache()
```

### 2. Добавьте graceful shutdown:
```python
async def shutdown(self):
    """Корректное завершение работы"""
    await self.db_manager.close_cache()
    # Остальная логика завершения
```

## 📊 Мониторинг кэша

### Команды для администратора:
- `/cache_stats` - статистика кэша
- `/clear_cache` - очистка кэша
- `/warm_cache` - прогрев кэша

### Redis CLI команды:
```bash
# Подключение к Redis
redis-cli

# Просмотр всех ключей
KEYS tggift:*

# Просмотр статистики
INFO memory

# Очистка базы данных
FLUSHDB
```

## 🔍 Что кэшируется:

1. **Данные пользователей** (TTL: 30 минут)
   - Основная информация о пользователе
   - Баланс и статистика

2. **Подписки** (TTL: 15 минут)
   - Информация о VIP подписках
   - Статус активации

3. **Подарки** (TTL: 5 минут)
   - Список доступных подарков
   - Актуальные цены

## ⚡ Производительность

### Ожидаемые улучшения:
- **Скорость ответа**: ↑ 300-500%
- **Нагрузка на БД**: ↓ 70-80%
- **Время отклика**: < 50ms для кэшированных данных

### Рекомендуемые настройки Redis:
```
# redis.conf
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

## 🔧 Troubleshooting

### Проблема: Redis не подключается
```bash
# Проверьте статус
sudo systemctl status redis-server

# Перезапустите
sudo systemctl restart redis-server
```

### Проблема: Кэш не работает
1. Проверьте `CACHE_ENABLED=true` в .env
2. Убедитесь что Redis запущен
3. Проверьте логи бота на ошибки подключения

### Проблема: Высокое потребление памяти
1. Уменьшите TTL значения
2. Настройте `maxmemory` в redis.conf
3. Используйте `FLUSHDB` для очистки

## 📈 Следующие шаги

После успешного внедрения Redis:
1. Мониторинг и метрики
2. Репликация Redis
3. Кластеризация для высоких нагрузок 