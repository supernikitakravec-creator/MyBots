# 🐘 Руководство по миграции на PostgreSQL

## 🎯 Зачем нужна миграция?

**SQLite** → **PostgreSQL** для поддержки:
- ✅ **Тысячи одновременных пользователей**
- ✅ **Concurrent доступ без блокировок** 
- ✅ **Профессиональные индексы и производительность**
- ✅ **Масштабирование на несколько серверов**
- ✅ **Надежность и резервное копирование**

## 🚀 Пошаговая миграция

### Шаг 1: Подготовка PostgreSQL

```bash
# Установка PostgreSQL (Ubuntu/Debian)
sudo apt update
sudo apt install postgresql postgresql-contrib

# Создание базы данных и пользователя
sudo -u postgres psql
```

```sql
CREATE DATABASE tggift_db;
CREATE USER tggift WITH PASSWORD 'tggift_password';
GRANT ALL PRIVILEGES ON DATABASE tggift_db TO tggift;
\q
```

### Шаг 2: Установка зависимостей

```bash
# Установка PostgreSQL зависимостей
pip install -r requirements_postgres.txt
```

### Шаг 3: Настройка переменных окружения

Добавьте в `.env`:
```bash
# PostgreSQL подключение
DATABASE_URL=postgresql://tggift:tggift_password@localhost:5432/tggift_db
USE_POSTGRES=true

# Настройки пула соединений (опционально)
DB_POOL_MIN_SIZE=10
DB_POOL_MAX_SIZE=50
DB_COMMAND_TIMEOUT=60
```

### Шаг 4: Остановка бота и резервное копирование

```bash
# Остановите бота
pkill -f main_bot.py

# Создайте резервную копию SQLite базы
cp gift_bot.db gift_bot.db.backup_$(date +%Y%m%d_%H%M%S)
```

### Шаг 5: Миграция данных

```bash
# Запуск скрипта миграции
python migrate_to_postgres.py
```

Скрипт автоматически:
- ✅ Создаст схему PostgreSQL с индексами
- ✅ Перенесет всех пользователей
- ✅ Перенесет балансы и транзакции
- ✅ Перенесет подписки и профили автопокупки
- ✅ Проверит целостность данных

### Шаг 6: Запуск бота с PostgreSQL

```bash
# Запуск с PostgreSQL
USE_POSTGRES=true python main_bot.py
```

Вы должны увидеть:
```
🐘 Используется PostgreSQL для масштабирования
✅ PostgreSQL подключен с пулом соединений
```

## 🔍 Проверка работоспособности

### Тестирование основных функций:
1. **Регистрация пользователя** - `/start`
2. **Проверка баланса** - должен сохраниться
3. **Пополнение Stars** - создание платежа
4. **Настройки автопокупки** - сохранение/изменение
5. **Подписки** - проверка активных подписок

### Мониторинг производительности:
```python
# Проверка пула соединений
from database_postgres import PostgresDatabaseManager
db = PostgresDatabaseManager()
await db.connect()
stats = await db.get_connection_stats()
print(stats)  # {'size': 15, 'idle_size': 10, ...}
```

## 📊 Преимущества PostgreSQL версии

### Производительность:
- **Пул соединений**: 10-50 одновременных подключений
- **Индексы**: Оптимизированные запросы для всех таблиц
- **Асинхронность**: Полная поддержка async/await
- **Batch операции**: Групповые операции для высокой нагрузки

### Надежность:
- **ACID транзакции**: Гарантия целостности данных
- **Репликация**: Возможность master-slave настройки
- **Резервное копирование**: Встроенные инструменты pg_dump
- **Мониторинг**: Подробная статистика запросов

### Масштабируемость:
- **Connection pooling**: Эффективное использование ресурсов
- **Партиционирование**: Разделение больших таблиц
- **Кэширование**: Интеграция с Redis
- **Load balancing**: Распределение нагрузки

## 🛠️ Настройка для продакшена

### PostgreSQL оптимизация:
```sql
-- Настройки производительности
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
SELECT pg_reload_conf();
```

### Мониторинг:
```bash
# Установка pg_stat_statements для мониторинга
sudo -u postgres psql -d tggift_db
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

## 🚨 Откат к SQLite (если нужен)

```bash
# Остановите бота
pkill -f main_bot.py

# Уберите PostgreSQL переменные
unset USE_POSTGRES
# или установите USE_POSTGRES=false

# Запустите с SQLite
python main_bot.py
```

## 📈 Метрики и мониторинг

PostgreSQL версия предоставляет:
- **Статистика пула соединений**
- **Время выполнения запросов**
- **Количество активных соединений**
- **Health check эндпоинт**

## 🆘 Решение проблем

### Ошибки подключения:
```bash
# Проверка статуса PostgreSQL
sudo systemctl status postgresql

# Проверка подключения
psql -h localhost -U tggift -d tggift_db
```

### Проблемы с производительностью:
```sql
-- Анализ медленных запросов
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY mean_time DESC LIMIT 10;
```

### Мониторинг соединений:
```sql
-- Активные соединения
SELECT * FROM pg_stat_activity WHERE datname = 'tggift_db';
```

## 🎉 Результат

После миграции ваш бот сможет:
- ⚡ **Обслуживать тысячи пользователей одновременно**
- 🔄 **Обрабатывать сотни запросов в секунду**
- 📈 **Масштабироваться горизонтально**
- 🛡️ **Гарантировать целостность данных**
- 📊 **Предоставлять детальную аналитику**

**Готово к продакшену!** 🚀 