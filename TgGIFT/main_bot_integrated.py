#!/usr/bin/env python3
"""
TgGIFT Bot - Полностью интегрированная версия со всеми системами
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# Telegram Bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Наши модули
from config import *

# Кэширование и Redis
from redis_cache import RedisCacheManager
from database_adapter_cached import CachedDatabaseAdapter

# Мониторинг и метрики
from metrics_collector import MetricsCollector, measure_time_async
from health_monitor import HealthMonitor
from alert_system import AlertSystem
from enhanced_logging import setup_enhanced_logging

# Отказоустойчивость
from backup_manager import BackupManager
from graceful_shutdown import GracefulShutdownManager, setup_graceful_shutdown, set_shutdown_manager
from auto_recovery import AutoRecoveryManager, setup_auto_recovery, set_recovery_manager, FailureType
from circuit_breaker import CircuitBreakerManager, setup_database_circuit_breaker, get_circuit_manager

# Безопасность
from encryption_manager import EncryptionManager, set_encryption_manager
from auth_manager import AuthManager, set_auth_manager, require_auth, require_role, UserRole, Permission
from security_audit import SecurityAuditLogger, set_security_audit_logger, SecurityValidationMiddleware

# Масштабирование
from cluster_manager import get_cluster_manager

logger = logging.getLogger(__name__)

class IntegratedTgGiftBot:
    """Полностью интегрированный TgGIFT Bot со всеми системами"""
    
    def __init__(self):
        self.application = None
        
        # Инициализация всех систем
        self.setup_logging()
        self.setup_security()
        self.setup_caching()
        self.setup_monitoring()
        self.setup_resilience()
        
        logger.info("🚀 TgGIFT Bot полностью инициализирован")
    
    def setup_logging(self):
        """Настройка улучшенного логирования"""
        self.enhanced_logger = setup_enhanced_logging(
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            json_format=os.getenv('LOG_JSON_FORMAT', 'false').lower() == 'true',
            max_file_size=int(os.getenv('LOG_MAX_FILE_SIZE', 10)) * 1024 * 1024,
            backup_count=int(os.getenv('LOG_BACKUP_COUNT', 5))
        )
        logger.info("📝 Улучшенное логирование настроено")
    
    def setup_security(self):
        """Настройка системы безопасности"""
        
        # Encryption Manager
        encryption_config = {
            'key_rotation_days': int(os.getenv('KEY_ROTATION_DAYS', 90)),
            'master_key_env': 'MASTER_ENCRYPTION_KEY'
        }
        self.encryption_manager = EncryptionManager(encryption_config)
        set_encryption_manager(self.encryption_manager)
        
        # Auth Manager
        auth_config = {
            'session_timeout_hours': int(os.getenv('SESSION_TIMEOUT_HOURS', 24)),
            'max_sessions_per_user': int(os.getenv('MAX_SESSIONS_PER_USER', 5)),
            'max_login_attempts': int(os.getenv('MAX_LOGIN_ATTEMPTS', 5)),
            'lockout_duration_minutes': int(os.getenv('LOCKOUT_DURATION_MINUTES', 15))
        }
        self.auth_manager = AuthManager(auth_config)
        set_auth_manager(self.auth_manager)
        
        # Security Audit Logger
        audit_config = {
            'log_file_path': os.getenv('SECURITY_LOG_FILE', 'security_audit.log'),
            'max_events_in_memory': int(os.getenv('MAX_EVENTS_IN_MEMORY', 10000)),
            'retention_days': int(os.getenv('AUDIT_RETENTION_DAYS', 90))
        }
        self.security_logger = SecurityAuditLogger(audit_config)
        set_security_audit_logger(self.security_logger)
        
        # Validation Middleware
        self.security_validator = SecurityValidationMiddleware(self.security_logger)
        
        logger.info("🔐 Система безопасности инициализирована")
    
    def setup_caching(self):
        """Настройка кэширования"""
        
        # Redis Cache Manager
        redis_config = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'db': int(os.getenv('REDIS_DB', 0)),
            'password': os.getenv('REDIS_PASSWORD'),
            'key_prefix': os.getenv('REDIS_KEY_PREFIX', 'tggift')
        }
        
        cache_config = {
            'default_ttl': int(os.getenv('CACHE_DEFAULT_TTL', 3600)),
            'user_data_ttl': int(os.getenv('CACHE_USER_DATA_TTL', 1800)),
            'subscription_ttl': int(os.getenv('CACHE_SUBSCRIPTION_TTL', 300))
        }
        
        self.cache_manager = RedisCacheManager(redis_config, cache_config)
        
        # Кэшированный адаптер базы данных
        from database_adapter_simple import DatabaseAdapterSimple
        base_adapter = DatabaseAdapterSimple()
        self.db_adapter = CachedDatabaseAdapter(base_adapter, self.cache_manager)
        
        logger.info("💾 Система кэширования инициализирована")
    
    def setup_monitoring(self):
        """Настройка мониторинга"""
        
        # Metrics Collector
        self.metrics_collector = MetricsCollector()
        
        # Health Monitor
        self.health_monitor = HealthMonitor()
        
        # Регистрируем health checks
        self.health_monitor.register_check("database", self.db_adapter.health_check)
        self.health_monitor.register_check("redis", self.cache_manager.health_check)
        
        # Alert System
        alert_config = {
            'telegram_chat_id': os.getenv('ALERT_TELEGRAM_CHAT_ID'),
            'telegram_token': os.getenv('ALERT_TELEGRAM_TOKEN'),
            'email_smtp_host': os.getenv('ALERT_EMAIL_SMTP_HOST'),
            'email_smtp_port': int(os.getenv('ALERT_EMAIL_SMTP_PORT', 587)),
            'email_user': os.getenv('ALERT_EMAIL_USER'),
            'email_password': os.getenv('ALERT_EMAIL_PASSWORD'),
            'email_to': os.getenv('ALERT_EMAIL_TO'),
            'webhook_url': os.getenv('ALERT_WEBHOOK_URL'),
            'cooldown_minutes': int(os.getenv('ALERT_COOLDOWN_MINUTES', 15))
        }
        self.alert_system = AlertSystem(alert_config)
        
        logger.info("📊 Система мониторинга инициализирована")
    
    def setup_resilience(self):
        """Настройка отказоустойчивости"""
        
        # Backup Manager
        backup_config = {
            'backup_dir': os.getenv('BACKUP_DIR', './backups'),
            'retention_days': int(os.getenv('BACKUP_RETENTION_DAYS', 30)),
            'compression': os.getenv('BACKUP_COMPRESSION', 'gzip'),
            'daily_hour': int(os.getenv('BACKUP_DAILY_HOUR', 2)),
            'weekly_day': int(os.getenv('BACKUP_WEEKLY_DAY', 0)),
            'monthly_day': int(os.getenv('BACKUP_MONTHLY_DAY', 1))
        }
        self.backup_manager = BackupManager(backup_config)
        
        # Auto Recovery Manager
        recovery_config = {
            'failure_window_minutes': int(os.getenv('FAILURE_WINDOW_MINUTES', 10)),
            'max_failures_per_window': int(os.getenv('MAX_FAILURES_PER_WINDOW', 5))
        }
        self.recovery_manager = setup_auto_recovery(recovery_config)
        set_recovery_manager(self.recovery_manager)
        
        # Circuit Breaker Manager
        circuit_config = {
            'failure_threshold': int(os.getenv('DEFAULT_FAILURE_THRESHOLD', 5)),
            'success_threshold': int(os.getenv('DEFAULT_SUCCESS_THRESHOLD', 3)),
            'timeout': int(os.getenv('DEFAULT_TIMEOUT', 60))
        }
        self.circuit_manager = CircuitBreakerManager()
        self.db_circuit_breaker = setup_database_circuit_breaker(circuit_config)
        
        # Graceful Shutdown Manager
        shutdown_config = {
            'graceful_timeout': int(os.getenv('GRACEFUL_SHUTDOWN_TIMEOUT', 30)),
            'force_timeout': int(os.getenv('FORCE_SHUTDOWN_TIMEOUT', 60))
        }
        self.shutdown_manager = setup_graceful_shutdown(
            shutdown_config, 
            self.get_app_state
        )
        set_shutdown_manager(self.shutdown_manager)
        
        logger.info("🛡️ Система отказоустойчивости инициализирована")
    
    async def initialize(self):
        """Асинхронная инициализация"""
        
        # Инициализация кэша
        await self.cache_manager.init()
        
        # Инициализация базы данных
        await self.db_adapter.init_cache()
        
        # Создание Telegram Application
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Регистрация handlers
        self.register_handlers()
        
        logger.info("✅ Асинхронная инициализация завершена")
    
    def register_handlers(self):
        """Регистрация обработчиков команд"""
        
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("profile", self.profile_command))
        
        # VIP команды
        self.application.add_handler(CommandHandler("vip", self.vip_command))
        self.application.add_handler(CommandHandler("grantvip", self.grant_vip_command))
        
        # Административные команды
        self.application.add_handler(CommandHandler("metrics", self.metrics_command))
        self.application.add_handler(CommandHandler("health", self.health_command))
        self.application.add_handler(CommandHandler("alerts", self.alerts_command))
        
        # Команды безопасности
        self.application.add_handler(CommandHandler("security", self.security_status_command))
        self.application.add_handler(CommandHandler("events", self.security_events_command))
        
        # Команды отказоустойчивости
        self.application.add_handler(CommandHandler("backup", self.backup_command))
        self.application.add_handler(CommandHandler("backups", self.backups_command))
        self.application.add_handler(CommandHandler("recovery_status", self.recovery_status_command))
        self.application.add_handler(CommandHandler("circuit_breakers", self.circuit_breakers_command))
        
        # Команды кластера
        self.application.add_handler(CommandHandler("cluster", self.cluster_status_command))
        self.application.add_handler(CommandHandler("scale", self.scale_workers_command))
        self.application.add_handler(CommandHandler("queues", self.queue_stats_command))
        
        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Message handler с валидацией
        self.application.add_handler(MessageHandler(filters.TEXT, self.message_handler))
        
        logger.info("🔧 Обработчики команд зарегистрированы")
    
    # =============================================================================
    # ОСНОВНЫЕ КОМАНДЫ
    # =============================================================================
    
    @measure_time_async
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        
        # Получаем данные пользователя (с кэшированием)
        user_data = await self.db_adapter.get_user(user_id)
        
        if not user_data:
            # Создаем нового пользователя
            user_data = {
                'user_id': user_id,
                'username': update.effective_user.username,
                'first_name': update.effective_user.first_name,
                'is_vip': False,
                'balance': 0,
                'created_at': datetime.now()
            }
            await self.db_adapter.save_user(user_data)
            
            welcome_text = (
                "🎉 Добро пожаловать в TgGIFT Bot!\n\n"
                "🎁 Здесь вы можете:\n"
                "• Отправлять подарки друзьям\n"
                "• Получать VIP статус\n"
                "• Управлять балансом\n\n"
                "Используйте /help для получения списка команд"
            )
        else:
            welcome_text = f"👋 С возвращением, {user_data.get('first_name', 'друг')}!\n\n"
            if user_data.get('is_vip'):
                welcome_text += "⭐ У вас VIP статус!\n"
            welcome_text += f"💰 Баланс: {user_data.get('balance', 0)} ⭐"
        
        await update.message.reply_text(welcome_text)
        
        # Записываем метрику
        self.metrics_collector.increment('commands.start')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = (
            "📋 **Доступные команды:**\n\n"
            "👤 **Основные:**\n"
            "• /start - Начать работу с ботом\n"
            "• /profile - Ваш профиль\n"
            "• /help - Эта справка\n\n"
            "⭐ **VIP:**\n"
            "• /vip - VIP функции\n\n"
            "🔧 **Для администраторов:**\n"
            "• /metrics - Метрики системы\n"
            "• /health - Состояние здоровья\n"
            "• /security - Статус безопасности\n"
            "• /cluster - Статус кластера\n"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /profile"""
        user_id = update.effective_user.id
        user_data = await self.db_adapter.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text("❌ Пользователь не найден. Используйте /start")
            return
        
        profile_text = f"👤 **Ваш профиль**\n\n"
        profile_text += f"🆔 ID: {user_id}\n"
        profile_text += f"👋 Имя: {user_data.get('first_name', 'Не указано')}\n"
        profile_text += f"💰 Баланс: {user_data.get('balance', 0)} ⭐\n"
        
        if user_data.get('is_vip'):
            profile_text += "⭐ Статус: VIP\n"
            
            # Получаем данные подписки
            subscription = await self.db_adapter.get_user_subscription(user_id)
            if subscription:
                profile_text += f"📅 VIP до: {subscription.get('expires_at', 'Не указано')}\n"
        else:
            profile_text += "👤 Статус: Обычный пользователь\n"
        
        await update.message.reply_text(profile_text, parse_mode='Markdown')
    
    # =============================================================================
    # VIP КОМАНДЫ
    # =============================================================================
    
    @require_role(UserRole.VIP)
    async def vip_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vip - VIP функции"""
        keyboard = [
            [InlineKeyboardButton("💰 Пополнить баланс", callback_data="vip_topup")],
            [InlineKeyboardButton("🎁 Отправить подарок", callback_data="vip_gift")],
            [InlineKeyboardButton("📊 Статистика", callback_data="vip_stats")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⭐ **VIP Панель**\n\nВыберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    @require_role(UserRole.ADMIN)
    async def grant_vip_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /grantvip - выдача VIP статуса"""
        if not context.args:
            await update.message.reply_text(
                "❌ Использование: /grantvip <user_id> [дни]\n"
                "Пример: /grantvip 123456789 30"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            days = int(context.args[1]) if len(context.args) > 1 else 30
            
            # Активируем подписку
            success = await self.db_adapter.activate_subscription(target_user_id, days)
            
            if success:
                await update.message.reply_text(
                    f"✅ VIP статус выдан пользователю {target_user_id} на {days} дней"
                )
            else:
                await update.message.reply_text("❌ Ошибка при выдаче VIP статуса")
                
        except ValueError:
            await update.message.reply_text("❌ Некорректный формат. Используйте числа.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    # =============================================================================
    # АДМИНИСТРАТИВНЫЕ КОМАНДЫ
    # =============================================================================
    
    @require_role(UserRole.ADMIN)
    async def metrics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /metrics - метрики системы"""
        
        metrics_summary = self.metrics_collector.get_summary()
        system_metrics = self.metrics_collector.get_system_metrics()
        
        text = f"📊 **Метрики системы**\n\n"
        
        # Системные метрики
        text += f"🖥️ **Система:**\n"
        text += f"• CPU: {system_metrics['cpu_percent']:.1f}%\n"
        text += f"• Память: {system_metrics['memory_percent']:.1f}%\n"
        text += f"• Диск: {system_metrics['disk_percent']:.1f}%\n\n"
        
        # Метрики приложения
        text += f"📈 **Приложение:**\n"
        text += f"• Всего операций: {metrics_summary['total_operations']}\n"
        text += f"• Ошибок: {metrics_summary['total_errors']}\n"
        
        if metrics_summary['top_operations']:
            text += f"\n🔝 **Топ операций:**\n"
            for op, count in metrics_summary['top_operations'][:5]:
                text += f"• {op}: {count}\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    @require_role(UserRole.ADMIN)
    async def health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /health - состояние здоровья системы"""
        
        health_results = await self.health_monitor.run_all_checks()
        overall_status = self.health_monitor.get_overall_status(health_results)
        
        status_emoji = "✅" if overall_status == "healthy" else "❌"
        text = f"{status_emoji} **Состояние системы: {overall_status}**\n\n"
        
        for check_name, result in health_results.items():
            emoji = "✅" if result.is_healthy else "❌"
            text += f"{emoji} **{check_name}**: {result.status.value}\n"
            
            if result.message:
                text += f"   └ {result.message}\n"
            
            if result.response_time:
                text += f"   └ Время отклика: {result.response_time:.2f}s\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    @require_role(UserRole.ADMIN)
    async def security_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /security - статус безопасности"""
        
        # Статистика шифрования
        encryption_stats = self.encryption_manager.get_encryption_stats()
        
        # Статистика аутентификации
        auth_stats = self.auth_manager.get_auth_stats()
        
        # Сводка безопасности
        security_summary = self.security_logger.get_security_summary(hours=24)
        
        text = f"🔐 **Статус безопасности**\n\n"
        
        text += f"🔑 **Шифрование:**\n"
        text += f"• Активных ключей: {encryption_stats['active_keys']}\n"
        text += f"• Истекших ключей: {encryption_stats['expired_keys']}\n"
        text += f"• Ротация каждые: {encryption_stats['key_rotation_days']} дней\n\n"
        
        text += f"👤 **Аутентификация:**\n"
        text += f"• Активных сессий: {auth_stats['active_sessions']}\n"
        text += f"• Успешность входа: {auth_stats['success_rate']:.1f}%\n"
        text += f"• Заблокированных пользователей: {auth_stats['locked_users']}\n\n"
        
        text += f"📊 **События безопасности (24ч):**\n"
        text += f"• Всего событий: {security_summary['total_events']}\n"
        text += f"• Критических: {security_summary['critical_events_count']}\n"
        text += f"• Топ IP: {security_summary['top_ips'][0][0] if security_summary['top_ips'] else 'N/A'}\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    # =============================================================================
    # КОМАНДЫ КЛАСТЕРА
    # =============================================================================
    
    @require_role(UserRole.ADMIN)
    async def cluster_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /cluster - статус кластера"""
        cluster_manager = get_cluster_manager()
        
        if not cluster_manager:
            await update.message.reply_text("❌ Кластер не инициализирован")
            return
        
        status = cluster_manager.get_cluster_status()
        
        text = f"🚀 **Статус кластера**\n\n"
        
        # Load Balancer
        lb_stats = status['load_balancer']
        text += f"⚖️ **Load Balancer**\n"
        text += f"• Стратегия: {lb_stats['strategy']}\n"
        text += f"• Воркеров: {lb_stats['healthy_workers']}/{lb_stats['total_workers']}\n"
        text += f"• Соединений: {lb_stats['total_connections']}\n"
        text += f"• Успешность: {lb_stats['success_rate_percent']}%\n\n"
        
        # Workers
        worker_stats = status['workers']['summary']
        text += f"👷 **Воркеры**\n"
        text += f"• Запущено: {worker_stats['running_workers']}/{worker_stats['total_workers']}\n"
        text += f"• CPU: {worker_stats['avg_cpu_usage']:.1f}%\n"
        text += f"• Память: {worker_stats['total_memory_mb']:.1f} MB\n\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    # =============================================================================
    # ОБРАБОТЧИКИ
    # =============================================================================
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "vip_topup":
            await query.edit_message_text("💰 Функция пополнения баланса в разработке")
        elif data == "vip_gift":
            await query.edit_message_text("🎁 Функция отправки подарков в разработке")
        elif data == "vip_stats":
            await query.edit_message_text("📊 Статистика VIP пользователя в разработке")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        
        # Валидация безопасности
        if not await self.security_validator.validate_message(update, context):
            return  # Сообщение заблокировано
        
        # Обычная обработка сообщения
        await update.message.reply_text(
            "👋 Привет! Используйте команды для взаимодействия с ботом.\n"
            "Наберите /help для получения списка доступных команд."
        )
    
    # =============================================================================
    # УТИЛИТЫ
    # =============================================================================
    
    async def handle_database_error(self, error: Exception, operation: str):
        """Обработка ошибок базы данных с auto-recovery"""
        logger.error(f"Ошибка базы данных в операции {operation}: {error}")
        
        # Сообщаем в систему восстановления
        self.recovery_manager.report_failure(
            component="database",
            failure_type=FailureType.DATABASE_ERROR,
            error_message=str(error),
            metadata={'operation': operation}
        )
    
    def get_app_state(self) -> Dict[str, Any]:
        """Получение состояния приложения для graceful shutdown"""
        return {
            'active_users': len(self.auth_manager.active_sessions),
            'cache_keys': len(self.cache_manager._client) if hasattr(self.cache_manager, '_client') else 0,
            'uptime_seconds': (datetime.now() - datetime.now()).total_seconds(),  # Заглушка
            'last_backup': getattr(self.backup_manager, 'last_backup_time', None)
        }
    
    async def run(self):
        """Запуск бота"""
        try:
            await self.initialize()
            
            logger.info("🚀 Запуск TgGIFT Bot...")
            await self.application.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            raise
        finally:
            # Graceful shutdown
            if self.shutdown_manager:
                await self.shutdown_manager.shutdown()
            
            # Закрываем соединения
            if self.cache_manager:
                await self.cache_manager.close()

async def main():
    """Главная функция"""
    bot = IntegratedTgGiftBot()
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Завершение работы бота...")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        exit(1) 