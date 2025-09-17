# 🚀 ФИНАЛЬНЫЙ ЧЕКЛИСТ РАЗВЕРТЫВАНИЯ TgGIFT BOT

## ✅ **ЛОКАЛЬНАЯ ПОДГОТОВКА (ЗАВЕРШЕНО)**

### 1. Тестирование основного бота ✅
- [x] Все модули импортируются корректно
- [x] База данных работает (PostgreSQL)
- [x] Депозитные аккаунты подключены (@GiftHelper1, @GiftHelper2)
- [x] Основные команды работают (/start, /balance, /subscriptions)
- [x] Платежная система функционирует
- [x] Мониторинг подарков активен

### 2. Проверка продакшен конфигураций ✅
- [x] Docker файлы готовы (Dockerfile.bot, Dockerfile.queue, Dockerfile.cluster)
- [x] Docker Compose конфигурация валидна
- [x] Nginx конфигурация готова
- [x] Requirements файлы полные

### 3. Финальный .env для продакшена ✅
- [x] Создан `env_production_final.txt`
- [x] Все параметры документированы
- [x] Инструкции по генерации ключей добавлены

### 4. Docker сборка протестирована ✅
- [x] Docker установлен и работает
- [x] Все необходимые файлы присутствуют
- [x] Синтаксис Dockerfile корректен
- [x] Dependencies файлы валидны
- [x] Docker Compose синтаксис корректен

---

## 🔄 **СЕРВЕРНАЯ ПОДГОТОВКА (ТРЕБУЕТСЯ ВЫПОЛНИТЬ)**

### 📋 **КРИТИЧЕСКИ ВАЖНО - 4 ОСНОВНЫХ ШАГА:**

## ⚡ **ШАГ 1: УСТАНОВКА И НАСТРОЙКА REDIS**

### 1.1 Установка Redis на сервере
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server

# CentOS/RHEL
sudo yum install redis
# или
sudo dnf install redis

# Проверка установки
redis-cli --version
```

### 1.2 Настройка Redis для продакшена
```bash
# Редактируем конфиг
sudo nano /etc/redis/redis.conf

# Основные настройки:
bind 127.0.0.1
port 6379
requirepass your_secure_redis_password_here
maxmemory 512mb
maxmemory-policy allkeys-lru
appendonly yes
```

### 1.3 Запуск и автозагрузка
```bash
sudo systemctl start redis
sudo systemctl enable redis
sudo systemctl status redis
```

### 1.4 Тестирование
```bash
redis-cli
> AUTH your_secure_redis_password_here
> ping
> set test "hello"
> get test
> exit
```

---

## 🐘 **ШАГ 2: УСТАНОВКА И НАСТРОЙКА POSTGRESQL**

### 2.1 Установка PostgreSQL
```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib

# CentOS/RHEL
sudo yum install postgresql-server postgresql-contrib
sudo postgresql-setup initdb

# Проверка версии
psql --version
```

### 2.2 Создание базы данных и пользователя
```bash
sudo -u postgres psql

-- В PostgreSQL консоли:
CREATE DATABASE tggift;
CREATE USER tggift_user WITH PASSWORD 'your_secure_database_password_here';
GRANT ALL PRIVILEGES ON DATABASE tggift TO tggift_user;
ALTER USER tggift_user CREATEDB;
\q
```

### 2.3 Настройка доступа
```bash
# Редактируем pg_hba.conf
sudo nano /etc/postgresql/*/main/pg_hba.conf

# Добавляем строку:
local   tggift    tggift_user                     md5

# Перезапускаем PostgreSQL
sudo systemctl restart postgresql
```

### 2.4 Тестирование подключения
```bash
psql -h localhost -U tggift_user -d tggift
# Введите пароль
\dt
\q
```

---

## 🌐 **ШАГ 3: НАСТРОЙКА ДОМЕНА И SSL**

### 3.1 Покупка и настройка домена
- [ ] **Купить домен** (например: yourdomain.com)
- [ ] **Настроить DNS записи** у регистратора:
  ```
  A    @           YOUR_SERVER_IP
  A    www         YOUR_SERVER_IP
  ```
- [ ] **Дождаться распространения DNS** (до 24 часов)

### 3.2 Проверка доступности домена
```bash
# На сервере проверяем
ping yourdomain.com
nslookup yourdomain.com
```

### 3.3 Установка SSL сертификата (Let's Encrypt)
```bash
# Устанавливаем certbot
sudo apt install certbot

# Получаем сертификат
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Проверяем сертификат
sudo certbot certificates
```

### 3.4 Настройка автообновления SSL
```bash
# Добавляем в crontab
sudo crontab -e

# Добавляем строку:
0 12 * * * /usr/bin/certbot renew --quiet
```

---

## 🔐 **ШАГ 4: ГЕНЕРАЦИЯ ПАРОЛЕЙ И КЛЮЧЕЙ БЕЗОПАСНОСТИ**

### 4.1 Генерация основных ключей
```bash
# MASTER_KEY (256-bit)
openssl rand -hex 32

# JWT_SECRET
openssl rand -base64 64

# WEBHOOK_SECRET
openssl rand -hex 32

# API_KEY_SALT
openssl rand -hex 16
```

### 4.2 Генерация ENCRYPTION_KEY
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4.3 Генерация паролей для сервисов
```bash
# Для PostgreSQL
openssl rand -base64 32

# Для Redis Cache
openssl rand -base64 32

# Для Redis Queue
openssl rand -base64 32
```

### 4.4 Безопасное сохранение ключей
- [ ] **Сохранить все ключи** в безопасном месте (менеджер паролей)
- [ ] **НЕ СОХРАНЯТЬ** ключи в git или открытых файлах
- [ ] **Использовать** только для продакшен сервера

---

## 🔧 **ДОПОЛНИТЕЛЬНЫЕ СЕРВЕРНЫЕ НАСТРОЙКИ**

### 5.1 Установка Docker на сервере
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Проверка
docker --version
docker-compose --version
```

### 5.2 Настройка файрвола
```bash
# UFW (Ubuntu)
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5432/tcp  # PostgreSQL (только для localhost)
sudo ufw allow 6379/tcp  # Redis (только для localhost)
sudo ufw enable
```

### 5.3 Создание пользователя для приложения
```bash
sudo useradd -m -s /bin/bash tggift
sudo usermod -aG docker tggift
sudo mkdir -p /home/tggift/app
sudo chown -R tggift:tggift /home/tggift/app
```

---

## 🚀 **РАЗВЕРТЫВАНИЕ НА СЕРВЕРЕ**

### 6.1 Подготовка файлов
- [ ] **Скопировать** все файлы проекта на сервер
- [ ] **Создать** `.env` файл на основе `env_production_final.txt`
- [ ] **Заменить** все placeholder значения реальными данными
- [ ] **Скопировать** файлы сессий депозитных аккаунтов

### 6.2 Финальная проверка конфигурации
```bash
# На сервере
cd /home/tggift/app
python3 test_bot_functions.py
python3 test_docker_build.py
```

### 6.3 Запуск продакшен системы
```bash
# Сборка образов
docker-compose -f docker-compose.production.yml build

# Запуск всех сервисов
docker-compose -f docker-compose.production.yml up -d

# Проверка статуса
docker-compose -f docker-compose.production.yml ps
```

### 6.4 Проверка работоспособности
```bash
# Проверка логов
docker-compose -f docker-compose.production.yml logs -f

# Проверка health check
curl http://localhost:8080/health

# Проверка метрик
curl http://localhost:8090/metrics
```

---

## 📊 **МОНИТОРИНГ И ПОДДЕРЖКА**

### 7.1 Настройка мониторинга
- [ ] **Grafana** доступна по адресу: http://yourdomain.com:3000
- [ ] **Prometheus** собирает метрики: http://yourdomain.com:9090
- [ ] **Алерты** настроены и работают

### 7.2 Бэкапы
```bash
# Настройка автоматических бэкапов
sudo crontab -e

# Добавить:
0 2 * * * /home/tggift/app/backup_script.sh
```

### 7.3 Логирование
- [ ] **Логи** пишутся в `/app/logs/`
- [ ] **Ротация логов** настроена
- [ ] **Мониторинг ошибок** активен

---

## ✅ **ФИНАЛЬНАЯ ПРОВЕРКА ПЕРЕД ЗАПУСКОМ**

### Обязательные проверки:
- [ ] **Redis** установлен и настроен
- [ ] **PostgreSQL** установлен и база создана
- [ ] **Домен** куплен и DNS настроен
- [ ] **SSL сертификат** получен и работает
- [ ] **Все ключи и пароли** сгенерированы и заменены
- [ ] **Docker** установлен на сервере
- [ ] **Файрвол** настроен
- [ ] **Файлы проекта** скопированы на сервер
- [ ] **.env файл** создан с реальными данными
- [ ] **Тесты** пройдены на сервере

### Критические параметры для замены в .env:
- [ ] `BOT_TOKEN` - новый продакшен токен
- [ ] `DOMAIN` - ваш реальный домен
- [ ] `DB_PASSWORD` - пароль PostgreSQL
- [ ] `REDIS_PASSWORD` - пароль Redis
- [ ] `MASTER_KEY` - мастер ключ шифрования
- [ ] `ENCRYPTION_KEY` - ключ Fernet
- [ ] `JWT_SECRET` - JWT секрет
- [ ] `WEBHOOK_SECRET` - вебхук секрет
- [ ] `YOOKASSA_SECRET_KEY` - продакшен ключ ЮКассы
- [ ] `TON_WALLET_*_ADDRESS` - продакшен TON кошельки
- [ ] `DEPOSIT_ACCOUNT_*` - продакшен депозитные аккаунты

---

## 🎯 **КОМАНДЫ ДЛЯ БЫСТРОГО РАЗВЕРТЫВАНИЯ**

После выполнения всех подготовительных шагов:

```bash
# 1. Клонирование проекта на сервер
git clone your-repo-url /home/tggift/app
cd /home/tggift/app

# 2. Создание .env файла
cp env_production_final.txt .env
nano .env  # Заменить все placeholder значения

# 3. Сборка и запуск
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

# 4. Проверка
docker-compose -f docker-compose.production.yml ps
curl http://localhost:8080/health
```

---

## 🆘 **ПОДДЕРЖКА И УСТРАНЕНИЕ ПРОБЛЕМ**

### Полезные команды:
```bash
# Просмотр логов
docker-compose -f docker-compose.production.yml logs -f [service_name]

# Перезапуск сервиса
docker-compose -f docker-compose.production.yml restart [service_name]

# Остановка всех сервисов
docker-compose -f docker-compose.production.yml down

# Обновление образов
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d
```

### Контакты поддержки:
- **Техническая документация**: [COMPLETE_SETUP_GUIDE.md](COMPLETE_SETUP_GUIDE.md)
- **Мониторинг**: [MONITORING_SETUP.md](MONITORING_SETUP.md)
- **Безопасность**: [SECURITY_SETUP.md](SECURITY_SETUP.md)

---

## 🎉 **ГОТОВО К ПРОДАКШЕНУ!**

После выполнения всех пунктов чеклиста ваш **TgGIFT Bot** будет готов к работе в продакшене с полной enterprise-архитектурой! 🚀 