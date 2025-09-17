# Система отказоустойчивости для TgGIFT Bot

## 🛡️ Обзор системы

Комплексная система отказоустойчивости включает:
- **Автоматические бэкапы** - PostgreSQL с восстановлением
- **Graceful shutdown** - корректное завершение работы
- **Auto recovery** - автовосстановление после сбоев
- **Circuit breaker** - предотвращение каскадных сбоев

## 📋 Компоненты системы

### 1. 💾 Система бэкапов PostgreSQL

**Возможности:**
- Автоматические полные и инкрементальные бэкапы
- Сжатие и шифрование (опционально)
- Проверка целостности
- Восстановление с подтверждением
- Очистка старых бэкапов
- Загрузка в удаленное хранилище

**Типы бэкапов:**
- `full` - полный бэкап базы данных
- `schema_only` - только структура
- `data_only` - только данные

### 2. 🔄 Graceful Shutdown

**Возможности:**
- Корректное завершение всех компонентов
- Приоритизация задач завершения
- Таймауты и принудительное завершение
- Сохранение состояния приложения
- Обработка системных сигналов

### 3. 🚀 Автовосстановление

**Возможности:**
- Автоматическое обнаружение сбоев
- Стратегии восстановления по типам сбоев
- Exponential backoff
- Обнаружение "шторма сбоев"
- Эскалация критических проблем

### 4. ⚡ Circuit Breaker

**Возможности:**
- Предотвращение каскадных сбоев
- Три состояния: Closed/Open/Half-Open
- Fallback функции
- Статистика и мониторинг
- Декораторы для простого использования

## 🚀 Установка и настройка

### 1. Добавьте в .env конфигурацию:

```env
# Бэкапы PostgreSQL
BACKUP_ENABLED=true
BACKUP_DIR=./backups
BACKUP_RETENTION_DAYS=30
BACKUP_COMPRESSION=true
BACKUP_DAILY_HOUR=2
BACKUP_WEEKLY_DAY=6
BACKUP_MONTHLY_DAY=1

# Graceful Shutdown
GRACEFUL_SHUTDOWN_TIMEOUT=30
FORCE_SHUTDOWN_TIMEOUT=10

# Auto Recovery
AUTO_RECOVERY_ENABLED=true
FAILURE_WINDOW_MINUTES=60
MAX_FAILURES_PER_WINDOW=10

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
DEFAULT_FAILURE_THRESHOLD=5
DEFAULT_SUCCESS_THRESHOLD=3
DEFAULT_TIMEOUT=60
```

### 2. Интегрируйте с main_bot.py:

```python
from backup_manager import BackupManager
from graceful_shutdown import setup_graceful_shutdown, set_shutdown_manager
from auto_recovery import setup_auto_recovery, set_recovery_manager, FailureType
from circuit_breaker import get_circuit_manager, setup_database_circuit_breaker

class TgGiftBot:
    def __init__(self):
        # ... существующий код ...
        
        # Настройка системы бэкапов
        backup_config = {
            'db_host': os.getenv('DB_HOST', 'localhost'),
            'db_port': int(os.getenv('DB_PORT', 5432)),
            'db_name': os.getenv('DB_NAME', 'tggift'),
            'db_user': os.getenv('DB_USER', 'tggift_user'),
            'db_password': os.getenv('DB_PASSWORD'),
            'backup_dir': os.getenv('BACKUP_DIR', './backups'),
            'retention_days': int(os.getenv('BACKUP_RETENTION_DAYS', 30)),
            'compression': os.getenv('BACKUP_COMPRESSION', 'true').lower() == 'true'
        }
        self.backup_manager = BackupManager(backup_config)
        
        # Настройка автовосстановления
        app_components = {
            'db_manager': self.db_manager,
            'cache_manager': self.cache_manager
        }
        self.recovery_manager = setup_auto_recovery(app_components)
        set_recovery_manager(self.recovery_manager)
        
        # Настройка Circuit Breakers
        self.db_circuit_breaker = setup_database_circuit_breaker(self.db_manager)
        
        # Настройка graceful shutdown
        app_components.update({
            'telegram_bot': self.application,
            'app_state': self.get_app_state()
        })
        self.shutdown_manager = setup_graceful_shutdown(app_components)
        set_shutdown_manager(self.shutdown_manager)
        
        logger.info("Системы отказоустойчивости инициализированы")
    
    def get_app_state(self) -> Dict[str, Any]:
        """Получение состояния приложения для сохранения"""
        return {
            'active_users': len(self.active_users) if hasattr(self, 'active_users') else 0,
            'total_payments': self.total_payments if hasattr(self, 'total_payments') else 0,
            'startup_time': self.startup_time.isoformat() if hasattr(self, 'startup_time') else None
        }
    
    async def handle_database_error(self, error: Exception):
        """Обработка ошибок базы данных с автовосстановлением"""
        
        # Определяем тип сбоя
        if "connection" in str(error).lower():
            failure_type = FailureType.CONNECTION_LOST
        elif "timeout" in str(error).lower():
            failure_type = FailureType.TIMEOUT
        else:
            failure_type = FailureType.UNKNOWN_ERROR
        
        # Сообщаем о сбое системе автовосстановления
        recovery_success = await self.recovery_manager.report_failure(
            'database',
            failure_type,
            str(error),
            {'function': 'database_operation', 'timestamp': datetime.now().isoformat()}
        )
        
        if not recovery_success:
            logger.critical("Автовосстановление базы данных не удалось")
            # Здесь можно добавить дополнительную логику
```

### 3. Добавьте команды администратора:

```python
@require_admin
async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /backup - создать бэкап"""
    args = context.args
    backup_type = args[0] if args else 'full'
    
    if backup_type not in ['full', 'schema_only', 'data_only']:
        await update.message.reply_text("❌ Неверный тип бэкапа. Используйте: full, schema_only, data_only")
        return
    
    await update.message.reply_text(f"🔄 Создаю {backup_type} бэкап...")
    
    try:
        result = await self.backup_manager.create_backup(
            backup_type=backup_type,
            description=f"Ручной бэкап по команде администратора"
        )
        
        if result['status'] == 'completed':
            text = f"✅ **Бэкап создан успешно**\n\n"
            text += f"📁 Файл: `{result['name']}`\n"
            text += f"💾 Размер: {result['file_size_mb']} MB\n"
            text += f"⏱️ Время: {result['duration']:.2f}s\n"
            text += f"🗜️ Сжат: {'Да' if result.get('compressed') else 'Нет'}"
        else:
            text = f"❌ **Ошибка создания бэкапа**\n\n"
            text += f"Причина: {result.get('error', 'Неизвестная ошибка')}"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Критическая ошибка: {str(e)}")

@require_admin
async def backups_list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /backups - список бэкапов"""
    backups = await self.backup_manager.list_backups(limit=10)
    
    if not backups:
        await update.message.reply_text("📂 Бэкапы не найдены")
        return
    
    text = f"📂 **Последние бэкапы:**\n\n"
    
    for backup in backups:
        status_emoji = "✅" if backup.get('status') == 'completed' else "❌"
        text += f"{status_emoji} `{backup['name']}`\n"
        text += f"   💾 {backup['file_size_mb']} MB\n"
        text += f"   📅 {backup['created'][:19].replace('T', ' ')}\n\n"
    
    stats = self.backup_manager.get_backup_stats()
    text += f"📊 **Статистика:**\n"
    text += f"• Всего бэкапов: {stats['total_backups']}\n"
    text += f"• Общий размер: {stats['total_size_mb']} MB\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

@require_admin
async def recovery_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /recovery - статус автовосстановления"""
    stats = self.recovery_manager.get_recovery_stats()
    
    text = f"🚀 **Автовосстановление**\n\n"
    text += f"📊 Всего сбоев: {stats['total_failures']}\n"
    text += f"✅ Восстановлено: {stats['successful_recoveries']}\n"
    text += f"❌ Не удалось: {stats['failed_recoveries']}\n"
    text += f"🚨 Эскалаций: {stats['escalations']}\n"
    text += f"📈 Успешность: {stats['success_rate_percent']}%\n\n"
    
    text += f"🔧 Активных восстановлений: {stats['active_recoveries']}\n"
    text += f"📦 Зарегистрированных компонентов: {stats['registered_components']}\n"
    
    # Показываем статус компонентов
    for component in ['database', 'cache']:
        status = self.recovery_manager.get_component_status(component)
        if 'error' not in status:
            status_emoji = {'healthy': '✅', 'failed': '❌', 'recovered': '🔄'}.get(status['status'], '❓')
            text += f"\n{status_emoji} **{component}**: {status['status']}"
            if status['recent_failures_1h'] > 0:
                text += f" ({status['recent_failures_1h']} сбоев за час)"
    
    await update.message.reply_text(text, parse_mode='Markdown')

@require_admin
async def circuit_breakers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /circuits - статус Circuit Breakers"""
    circuit_manager = get_circuit_manager()
    stats = circuit_manager.get_all_stats()
    
    text = f"⚡ **Circuit Breakers**\n\n"
    text += f"📊 Всего: {stats['summary']['total_breakers']}\n"
    text += f"🚨 Открытых: {stats['summary']['open_breakers']}\n"
    text += f"🔄 Тестирования: {stats['summary']['half_open_breakers']}\n"
    text += f"✅ Здоровых: {stats['summary']['healthy_breakers']}\n\n"
    
    for name, cb_stats in stats['circuit_breakers'].items():
        state_emoji = {'closed': '✅', 'open': '🚨', 'half_open': '🔄'}
        emoji = state_emoji.get(cb_stats['state'], '❓')
        
        text += f"{emoji} **{name}**: {cb_stats['state']}\n"
        text += f"   📞 Вызовов: {cb_stats['total_calls']}\n"
        text += f"   📈 Успешность: {cb_stats['success_rate_percent']}%\n"
        if cb_stats['avg_response_time_ms'] > 0:
            text += f"   ⏱️ Среднее время: {cb_stats['avg_response_time_ms']}ms\n"
        text += "\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')
```

## 🔧 Использование декораторов

### Circuit Breaker декоратор:

```python
from circuit_breaker import circuit_breaker

@circuit_breaker("telegram_api", failure_threshold=3, timeout=30.0)
async def send_telegram_message(chat_id: int, text: str):
    """Отправка сообщения через Telegram API с защитой"""
    # Ваш код отправки сообщения
    pass

@circuit_breaker("payment_processing", failure_threshold=2, timeout=60.0,
                fallback_func=lambda *args: {"status": "queued", "fallback": True})
async def process_payment(user_id: int, amount: float):
    """Обработка платежа с fallback"""
    # Ваш код обработки платежа
    pass
```

### Автовосстановление:

```python
from auto_recovery import get_recovery_manager, FailureType

async def database_operation():
    try:
        # Операция с базой данных
        result = await db.execute("SELECT * FROM users")
        return result
    except Exception as e:
        # Сообщаем о сбое
        recovery_manager = get_recovery_manager()
        if recovery_manager:
            await recovery_manager.report_failure(
                'database',
                FailureType.CONNECTION_LOST,
                str(e)
            )
        raise
```

## 📊 Мониторинг отказоустойчивости

### Ключевые метрики:

1. **Бэкапы:**
   - Успешность создания бэкапов
   - Размер бэкапов
   - Время создания
   - Доступность для восстановления

2. **Автовосстановление:**
   - Количество сбоев по компонентам
   - Успешность восстановления
   - Время восстановления
   - Частота эскалаций

3. **Circuit Breakers:**
   - Состояние всех breakers
   - Частота срабатываний
   - Использование fallback
   - Время восстановления

### Алерты:

- 🚨 **Critical**: Сбой автовосстановления, открытие критического Circuit Breaker
- ⚠️ **Warning**: Частые сбои, медленное восстановление
- ℹ️ **Info**: Успешное восстановление, создание бэкапа

## 🧪 Тестирование отказоустойчивости

### 1. Тест бэкапов:

```bash
# Создание тестового бэкапа
/backup full

# Проверка целостности
python -c "
from backup_manager import BackupManager
import asyncio

async def test():
    bm = BackupManager({'db_host': 'localhost', ...})
    backups = await bm.list_backups(1)
    if backups:
        result = await bm.verify_backup(backups[0]['file_path'])
        print(f'Проверка: {result}')

asyncio.run(test())
"
```

### 2. Тест автовосстановления:

```python
# Симуляция сбоя базы данных
async def test_db_failure():
    recovery_manager = get_recovery_manager()
    
    # Имитируем сбой
    success = await recovery_manager.report_failure(
        'database',
        FailureType.CONNECTION_LOST,
        'Test connection failure'
    )
    
    print(f"Восстановление: {'успешно' if success else 'не удалось'}")
```

### 3. Тест Circuit Breaker:

```python
@circuit_breaker("test_service", failure_threshold=2, timeout=5.0)
async def failing_service():
    raise ConnectionError("Service unavailable")

# Тестируем
for i in range(5):
    try:
        await failing_service()
    except Exception as e:
        print(f"Попытка {i+1}: {e}")
```

## 🚨 План действий при сбоях

### Критический сбой базы данных:

1. **Автоматически**: Система попытается переподключиться
2. **При неудаче**: Переход в режим только чтения
3. **Администратор**: Получает критический алерт
4. **Восстановление**: Из последнего бэкапа при необходимости

### Каскадный сбой:

1. **Circuit Breakers**: Изолируют проблемные компоненты
2. **Fallback**: Активируются резервные функции
3. **Graceful degradation**: Система работает с ограниченным функционалом
4. **Мониторинг**: Отслеживает восстановление компонентов

### Полный отказ системы:

1. **Graceful shutdown**: Корректное сохранение состояния
2. **Бэкапы**: Автоматическое создание экстренного бэкапа
3. **Восстановление**: Из последнего валидного состояния
4. **Анализ**: Детальное логирование причин сбоя

## 📈 Оптимизация производительности

### Рекомендации:

1. **Бэкапы**: Запускайте в низконагруженное время (ночью)
2. **Circuit Breakers**: Настройте пороги под вашу нагрузку
3. **Автовосстановление**: Используйте exponential backoff
4. **Мониторинг**: Регулярно анализируйте метрики

### Настройки для высоконагруженных систем:

```env
# Более агрессивные настройки
BACKUP_RETENTION_DAYS=7  # Меньше хранения
DEFAULT_FAILURE_THRESHOLD=10  # Больше терпимости к сбоям
DEFAULT_TIMEOUT=30  # Быстрее восстановление
MAX_FAILURES_PER_WINDOW=20  # Больше сбоев до эскалации
```

---

**Система отказоустойчивости готова обеспечить стабильную работу вашего бота в любых условиях!** 🛡️

Следующий этап: **Горизонтальное масштабирование** с load balancer и очередями сообщений. 