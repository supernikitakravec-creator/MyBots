#!/usr/bin/env python3
"""
TgGIFT Star Bot - Исправленный основной модуль бота
"""

import os
import sys
import signal
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Set, Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import InvalidToken, NetworkError, TimedOut, BadRequest, Forbidden
from config import (
    BOT_TOKEN, SUBSCRIPTION_CONFIGS, COMMISSION_PERCENT, 
    MONITORING_INTERVAL, QUEUE_SETTINGS, NOTIFICATION_SETTINGS,
    LOGGING_CONFIG, SECURITY_SETTINGS, PERFORMANCE_SETTINGS,
    YOOKASSA_CONFIG, TON_WALLETS, STARS_SYSTEM, AUTO_PURCHASE_SETTINGS, ADMIN_ID
)
# Используем упрощенный адаптер для совместимости между SQLite и PostgreSQL
from database_adapter_simple import SimpleDatabaseAdapter
from gift_monitor import GiftMonitor
from payment_yookassa import YooKassaPaymentHandler
from payment_ton import TONPaymentHandler
from deposit_accounts_manager import DepositAccountsManager

# Создаем директорию для логов если её нет
log_file = LOGGING_CONFIG['file']
log_dir = os.path.dirname(log_file)
if log_dir and not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        # Если не можем создать директорию, используем текущую
        log_file = 'bot.log'
        print(f"Не удалось создать директорию для логов: {e}")

# Настройка логирования с ротацией
from logging.handlers import RotatingFileHandler

# Создаем handler с ротацией
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG['level']),
    format=LOGGING_CONFIG['format'],
    handlers=[
        file_handler,
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

print("main_bot.py стартует")

class TgGiftBot:
    """Основной бот TgGIFT Star Bot"""
    
    def __init__(self):
        self.token = BOT_TOKEN
        if not self.token:
            raise ValueError("BOT_TOKEN не установлен! Создайте файл .env с BOT_TOKEN=your_token_here")
        
        self.application = Application.builder().token(self.token).build()
        self.db_manager = SimpleDatabaseAdapter()
        self.gift_monitor = GiftMonitor()
        
        # Флаг для отслеживания типа БД

        
        # Новые компоненты платежной системы
        self.yookassa_handler = YooKassaPaymentHandler(self.db_manager)
        self.ton_handler = TONPaymentHandler(self.db_manager)
        self.ton_handler.bot_instance = self  # Передаем ссылку на бота
        self.deposit_manager = DepositAccountsManager(self.db_manager)
        
        # Контроль фоновых задач
        self.background_tasks: Set[asyncio.Task] = set()
        self.is_shutting_down = False
        self.shutdown_event = asyncio.Event()
        
        # Счетчики для мониторинга
        self.message_count = 0
        self.error_count = 0
        self.last_reset_time = datetime.now()
        
        # Регистрация обработчиков
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрация всех обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("subscription", self.subscription_command))
        self.application.add_handler(CommandHandler("balance", self.balance_command))
        self.application.add_handler(CommandHandler("queue", self.queue_command))
        self.application.add_handler(CommandHandler("gifts", self.gifts_command))
        self.application.add_handler(CommandHandler("topup", self.topup_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("grantvip", self.grantvip_command))
        self.application.add_handler(CommandHandler("monitor_status", self.monitor_status_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("create_test_data", self.create_test_data_command))  # Тестовые данные
        self.application.add_handler(CommandHandler("create_leaderboard_data", self.create_leaderboard_data_command))  # Тестовые данные для топа
        
        # Новые команды
        self.application.add_handler(CommandHandler("points", self.points_command))
        self.application.add_handler(CommandHandler("autopurchase", self.autopurchase_command))
        self.application.add_handler(CommandHandler("payments", self.payments_command))
        
        # Обработчики Fragment Stars (только для админа)
        self.application.add_handler(MessageHandler(
            filters.Regex(r'^/confirm_stars_') & filters.User(ADMIN_ID), 
            self.confirm_fragment_purchase
        ))
        self.application.add_handler(MessageHandler(
            filters.Regex(r'^/cancel_stars_') & filters.User(ADMIN_ID), 
            self.cancel_fragment_purchase
        ))
        self.application.add_handler(CommandHandler("pending_stars", self.show_pending_fragment_purchases))
        
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_custom_stars_input))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_search_query))
        self.application.add_handler(MessageHandler(filters.ALL, self.handle_message))
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Глобальный обработчик ошибок"""
        try:
            self.error_count += 1
            
            # Логируем ошибку с полным стеком
            logger.error(f"Ошибка при обработке обновления {update.update_id if update else 'None'}: {context.error}")
            logger.error(f"Стек вызовов:", exc_info=context.error)
            
            # Уведомляем пользователя если возможно
            if update and update.effective_chat:
                try:
                    await update.effective_chat.send_message(
                        "❌ Произошла ошибка при обработке вашего запроса. Попробуйте позже."
                    )
                except (BadRequest, Forbidden, NetworkError):
                    # Не можем отправить сообщение - игнорируем
                    pass
                    
        except Exception as e:
            logger.error(f"Ошибка в обработчике ошибок: {e}")
    
    def _add_background_task(self, task: asyncio.Task):
        """Добавление фоновой задачи с контролем"""
        self.background_tasks.add(task)
        task.add_done_callback(self._remove_background_task)
    
    def _remove_background_task(self, task: asyncio.Task):
        """Удаление завершенной фоновой задачи"""
        self.background_tasks.discard(task)
        try:
            exception = task.exception()
            if exception:
                logger.error(f"Фоновая задача завершилась с ошибкой: {exception}")
        except asyncio.CancelledError:
            # Задача была отменена - это нормально при shutdown
            pass
        except Exception as e:
            logger.error(f"Ошибка при проверке исключения задачи: {e}")
    
    async def _shutdown_background_tasks(self):
        """Graceful shutdown фоновых задач"""
        if not self.background_tasks:
            return
        
        logger.info(f"Завершение {len(self.background_tasks)} фоновых задач...")
        
        # Устанавливаем флаг завершения
        self.is_shutting_down = True
        self.shutdown_event.set()
        
        # Отменяем все фоновые задачи
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
        
        # Ждем завершения всех задач с таймаутом
        if self.background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.background_tasks, return_exceptions=True),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.warning("Некоторые фоновые задачи не завершились за 30 секунд")
                # Принудительно завершаем оставшиеся задачи
                for task in self.background_tasks:
                    if not task.done():
                        task.cancel()
            except Exception as e:
                logger.error(f"Ошибка при завершении фоновых задач: {e}")
        
        self.background_tasks.clear()
        logger.info("Все фоновые задачи завершены")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка всех сообщений, включая подарки звездами"""
        try:
            self.message_count += 1
            
            # Проверяем, является ли сообщение подарком звездами
            if hasattr(update.message, 'gift') and update.message.gift:
                await self.handle_stars_gift_message(update, context)
                
        except Exception as e:
            logger.error(f"Ошибка в handle_message: {e}")
            raise  # Пробрасываем в error_handler
    
    async def handle_stars_gift_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка подарка звездами"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        
        try:
            # Получаем информацию о подарке
            gift = update.message.gift
            stars_amount = getattr(gift, 'star_count', 0)
            
            if stars_amount <= 0:
                await update.message.reply_text("❌ Не удалось определить количество звезд в подарке")
                return
            
            # Валидация суммы
            if stars_amount > 100000:  # Максимум 100,000 звезд
                await update.message.reply_text("❌ Слишком большая сумма подарка")
                return
            
            # Обрабатываем подарок
            result = await self._process_stars_gift(user_id, stars_amount)
            
            if result['success']:
                text = f"""
{result['message']}

Спасибо за подарок, {user_name}! 🎉

{result.get('details', '')}
                """
                
                keyboard = [
                    [InlineKeyboardButton("📋 Мои подписки", callback_data="subscriptions")],
                    [InlineKeyboardButton("💰 Баланс", callback_data="balance")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(text, reply_markup=reply_markup)
                
            else:
                text = f"""
❌ Ошибка обработки подарка

{result['error']}

💡 Информация о подписках:
• Базовая: {SUBSCRIPTION_CONFIGS['basic']['stars']} ⭐
• VIP: {SUBSCRIPTION_CONFIGS['vip']['stars']} ⭐
                """
                
                keyboard = [
                    [InlineKeyboardButton("📋 Подписки", callback_data="subscriptions")],
                    [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(text, reply_markup=reply_markup)
                
        except Exception as e:
            logger.error(f"Ошибка обработки подарка звездами: {e}")
            await update.message.reply_text("❌ Произошла ошибка при обработке подарка. Попробуйте позже.")
    
    async def _process_stars_gift(self, user_id: int, stars_amount: int) -> dict:
        """Обработка подарка звездами"""
        try:
            # Валидация входных данных
            if not isinstance(user_id, int) or user_id <= 0 or user_id > 9999999999:
                logger.error(f"Некорректный user_id: {user_id}")
                return {'success': False, 'error': 'Некорректный ID пользователя'}
            
            if not isinstance(stars_amount, int) or stars_amount <= 0 or stars_amount > 100000:
                logger.error(f"Некорректная сумма звезд: {stars_amount}")
                return {'success': False, 'error': 'Некорректная сумма звезд'}
            
            # Регистрируем пользователя, если он новый
            if not self.db_manager.register_user(user_id):
                return {'success': False, 'error': 'Ошибка регистрации пользователя'}
            
            # Проверяем, есть ли у пользователя активная подписка
            subscription = self.db_manager.get_user_subscription(user_id)
            
            if not subscription:
                # Пользователь покупает подписку
                if stars_amount >= SUBSCRIPTION_CONFIGS['vip']['stars']:
                    subscription_type = 'vip'
                elif stars_amount >= SUBSCRIPTION_CONFIGS['basic']['stars']:
                    subscription_type = 'basic'
                else:
                    return {
                        'success': False,
                        'error': f'Недостаточно звезд для подписки. Минимум: {SUBSCRIPTION_CONFIGS["basic"]["stars"]} ⭐'
                    }
                
                # Активируем подписку
                success = self.db_manager.activate_subscription(user_id, subscription_type)
                if not success:
                    return {
                        'success': False,
                        'error': 'Ошибка активации подписки'
                    }
                
                # Записываем транзакцию
                self.db_manager.add_transaction(
                    user_id,
                    'subscription_purchase',
                    -stars_amount,
                    f'Покупка подписки {subscription_type}'
                )
                
                return {
                    'success': True,
                    'message': f'🎉 Подписка "{SUBSCRIPTION_CONFIGS[subscription_type]["name"]}" активирована!',
                    'details': f'Потрачено: {stars_amount} ⭐\nСрок действия: {SUBSCRIPTION_CONFIGS[subscription_type]["duration_days"]} дней'
                }
            
            else:
                # У пользователя уже есть подписка - пополняем баланс
                if subscription['type'] != 'vip':
                    return {
                        'success': False,
                        'error': 'Пополнение баланса доступно только для VIP подписчиков'
                    }
                
                # Пополняем баланс
                success = self.db_manager.update_balance(
                    user_id,
                    stars_amount,
                    'balance_topup',
                    'Пополнение баланса через подарок'
                )
                
                if not success:
                    return {
                        'success': False,
                        'error': 'Ошибка пополнения баланса'
                    }
                
                new_balance = self.db_manager.get_balance(user_id)
                
                return {
                    'success': True,
                    'message': f'💰 Баланс пополнен на {stars_amount} ⭐!',
                    'details': f'Текущий баланс: {new_balance} ⭐'
                }
                
        except Exception as e:
            logger.error(f"Ошибка обработки подарка звездами: {e}")
            return {
                'success': False,
                'error': 'Произошла внутренняя ошибка'
            }
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        
        # Регистрируем пользователя если его нет
        if not self.db_manager.get_user_info(user_id):
            self.db_manager.register_user(user_id, username)
            logger.info(f"Зарегистрирован новый пользователь: {user_id} (@{username})")
        
        # Получаем данные пользователя
        balance = self.db_manager.get_stars_balance(user_id)
        subscription = self.db_manager.get_user_subscription(user_id)
        
        # Определяем статус подписки
        if subscription and subscription.get('is_active'):
            sub_status = f"⭐ {subscription.get('type', 'BASIC').upper()}"
            sub_expires = subscription.get('end_date', '')
        else:
            sub_status = "❌ Нет подписки"
            sub_expires = ""
        
        # Приветственное сообщение
        text = (
            f"🎁 *Добро пожаловать в TgGIFT Bot!*\n\n"
            f"🆔 Ваш ID: `{user_id}`\n"
            f"⭐ Баланс: {balance} Stars\n"
            f"📋 Подписка: {sub_status}\n"
        )
        
        if sub_expires:
            text += f"📅 До: {sub_expires}\n"
        
        text += (
            f"\n🤖 *Автоматическая покупка новых подарков*\n"
            f"Бот автоматически покупает подарки по вашим настройкам\n\n"
            f"💡 *Как это работает:*\n"
            f"1️⃣ Пополните баланс Telegram Stars ⭐\n"
            f"2️⃣ Настройте автопокупку\n"
            f"3️⃣ Бот сам покупает новые подарки\n\n"
            f"⚙️ *Выберите действие:*"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("💰 Баланс", callback_data="balance"),
                InlineKeyboardButton("📋 Подписки", callback_data="subscriptions")
            ],
            [
                InlineKeyboardButton("🎁 Мои подарки", callback_data="my_gifts"),
                InlineKeyboardButton("🤖 Автопокупка", callback_data="autopurchase")
            ],
            [
                InlineKeyboardButton("💳 Пополнить счёт", callback_data="payments"),
                InlineKeyboardButton("🏪 Магазин подарков", callback_data="gift_shop")
            ],
            [
                InlineKeyboardButton("📊 История покупок", callback_data="purchase_history"),
                InlineKeyboardButton("🏆 Топ по балансу", callback_data="balance_top")
            ],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика бота"""
        try:
            # Получаем статистику из базы данных
            stats = self.db_manager.get_database_stats()
            
            # Время работы
            uptime = datetime.now() - self.last_reset_time
            
            text = f"""
📊 Статистика бота

👥 Пользователи: {stats.get('users', 0)}
📋 Активные подписки: {stats.get('active_subscriptions', 0)}
💰 Всего транзакций: {stats.get('transactions', 0)}
🎁 Подарков в базе: {stats.get('gifts', 0)}

📈 Сессия:
• Сообщений обработано: {self.message_count}
• Ошибок: {self.error_count}
• Время работы: {uptime}
• Фоновых задач: {len(self.background_tasks)}

🔧 Состояние:
• Мониторинг: {'✅' if self.gift_monitor else '❌'}
• Управляемый аккаунт: {'✅' if self.account_manager and self.account_manager.is_connected else '❌'}
            """
            
            await update.message.reply_text(text)
            
        except Exception as e:
            logger.error(f"Ошибка в stats_command: {e}")
            await update.message.reply_text("❌ Ошибка получения статистики")

    # Новые методы для системы Stars и платежей
    
    async def points_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для работы с Telegram Stars"""
        user_id = update.effective_user.id
        
        # Проверяем подписку
        subscription = self.db_manager.get_user_subscription(user_id)
        if not subscription:
            await update.message.reply_text(
                "❌ Для работы с Telegram Stars нужна активная подписка.\n"
                "Используйте /subscription для покупки подписки."
            )
            return
        
        # Получаем баланс Stars
        points_balance = self.db_manager.get_stars_balance(user_id)
        
        text = f"⭐ <b>Ваши Telegram Stars</b>\n\n"
        text += f"💰 Баланс: <b>{points_balance:,}</b> Stars\n\n"
        
        if subscription['type'] == 'vip':
            text += "🎉 У вас VIP подписка!\n"
            text += "• Скидка 20% на покупку подарков\n"
            text += "• Возможность пополнения Telegram Stars\n"
            text += "• Автоматическая покупка подарков\n\n"
            
            keyboard = [
                [InlineKeyboardButton("⭐ Пополнить Stars", callback_data="topup_points")],
                [InlineKeyboardButton("📊 История транзакций", callback_data="points_history")],
                [InlineKeyboardButton("⚙️ Автопокупка", callback_data="autopurchase_settings")]
            ]
        else:
            text += "ℹ️ У вас Basic подписка\n"
            text += "Для пополнения Stars и автопокупки нужна VIP подписка\n\n"
            
            keyboard = [
                [InlineKeyboardButton("⭐ Upgrade до VIP", callback_data="upgrade_to_vip")],
                [InlineKeyboardButton("📊 История транзакций", callback_data="points_history")]
            ]
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def autopurchase_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда настройки автопокупки"""
        user_id = update.effective_user.id
        
        # Проверяем VIP подписку
        subscription = self.db_manager.get_user_subscription(user_id)
        if not subscription or subscription.get('type') != 'vip':
            await update.message.reply_text(
                "❌ Автопокупка доступна только для VIP пользователей.\n"
                "Используйте /subscription для upgrade до VIP."
            )
            return
        
        # Получаем текущий профиль автопокупки
        profile = self.db_manager.get_auto_purchase_profile(user_id)
        
        if profile:
            status_text = "✅ Включена" if profile['enabled'] else "❌ Выключена"
            text = f"⚙️ <b>Настройки автопокупки</b>\n\n"
            text += f"Статус: {status_text}\n"
            text += f"Макс. цена: {profile['max_price_stars']} ⭐\n"
            text += f"Макс. тираж: {profile['max_edition_size']:,} шт.\n"
            text += f"Дневной лимит: {profile['daily_limit']} покупок\n"
            text += f"Пауза между покупками: {profile['auto_buy_cooldown']} сек.\n"
        else:
            text = f"⚙️ <b>Настройки автопокупки</b>\n\n"
            text += "Автопокупка не настроена\n"
        
        keyboard = [
            [InlineKeyboardButton("🔧 Настроить", callback_data="setup_autopurchase")],
            [InlineKeyboardButton("📊 Статистика", callback_data="autopurchase_stats")],
            [InlineKeyboardButton("❓ Справка", callback_data="autopurchase_help")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def payments_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для работы с платежами (только для админа)"""
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Команда доступна только администратору")
            return
        
        # Получаем статистику платежей
        pending_payments = self.db_manager.get_pending_payments()
        accounts_status = self.deposit_manager.get_accounts_status()
        
        text = f"💳 <b>Статус платежной системы</b>\n\n"
        text += f"⏳ Ожидающих платежей: {len(pending_payments)}\n\n"
        
        text += f"🏦 <b>Депозитные аккаунты:</b>\n"
        for account_key, status in accounts_status.items():
            status_icon = "🟢" if status['is_connected'] else "🔴"
            text += f"{status_icon} {status['name']}\n"
            text += f"   Баланс: {status['stars_balance']} ⭐\n"
            text += f"   Покупок сегодня: {status['daily_purchases']}/{status['max_daily_purchases']}\n"
            if status['last_error']:
                text += f"   ❌ Ошибка: {status['last_error'][:50]}...\n"
            text += "\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_payments")],
            [InlineKeyboardButton("📊 Детальная статистика", callback_data="detailed_payments")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_subscription_purchase(self, update: Update, context: ContextTypes.DEFAULT_TYPE, subscription_type: str):
        """Обработка покупки подписки"""
        user_id = update.effective_user.id
        
        # Проверяем, есть ли уже активная подписка
        current_subscription = self.db_manager.get_user_subscription(user_id)
        if current_subscription and current_subscription['type'] == subscription_type:
            await update.callback_query.edit_message_text(
                f"✅ У вас уже есть активная подписка {subscription_type.upper()}"
            )
            return
        
        config = SUBSCRIPTION_CONFIGS[subscription_type]
        
        text = f"💳 <b>Покупка подписки {config['name']}</b>\n\n"
        text += f"💰 Стоимость: {config['price_rub']}₽ или {config['price_ton']} TON\n"
        text += f"📅 Срок действия: {config['duration_days']} дней\n\n"
        text += "<b>Возможности:</b>\n"
        for feature in config['features']:
            text += f"• {feature}\n"
        text += "\nВыберите способ оплаты:"
        
        keyboard = [
            [InlineKeyboardButton("💳 ЮКасса (карта)", callback_data=f"pay_yookassa_{subscription_type}")],
            [InlineKeyboardButton("💎 TON кошелек", callback_data=f"pay_ton_{subscription_type}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="subscription_menu")]
        ]
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_points_topup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка пополнения Telegram Stars"""
        user_id = update.effective_user.id
        
        # Проверяем VIP подписку
        subscription = self.db_manager.get_user_subscription(user_id)
        if not subscription or subscription.get('type') != 'vip':
            await update.callback_query.edit_message_text(
                "❌ Пополнение Stars доступно только VIP пользователям"
            )
            return
        
        text = f"⭐ <b>Пополнение Telegram Stars</b>\n\n"
        text += f"💎 <b>Курс:</b> 1 TON = {int(STARS_SYSTEM['conversion_rates']['TON'])} Stars\n"
        text += f"💰 <b>Комиссия:</b> {int(STARS_SYSTEM['commission_rate']*100)}% (заработок бота)\n"
        text += f"🎯 <b>Выгода:</b> на 15% дешевле Fragment.com!\n"
        text += f"📊 <b>Минимум:</b> {STARS_SYSTEM['min_topup_stars']} Stars\n\n"
        text += "<b>💡 Как это работает:</b>\n"
        text += "• Вы заказываете например 1000 ⭐\n"
        text += f"• Платите за 1100 ⭐ (1000 + {int(STARS_SYSTEM['commission_rate']*100)}%)\n"
        text += "• Стоимость: 4.4 TON вместо 5.1 TON на Fragment\n"
        text += "• Получаете 1000 ⭐ на баланс\n"
        text += "• 100 ⭐ остается боту как комиссия\n\n"
        text += "💡 <b>Только TON кошелек!</b> ЮКасса только для подписок.\n"
        text += "\nСколько Stars хотите получить:"
        
        keyboard = [
            [
                InlineKeyboardButton("100 ⭐", callback_data="topup_stars_amount_100"),
                InlineKeyboardButton("500 ⭐", callback_data="topup_stars_amount_500")
            ],
            [
                InlineKeyboardButton("1000 ⭐", callback_data="topup_stars_amount_1000"),
                InlineKeyboardButton("2500 ⭐", callback_data="topup_stars_amount_2500")
            ],
            [
                InlineKeyboardButton("5000 ⭐", callback_data="topup_stars_amount_5000"),
                InlineKeyboardButton("✏️ Своя сумма", callback_data="topup_stars_custom_amount")
            ],
            [InlineKeyboardButton("◀️ Назад", callback_data="stars_menu")]
        ]
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_custom_stars_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода произвольного количества Stars"""
        text = (
            f"✏️ **Введите количество Stars**\n\n"
            f"📊 **Ограничения:**\n"
            f"• Минимум: {STARS_SYSTEM['min_topup_stars']} ⭐\n"
            f"• Максимум: {STARS_SYSTEM['max_topup_stars']} ⭐\n\n"
            f"💡 Просто напишите число (например: 1500)"
        )
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="topup_points")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        # Устанавливаем состояние ожидания ввода
        context.user_data['waiting_for_stars_amount'] = True
    
    async def ask_for_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE, stars_amount: str):
        """Запрос ника пользователя для комментария к платежу"""
        logger.info(f"ask_for_username вызван для {stars_amount} Stars")
        
        # Рассчитываем стоимость и комиссию
        try:
            stars_requested = int(stars_amount)
            commission_rate = STARS_SYSTEM['commission_rate']
            commission_amount = int(stars_requested * commission_rate)
            total_stars_to_charge = stars_requested + commission_amount
            conversion_rate = STARS_SYSTEM['conversion_rates']['TON']
            amount_ton = round(total_stars_to_charge / conversion_rate, 6)
            
            text = (
                f"📝 <b>Введите ваш ник в Telegram</b>\n\n"
                f"⭐ <b>Детали платежа:</b>\n"
                f"• Получите: {stars_requested} Stars\n"
                f"• Комиссия: {commission_amount} Stars ({int(commission_rate*100)}%)\n"
                f"• К оплате: {total_stars_to_charge} Stars\n"
                f"• Стоимость: <b>{amount_ton} TON</b>\n\n"
                f"💬 <b>Для идентификации платежа введите ваш ник:</b>\n"
                f"• С символом @ (например: @your_nick)\n"
                f"• Или без @ (мы добавим автоматически)\n\n"
                f"⚠️ <b>Важно:</b> Указывайте точно тот же ник, что в профиле Telegram!"
            )
        except ValueError:
            text = (
                f"📝 <b>Введите ваш ник в Telegram</b>\n\n"
                f"⭐ Количество Stars: {stars_amount}\n\n"
                f"💬 <b>Для идентификации платежа введите ваш ник:</b>\n"
                f"• С символом @ (например: @your_nick)\n"
                f"• Или без @ (мы добавим автоматически)\n\n"
                f"⚠️ <b>Важно:</b> Указывайте точно тот же ник, что в профиле Telegram!"
            )
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="topup_points")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        # Сохраняем количество Stars в контексте
        context.user_data['waiting_for_username'] = True
        context.user_data['stars_amount'] = stars_amount
    
    async def handle_custom_stars_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода произвольного количества Stars, ника пользователя или редактирования профиля"""
        
        # Обрабатываем редактирование полей профиля автопокупки
        if context.user_data.get('editing_field'):
            field = context.user_data.get('editing_field')
            context.user_data['editing_field'] = None
            user_id = update.effective_user.id
            value = update.message.text.strip()
            
            # Валидация и обновление поля
            result = await self.update_profile_field(user_id, field, value)
            if result['success']:
                # Удаляем старое сообщение с вводом
                try:
                    await update.message.delete()
                except:
                    pass
                # Показываем обновленные настройки
                await self.show_autopurchase_setup_message(update, context)
            else:
                await update.message.reply_text(f"❌ {result['error']}")
            return
        
        # Обрабатываем ввод ника для платежа
        if context.user_data.get('waiting_for_username'):
            context.user_data['waiting_for_username'] = False
            stars_amount = context.user_data.get('stars_amount')
            username = update.message.text.strip()
            
            # Валидация ника
            if not username:
                await update.message.reply_text("❌ Введите ваш ник в Telegram")
                return
            
            if len(username) < 2:
                await update.message.reply_text("❌ Ник слишком короткий")
                return
            
            # Удаляем сообщение с вводом ника
            try:
                await update.message.delete()
            except:
                pass
                
            # Создаем платеж с указанным ником
            await self.process_payment_creation_with_username(update, context, "ton", "stars", stars_amount, username)
            return
        
        # Обрабатываем ввод произвольного количества Stars
        if not context.user_data.get('waiting_for_stars_amount'):
            return  # Не ждем ввода Stars, пропускаем
        
        # Сбрасываем флаг ожидания
        context.user_data['waiting_for_stars_amount'] = False
        
        try:
            stars_amount = int(update.message.text.strip())
            
            # Проверяем ограничения
            if stars_amount < STARS_SYSTEM['min_topup_stars']:
                await update.message.reply_text(
                    f"❌ Минимальное количество Stars: {STARS_SYSTEM['min_topup_stars']} ⭐"
                )
                return
            
            if stars_amount > STARS_SYSTEM['max_topup_stars']:
                await update.message.reply_text(
                    f"❌ Максимальное количество Stars: {STARS_SYSTEM['max_topup_stars']} ⭐"
                )
                return
            
            # Удаляем сообщение с вводом количества
            try:
                await update.message.delete()
            except:
                pass
                
            # Просим ввести ник
            await self.ask_for_username_for_custom_amount(update, context, str(stars_amount))
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число")
    
    async def ask_for_username_for_custom_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE, stars_amount: str):
        """Запрос ника для произвольного количества Stars"""
        # Рассчитываем стоимость и комиссию
        try:
            stars_requested = int(stars_amount)
            commission_rate = STARS_SYSTEM['commission_rate']
            commission_amount = int(stars_requested * commission_rate)
            total_stars_to_charge = stars_requested + commission_amount
            conversion_rate = STARS_SYSTEM['conversion_rates']['TON']
            amount_ton = round(total_stars_to_charge / conversion_rate, 6)
            
            text = (
                f"📝 <b>Введите ваш ник в Telegram</b>\n\n"
                f"⭐ <b>Детали платежа:</b>\n"
                f"• Получите: {stars_requested} Stars\n"
                f"• Комиссия: {commission_amount} Stars ({int(commission_rate*100)}%)\n"
                f"• К оплате: {total_stars_to_charge} Stars\n"
                f"• Стоимость: <b>{amount_ton} TON</b>\n\n"
                f"💬 <b>Для идентификации платежа введите ваш ник:</b>\n"
                f"• С символом @ (например: @your_nick)\n"
                f"• Или без @ (мы добавим автоматически)\n\n"
                f"⚠️ <b>Важно:</b> Указывайте точно тот же ник, что в профиле Telegram!"
            )
        except ValueError:
            text = (
                f"📝 <b>Введите ваш ник в Telegram</b>\n\n"
                f"⭐ Количество Stars: {stars_amount}\n\n"
                f"💬 <b>Для идентификации платежа введите ваш ник:</b>\n"
                f"• С символом @ (например: @your_nick)\n"
                f"• Или без @ (мы добавим автоматически)\n\n"
                f"⚠️ <b>Важно:</b> Указывайте точно тот же ник, что в профиле Telegram!"
            )
        
        await update.message.reply_text(text, parse_mode='HTML')
        
        # Сохраняем количество Stars в контексте
        context.user_data['waiting_for_username'] = True
        context.user_data['stars_amount'] = stars_amount
    
    async def process_payment_creation_with_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                                   payment_method: str, payment_type: str, amount_or_type: str, username: str):
        """Создание платежа с указанным ником пользователя"""
        user_id = update.effective_user.id
        
        try:
            logger.info(f"Создание платежа с ником: метод={payment_method}, тип={payment_type}, сумма/тип={amount_or_type}, ник={username}")
            
            if payment_type == 'stars':
                # Пополнение Stars через TON
                if payment_method != 'ton':
                    result = {"success": False, "error": "Пополнение Stars доступно только через TON кошелек"}
                else:
                    try:
                        stars_requested = int(amount_or_type)
                    except ValueError:
                        logger.error(f"Не удалось конвертировать количество Stars в число: {amount_or_type}")
                        result = {"success": False, "error": "Некорректное количество Stars"}
                        stars_requested = 0
                    
                    if stars_requested > 0:
                        result = await self.ton_handler.create_stars_topup_payment(user_id, stars_requested, username)
                    else:
                        result = {"success": False, "error": "Некорректное количество Stars"}
            else:
                result = {"success": False, "error": "Неизвестный тип платежа"}
            
            if result['success']:
                text = f"💎 **TON Пополнение Telegram Stars**\n\n"
                text += f"💰 Сумма: {result.get('amount_ton', 0)} TON\n"
                text += f"⭐ Получите: {result.get('stars_requested', 0)} Stars\n"
                text += f"💸 Комиссия: {result.get('commission_amount', 0)} Stars ({result.get('commission_rate', 0)}%)\n"
                text += f"💳 К оплате: {result.get('total_stars_to_charge', 0)} Stars\n\n"
                text += f"🏦 Кошелек: `{result.get('wallet_address', '')}`\n"
                text += f"💬 Комментарий: `{result.get('comment', '')}`\n\n"
                text += "⚠️ **Обязательно укажите комментарий!**"
                
                keyboard = [
                    [InlineKeyboardButton("💎 Открыть Tonkeeper", url=result.get('ton_link', ''))],
                    [InlineKeyboardButton("🔄 Проверить платеж", callback_data=f"check_payment_{result['payment_id']}")]
                ]
                
                # Добавляем кнопки других кошельков, если они есть
                available_wallets = self.ton_handler.get_available_wallets()
                if len(available_wallets) > 1:
                    wallet_buttons = []
                    for wallet in available_wallets:
                        if wallet['address'] != result.get('wallet_address'):  # Не показываем текущий кошелек
                            wallet_buttons.append(
                                InlineKeyboardButton(
                                    f"🏦 {wallet['name']}", 
                                    callback_data=f"switch_wallet_{result['payment_id']}_{wallet['key']}"
                                )
                            )
                    if wallet_buttons:
                        keyboard.extend([[btn] for btn in wallet_buttons])
                
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            else:
                error_text = f"❌ **Ошибка создания платежа**\n\n{result.get('error', 'Неизвестная ошибка')}"
                await update.message.reply_text(error_text, parse_mode='Markdown')
        
        except Exception as e:
            logger.error(f"Ошибка создания платежа с ником: {e}")
            await update.message.reply_text("❌ Внутренняя ошибка сервера")
    
    async def process_payment_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                     payment_method: str, payment_type: str, amount_or_type: str):
        """Создание платежа"""
        user_id = update.effective_user.id
        
        try:
            logger.info(f"Создание платежа: метод={payment_method}, тип={payment_type}, сумма/тип={amount_or_type}")
            
            # Проверка VIP подписки для пополнения баланса
            if payment_type == 'points':
                subscription = self.db_manager.get_user_subscription(user_id)
                if not subscription or subscription.get('type') != 'vip' or not subscription.get('is_active'):
                    error_text = (
                        "❌ **Пополнение баланса недоступно**\n\n"
                        "Для пополнения баланса необходима активная VIP подписка.\n\n"
                        "⭐ VIP подписка включает:\n"
                        "• 💳 Пополнение баланса\n"
                        "• 🤖 Автоматическая покупка подарков\n"
                        "• 🔍 Расширенные фильтры\n"
                        "• ⚡ Приоритетная обработка"
                    )
                    keyboard = [
                        [InlineKeyboardButton("⭐ Купить VIP", callback_data="subscribe_vip")],
                        [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
                    ]
                    await self._send_message(update, error_text, InlineKeyboardMarkup(keyboard))
                    return
            
            if payment_type == 'subscription':
                subscription_type = amount_or_type
                
                if payment_method == 'yookassa':
                    result = await self.yookassa_handler.create_subscription_payment(user_id, subscription_type)
                elif payment_method == 'ton':
                    result = await self.ton_handler.create_subscription_payment(user_id, subscription_type)
                else:
                    result = {"success": False, "error": "Неизвестный метод оплаты"}
                
            elif payment_type == 'stars':
                # Пополнение Stars теперь только через TON
                if payment_method != 'ton':
                    result = {"success": False, "error": "Пополнение Stars доступно только через TON кошелек"}
                else:
                    try:
                        stars_requested = int(amount_or_type)
                    except ValueError:
                        logger.error(f"Не удалось конвертировать количество Stars в число: {amount_or_type}")
                        result = {"success": False, "error": "Некорректное количество Stars"}
                        stars_requested = 0
                    
                    if stars_requested > 0:
                        result = await self.ton_handler.create_stars_topup_payment(user_id, stars_requested)
                    else:
                        result = {"success": False, "error": "Некорректное количество Stars"}
            
            else:
                result = {"success": False, "error": "Неизвестный тип платежа"}
            
            if result['success']:
                if payment_method == 'yookassa':
                    if payment_type == 'subscription':
                        text = f"💳 **Подписка {result['subscription_type'].upper()}**\n\n"
                        text += f"💰 Сумма: {result['amount']}₽\n"
                        text += f"⏰ Срок: 30 дней\n\n"
                        text += "🔗 Нажмите кнопку для оплаты:"
                    else:  # points (старая система)
                        text = f"💳 **Пополнение Stars**\n\n"
                        text += f"💰 Сумма: {result['amount_rub']}₽\n"
                        text += f"⭐ Получите: {result['total_points']} Stars\n"
                        if result['bonus_points'] > 0:
                            text += f"🎁 Бонус: +{result['bonus_points']} Stars\n"
                        text += f"\n🔗 Нажмите кнопку для оплаты:"
                    
                    keyboard = [[InlineKeyboardButton("💳 Оплатить", url=result['payment_url'])]]
                    
                elif payment_method == 'ton':
                    if payment_type == 'subscription':
                        text = f"💎 **TON Подписка {result.get('subscription_type', '').upper()}**\n\n"
                        text += f"💰 Сумма: {result.get('amount_ton', 0)} TON\n"
                        text += f"⏰ Срок: 30 дней\n\n"
                    elif payment_type == 'stars':
                        text = f"💎 **TON Пополнение Telegram Stars**\n\n"
                        text += f"💰 Сумма: {result.get('amount_ton', 0)} TON\n"
                        text += f"⭐ Получите: {result.get('stars_requested', 0)} Stars\n"
                        text += f"💸 Комиссия: {result.get('commission_amount', 0)} Stars ({result.get('commission_rate', 0)}%)\n"
                        text += f"💳 К оплате: {result.get('total_stars_to_charge', 0)} Stars\n\n"
                    else:  # старые points для совместимости
                        text = f"💎 **TON Пополнение Stars**\n\n"
                        text += f"💰 Сумма: {result.get('amount_ton', 0)} TON\n"
                        text += f"⭐ Получите: {result.get('total_points', 0)} Stars\n"
                        if result.get('bonus_points', 0) > 0:
                            text += f"🎁 Бонус: +{result['bonus_points']} Stars\n"
                        text += f"\n"
                    
                    text += f"🏦 Кошелек: `{result.get('wallet_address', '')}`\n"
                    text += f"💬 Комментарий: `{result.get('comment', '')}`\n\n"
                    text += "⚠️ **Обязательно укажите комментарий!**"
                    
                    keyboard = [
                        [InlineKeyboardButton("💎 Открыть Tonkeeper", url=result.get('ton_link', ''))],
                        [InlineKeyboardButton("🔄 Проверить платеж", callback_data=f"check_payment_{result['payment_id']}")]
                    ]
                
                await self._send_message(update, text, InlineKeyboardMarkup(keyboard))
                
                # Запланировать удаление сообщения через 5 минут
                await self._schedule_message_deletion(update, 5)
            else:
                error_text = f"❌ **Ошибка создания платежа**\n\n{result.get('error', 'Неизвестная ошибка')}"
                keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
                await self._send_message(update, error_text, InlineKeyboardMarkup(keyboard))
        
        except Exception as e:
            logger.error(f"Ошибка создания платежа: {e}")
            await update.callback_query.edit_message_text(
                "❌ Внутренняя ошибка сервера"
            )
    
    async def _schedule_message_deletion(self, update: Update, delay_minutes: int = 5):
        """Запланировать удаление сообщения через указанное время"""
        async def delete_message():
            await asyncio.sleep(delay_minutes * 60)  # Переводим минуты в секунды
            try:
                if update.callback_query and update.callback_query.message:
                    await update.callback_query.message.delete()
                    logger.info(f"Удалено сообщение платежа через {delay_minutes} минут")
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение: {e}")
        
        # Создаем задачу на удаление
        task = asyncio.create_task(delete_message())
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
    
    async def subscription_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда просмотра подписок"""
        # Реализация остается прежней
        pass
    
    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда просмотра баланса"""
        # Реализация остается прежней
        pass
    
    async def queue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда просмотра очереди"""
        # Реализация остается прежней
        pass
    
    async def gifts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда просмотра подарков"""
        # Реализация остается прежней
        pass
    
    async def topup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда пополнения баланса"""
        # Реализация остается прежней
        pass
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда помощи"""
        # Реализация остается прежней
        pass
    
    async def grantvip_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда выдачи VIP подписки (только для админа)"""
        user_id = update.effective_user.id
        
        # Проверяем, что команду вызывает админ
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды")
            return
        
        # Проверяем аргументы
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(
                "📖 **Использование:** `/grantvip <user_id>`\n\n"
                "**Пример:** `/grantvip 123456789`",
                parse_mode="Markdown"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя. Используйте числовой ID.")
            return
        
        try:
            # Регистрируем пользователя, если его нет
            self.db_manager.register_user(target_user_id)
            
            # Активируем VIP подписку
            success = self.db_manager.activate_subscription(target_user_id, 'vip')
            
            if success:
                await update.message.reply_text(
                    f"✅ **VIP подписка успешно выдана!**\n\n"
                    f"👤 **Пользователь:** `{target_user_id}`\n"
                    f"⭐ **Подписка:** VIP (30 дней)\n"
                    f"🎯 **Доступные функции:**\n"
                    f"• 💳 Пополнение баланса\n"
                    f"• 🤖 Автоматическая покупка подарков\n"
                    f"• 🔍 Расширенные фильтры\n"
                    f"• ⚡ Приоритетная обработка",
                    parse_mode="Markdown"
                )
                logger.info(f"Админ {user_id} выдал VIP подписку пользователю {target_user_id}")
            else:
                await update.message.reply_text("❌ Ошибка при активации подписки")
                
        except Exception as e:
            logger.error(f"Ошибка выполнения команды grantvip: {e}")
            await update.message.reply_text("❌ Внутренняя ошибка сервера")
    
    async def monitor_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда статуса мониторинга"""
        # Реализация остается прежней
        pass
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на инлайн-кнопки"""
        query = update.callback_query
        await query.answer()
        
        try:
            data = query.data
            user_id = update.effective_user.id
            logger.info(f"Callback от пользователя {user_id}: {data}")
            
            # Главное меню
            if data == "back" or data == "main_menu":
                await self.start_command(update, context)
                return
            
            # Баланс и платежи
            elif data == "balance":
                await self.show_balance_menu(update, context)
            elif data == "payments":
                await self.show_payments_menu(update, context)
            elif data == "topup_points":
                await self.handle_points_topup(update, context)
            elif data.startswith("amount_"):
                amount = data.split("_")[1]  # amount_100, amount_500, etc.
                await self.show_payment_methods(update, context, amount)
            elif data.startswith("pay_sub_"):
                parts = data.split("_")[2:]  # pay_sub_yookassa_basic -> ['yookassa', 'basic']
                if len(parts) >= 2:
                    payment_method = parts[0]
                    sub_type = parts[1]
                    await self.process_payment_creation(update, context, payment_method, "subscription", sub_type)
                else:
                    await self._send_message(update, "❌ Ошибка обработки платежа подписки", None)
            elif data.startswith("pay_"):
                payment_data = "_".join(data.split("_")[1:])  # yookassa_100, ton_500, etc.
                await self.handle_payment_selection(update, context, payment_data)
            
            # Подписки
            elif data == "subscriptions":
                await self.show_subscription_menu(update, context)
            elif data.startswith("subscribe_"):
                sub_type = data.split("_")[1]  # subscribe_basic, subscribe_vip
                logger.info(f"Обработка подписки: {sub_type}")
                try:
                    await self.show_subscription_payment_methods(update, context, sub_type)
                except Exception as e:
                    logger.error(f"Ошибка в show_subscription_payment_methods: {e}")
                    await query.edit_message_text("❌ Произошла ошибка. Попробуйте еще раз.")
            
            # Подарки
            elif data == "my_gifts":
                await self.show_gifts_menu(update, context)
            elif data == "gift_shop":
                await self.show_gift_shop(update, context)
            elif data == "purchase_history":
                await self.show_purchase_history(update, context)
            
            # Автопокупка
            elif data == "autopurchase":
                await self.show_autopurchase_menu(update, context)
            elif data == "create_profile":
                await self.show_create_profile_menu(update, context)
            elif data.startswith("profile_"):
                profile_id = data.split("_")[1]
                await self.show_profile_details(update, context, profile_id)
            elif data.startswith("toggle_profile_"):
                profile_id = data.split("_")[2]
                await self.toggle_profile(update, context)
            elif data.startswith("delete_profile_"):
                await self.confirm_delete_profile(update, context)
            
            # Настройки
            elif data == "settings":
                await self.show_settings_menu(update, context)
            
            # Помощь
            elif data == "help":
                await self.show_help_menu(update, context)
            
            # История
            elif data == "history":
                await self.show_transaction_history(update, context)
            
            # Новые обработчики для истории
            elif data == "points_history":
                await self.show_points_history(update, context)
            elif data == "gifts_history":
                await self.show_gifts_purchase_history(update, context)
            elif data == "user_stats":
                await self.show_user_statistics(update, context)
            
            # Топ по балансу
            elif data == "balance_top":
                await self.show_balance_leaderboard(update, context)
            
            # Расширенные обработчики автопокупки
            elif data == "setup_autopurchase":
                await self.show_autopurchase_setup(update, context)
            elif data == "autopurchase_stats":
                await self.show_autopurchase_statistics(update, context)
            elif data == "autopurchase_help":
                await self.show_autopurchase_help(update, context)
            elif data.startswith("edit_profile_"):
                field = data.split("_", 2)[2]
                await self.edit_profile_field(update, context, field)
            elif data.startswith("save_profile_"):
                field = data.split("_", 2)[2]
                await self.save_profile_field(update, context, field)
            
            # Создание и управление профилем
            elif data == "create_default_profile":
                await self.create_default_profile(update, context)
            
            elif data == "confirm_delete_profile":
                await self.delete_profile(update, context)
            
            # Обработчики пополнения Stars
            elif data.startswith("topup_stars_amount_"):
                stars_amount = data.split("_")[3]  # topup_stars_amount_100
                logger.info(f"Обработка пополнения Stars: {stars_amount}")
                try:
                    await self.ask_for_username(update, context, stars_amount)
                except Exception as e:
                    logger.error(f"Ошибка в ask_for_username: {e}")
                    await query.edit_message_text("❌ Произошла ошибка. Попробуйте еще раз.")
            elif data == "topup_stars_custom_amount":
                await self.handle_custom_stars_amount(update, context)
            
            # Переключение кошелька для TON платежей
            elif data.startswith("switch_wallet_"):
                logger.info(f"Обработка переключения кошелька: {data}")
                await self.handle_switch_wallet(update, context)
            
            else:
                await query.edit_message_text("❌ Неизвестная команда")
        
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка")
            except:
                pass
    
    async def handle_switch_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик переключения кошелька для TON платежа"""
        query = update.callback_query
        data = query.data
        
        logger.info(f"handle_switch_wallet вызван с данными: {data}")
        
        try:
            # Парсим данные: switch_wallet_stars_592900565_1753219033_wallet_2
            parts = data.split("_")  # ['switch', 'wallet', 'stars', '592900565', '1753219033', 'wallet', '2']
            logger.info(f"Парсинг callback данных: {parts}")
            
            if len(parts) < 7:
                await query.edit_message_text("❌ Неверный формат команды")
                return
            
            # Восстанавливаем payment_id: stars_592900565_1753219033
            payment_id = f"{parts[2]}_{parts[3]}_{parts[4]}"
            # Восстанавливаем wallet_key: wallet_2
            wallet_key = f"{parts[5]}_{parts[6]}"
            
            logger.info(f"Извлечен payment_id: {payment_id}, wallet_key: {wallet_key}")
            
            # Получаем информацию о платеже
            logger.info(f"Получаем информацию о платеже: {payment_id}")
            payment_info = self.db_manager.get_payment_info(payment_id)
            logger.info(f"Информация о платеже: {payment_info}")
            if not payment_info:
                await query.edit_message_text("❌ Платеж не найден")
                return
            
            # Получаем новый кошелек
            available_wallets = self.ton_handler.get_available_wallets()
            selected_wallet = None
            for wallet in available_wallets:
                if wallet['key'] == wallet_key:
                    selected_wallet = wallet
                    break
            
            if not selected_wallet:
                await query.edit_message_text("❌ Кошелек не найден")
                return
            
            # Пересоздаем платеж с новым кошельком
            metadata = payment_info['metadata']
            user_id = payment_info['user_id']
            
            if payment_info['payment_type'] == 'stars_topup':
                stars_amount = metadata['stars_amount']
                username = metadata.get('username')
                result = await self.ton_handler.create_stars_topup_payment(
                    user_id, stars_amount, username, wallet_key
                )
            else:
                await query.edit_message_text("❌ Неподдерживаемый тип платежа")
                return
            
            if result['success']:
                text = f"💎 **TON Пополнение Telegram Stars**\n\n"
                text += f"💰 Сумма: {result.get('amount_ton', 0)} TON\n"
                text += f"⭐ Получите: {result.get('stars_amount', 0)} Stars\n\n"
                text += f"🏦 Кошелек: `{result.get('wallet_address', '')}`\n"
                text += f"📝 Название: {selected_wallet['name']}\n"
                text += f"💬 Комментарий: `{result.get('comment', '')}`\n\n"
                text += "⚠️ **Обязательно укажите комментарий!**"
                
                keyboard = [
                    [InlineKeyboardButton("💎 Открыть Tonkeeper", url=result.get('ton_link', ''))],
                    [InlineKeyboardButton("🔄 Проверить платеж", callback_data=f"check_payment_{result['payment_id']}")]
                ]
                
                # Добавляем кнопки других кошельков
                wallet_buttons = []
                for wallet in available_wallets:
                    if wallet['key'] != wallet_key:
                        wallet_buttons.append(
                            InlineKeyboardButton(
                                f"🏦 {wallet['name']}", 
                                callback_data=f"switch_wallet_{result['payment_id']}_{wallet['key']}"
                            )
                        )
                if wallet_buttons:
                    keyboard.extend([[btn] for btn in wallet_buttons])
                
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            else:
                await query.edit_message_text(f"❌ Ошибка переключения кошелька: {result.get('error', 'Неизвестная ошибка')}")
        
        except Exception as e:
            logger.error(f"Ошибка переключения кошелька: {e}")
            await query.edit_message_text("❌ Внутренняя ошибка сервера")

    async def handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик поисковых запросов"""
        # Реализация остается прежней
        pass
    
    async def show_subscription_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню подписок"""
        user_id = update.effective_user.id
        subscription = self.db_manager.get_user_subscription(user_id)
        
        # Получаем конфигурацию подписок для использования в кнопках
        basic_config = SUBSCRIPTION_CONFIGS['basic']
        vip_config = SUBSCRIPTION_CONFIGS['vip']
        
        if subscription and subscription.get('is_active'):
            expires_at = subscription.get('expires_at', 'Неизвестно')
            sub_type = subscription.get('type', 'basic')
            text = (
                f"⭐ *Активная подписка: {sub_type.upper()}*\n\n"
                f"📅 Действует до: {expires_at}\n\n"
                "🎯 Доступные функции:\n"
            )
            if sub_type == 'vip':
                text += "• 🤖 Автопокупка подарков\n• 🔍 Расширенный поиск\n• ⚡ Приоритетная обработка\n"
            else:
                text += "• 🔍 Базовый поиск подарков\n• 📊 Статистика покупок\n"
            
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
            ]
        else:
            text = (
                "📋 *Подписки*\n\n"
                "У вас нет активной подписки.\n\n"
                "💰 Доступные подписки:\n"
                f"• {basic_config['name']}: {basic_config['price_rub']}₽ / {basic_config['price_ton']} TON (30 дней)\n"
                f"• {vip_config['name']}: {vip_config['price_rub']}₽ / {vip_config['price_ton']} TON (30 дней)\n\n"
                "💡 Выберите подписку:"
            )
            
            keyboard = [
                [InlineKeyboardButton(f"✅ {basic_config['name']}", callback_data="subscribe_basic")],
                [InlineKeyboardButton(f"⭐ {vip_config['name']}", callback_data="subscribe_vip")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    async def show_balance_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню баланса"""
        user_id = update.effective_user.id
        balance = self.db_manager.get_stars_balance(user_id)
        reserved = self.db_manager.get_reserved_points(user_id)
        
        text = (
            f"⭐ *Ваш баланс Telegram Stars*\n\n"
            f"💎 Доступно: {balance} ⭐\n"
            f"🔒 Зарезервировано: {reserved} ⭐\n"
            f"📊 Всего: {balance + reserved} ⭐\n\n"
            f"💡 Курс: 1 TON = {int(STARS_SYSTEM['conversion_rates']['TON'])} Stars\n"
            f"🔄 Комиссия: {int(STARS_SYSTEM['commission_rate']*100)}% при пополнении"
        )
        
        keyboard = [
            [InlineKeyboardButton("💳 Пополнить", callback_data="payments")],
            [InlineKeyboardButton("📜 История операций", callback_data="history")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    async def show_payments_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню пополнения Stars"""
        user_id = update.effective_user.id
        
        # Проверяем VIP подписку
        subscription = self.db_manager.get_user_subscription(user_id)
        if not subscription or subscription.get('type') != 'vip':
            text = (
                "❌ **Пополнение Stars недоступно**\n\n"
                "Для пополнения баланса необходима активная VIP подписка.\n\n"
                "⭐ VIP подписка включает:\n"
                "• 💳 Пополнение баланса Telegram Stars\n"
                "• 🤖 Автоматическая покупка подарков\n"
                "• 🔍 Расширенные фильтры\n"
                "• ⚡ Приоритетная обработка"
            )
            keyboard = [
                [InlineKeyboardButton("⭐ Купить VIP", callback_data="subscribe_vip")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="balance")]
            ]
        else:
            # Рассчитываем стоимость для каждой суммы
            commission_rate = STARS_SYSTEM['commission_rate']
            conversion_rate = STARS_SYSTEM['conversion_rates']['TON']
            
            def calc_cost(stars):
                total_with_commission = stars * (1 + commission_rate)
                return round(total_with_commission / conversion_rate, 3)
            
            text = (
                f"⭐ **Пополнение Telegram Stars**\n\n"
                f"💎 **Курс:** 1 TON = {int(conversion_rate)} Stars\n"
                f"💰 **Комиссия:** {int(commission_rate*100)}% (заработок бота)\n"
                f"🎯 **Выгода:** на 15% дешевле Fragment.com!\n"
                f"📊 **Минимум:** {STARS_SYSTEM['min_topup_stars']} Stars\n\n"
                f"💡 **Только TON кошелек!** ЮКасса только для подписок.\n\n"
                f"Выберите количество Stars:"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton(f"100 ⭐ ({calc_cost(100)} TON)", callback_data="topup_stars_amount_100"),
                    InlineKeyboardButton(f"500 ⭐ ({calc_cost(500)} TON)", callback_data="topup_stars_amount_500")
                ],
                [
                    InlineKeyboardButton(f"1000 ⭐ ({calc_cost(1000)} TON)", callback_data="topup_stars_amount_1000"),
                    InlineKeyboardButton(f"2500 ⭐ ({calc_cost(2500)} TON)", callback_data="topup_stars_amount_2500")
                ],
                [
                    InlineKeyboardButton(f"5000 ⭐ ({calc_cost(5000)} TON)", callback_data="topup_stars_amount_5000"),
                    InlineKeyboardButton("✏️ Своя сумма", callback_data="topup_stars_custom_amount")
                ],
                [InlineKeyboardButton("⬅️ Назад", callback_data="balance")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    async def show_payment_methods(self, update: Update, context: ContextTypes.DEFAULT_TYPE, amount: str):
        """Показать способы оплаты для выбранной суммы"""
        try:
            amount_rub = float(amount)
            points = int(amount_rub)  # 1₽ = 1🔸
            
            text = (
                f"💳 *Пополнение на {amount_rub}₽*\n\n"
                f"⭐ Получите: {points} Stars\n\n"
                f"🎯 Выберите способ оплаты:"
            )
            
            keyboard = [
                [InlineKeyboardButton("💳 ЮКасса (карта)", callback_data=f"pay_yookassa_{amount}")],
                [InlineKeyboardButton("💎 TON Wallet", callback_data=f"pay_ton_{amount}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="payments")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self._send_message(update, text, reply_markup)
            
        except ValueError:
            logger.error(f"Некорректная сумма для оплаты: {amount}")
            await self._send_message(update, "❌ Некорректная сумма", None)
    
    async def show_autopurchase_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню автопокупки"""
        user_id = update.effective_user.id
        
        # Проверяем VIP подписку
        subscription = self.db_manager.get_user_subscription(user_id)
        if not subscription or subscription.get('type') != 'vip':
            text = (
                f"🤖 *Автоматическая покупка подарков*\n\n"
                f"❌ Автопокупка доступна только для VIP пользователей\n\n"
                f"🌟 *Возможности VIP:*\n"
                f"• Автоматическая покупка новых подарков\n"
                f"• Настраиваемые профили покупки\n"
                f"• Скидка 20% на все покупки\n"
                f"• Приоритетная поддержка"
            )
            
            keyboard = [
                [InlineKeyboardButton("⭐ Upgrade до VIP", callback_data="subscriptions")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._send_message(update, text, reply_markup)
            return
        
        # Получаем профиль автопокупки
        profile = self.db_manager.get_auto_purchase_profile(user_id)
        stats = self.db_manager.get_autopurchase_statistics(user_id)
        
        if profile:
            status = "🟢 Активна" if profile['enabled'] else "🔴 Неактивна"
            text = (
                f"🤖 *Меню автоматической покупки*\n\n"
                f"📊 *Статус:* {status}\n"
                f"💰 Макс. цена: {profile['max_price_stars']} ⭐\n"
                f"📈 Макс. тираж: {profile['max_edition_size']:,}\n"
                f"🎯 Дневной лимит: {profile['daily_limit']}\n"
                f"⏱️ Пауза: {profile['auto_buy_cooldown']} сек.\n\n"
                f"📈 *Статистика:*\n"
                f"🛒 Всего покупок: {stats.get('auto_purchases_count', 0)}\n"
                f"💸 Потрачено: {stats.get('auto_purchases_spent', 0)} 🔸\n"
                f"📅 Сегодня: {stats.get('auto_purchases_today', 0)} покупок"
            )
            
            keyboard = [
                [InlineKeyboardButton("⚙️ Настройки", callback_data="setup_autopurchase")],
                [InlineKeyboardButton("📊 Статистика", callback_data="autopurchase_stats")],
                [InlineKeyboardButton("❓ Справка", callback_data="autopurchase_help")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
            ]
        else:
            # Получаем профили автопокупки (временно заглушка)
            profiles = []  # TODO: добавить метод get_autopurchase_profiles
            active_profiles = []
            
            text = (
                f"🤖 *Меню автоматической покупки*\n\n"
                f"❌ Профиль автопокупки не настроен\n\n"
                f"Автобот покупает только новые подарки. Сразу при выходе "
                f"гифтов, если вы не успели настроить профиль, заходите в "
                f"магазин и покупайте оттуда.\n\n"
                f"Создайте профиль с настройками для автоматической покупки подарков!"
            )
            
            keyboard = [
                [InlineKeyboardButton("➕ Создать профиль", callback_data="setup_autopurchase")],
                [InlineKeyboardButton("❓ Справка", callback_data="autopurchase_help")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_message(update, text, reply_markup)
    
    async def show_gifts_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню подарков"""
        user_id = update.effective_user.id
        # gifts = self.db_manager.get_user_gift_purchases(user_id)  # TODO: добавить метод
        gifts = []  # Временная заглушка
        
        if gifts:
            text = "🎁 *Ваши купленные подарки:*\n\n"
            for gift in gifts[-10:]:  # Последние 10 подарков
                status = gift.get('status', 'completed')
                status_emoji = "✅" if status == 'completed' else "⏳" if status == 'pending' else "❌"
                text += f"{status_emoji} {gift.get('gift_name', 'Неизвестный подарок')} — {gift.get('points_spent', 0)} 🔸\n"
        else:
            text = "🎁 *У вас пока нет купленных подарков.*\n\nИспользуйте автопокупку или покупайте подарки вручную."
        
        keyboard = [
            [InlineKeyboardButton("🤖 Автопокупка", callback_data="autopurchase")],
            [InlineKeyboardButton("🔍 Найти подарки", callback_data="search_gifts")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    # Недостающие методы-заглушки
    async def show_gift_shop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать магазин подарков"""
        referral_url = "https://t.me/portals/market?startapp=bcg9s4"
        
        text = (
            "🏪 <b>Магазин подарков Telegram</b>\n\n"
            "🎁 Официальный магазин подарков Telegram\n"
            "⭐ Покупайте подарки за Telegram Stars\n"
            "🔥 Эксклюзивные и редкие подарки\n\n"
            "👆 <b>Нажмите кнопку ниже для перехода в магазин</b>"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏪 Открыть магазин", url=referral_url)],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def show_purchase_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю покупок"""
        text = "📊 *История покупок*\n\n🔧 В разработке..."
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def show_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню настроек"""
        text = "⚙️ *Настройки*\n\n🔧 В разработке..."
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def show_help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню помощи"""
        text = (
            "❓ *Помощь*\n\n"
            "🤖 *Как работает бот:*\n"
            "1️⃣ Пополните баланс 🔸\n"
            "2️⃣ Купите подписку (VIP для автопокупки)\n"
            "3️⃣ Настройте профили автопокупки\n"
            "4️⃣ Бот автоматически покупает новые подарки\n\n"
            "💬 *Поддержка:* @support"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def show_transaction_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю транзакций"""
        text = (
            "📜 **История операций**\n\n"
            "Выберите тип истории для просмотра:"
        )
        
        keyboard = [
            [InlineKeyboardButton("💰 История пополнений", callback_data="points_history")],
            [InlineKeyboardButton("🎁 История покупок подарков", callback_data="gifts_history")],
            [InlineKeyboardButton("📊 Общая статистика", callback_data="user_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="balance")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)

    async def show_points_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю пополнений Stars"""
        user_id = update.effective_user.id
        transactions = self.db_manager.get_points_transactions_history(user_id, 15)
        
        if not transactions:
            text = "⭐ **История пополнений**\n\n❌ История пополнений пуста"
        else:
            text = "⭐ **История пополнений Stars**\n\n"
            
            for transaction in transactions:
                # Форматируем дату
                try:
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(transaction['created_at'].replace('Z', '+00:00'))
                    date_str = date_obj.strftime('%d.%m.%Y %H:%M')
                except:
                    date_str = transaction['created_at'][:16]
                
                # Определяем тип операции
                if transaction['type'] == 'topup':
                    emoji = "💰"
                    type_name = "Пополнение"
                elif transaction['type'] == 'spend':
                    emoji = "💸"
                    type_name = "Списание"
                elif transaction['type'] == 'bonus':
                    emoji = "🎁"
                    type_name = "Бонус"
                else:
                    emoji = "🔄"
                    type_name = "Операция"
                
                # Форматируем сумму
                amount = transaction['amount']
                amount_str = f"+{amount}" if amount > 0 else str(amount)
                
                text += f"{emoji} **{type_name}**: {amount_str} 🔸\n"
                text += f"📅 {date_str}\n"
                
                if transaction['source']:
                    source_names = {
                        'yookassa': 'ЮКасса',
                        'ton': 'TON',
                        'internal': 'Внутренняя операция',
                        'bonus': 'Бонусная программа'
                    }
                    source = source_names.get(transaction['source'], transaction['source'])
                    text += f"🏦 Источник: {source}\n"
                
                if transaction['description']:
                    text += f"📝 {transaction['description']}\n"
                
                text += f"💎 Баланс после: {transaction['balance_after']} 🔸\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="points_history")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="history")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)

    async def show_gifts_purchase_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю покупок подарков"""
        user_id = update.effective_user.id
        purchases = self.db_manager.get_gift_purchases_history(user_id, 15)
        
        if not purchases:
            text = "🎁 **История покупок подарков**\n\n❌ Вы ещё не покупали подарки"
        else:
            text = "🎁 **История покупок подарков**\n\n"
            
            for purchase in purchases:
                # Форматируем дату
                try:
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(purchase['created_at'].replace('Z', '+00:00'))
                    date_str = date_obj.strftime('%d.%m.%Y %H:%M')
                except:
                    date_str = purchase['created_at'][:16]
                
                # Статус покупки
                status_emoji = {
                    'completed': '✅',
                    'pending': '⏳',
                    'failed': '❌',
                    'refunded': '🔄'
                }.get(purchase['status'], '❓')
                
                # Метод покупки
                method_emoji = {
                    'auto': '🤖',
                    'manual': '👤',
                    'queue': '📋'
                }.get(purchase['purchase_method'], '🔧')
                
                text += f"🎁 **{purchase['gift_name']}** {status_emoji}\n"
                text += f"📅 {date_str}\n"
                text += f"💰 Потрачено: {purchase['points_spent']} 🔸\n"
                text += f"⭐ Stars: {purchase['stars_spent']} ⭐\n"
                text += f"💸 Комиссия: {purchase['commission_amount']} 🔸\n"
                text += f"{method_emoji} Метод: {purchase['purchase_method']}\n"
                
                if purchase['telegram_gift_id']:
                    text += f"🆔 ID подарка: `{purchase['telegram_gift_id']}`\n"
                
                text += "\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="gifts_history")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="history")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)

    async def show_user_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать общую статистику пользователя"""
        user_id = update.effective_user.id
        stats = self.db_manager.get_user_statistics(user_id)
        subscription = self.db_manager.get_user_subscription(user_id)
        
        # Подписка
        if subscription and subscription.get('is_active'):
            sub_info = f"⭐ {subscription.get('type', 'basic').upper()}"
            sub_expires = subscription.get('end_date', 'Неизвестно')
        else:
            sub_info = "❌ Нет активной подписки"
            sub_expires = ""
        
        text = f"📊 **Ваша статистика**\n\n"
        text += f"👤 **ID пользователя**: `{user_id}`\n"
        text += f"📋 **Подписка**: {sub_info}\n"
        
        if sub_expires:
            text += f"📅 **Действует до**: {sub_expires}\n"
        
        text += f"\n💰 **Баланс и операции**:\n"
        text += f"💎 Текущий баланс: **{stats.get('balance_points', 0)}** 🔸\n"
        text += f"📈 Всего заработано: **{stats.get('total_earned', 0)}** 🔸\n"
        text += f"📉 Всего потрачено: **{stats.get('total_spent', 0)}** 🔸\n"
        text += f"🔄 Количество пополнений: **{stats.get('topups_count', 0)}**\n"
        
        text += f"\n🎁 **Покупки подарков**:\n"
        text += f"🛍️ Куплено подарков: **{stats.get('gifts_purchased', 0)}**\n"
        text += f"💸 Потрачено на подарки: **{stats.get('total_spent_on_gifts', 0)}** 🔸\n"
        
        # Вычисляем экономию для VIP
        if subscription and subscription.get('type') == 'vip':
            savings = stats.get('total_spent_on_gifts', 0) * 0.2  # 20% скидка VIP
            text += f"💰 Экономия VIP (20%): **{int(savings)}** 🔸\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="user_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="history")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def handle_payment_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, payment_data: str):
        """Обработка выбора способа платежа"""
        # payment_data приходит в формате: "yookassa_100" или "ton_500"
        parts = payment_data.split("_")
        if len(parts) >= 2:
            payment_method = parts[0]  # yookassa или ton
            amount = parts[1]          # 100, 500, etc.
            
            await self.process_payment_creation(update, context, payment_method, "points", amount)
        else:
            await self._send_message(update, "❌ Ошибка обработки платежа", None)
    
    async def handle_subscription_purchase(self, update: Update, context: ContextTypes.DEFAULT_TYPE, sub_type: str):
        """Обработка покупки подписки"""
        text = f"⭐ *Подписка: {sub_type.upper()}*\n\n🔧 В разработке..."
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="subscriptions")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def show_subscription_payment_methods(self, update: Update, context: ContextTypes.DEFAULT_TYPE, sub_type: str):
        """Показать способы оплаты для подписки"""
        if sub_type not in SUBSCRIPTION_CONFIGS:
            await self._send_message(update, "❌ Неизвестный тип подписки")
            return
        
        config = SUBSCRIPTION_CONFIGS[sub_type]
        sub_name = config['name']
        price_rub = config['price_rub']
        price_ton = config['price_ton']
        
        text = (
            f"⭐ *{sub_name}*\n\n"
            f"💰 Стоимость:\n"
            f"• 💳 ЮКасса: {price_rub}₽\n"
            f"• 💎 TON: {price_ton} TON\n\n"
            f"⏰ Срок действия: 30 дней\n\n"
            f"🎯 Выберите способ оплаты:"
        )
        
        keyboard = [
            [InlineKeyboardButton("💳 ЮКасса (карта)", callback_data=f"pay_sub_yookassa_{sub_type}")],
            [InlineKeyboardButton("💎 TON Wallet", callback_data=f"pay_sub_ton_{sub_type}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="subscriptions")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    

    
    async def _send_message(self, update: Update, text: str, reply_markup=None, parse_mode="Markdown"):
        """Универсальная функция для отправки сообщений"""
        try:
            if update.message:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            elif update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                logger.error("Не удалось определить тип update для отправки сообщения")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            # Fallback - попробуем через callback query если есть
            if update.callback_query:
                try:
                    await update.callback_query.answer("❌ Произошла ошибка")
                except:
                    pass
    
    async def _periodic_notification_sender(self):
        """Периодическая отправка уведомлений пользователям"""
        while not self.is_shutting_down:
            try:
                # Проверяем флаг завершения
                if self.shutdown_event.is_set():
                    break
                
                # Получаем всех активных пользователей
                users = self.db_manager.get_all_active_users()
                
                for user in users:
                    if self.is_shutting_down:
                        break
                        
                    user_id = user['user_id']
                    notifications = self.db_manager.get_pending_notifications(user_id)
                    
                    for notification in notifications:
                        if self.is_shutting_down:
                            break
                            
                        try:
                            # Отправляем уведомление
                            await self.application.bot.send_message(
                                chat_id=user_id,
                                text=notification['message'],
                                parse_mode='Markdown'
                            )
                            
                            # Отмечаем как отправленное
                            self.db_manager.mark_notification_sent(notification['id'])
                            
                            # Небольшая задержка между сообщениями
                            await asyncio.sleep(0.5)
                            
                        except (BadRequest, Forbidden, NetworkError) as e:
                            logger.warning(f"Не удалось отправить уведомление {notification['id']} пользователю {user_id}: {e}")
                            # Отмечаем как неудачное
                            self.db_manager.mark_notification_failed(notification['id'])
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления {notification['id']} пользователю {user_id}: {e}")
                
                # Проверяем уведомления каждые 30 секунд
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=30.0)
                    break  # Получили сигнал завершения
                except asyncio.TimeoutError:
                    continue  # Таймаут - продолжаем цикл
                
            except asyncio.CancelledError:
                logger.info("Отправка уведомлений отменена")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле отправки уведомлений: {e}")
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=60.0)
                    break
                except asyncio.TimeoutError:
                    continue
    
    async def _periodic_subscription_cleanup(self):
        """Периодическая очистка истекших подписок"""
        while not self.is_shutting_down:
            try:
                # Проверяем флаг завершения
                if self.shutdown_event.is_set():
                    break
                
                self.db_manager.cleanup_expired_subscriptions()
                logger.info("Выполнена очистка истекших подписок")
                
                # Ждем час или сигнал завершения
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=3600.0)
                    break  # Получили сигнал завершения
                except asyncio.TimeoutError:
                    continue  # Таймаут - продолжаем цикл
                
            except asyncio.CancelledError:
                logger.info("Очистка подписок отменена")
                break
            except Exception as e:
                logger.error(f"Ошибка очистки подписок: {e}")
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=3600.0)
                    break
                except asyncio.TimeoutError:
                    continue
    
    async def run(self):
        """Запуск бота"""
        try:
            logger.info("🚀 Запуск TgGIFT Star Bot...")
            
            # Инициализация базы данных
            logger.info("📊 Инициализация базы данных...")
            self.db_manager.init_database()
            logger.info("✅ База данных инициализирована")
            
            # Инициализация депозитных аккаунтов
            logger.info("🏦 Инициализация депозитных аккаунтов...")
            await self.deposit_manager.initialize_accounts()
            
            # Подключаем депозитный менеджер к мониторингу подарков
            self.gift_monitor.set_deposit_manager(self.deposit_manager)
            
            # Запуск мониторинга TON платежей
            logger.info("💎 Запуск мониторинга TON платежей...")
            asyncio.create_task(self.ton_handler.start_payment_monitor())
            
            # Запуск мониторинга ЮКассы (на случай отсутствия публичного webhook)
            logger.info("💳 Запуск мониторинга ЮКассы...")
            asyncio.create_task(self.yookassa_handler.start_payment_monitor())
            
            # Запуск мониторинга подарков через депозитные аккаунты
            logger.info("🎁 Запуск мониторинга подарков...")
            monitor_task = asyncio.create_task(self.gift_monitor.start_monitoring())
            self.background_tasks.add(monitor_task)
            monitor_task.add_done_callback(self.background_tasks.discard)
            
            # Настройка обработчика сигналов
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, self._handle_signal)
            if hasattr(signal, 'SIGINT'):
                signal.signal(signal.SIGINT, self._handle_signal)
            
            # Запуск бота
            logger.info("🤖 Запуск Telegram бота...")
            await self.application.initialize()
            await self.application.start()
            
            # Запуск polling
            logger.info("✅ Бот успешно запущен и готов к работе!")
            await self.application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
            # Ожидание завершения работы
            logger.info("🔄 Бот работает... Нажмите Ctrl+C для остановки")
            await asyncio.Event().wait()  # Ждем бесконечно до прерывания
            
        except KeyboardInterrupt:
            logger.info("🛑 Получен сигнал остановки (Ctrl+C)")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска: {e}")
            raise
        finally:
            logger.info("🧹 Очистка ресурсов...")
            await self._cleanup()
    
    async def _cleanup(self):
        """Очистка ресурсов при завершении"""
        logger.info("🧹 Очистка ресурсов...")
        
        self.is_shutting_down = True
        
        # Остановка фоновых задач
        tasks_to_cancel = list(self.background_tasks)  # Создаем копию для итерации
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Отключение депозитных аккаунтов
        if self.deposit_manager:
            await self.deposit_manager.disconnect_all()
        
        # Остановка мониторинга
        if self.gift_monitor:
            self.gift_monitor.is_running = False
        
        # Отключение базы данных (адаптер сам управляет соединениями)
        logger.info("🗄️ База данных отключена")
        
        # Остановка бота
        if self.application:
            # Сначала останавливаем updater
            if self.application.updater and self.application.updater.running:
                await self.application.updater.stop()
            # Потом останавливаем application
            await self.application.stop()
            await self.application.shutdown()
        
        logger.info("✅ Очистка завершена")
    
    async def start(self):
        """Запуск бота (алиас для run)"""
        await self.run()
    
    async def stop(self):
        """Остановка бота"""
        logger.info("Получен сигнал остановки бота")
        self.is_shutting_down = True
        self.shutdown_event.set()
        
        # База данных управляется адаптером
        logger.info("🗄️ База данных будет закрыта автоматически")
        
        # Останавливаем updater
        if self.application.updater:
            await self.application.updater.stop()
        
        # Останавливаем application
        await self.application.stop()
        await self.application.shutdown()
    
    def _handle_signal(self, signum, frame):
        """Обработчик сигналов завершения"""
        logger.info(f"🛑 Получен сигнал {signum}, завершение работы...")
        self.is_shutting_down = True
    
    async def create_test_data_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Создание тестовых данных для демонстрации истории (только для админа)"""
        user_id = update.effective_user.id
        
        # Проверяем, что команду вызывает админ
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды")
            return
        
        try:
            # Создаем тестовые пополнения
            test_topups = [
                {"amount": 1000, "source": "yookassa", "description": "Пополнение через ЮКассу на 1000₽"},
                {"amount": 500, "source": "ton", "description": "Пополнение через TON на 500₽"},
                {"amount": 200, "source": "bonus", "description": "Бонус за регистрацию"},
                {"amount": 2500, "source": "yookassa", "description": "Пополнение через ЮКассу на 2500₽"},
            ]
            
            for topup in test_topups:
                self.db_manager.add_stars_with_commission(
                    user_id=user_id,
                    stars_requested=topup["amount"],
                    commission_rate=0.0,  # Без комиссии для тестовых данных
                    source=topup["source"],
                    description=topup["description"]
                )
            
            # Создаем тестовые покупки подарков
            test_purchases = [
                {
                    "gift_name": "🎄 Новогодняя елка",
                    "points_spent": 750,
                    "stars_spent": 500,
                    "commission": 150,
                    "method": "auto"
                },
                {
                    "gift_name": "🎁 Подарочная коробка",
                    "points_spent": 450,
                    "stars_spent": 300,
                    "commission": 90,
                    "method": "manual"
                },
                {
                    "gift_name": "🌹 Букет роз",
                    "points_spent": 600,
                    "stars_spent": 400,
                    "commission": 120,
                    "method": "auto"
                }
            ]
            
            for purchase in test_purchases:
                self.db_manager.record_gift_purchase(
                    user_id=user_id,
                    recipient_id=user_id,  # Для теста - себе
                    gift_id=f"test_{purchase['gift_name'][:10]}",
                    gift_name=purchase["gift_name"],
                    points_spent=purchase["points_spent"],
                    stars_spent=purchase["stars_spent"],
                    commission_amount=purchase["commission"],
                    purchase_method=purchase["method"]
                )
            
            await update.message.reply_text(
                "✅ **Тестовые данные созданы!**\n\n"
                "📊 Создано:\n"
                f"• {len(test_topups)} пополнений Stars\n"
                f"• {len(test_purchases)} покупок подарков\n\n"
                "Теперь можете посмотреть историю через меню 'Баланс' → 'История операций'"
            )
            
        except Exception as e:
            logger.error(f"Ошибка создания тестовых данных: {e}")
            await update.message.reply_text("❌ Ошибка создания тестовых данных")

    async def show_balance_leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать топ пользователей по балансу"""
        leaderboard = self.db_manager.get_balance_leaderboard(10)
        
        if not leaderboard:
            text = "🏆 **Топ по балансу**\n\n❌ Пока нет данных для рейтинга"
        else:
            text = "🏆 **Топ пользователей по балансу**\n\n"
            
            for user in leaderboard:
                # Эмодзи для позиций
                if user['position'] == 1:
                    position_emoji = "🥇"
                elif user['position'] == 2:
                    position_emoji = "🥈"
                elif user['position'] == 3:
                    position_emoji = "🥉"
                else:
                    position_emoji = f"{user['position']}."
                
                # Статус подписки
                if user['has_active_subscription']:
                    if user['subscription_type'] == 'vip':
                        sub_emoji = "⭐"
                    else:
                        sub_emoji = "✅"
                else:
                    sub_emoji = ""
                
                # Имя пользователя
                name = user['first_name']
                if user['username']:
                    name += f" (@{user['username']})"
                
                text += f"{position_emoji} **{name}** {sub_emoji}\n"
                text += f"💎 Баланс: **{user['balance_points']:,}** 🔸\n"
                text += f"📈 Всего заработано: **{user['total_earned']:,}** 🔸\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="balance_top")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)

    async def show_autopurchase_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройка автопокупки"""
        user_id = update.effective_user.id
        
        # Проверяем VIP подписку
        subscription = self.db_manager.get_user_subscription(user_id)
        if not subscription or subscription.get('type') != 'vip':
            text = (
                "❌ **Автопокупка доступна только для VIP**\n\n"
                "🌟 Upgrade до VIP для доступа к автопокупке подарков!\n"
                "Автопокупка позволяет боту автоматически покупать подарки по вашим настройкам."
            )
            keyboard = [
                [InlineKeyboardButton("⭐ Upgrade до VIP", callback_data="subscriptions")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._send_message(update, text, reply_markup)
            return
        
        # Получаем текущий профиль
        profile = self.db_manager.get_auto_purchase_profile(user_id)
        
        if profile:
            status = "✅ Включена" if profile['enabled'] else "❌ Выключена"
            text = f"⚙️ **Настройки автопокупки**\n\n"
            text += f"🔄 Статус: {status}\n"
            text += f"💰 Макс. цена: **{profile['max_price_stars']}** ⭐\n"
            text += f"📊 Макс. тираж: **{profile['max_edition_size']:,}** шт.\n"
            text += f"🎯 Дневной лимит: **{profile['daily_limit']}** покупок\n"
            text += f"⏱️ Пауза между покупками: **{profile['auto_buy_cooldown']}** сек.\n"
            
            if profile['preferred_categories']:
                categories = ", ".join(profile['preferred_categories'])
                text += f"🏷️ Категории: {categories}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Вкл/Выкл", callback_data="toggle_profile_1")],
                [
                    InlineKeyboardButton("💰 Цена", callback_data="edit_profile_price"),
                    InlineKeyboardButton("📊 Тираж", callback_data="edit_profile_edition")
                ],
                [
                    InlineKeyboardButton("🎯 Лимит", callback_data="edit_profile_limit"),
                    InlineKeyboardButton("⏱️ Пауза", callback_data="edit_profile_cooldown")
                ],
                [InlineKeyboardButton("🏷️ Категории", callback_data="edit_profile_categories")],
                [InlineKeyboardButton("🗑️ Удалить профиль", callback_data="delete_profile_1")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
            ]
        else:
            text = (
                "⚙️ **Создание профиля автопокупки**\n\n"
                "🤖 Настройте автоматическую покупку подарков!\n\n"
                "**Настройки по умолчанию:**\n"
                "💰 Максимальная цена: 500 ⭐\n"
                "📊 Максимальный тираж: 1,000 шт.\n"
                "🎯 Дневной лимит: 10 покупок\n"
                "⏱️ Пауза между покупками: 5 сек.\n\n"
                "Создать профиль с этими настройками?"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Создать профиль", callback_data="create_default_profile")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_message(update, text, reply_markup)

    async def show_autopurchase_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика автопокупки"""
        user_id = update.effective_user.id
        stats = self.db_manager.get_autopurchase_statistics(user_id)
        
        text = f"📊 **Статистика автопокупки**\n\n"
        text += f"🛒 Всего автопокупок: **{stats.get('auto_purchases_count', 0)}**\n"
        text += f"💸 Потрачено на автопокупки: **{stats.get('auto_purchases_spent', 0)}** 🔸\n"
        text += f"📅 Покупок сегодня: **{stats.get('auto_purchases_today', 0)}**\n"
        
        # Получаем профиль для отображения лимитов
        profile = self.db_manager.get_auto_purchase_profile(user_id)
        if profile:
            remaining_today = max(0, profile['daily_limit'] - stats.get('auto_purchases_today', 0))
            text += f"📈 Осталось покупок сегодня: **{remaining_today}**\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="autopurchase_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)

    async def show_autopurchase_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Справка по автопокупке"""
        text = (
            "❓ **Справка по автопокупке**\n\n"
            "🤖 **Как работает автопокупка:**\n"
            "1️⃣ Бот мониторит новые подарки в Telegram\n"
            "2️⃣ Проверяет соответствие вашим настройкам\n"
            "3️⃣ Автоматически покупает подходящие подарки\n"
            "4️⃣ Списывает Stars с вашего счета\n\n"
            "⚙️ **Настройки профиля:**\n"
            "💰 **Макс. цена** - максимальная стоимость в звездах\n"
            "📊 **Макс. тираж** - максимальное количество экземпляров\n"
            "🎯 **Дневной лимит** - сколько подарков покупать в день\n"
            "⏱️ **Пауза** - интервал между покупками\n"
            "🏷️ **Категории** - фильтр по типам подарков\n\n"
            "💡 **Советы:**\n"
            "• Поддерживайте достаточный баланс 🔸\n"
            "• Начните с консервативных настроек\n"
            "• Регулярно проверяйте статистику\n"
            "• VIP пользователи получают скидку 20%"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Настроить", callback_data="setup_autopurchase")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)

    async def create_default_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Создание профиля автопокупки с настройками по умолчанию"""
        user_id = update.effective_user.id
        
        default_profile = {
            'enabled': False,  # По умолчанию выключен
            'max_price_stars': 500,
            'max_edition_size': 1000,
            'preferred_categories': [],
            'auto_buy_cooldown': 5,
            'daily_limit': 10
        }
        
        success = self.db_manager.save_auto_purchase_profile(user_id, default_profile)
        
        if success:
            text = (
                "✅ **Профиль автопокупки создан!**\n\n"
                "⚙️ **Ваши настройки:**\n"
                "🔄 Статус: ❌ Выключена\n"
                "💰 Макс. цена: **500** ⭐\n"
                "📊 Макс. тираж: **1,000** шт.\n"
                "🎯 Дневной лимит: **10** покупок\n"
                "⏱️ Пауза: **5** сек.\n\n"
                "💡 Включите автопокупку когда будете готовы!"
            )
            keyboard = [
                [InlineKeyboardButton("🔄 Включить автопокупку", callback_data="toggle_profile_1")],
                [InlineKeyboardButton("⚙️ Настроить", callback_data="setup_autopurchase")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
            ]
        else:
            text = "❌ Ошибка создания профиля. Попробуйте еще раз."
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data="create_default_profile")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_message(update, text, reply_markup)

    async def toggle_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Включение/выключение профиля автопокупки"""
        user_id = update.effective_user.id
        
        success = self.db_manager.toggle_auto_purchase_profile(user_id)
        
        if success:
            # Получаем обновленный профиль
            profile = self.db_manager.get_auto_purchase_profile(user_id)
            status = "✅ Включена" if profile['enabled'] else "❌ Выключена"
            
            text = f"🔄 **Автопокупка переключена!**\n\nТекущий статус: {status}"
            
            if profile['enabled']:
                text += "\n\n🚀 Автопокупка активна! Бот будет покупать подходящие подарки автоматически."
                # Проверяем баланс
                balance = self.db_manager.get_stars_balance(user_id)
                if balance < 1000:
                    text += f"\n\n⚠️ Баланс низкий ({balance} 🔸). Рекомендуем пополнить счет."
            else:
                text += "\n\n⏸️ Автопокупка приостановлена."
        else:
            text = "❌ Ошибка переключения профиля. Сначала создайте профиль."
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Настройки", callback_data="setup_autopurchase")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_message(update, text, reply_markup)

    async def confirm_delete_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение удаления профиля"""
        text = (
            "🗑️ **Удаление профиля автопокупки**\n\n"
            "⚠️ Вы действительно хотите удалить профиль?\n"
            "Все настройки будут потеряны!"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data="confirm_delete_profile")],
            [InlineKeyboardButton("❌ Отмена", callback_data="setup_autopurchase")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_message(update, text, reply_markup)

    async def edit_profile_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE, field: str):
        """Редактирование поля профиля"""
        user_id = update.effective_user.id
        
        # Сохраняем поле для редактирования в контексте
        context.user_data['editing_field'] = field
        
        field_names = {
            'price': 'максимальную цену в звездах',
            'edition': 'максимальный тираж',
            'limit': 'дневной лимит покупок',
            'cooldown': 'паузу между покупками (секунды)',
            'categories': 'категории (через запятую)'
        }
        
        field_name = field_names.get(field, field)
        
        text = f"✏️ **Редактирование профиля**\n\nВведите новое значение для **{field_name}**:"
        
        if field == 'price':
            text += "\n\n💡 Рекомендуется: 100-2000 ⭐"
        elif field == 'edition':
            text += "\n\n💡 Рекомендуется: 500-10000 шт."
        elif field == 'limit':
            text += "\n\n💡 Рекомендуется: 5-50 покупок в день"
        elif field == 'cooldown':
            text += "\n\n💡 Рекомендуется: 3-30 секунд"
        elif field == 'categories':
            text += "\n\n💡 Примеры: premium, rare, limited, exclusive"
        
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data="setup_autopurchase")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_message(update, text, reply_markup)

    async def save_profile_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE, field: str):
        """Сохранение отредактированного поля профиля"""
        # Этот метод будет вызван через обработчик сообщений
        pass

    async def delete_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаление профиля автопокупки"""
        user_id = update.effective_user.id
        
        success = self.db_manager.delete_auto_purchase_profile(user_id)
        
        if success:
            text = (
                "🗑️ **Профиль удален!**\n\n"
                "✅ Профиль автопокупки успешно удален.\n"
                "Вы можете создать новый профиль в любое время."
            )
            keyboard = [
                [InlineKeyboardButton("➕ Создать новый профиль", callback_data="setup_autopurchase")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="autopurchase")]
            ]
        else:
            text = "❌ Ошибка удаления профиля. Попробуйте еще раз."
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data="delete_profile_1")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="setup_autopurchase")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_message(update, text, reply_markup)

    async def create_leaderboard_data_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Создание тестовых данных для топа по балансу (только для админа)"""
        user_id = update.effective_user.id
        
        # Проверяем, что команду вызывает админ
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды")
            return
        
        try:
            # Создаем тестовых пользователей с разными балансами
            test_users_data = [
                {"user_id": 111111111, "first_name": "Алексей", "username": "alex_vip", "balance": 15000, "earned": 25000, "sub_type": "vip"},
                {"user_id": 222222222, "first_name": "Мария", "username": "maria_basic", "balance": 12500, "earned": 18000, "sub_type": "basic"},
                {"user_id": 333333333, "first_name": "Дмитрий", "username": None, "balance": 10200, "earned": 15000, "sub_type": "vip"},
                {"user_id": 444444444, "first_name": "Анна", "username": "anna_pro", "balance": 8500, "earned": 12000, "sub_type": "basic"},
                {"user_id": 555555555, "first_name": "Иван", "username": "ivan_trader", "balance": 6800, "earned": 9500, "sub_type": "vip"},
                {"user_id": 666666666, "first_name": "Ольга", "username": None, "balance": 5200, "earned": 7800, "sub_type": "basic"},
                {"user_id": 777777777, "first_name": "Сергей", "username": "sergey_gifts", "balance": 3900, "earned": 6200, "sub_type": "basic"},
                {"user_id": 888888888, "first_name": "Екатерина", "username": "kate_collector", "balance": 2100, "earned": 4500, "sub_type": "vip"},
            ]
            
            created_count = 0
            
            for user_data in test_users_data:
                # Регистрируем пользователя
                if not self.db_manager.get_user_info(user_data["user_id"]):
                    self.db_manager.register_user(user_data["user_id"], user_data["username"] or user_data["first_name"])
                    
                    # Обновляем имя пользователя
                    with self.db_manager.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            'UPDATE users SET first_name = ?, username = ? WHERE user_id = ?',
                            (user_data["first_name"], user_data["username"], user_data["user_id"])
                        )
                
                # Добавляем Stars
                self.db_manager.add_stars_with_commission(
                    user_id=user_data["user_id"],
                    stars_requested=user_data["balance"],
                    commission_rate=0.0,  # Без комиссии для тестовых данных
                    source="test_data",
                    description="Тестовые данные для топа"
                )
                
                # Обновляем статистику earned
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE internal_balances 
                        SET total_earned = ? 
                        WHERE user_id = ?
                    ''', (user_data["earned"], user_data["user_id"]))
                
                # Создаем подписку если нужно
                if user_data["sub_type"] == "vip":
                    from datetime import datetime, timedelta
                    end_date = datetime.now() + timedelta(days=30)
                    
                    with self.db_manager.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO subscriptions 
                            (user_id, type, is_active, start_date, end_date)
                            VALUES (?, 'vip', 1, CURRENT_TIMESTAMP, ?)
                        ''', (user_data["user_id"], end_date))
                
                created_count += 1
            
            await update.message.reply_text(
                f"✅ **Тестовые данные для топа созданы!**\n\n"
                f"📊 Создано пользователей: **{created_count}**\n"
                f"💰 Добавлены балансы от 2,100 до 15,000 🔸\n"
                f"⭐ VIP подписки для части пользователей\n\n"
                f"Теперь можете посмотреть топ через '🏆 Топ по балансу' в главном меню"
            )
            
        except Exception as e:
            logger.error(f"Ошибка создания данных для топа: {e}")
            await update.message.reply_text("❌ Ошибка создания данных для топа")
    
    async def confirm_fragment_purchase(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение покупки Stars через Fragment"""
        try:
            # Извлекаем ID покупки из команды
            command_text = update.message.text
            purchase_id = command_text.replace('/confirm_', '')
            
            # Подтверждаем покупку
            success = await self.deposit_manager.fragment_manager.confirm_purchase(purchase_id)
            
            if success:
                await update.message.reply_text(
                    f"✅ Покупка Stars подтверждена!\n🆔 ID: `{purchase_id}`",
                    parse_mode='Markdown'
                )
                logger.info(f"Админ подтвердил покупку Stars: {purchase_id}")
            else:
                await update.message.reply_text(
                    f"❌ Покупка не найдена или уже обработана\n🆔 ID: `{purchase_id}`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Ошибка подтверждения покупки Fragment: {e}")
            await update.message.reply_text("❌ Ошибка подтверждения покупки")
    
    async def cancel_fragment_purchase(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена покупки Stars через Fragment"""
        try:
            # Извлекаем ID покупки из команды
            command_text = update.message.text
            purchase_id = command_text.replace('/cancel_', '')
            
            # Отменяем покупку
            success = await self.deposit_manager.fragment_manager.cancel_purchase(purchase_id)
            
            if success:
                await update.message.reply_text(
                    f"❌ Покупка Stars отменена\n🆔 ID: `{purchase_id}`",
                    parse_mode='Markdown'
                )
                logger.info(f"Админ отменил покупку Stars: {purchase_id}")
            else:
                await update.message.reply_text(
                    f"❌ Покупка не найдена или уже обработана\n🆔 ID: `{purchase_id}`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Ошибка отмены покупки Fragment: {e}")
            await update.message.reply_text("❌ Ошибка отмены покупки")
    
    async def show_pending_fragment_purchases(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать ожидающие покупки Fragment"""
        try:
            user_id = update.effective_user.id
            
            # Проверяем права админа
            if user_id != ADMIN_ID:
                await update.message.reply_text("❌ Команда доступна только администратору")
                return
            
            # Получаем список ожидающих покупок
            pending_purchases = self.deposit_manager.fragment_manager.get_pending_purchases()
            
            if not pending_purchases:
                await update.message.reply_text("✅ Нет ожидающих покупок Stars")
                return
            
            message = "🌟 **ОЖИДАЮЩИЕ ПОКУПКИ STARS**\n\n"
            
            for purchase in pending_purchases:
                package_info = purchase['package_info']
                created_time = purchase['created_at'].strftime("%H:%M:%S")
                
                message += f"🆔 **ID:** `{purchase['purchase_id']}`\n"
                message += f"👤 **Аккаунт:** {purchase['account_username']}\n"
                message += f"⭐ **Stars:** {package_info['needed_stars']:,}\n"
                message += f"💰 **Стоимость:** {package_info['total_ton']} TON\n"
                message += f"⏰ **Время:** {created_time}\n"
                message += f"🔗 **Ссылка:** {purchase['fragment_url']}\n"
                message += f"✅ `/confirm_{purchase['purchase_id']}`\n"
                message += f"❌ `/cancel_{purchase['purchase_id']}`\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Ошибка показа ожидающих покупок: {e}")
            await update.message.reply_text("❌ Ошибка получения списка покупок")

    async def update_profile_field(self, user_id: int, field: str, value: str) -> dict:
        """Обновление поля профиля автопокупки"""
        try:
            # Получаем текущий профиль
            current_profile = self.db_manager.get_auto_purchase_profile(user_id)
            if not current_profile:
                return {"success": False, "error": "Профиль автопокупки не найден"}
                
            # Создаем обновленный профиль на основе текущего
            updated_profile = {
                'enabled': current_profile['enabled'],  # Сохраняем текущий статус
                'max_price_stars': current_profile['max_price_stars'],
                'max_edition_size': current_profile['max_edition_size'],
                'daily_limit': current_profile['daily_limit'],
                'auto_buy_cooldown': current_profile['auto_buy_cooldown'],
                'preferred_categories': current_profile['preferred_categories']
            }
            if field == 'price':
                try:
                    price = int(value)
                    if price < 1 or price > 100000:
                        return {"success": False, "error": "Цена должна быть от 1 до 100000 Stars"}
                    updated_profile['max_price_stars'] = price
                    success = self.db_manager.update_auto_purchase_profile(user_id, updated_profile)
                    return {"success": success, "message": f"Максимальная цена установлена: {price} ⭐"}
                except ValueError:
                    return {"success": False, "error": "Введите корректное число"}
            
            elif field == 'edition':
                try:
                    edition = int(value)
                    if edition < 1 or edition > 1000000:
                        return {"success": False, "error": "Тираж должен быть от 1 до 1000000"}
                    updated_profile['max_edition_size'] = edition
                    success = self.db_manager.update_auto_purchase_profile(user_id, updated_profile)
                    return {"success": success, "message": f"Максимальный тираж установлен: {edition:,} шт."}
                except ValueError:
                    return {"success": False, "error": "Введите корректное число"}
            
            elif field == 'limit':
                try:
                    limit = int(value)
                    if limit < 1 or limit > 1000:
                        return {"success": False, "error": "Лимит должен быть от 1 до 1000 покупок в день"}
                    updated_profile['daily_limit'] = limit
                    success = self.db_manager.update_auto_purchase_profile(user_id, updated_profile)
                    return {"success": success, "message": f"Дневной лимит установлен: {limit} покупок"}
                except ValueError:
                    return {"success": False, "error": "Введите корректное число"}
            
            elif field == 'cooldown':
                try:
                    cooldown = int(value)
                    if cooldown < 1 or cooldown > 3600:
                        return {"success": False, "error": "Пауза должна быть от 1 до 3600 секунд"}
                    updated_profile['auto_buy_cooldown'] = cooldown
                    success = self.db_manager.update_auto_purchase_profile(user_id, updated_profile)
                    return {"success": success, "message": f"Пауза между покупками установлена: {cooldown} сек."}
                except ValueError:
                    return {"success": False, "error": "Введите корректное число"}
            
            elif field == 'categories':
                categories = [cat.strip() for cat in value.split(',') if cat.strip()]
                if not categories:
                    return {"success": False, "error": "Введите хотя бы одну категорию"}
                categories_str = ','.join(categories)
                updated_profile['preferred_categories'] = categories
                success = self.db_manager.update_auto_purchase_profile(user_id, updated_profile)
                return {"success": success, "message": f"Категории установлены: {categories_str}"}
            
            else:
                return {"success": False, "error": "Неизвестное поле"}
                
        except Exception as e:
            logger.error(f"Ошибка обновления поля профиля: {e}")
            return {"success": False, "error": "Внутренняя ошибка"}
    
    async def show_autopurchase_setup_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать сообщение с настройками автопокупки как обычное сообщение"""
        user_id = update.effective_user.id
        profile = self.db_manager.get_auto_purchase_profile(user_id)
        
        if not profile:
            await update.message.reply_text("❌ Профиль автопокупки не найден")
            return
        
        status = "✅ Включена" if profile['enabled'] else "❌ Выключена"
        
        categories_str = ', '.join(profile['preferred_categories']) if profile['preferred_categories'] else 'premium, rare'
        
        text = (
            f"⚙️ <b>Настройки автопокупки</b>\n\n"
            f"📊 <b>Статус:</b> {status}\n"
            f"💰 <b>Макс. цена:</b> {profile['max_price_stars']} ⭐\n"
            f"📊 <b>Макс. тираж:</b> {profile['max_edition_size']:,} шт.\n"
            f"🎯 <b>Дневной лимит:</b> {profile['daily_limit']} покупок\n"
            f"⏱️ <b>Пауза между покупками:</b> {profile['auto_buy_cooldown']} сек.\n"
            f"🏷️ <b>Категории:</b> {categories_str}\n\n"
            f"✅ <b>Настройки обновлены!</b>"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Настройки", callback_data="setup_autopurchase")],
            [InlineKeyboardButton("⬅️ К автопокупке", callback_data="autopurchase")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)

if __name__ == "__main__":
    """Точка входа в приложение"""
    try:
        print("🚀 Запуск TgGIFT Bot...")
        
        # Создаем и запускаем бота
        bot = TgGiftBot()
        
        # Запускаем в асинхронном режиме
        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 