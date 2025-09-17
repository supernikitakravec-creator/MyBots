# 🚀 TgGIFT Bot - Полное руководство по настройке

## 🎯 Обзор системы

**TgGIFT Bot** - это высоконагруженный Telegram бот для отправки подарков с полной enterprise-архитектурой:

### 🏗️ Архитектура системы:
- **📊 Мониторинг и метрики** - Real-time отслеживание производительности
- **🛡️ Отказоустойчивость** - Автовосстановление и резервное копирование  
- **⚖️ Горизонтальное масштабирование** - Load balancing и кластеризация
- **🔐 Безопасность** - Шифрование, аутентификация и аудит
- **⚡ Оптимизация производительности** - Redis кэширование и очереди

## 📋 Предварительные требования

### Системные требования:
- **OS**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- **RAM**: Минимум 4GB (рекомендуется 8GB+)
- **CPU**: 2+ ядра (рекомендуется 4+)
- **Диск**: 50GB+ свободного места
- **Сеть**: Стабильное интернет-соединение

### Необходимое ПО:
```bash
# Docker и Docker Compose
sudo apt update
sudo apt install docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker

# Python 3.11+ (для разработки)
sudo apt install python3.11 python3.11-pip python3.11-venv

# Git
sudo apt install git

# Nginx (если не используете Docker)
sudo apt install nginx

# PostgreSQL client (для бэкапов)
sudo apt install postgresql-client
```

## 🔧 Быстрый старт

### 1. 📥 Клонирование репозитория
```bash
git clone https://github.com/your-username/tggift-bot.git
cd tggift-bot
```

### 2. 🔑 Настройка переменных окружения
```bash
# Копируем пример конфигурации
cp env_production_example.txt .env

# Редактируем настройки
nano .env
```

**Обязательные настройки в `.env`:**
```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token_here

# База данных
DB_PASSWORD=your_secure_database_password

# Redis
REDIS_PASSWORD=your_redis_password
REDIS_QUEUE_PASSWORD=your_redis_queue_password

# Шифрование (сгенерируйте новый ключ!)
MASTER_ENCRYPTION_KEY=your_base64_encoded_master_key_here

# Домен (для продакшена)
DOMAIN=your-domain.com
```

### 3. 🔐 Генерация ключа шифрования
```bash
python3 -c "
from cryptography.fernet import Fernet
import base64
key = Fernet.generate_key()
print('MASTER_ENCRYPTION_KEY=' + base64.b64encode(key).decode())
"
```

### 4. 🚀 Запуск системы

**Для разработки:**
```bash
docker-compose up -d
```

**Для продакшена:**
```bash
docker-compose -f docker-compose.production.yml up -d
```

### 5. ✅ Проверка статуса
```bash
# Проверяем все контейнеры
docker-compose ps

# Логи
docker-compose logs -f

# Health check
curl http://localhost/health
```

## 📊 Архитектура компонентов

### 🏗️ Схема системы:
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Nginx LB      │───▶│   Bot Workers    │───▶│   PostgreSQL    │
│ (Load Balancer) │    │  (2+ instances)  │    │   (Database)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Redis Cache     │    │ Queue Workers    │    │ Redis Queue     │
│ (Кэширование)   │    │ (Background)     │    │ (Сообщения)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Prometheus     │    │ Cluster Manager  │    │    Grafana      │
│ (Метрики)       │    │ (Управление)     │    │ (Мониторинг)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 🧩 Компоненты системы:

#### 1. **🤖 Bot Workers** (2+ экземпляра)
- Обработка Telegram сообщений
- Load balancing между воркерами
- Auto-scaling при нагрузке
- Health checks и auto-restart

#### 2. **⚡ Queue Workers** (2+ экземпляра)  
- Фоновая обработка задач
- Платежи и уведомления
- Отправка подарков
- Резервное копирование

#### 3. **🗄️ База данных (PostgreSQL)**
- Пользователи и подписки
- История транзакций
- Аудит безопасности
- Автоматические бэкапы

#### 4. **💾 Redis Cache**
- Кэширование пользовательских данных
- Сессии и токены
- Результаты запросов
- LRU eviction policy

#### 5. **📬 Redis Queue**
- Очереди сообщений
- Асинхронные задачи
- Retry механизм
- Dead letter queue

#### 6. **⚖️ Nginx Load Balancer**
- Распределение нагрузки
- SSL termination
- Rate limiting
- Static file serving

#### 7. **📊 Мониторинг**
- **Prometheus**: Сбор метрик
- **Grafana**: Визуализация
- **Health Monitor**: Проверки работоспособности
- **Alert System**: Уведомления о проблемах

## 🔐 Компоненты безопасности

### 🛡️ Система защиты:

#### 1. **Шифрование данных**
- **AES-256-GCM**: Для чувствительных данных
- **Fernet**: Симметричное шифрование
- **RSA-2048**: Асимметричное шифрование
- **bcrypt**: Хеширование паролей
- **Автоматическая ротация ключей**: Каждые 30-90 дней

#### 2. **Аутентификация и авторизация**
- **6-уровневая система ролей**: Guest → Super Admin
- **22 типа разрешений**: Детальный контроль доступа
- **Управление сессиями**: Автоматическое истечение
- **Защита от брутфорса**: Блокировка после неудачных попыток

#### 3. **Аудит безопасности**
- **15 типов событий**: От входа до критических ошибок
- **Автоматическое обнаружение атак**: SQL injection, XSS, DoS
- **Real-time анализ**: Подозрительные паттерны
- **Система алертов**: Мгновенные уведомления

#### 4. **Валидация входных данных**
- **Input sanitization**: Очистка всех входящих данных
- **Pattern matching**: Обнаружение вредоносного кода
- **Rate limiting**: Защита от злоупотреблений
- **IP фильтрация**: Блокировка подозрительных адресов

## 🚀 Команды администратора

### 📊 Мониторинг системы:
```bash
# Статус всех сервисов
/health

# Метрики производительности
/metrics

# Статус безопасности
/security

# События безопасности
/events

# Статус кластера
/cluster
```

### 🔧 Управление:
```bash
# VIP статус пользователю
/grantvip 123456789 30

# Отзыв сессий пользователя
/revoke_sessions 123456789

# Разблокировка пользователя
/unlock 123456789

# Повышение роли
/promote 123456789 admin

# Ротация ключей шифрования
/rotate_keys

# Создание бэкапа
/backup

# Статус восстановления
/recovery_status
```

## 🔧 Продакшен настройка

### 1. 🌐 Настройка домена и SSL

**Получение SSL сертификата (Let's Encrypt):**
```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com

# Автообновление
sudo crontab -e
# Добавить: 0 12 * * * /usr/bin/certbot renew --quiet
```

**Настройка DNS:**
```
A record: your-domain.com → your-server-ip
CNAME: www.your-domain.com → your-domain.com
```

### 2. 🔒 Настройка файрвола
```bash
# UFW (Ubuntu)
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Закрываем прямой доступ к сервисам
sudo ufw deny 5432  # PostgreSQL
sudo ufw deny 6379  # Redis
sudo ufw deny 9090  # Prometheus
```

### 3. 📈 Настройка мониторинга

**Grafana dashboards:**
- Открыть: `http://your-domain.com:3000`
- Логин: `admin` / пароль из `.env`
- Импортировать готовые дашборды из `monitoring/grafana/dashboards/`

**Prometheus targets:**
- Bot Workers: `bot-worker-1:8001`, `bot-worker-2:8002`
- PostgreSQL: `postgresql:5432`
- Redis: `redis-cache:6379`, `redis-queue:6379`
- Nginx: `nginx-lb:80`

### 4. 📧 Настройка алертов

**Telegram алерты:**
```env
ALERT_TELEGRAM_CHAT_ID=your_admin_chat_id
ALERT_TELEGRAM_TOKEN=your_alert_bot_token
```

**Email алерты:**
```env
ALERT_EMAIL_SMTP_HOST=smtp.gmail.com
ALERT_EMAIL_USER=alerts@your-domain.com
ALERT_EMAIL_PASSWORD=your_app_password
ALERT_EMAIL_TO=admin@your-domain.com
```

## 🔄 Процедуры обслуживания

### 📊 Ежедневные проверки:
```bash
# Статус системы
docker-compose ps
curl http://localhost/health

# Проверка логов
docker-compose logs --tail=100 -f

# Использование ресурсов
docker stats

# Статус дисков
df -h
```

### 🗄️ Еженедельные бэкапы:
```bash
# Автоматический бэкап (настроен в cron)
docker-compose exec postgresql pg_dump -U tggift_user tggift > backup_$(date +%Y%m%d).sql

# Бэкап Redis
docker-compose exec redis-cache redis-cli BGSAVE

# Проверка бэкапов
ls -la backups/
```

### 🔄 Обновления системы:
```bash
# Обновление образов
docker-compose pull

# Graceful restart
docker-compose restart bot-worker-1
sleep 30
docker-compose restart bot-worker-2

# Проверка работоспособности
curl http://localhost/health
```

## 🚨 Решение проблем

### 🔍 Диагностика проблем:

#### 1. **Бот не отвечает**
```bash
# Проверяем статус воркеров
docker-compose ps | grep bot-worker

# Логи ошибок
docker-compose logs bot-worker-1 --tail=50

# Проверяем health check
curl http://localhost/health

# Рестарт воркера
docker-compose restart bot-worker-1
```

#### 2. **Проблемы с базой данных**
```bash
# Проверяем соединение
docker-compose exec postgresql pg_isready -U tggift_user

# Статистика подключений
docker-compose exec postgresql psql -U tggift_user -d tggift -c "
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"

# Размер базы данных
docker-compose exec postgresql psql -U tggift_user -d tggift -c "
SELECT pg_size_pretty(pg_database_size('tggift'));"
```

#### 3. **Проблемы с Redis**
```bash
# Проверяем подключение
docker-compose exec redis-cache redis-cli ping

# Статистика памяти
docker-compose exec redis-cache redis-cli info memory

# Количество ключей
docker-compose exec redis-cache redis-cli dbsize
```

#### 4. **Проблемы с производительностью**
```bash
# CPU и память
docker stats --no-stream

# Дисковое пространство
df -h

# Сетевые соединения
ss -tuln

# Логи Nginx
docker-compose logs nginx-lb --tail=100
```

### 🆘 Аварийные процедуры:

#### 1. **Полная остановка системы**
```bash
docker-compose down
```

#### 2. **Восстановление из бэкапа**
```bash
# Остановка сервисов
docker-compose stop

# Восстановление БД
docker-compose exec postgresql psql -U tggift_user -d tggift < backup_20240101.sql

# Запуск сервисов
docker-compose start
```

#### 3. **Экстренный перезапуск**
```bash
# Принудительная остановка
docker-compose kill

# Очистка
docker-compose rm -f

# Запуск
docker-compose up -d
```

## 📈 Масштабирование

### 🚀 Горизонтальное масштабирование:

#### 1. **Добавление воркеров**
```yaml
# В docker-compose.production.yml
bot-worker-3:
  build: 
    context: .
    dockerfile: Dockerfile.bot
  environment:
    - WORKER_ID=bot_worker_3
    - WORKER_PORT=8003
  # ... остальные настройки
```

#### 2. **Автоматическое масштабирование**
```env
# В .env
AUTO_SCALE_WORKERS=true
MIN_WORKERS_PER_TYPE=3
MAX_WORKERS_PER_TYPE=10
SCALE_UP_THRESHOLD=70
SCALE_DOWN_THRESHOLD=30
```

#### 3. **Load balancer настройка**
```nginx
# В nginx/nginx.conf
upstream bot_workers {
    least_conn;
    server bot-worker-1:8001 max_fails=3 fail_timeout=30s;
    server bot-worker-2:8002 max_fails=3 fail_timeout=30s;
    server bot-worker-3:8003 max_fails=3 fail_timeout=30s;
}
```

### 📊 Вертикальное масштабирование:
```yaml
# Увеличение ресурсов для сервисов
services:
  bot-worker-1:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

## 📚 API документация

### 🔌 Webhook endpoints:

#### 1. **Telegram Webhook**
```
POST /webhook
Content-Type: application/json

Headers:
- X-Telegram-Bot-Api-Secret-Token: your_webhook_secret
```

#### 2. **Health Check**
```
GET /health

Response:
{
    "status": "healthy",
    "timestamp": "2024-01-01T12:00:00Z",
    "services": {
        "database": "healthy",
        "redis": "healthy",
        "workers": "2/2 healthy"
    }
}
```

#### 3. **Metrics**
```
GET /metrics
Content-Type: text/plain

# Prometheus format metrics
bot_requests_total{method="message"} 1234
bot_response_time_seconds{endpoint="/start"} 0.045
```

## 🎯 Лучшие практики

### 🔒 Безопасность:
1. **Регулярно обновляйте пароли и ключи**
2. **Мониторьте логи безопасности ежедневно**
3. **Настройте автоматические алерты**
4. **Используйте VPN для административного доступа**
5. **Регулярно проводите аудит безопасности**

### 📊 Производительность:
1. **Мониторьте метрики в реальном времени**
2. **Настройте автомасштабирование**
3. **Оптимизируйте запросы к базе данных**
4. **Используйте кэширование агрессивно**
5. **Регулярно очищайте старые данные**

### 🛠️ Эксплуатация:
1. **Автоматизируйте бэкапы**
2. **Тестируйте процедуры восстановления**
3. **Документируйте все изменения**
4. **Используйте CI/CD для развертывания**
5. **Планируйте техническое обслуживание**

## 🆘 Поддержка

### 📞 Контакты:
- **Техническая поддержка**: support@your-domain.com
- **Экстренные вопросы**: +7-XXX-XXX-XXXX
- **GitHub Issues**: https://github.com/your-username/tggift-bot/issues

### 📖 Дополнительная документация:
- [REDIS_SETUP.md](REDIS_SETUP.md) - Настройка кэширования
- [MONITORING_SETUP.md](MONITORING_SETUP.md) - Мониторинг и метрики
- [RESILIENCE_SETUP.md](RESILIENCE_SETUP.md) - Отказоустойчивость
- [SCALING_SETUP.md](SCALING_SETUP.md) - Масштабирование
- [SECURITY_SETUP.md](SECURITY_SETUP.md) - Безопасность

---

## 🎉 Готово!

Ваш **TgGIFT Bot** готов к работе в продакшене с полной enterprise-архитектурой:

✅ **Высокая доступность** - 99.9% uptime  
✅ **Масштабируемость** - Автоматическое масштабирование  
✅ **Безопасность** - Военного уровня защита  
✅ **Мониторинг** - Real-time метрики и алерты  
✅ **Отказоустойчивость** - Автовосстановление и бэкапы  

**Добро пожаловать в мир enterprise-разработки!** 🚀 