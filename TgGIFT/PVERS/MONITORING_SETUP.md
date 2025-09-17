# Система мониторинга и метрик для TgGIFT Bot

## 📊 Обзор системы

Комплексная система мониторинга включает:
- **Сбор метрик** - производительность, системные ресурсы, операции
- **Health checks** - проверка состояния компонентов
- **Система алертов** - уведомления о проблемах
- **Улучшенное логирование** - структурированные логи с ротацией

## 🚀 Установка и настройка

### 1. Установите зависимости:
```bash
pip install -r requirements_monitoring.txt
```

### 2. Добавьте в .env конфигурацию мониторинга:
```env
# Мониторинг
MONITORING_ENABLED=true
METRICS_COLLECTION_INTERVAL=60
HEALTH_CHECK_INTERVAL=300

# Логирование
LOG_LEVEL=INFO
LOG_JSON_FORMAT=true
LOG_MAX_FILE_SIZE=52428800  # 50MB
LOG_BACKUP_COUNT=5

# Алерты - Telegram
ALERT_TELEGRAM_ENABLED=true
ALERT_TELEGRAM_BOT_TOKEN=your_monitoring_bot_token
ALERT_TELEGRAM_CHAT_ID=your_monitoring_chat_id

# Алерты - Email (опционально)
ALERT_EMAIL_ENABLED=false
ALERT_EMAIL_SMTP_SERVER=smtp.gmail.com
ALERT_EMAIL_SMTP_PORT=587
ALERT_EMAIL_USERNAME=your_email@gmail.com
ALERT_EMAIL_PASSWORD=your_app_password
ALERT_EMAIL_TO=admin@yourcompany.com

# Алерты - Webhook (опционально)
ALERT_WEBHOOK_ENABLED=false
ALERT_WEBHOOK_URL=https://your-webhook-url.com/alerts
```

### 3. Интегрируйте с main_bot.py:

```python
from metrics_collector import metrics_collector, measure_time_async
from health_monitor import health_monitor
from alert_system import create_alert_system
from enhanced_logging import setup_enhanced_logging

# В классе TgGiftBot:
def __init__(self):
    # Настройка улучшенного логирования
    self.enhanced_logger = setup_enhanced_logging({
        'log_dir': 'logs',
        'json_logs': True,
        'console_level': 'INFO',
        'file_level': 'DEBUG'
    })
    
    # Настройка системы алертов
    alert_config = {
        'telegram': {
            'enabled': os.getenv('ALERT_TELEGRAM_ENABLED', 'false').lower() == 'true',
            'bot_token': os.getenv('ALERT_TELEGRAM_BOT_TOKEN'),
            'chat_id': os.getenv('ALERT_TELEGRAM_CHAT_ID'),
            'min_level': 'warning'
        }
    }
    self.alert_system = create_alert_system(alert_config)
    
    # Регистрируем проверки здоровья
    health_monitor.register_check("database", self._check_database_health)
    health_monitor.register_check("redis", self._check_redis_health)

async def _check_database_health(self):
    """Проверка состояния базы данных"""
    return await health_monitor.check_database(self.db_manager)

async def _check_redis_health(self):
    """Проверка состояния Redis"""
    return await health_monitor.check_redis(self.cache_manager)

# Декорируйте критические методы для измерения производительности:
@measure_time_async("user_registration")
async def register_user(self, user_id: int, username: str = None):
    # ... ваш код ...
    
@measure_time_async("subscription_activation")
async def activate_subscription(self, user_id: int, subscription_type: str):
    # ... ваш код ...
```

## 📈 Команды мониторинга для администратора

Добавьте эти команды в main_bot.py:

```python
@require_admin
async def metrics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /metrics - показать метрики системы"""
    summary = metrics_collector.get_summary(15)  # За последние 15 минут
    
    text = f"📊 **Метрики системы (15 мин)**\n\n"
    text += f"📈 Всего метрик: {summary['total_metrics']}\n"
    text += f"🔢 Уникальных: {summary['unique_metrics']}\n\n"
    
    # Системные метрики
    system = summary['system']['system']
    text += f"💻 **Система:**\n"
    text += f"• CPU: {system['cpu_percent']:.1f}%\n"
    text += f"• RAM: {system['memory_percent']:.1f}%\n"
    text += f"• Disk: {system['disk_percent']:.1f}%\n\n"
    
    # Топ операций
    top_ops = metrics_collector.get_top_operations(5)
    if top_ops:
        text += f"⚡ **Топ операций:**\n"
        for op in top_ops:
            text += f"• {op['operation']}: {op['avg_time']:.3f}s ({op['count']} раз)\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

@require_admin
async def health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /health - проверка состояния системы"""
    results = await health_monitor.run_all_checks()
    overall_status = health_monitor.get_overall_status()
    
    status_emoji = {
        'healthy': '✅',
        'warning': '⚠️', 
        'critical': '🚨',
        'unknown': '❓'
    }
    
    text = f"{status_emoji[overall_status.value]} **Состояние системы: {overall_status.value.upper()}**\n\n"
    
    for name, result in results.items():
        emoji = status_emoji[result.status.value]
        text += f"{emoji} **{name}**: {result.message}\n"
        text += f"   ⏱️ {result.response_time:.3f}s\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

@require_admin
async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /alerts - показать активные алерты"""
    active_alerts = self.alert_system.get_active_alerts()
    stats = self.alert_system.get_alert_stats()
    
    text = f"🚨 **Система алертов**\n\n"
    text += f"📊 Активных: {stats['active_alerts']}\n"
    text += f"⚠️ Warning: {stats['active_by_level']['warning']}\n"
    text += f"🚨 Critical: {stats['active_by_level']['critical']}\n\n"
    
    if active_alerts:
        text += f"**Активные алерты:**\n"
        for alert in active_alerts[-5:]:  # Последние 5
            text += f"• {alert.component}: {alert.message}\n"
    else:
        text += "✅ Активных алертов нет"
    
    await update.message.reply_text(text, parse_mode='Markdown')
```

## 🔍 Мониторинг в действии

### Автоматические метрики:
- **Системные ресурсы**: CPU, RAM, диск каждую минуту
- **Производительность операций**: время выполнения, количество вызовов
- **Ошибки**: количество и типы ошибок
- **Пользовательская активность**: регистрации, подписки, платежи

### Health Checks:
- **База данных**: доступность, время отклика
- **Redis**: состояние кэша, статистика
- **Системные ресурсы**: пороговые значения
- **Процесс**: потребление памяти, количество потоков

### Алерты:
- **Critical**: база недоступна, критическая ошибка, нехватка ресурсов
- **Warning**: медленные запросы, высокая нагрузка, проблемы с кэшем
- **Info**: восстановление после проблем

## 📁 Структура логов:

```
logs/
├── tggift_bot.log          # Основные логи (JSON)
├── tggift_bot.log.1        # Ротированные файлы
├── errors.log              # Только ошибки
├── audit.log               # Аудит действий
├── security.log            # События безопасности
└── payments.log            # Логи платежей
```

## 🔧 Настройка алертов

### Telegram алерты:
1. Создайте отдельного бота для мониторинга
2. Добавьте его в чат/канал для алертов
3. Укажите токен и chat_id в .env

### Email алерты:
1. Настройте SMTP (Gmail, Yandex, etc.)
2. Для Gmail используйте App Password
3. Укажите получателей в конфигурации

### Webhook алерты:
1. Настройте endpoint для приема алертов
2. Обрабатывайте JSON payload с информацией об алерте

## 📊 Интеграция с внешними системами

### Prometheus (опционально):
```python
# Экспорт метрик в формате Prometheus
@app.route('/metrics')
def prometheus_metrics():
    return metrics_collector.export_metrics('prometheus')
```

### Grafana Dashboard:
- Импортируйте метрики из Prometheus
- Создайте дашборды для визуализации
- Настройте алерты на основе метрик

## 🧹 Обслуживание

### Автоматическая очистка:
```python
# Добавьте в cron или как периодическую задачу
async def cleanup_task():
    # Очистка старых метрик (каждый день)
    metrics_collector.clear_old_metrics(24)
    
    # Очистка старых алертов (каждую неделю) 
    alert_system.clear_old_alerts(168)
    
    # Очистка старых логов (каждый месяц)
    enhanced_logger.cleanup_old_logs(30)
```

### Мониторинг дискового пространства:
- Логи ротируются автоматически
- Старые файлы удаляются по расписанию
- Алерты при заполнении диска > 90%

## 📈 Следующие шаги

После внедрения мониторинга:
1. **Анализ метрик** - определение узких мест
2. **Настройка дашбордов** - визуализация данных  
3. **Оптимизация алертов** - уменьшение ложных срабатываний
4. **Масштабирование** - подготовка к росту нагрузки 