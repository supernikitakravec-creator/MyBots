# TgGIFT Star Bot - Production Deployment Guide

## 🚀 Production-Ready Features

### ✅ Реализованные улучшения для production:

1. **Graceful Shutdown** - корректное завершение всех процессов
2. **Health Check** - мониторинг состояния системы
3. **Rate Limiting** - защита от перегрузки
4. **Connection Pooling** - оптимизация работы с БД
5. **Retry Logic** - автоматические повторы при ошибках
6. **Comprehensive Logging** - детальное логирование
7. **Security Hardening** - улучшенная безопасность
8. **Resource Management** - контроль ресурсов
9. **Error Handling** - обработка всех типов ошибок
10. **Configuration Validation** - валидация настроек

## 📋 Требования к системе

- Python 3.11+
- 2GB RAM минимум
- 10GB свободного места
- Linux/Unix система (для systemd)

## 🔧 Установка и настройка

### 1. Клонирование и настройка

```bash
git clone <repository>
cd TgGIFT
```

### 2. Создание .env файла

```bash
cp .env.example .env
nano .env
```

**Обязательные переменные:**
```env
# Telegram Bot
BOT_TOKEN=your_bot_token_here

# Telegram Client API (для управляемого аккаунта)
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=+1234567890

# База данных
DATABASE_PATH=/opt/tggift-bot/data/gift_bot.db

# Логирование
LOG_FILE=/opt/tggift-bot/logs/bot.log
LOG_LEVEL=INFO

# Мониторинг
MONITORING_INTERVAL=60
GIFT_CHECK_INTERVAL=30

# Очередь
MAX_QUEUE_SIZE=1000
MIN_BALANCE_FOR_PURCHASE=100

# Уведомления
NOTIFICATIONS_ENABLED=true
MAX_NOTIFICATIONS_PER_HOUR=50

# Безопасность
ENABLE_RATE_LIMITING=true
MAX_REQUESTS_PER_MINUTE=60

# Health Check
HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_INTERVAL=300

# Graceful Shutdown
GRACEFUL_TIMEOUT=30
FORCE_SHUTDOWN_TIMEOUT=60
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Инициализация базы данных

```bash
python -c "from database import DatabaseManager; DatabaseManager().init_database()"
```

## 🐳 Docker Deployment

### 1. Сборка и запуск

```bash
# Сборка образа
docker build -t tggift-bot .

# Запуск с docker-compose
docker-compose up -d

# Просмотр логов
docker-compose logs -f tggift-bot
```

### 2. Обновление

```bash
docker-compose pull
docker-compose up -d --force-recreate
```

## 🖥️ Systemd Deployment

### 1. Создание пользователя

```bash
sudo useradd -r -s /bin/false tggift
sudo mkdir -p /opt/tggift-bot/{data,logs}
sudo chown -R tggift:tggift /opt/tggift-bot
```

### 2. Копирование файлов

```bash
sudo cp -r . /opt/tggift-bot/
sudo cp tggift-bot.service /etc/systemd/system/
sudo chown -R tggift:tggift /opt/tggift-bot
```

### 3. Активация сервиса

```bash
sudo systemctl daemon-reload
sudo systemctl enable tggift-bot
sudo systemctl start tggift-bot
```

### 4. Управление сервисом

```bash
# Статус
sudo systemctl status tggift-bot

# Логи
sudo journalctl -u tggift-bot -f

# Перезапуск
sudo systemctl restart tggift-bot

# Остановка
sudo systemctl stop tggift-bot
```

## 📊 Мониторинг

### 1. Health Check

```bash
# Проверка состояния
curl http://localhost:8080/health

# Просмотр статистики
python -c "from database import DatabaseManager; print(DatabaseManager().get_database_stats())"
```

### 2. Логирование

Логи сохраняются в:
- Docker: `./logs/bot.log`
- Systemd: `journalctl -u tggift-bot`

### 3. Метрики

Основные метрики:
- Количество пользователей
- Размер очереди
- Количество активных подписок
- Статус подключений

## 🔒 Безопасность

### 1. Firewall

```bash
# Открываем только необходимые порты
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 2. SSL/TLS

Для HTTPS настройте SSL сертификаты в nginx.conf

### 3. Резервное копирование

```bash
# Скрипт для бэкапа
#!/bin/bash
BACKUP_DIR="/backup/tggift"
DATE=$(date +%Y%m%d_%H%M%S)

# Бэкап БД
cp /opt/tggift-bot/data/gift_bot.db "$BACKUP_DIR/db_$DATE.db"

# Бэкап логов
tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" /opt/tggift-bot/logs/

# Удаление старых бэкапов (старше 30 дней)
find "$BACKUP_DIR" -name "*.db" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
```

## 🚨 Troubleshooting

### 1. Бот не запускается

```bash
# Проверка конфигурации
python -c "from config import validate_config; validate_config()"

# Проверка зависимостей
pip list | grep -E "(telegram|pyrogram|sqlite)"

# Проверка прав доступа
ls -la /opt/tggift-bot/
```

### 2. Ошибки подключения

```bash
# Проверка токена бота
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"

# Проверка API credentials
python -c "from config import API_ID, API_HASH; print(f'API_ID: {API_ID}, API_HASH: {API_HASH}')"
```

### 3. Проблемы с БД

```bash
# Проверка целостности БД
sqlite3 /opt/tggift-bot/data/gift_bot.db "PRAGMA integrity_check;"

# Резервное копирование
sqlite3 /opt/tggift-bot/data/gift_bot.db ".backup '/backup/gift_bot_backup.db'"
```

## 📈 Масштабирование

### 1. Горизонтальное масштабирование

Для высоких нагрузок используйте:
- Балансировщик нагрузки
- Несколько экземпляров бота
- Общую БД (PostgreSQL вместо SQLite)

### 2. Вертикальное масштабирование

Увеличьте ресурсы:
- RAM: 4-8GB
- CPU: 4+ ядра
- SSD для БД

## 🔄 Обновления

### 1. Автоматические обновления

```bash
# Скрипт обновления
#!/bin/bash
cd /opt/tggift-bot
git pull origin main
sudo systemctl restart tggift-bot
```

### 2. Откат изменений

```bash
git log --oneline
git checkout <commit_hash>
sudo systemctl restart tggift-bot
```

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи: `journalctl -u tggift-bot -f`
2. Проверьте конфигурацию: `python -c "from config import get_config_summary; print(get_config_summary())"`
3. Проверьте health check
4. Создайте issue с логами и описанием проблемы

## 🎯 Production Checklist

- [ ] BOT_TOKEN настроен
- [ ] API credentials настроены
- [ ] База данных инициализирована
- [ ] Логирование настроено
- [ ] Firewall настроен
- [ ] SSL сертификаты установлены
- [ ] Резервное копирование настроено
- [ ] Мониторинг настроен
- [ ] Graceful shutdown работает
- [ ] Health check проходит
- [ ] Rate limiting включен
- [ ] Error handling работает
- [ ] Security hardening применен 