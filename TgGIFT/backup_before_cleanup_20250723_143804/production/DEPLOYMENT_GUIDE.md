# 🚀 Руководство по развертыванию TgGIFT Star Bot

## 📋 Требования

### Системные требования
- **ОС**: Ubuntu 20.04+ / Debian 10+
- **RAM**: Минимум 1GB (рекомендуется 2GB)
- **Диск**: Минимум 10GB свободного места
- **CPU**: 1 ядро (рекомендуется 2 ядра)
- **Python**: 3.8+

### Необходимые компоненты
- Python 3.8+
- pip
- virtualenv
- systemd
- nginx (опционально)
- PostgreSQL (для production)

## 🔧 Подготовка сервера

### 1. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Установка зависимостей
```bash
sudo apt install -y python3 python3-pip python3-venv git nginx postgresql postgresql-contrib
```

### 3. Создание пользователя для бота
```bash
sudo useradd -m -s /bin/bash tggift
sudo passwd tggift
```

## 📦 Установка бота

### 1. Клонирование репозитория
```bash
sudo su - tggift
git clone https://github.com/yourusername/tggift-bot.git /opt/tggift-bot
cd /opt/tggift-bot
```

### 2. Создание виртуального окружения
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установка зависимостей
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Настройка конфигурации
```bash
cp env_example.txt .env
nano .env
```

Обязательно установите:
- `BOT_TOKEN` - токен вашего бота
- `API_ID` и `API_HASH` - для управляемого аккаунта
- `PHONE_NUMBER` - номер телефона управляемого аккаунта
- `DATABASE_PATH` - путь к базе данных

### 5. Инициализация базы данных
```bash
python init_database.py
```

### 6. Проверка конфигурации
```bash
python check_config.py
```

## 🏃 Запуск бота

### Ручной запуск (для тестирования)
```bash
python main_bot.py
```

### Автоматический запуск через systemd

1. Скопируйте файл службы:
```bash
sudo cp tggift-bot.service /etc/systemd/system/
```

2. Обновите пути в файле службы:
```bash
sudo nano /etc/systemd/system/tggift-bot.service
```

3. Перезагрузите systemd и запустите службу:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tggift-bot
sudo systemctl start tggift-bot
```

4. Проверьте статус:
```bash
sudo systemctl status tggift-bot
```

## 📊 Мониторинг

### Просмотр логов
```bash
# Логи systemd
sudo journalctl -u tggift-bot -f

# Логи приложения
tail -f /opt/tggift-bot/bot.log
```

### Мониторинг производительности
```bash
python monitor_system.py
# Или для непрерывного мониторинга
python monitor_system.py --continuous --interval 300
```

### Тестирование функций
```bash
python test_bot_functions.py
```

## 🔒 Безопасность

### 1. Настройка прав доступа
```bash
chmod 600 /opt/tggift-bot/.env
chmod 700 /opt/tggift-bot/data
```

### 2. Настройка firewall
```bash
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 3. Регулярное резервное копирование
```bash
# Создайте скрипт backup.sh
#!/bin/bash
BACKUP_DIR="/backup/tggift-bot"
mkdir -p $BACKUP_DIR
cp /opt/tggift-bot/data/gift_bot.db $BACKUP_DIR/gift_bot_$(date +%Y%m%d_%H%M%S).db
cp /opt/tggift-bot/.env $BACKUP_DIR/env_$(date +%Y%m%d_%H%M%S)
find $BACKUP_DIR -type f -mtime +7 -delete  # Удаляем старые бэкапы
```

Добавьте в crontab:
```bash
0 3 * * * /opt/tggift-bot/backup.sh
```

## 🚦 Управление ботом

### Остановка
```bash
sudo systemctl stop tggift-bot
```

### Перезапуск
```bash
sudo systemctl restart tggift-bot
```

### Обновление
```bash
cd /opt/tggift-bot
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart tggift-bot
```

## 🐳 Docker (альтернативный вариант)

### Сборка образа
```bash
docker build -t tggift-bot .
```

### Запуск через docker-compose
```bash
docker-compose up -d
```

### Просмотр логов
```bash
docker-compose logs -f tggift-bot
```

## 🔧 Устранение неполадок

### Бот не запускается
1. Проверьте логи: `sudo journalctl -u tggift-bot -n 100`
2. Проверьте конфигурацию: `python check_config.py`
3. Проверьте права доступа к файлам

### Ошибки подключения к Telegram
1. Проверьте токен бота
2. Проверьте интернет-соединение
3. Проверьте, не заблокирован ли IP

### Проблемы с базой данных
1. Проверьте права доступа к файлу БД
2. Проверьте свободное место на диске
3. Запустите проверку БД: `python test_bot_functions.py`

### Высокое потребление ресурсов
1. Проверьте мониторинг: `python monitor_system.py`
2. Увеличьте интервал парсинга в конфигурации
3. Проверьте размер логов и БД

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи
2. Запустите диагностику: `python check_config.py`
3. Проверьте мониторинг: `python monitor_system.py`
4. Обратитесь к документации

## 🎯 Чек-лист запуска

- [ ] Сервер обновлен
- [ ] Python и зависимости установлены
- [ ] Репозиторий склонирован
- [ ] Виртуальное окружение создано
- [ ] Зависимости установлены
- [ ] .env файл настроен
- [ ] База данных инициализирована
- [ ] Конфигурация проверена
- [ ] Systemd служба настроена
- [ ] Бот запущен и работает
- [ ] Мониторинг настроен
- [ ] Резервное копирование настроено
- [ ] Безопасность настроена 