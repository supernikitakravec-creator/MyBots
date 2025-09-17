from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from loguru import logger
from config.settings import settings
from utils.helpers import format_price_message

class BotHandlers:
    """Обработчики команд Telegram-бота"""
    
    def __init__(self, parser_manager, webasyst_api):
        self.parser_manager = parser_manager
        self.webasyst_api = webasyst_api
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        # Проверяем, является ли пользователь администратором
        if str(user_id) != settings.TELEGRAM_ADMIN_ID:
            await update.message.reply_text(
                "🚫 У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору для получения доступа."
            )
            return
        
        welcome_text = (
            "🤖 <b>Парсер цен - Центр управления</b>\n\n"
            "Добро пожаловать! Я помогу вам отслеживать цены конкурентов "
            "и автоматически обновлять цены в вашем магазине Webasyst.\n\n"
            "<b>Доступные команды:</b>\n"
            "📊 /status - Статус системы\n"
            "🔍 /parse_now - Запустить парсинг сейчас\n"
            "⚙️ /settings - Настройки\n"
            "📈 /stats - Статистика\n"
            "❓ /help - Помощь"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Статус", callback_data="status"),
                InlineKeyboardButton("🔍 Парсинг", callback_data="parse_now")
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
                InlineKeyboardButton("📈 Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        await self._check_admin(update)
        await self._show_status(update, context)
    
    async def parse_now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /parse_now"""
        await self._check_admin(update)
        await self._start_parsing(update, context)
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /settings"""
        await self._check_admin(update)
        await self._show_settings(update, context)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats"""
        await self._check_admin(update)
        await self._show_stats(update, context)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "❓ <b>Справка по командам</b>\n\n"
            "<b>Основные команды:</b>\n"
            "• /start - Запуск бота и главное меню\n"
            "• /status - Показать текущий статус системы\n"
            "• /parse_now - Запустить парсинг цен вручную\n"
            "• /settings - Настройки парсера и API\n"
            "• /stats - Статистика работы\n"
            "• /help - Эта справка\n\n"
            "<b>Автоматические уведомления:</b>\n"
            "• Изменения цен в реальном времени\n"
            "• Ошибки парсинга\n"
            "• Статус обновлений в Webasyst\n\n"
            "<b>Настройка:</b>\n"
            "1. Укажите токен бота в .env файле\n"
            "2. Настройте Webasyst API\n"
            "3. Добавьте сайты для парсинга\n"
            "4. Запустите автоматический режим"
        )
        
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "status":
            await self._show_status(update, context, query)
        elif query.data == "parse_now":
            await self._start_parsing(update, context, query)
        elif query.data == "settings":
            await self._show_settings(update, context, query)
        elif query.data == "stats":
            await self._show_stats(update, context, query)
        elif query.data == "help":
            await self._show_help(update, context, query)
    
    async def _check_admin(self, update: Update):
        """Проверка прав администратора"""
        user_id = update.effective_user.id
        if str(user_id) != settings.TELEGRAM_ADMIN_ID:
            await update.message.reply_text("🚫 У вас нет доступа к этой команде.")
            return False
        return True
    
    async def _show_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Показать статус системы"""
        status_text = (
            "📊 <b>Статус системы</b>\n\n"
            f"🤖 <b>Бот:</b> Активен\n"
            f"🔗 <b>Webasyst API:</b> {'Подключен' if self.webasyst_api.token else 'Не настроен'}\n"
            f"⏰ <b>Интервал парсинга:</b> {settings.PARSING_INTERVAL_MINUTES} мин\n"
            f"🌐 <b>Сайтов для парсинга:</b> {len([s for s in settings.TARGET_SITES if s['enabled']])}\n"
            f"📈 <b>Последний парсинг:</b> {self.parser_manager.get_last_parsing_time()}\n"
            f"✅ <b>Автопарсинг:</b> {'Включен' if self.parser_manager.is_auto_parsing_enabled() else 'Выключен'}"
        )
        
        if query:
            await query.edit_message_text(status_text, parse_mode='HTML')
        else:
            await update.message.reply_text(status_text, parse_mode='HTML')
    
    async def _start_parsing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Запустить парсинг"""
        message = query.edit_message_text if query else update.message.reply_text
        
        await message("🔍 <b>Запуск парсинга...</b>", parse_mode='HTML')
        
        try:
            # Запускаем парсинг
            results = await self.parser_manager.run_parsing()
            
            if results:
                summary = (
                    f"✅ <b>Парсинг завершен!</b>\n\n"
                    f"📊 <b>Результаты:</b>\n"
                    f"• Обработано сайтов: {len(results)}\n"
                    f"• Найдено товаров: {sum(len(r.get('products', [])) for r in results)}\n"
                    f"• Обновлено цен: {sum(r.get('updated_prices', 0) for r in results)}"
                )
                
                await message(summary, parse_mode='HTML')
                
                # Отправляем детальные результаты
                for result in results:
                    if result.get('updated_prices', 0) > 0:
                        site_name = result.get('site_name', 'Неизвестный сайт')
                        await message(
                            f"📈 <b>{site_name}</b>: обновлено {result['updated_prices']} цен",
                            parse_mode='HTML'
                        )
            else:
                await message("❌ <b>Ошибка при парсинге</b>", parse_mode='HTML')
                
        except Exception as e:
            logger.error(f"Ошибка при парсинге: {e}")
            await message(f"❌ <b>Ошибка:</b> {str(e)}", parse_mode='HTML')
    
    async def _show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Показать настройки"""
        settings_text = (
            "⚙️ <b>Настройки системы</b>\n\n"
            f"⏰ <b>Интервал парсинга:</b> {settings.PARSING_INTERVAL_MINUTES} мин\n"
            f"⏳ <b>Задержка между запросами:</b> {settings.REQUEST_DELAY_SECONDS} сек\n"
            f"🔄 <b>Максимум попыток:</b> {settings.MAX_RETRIES}\n"
            f"💰 <b>Минимальная наценка:</b> {settings.MIN_PRICE_MARGIN * 100}%\n"
            f"📉 <b>Максимальное снижение:</b> {settings.MAX_PRICE_DROP * 100}%\n\n"
            f"🌐 <b>Сайты для парсинга:</b>\n"
        )
        
        for site in settings.TARGET_SITES:
            status = "✅" if site['enabled'] else "❌"
            settings_text += f"{status} {site['name']}\n"
        
        if query:
            await query.edit_message_text(settings_text, parse_mode='HTML')
        else:
            await update.message.reply_text(settings_text, parse_mode='HTML')
    
    async def _show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Показать статистику"""
        stats = self.parser_manager.get_statistics()
        
        stats_text = (
            "📈 <b>Статистика работы</b>\n\n"
            f"📅 <b>Сегодня:</b>\n"
            f"• Запусков парсинга: {stats.get('today_runs', 0)}\n"
            f"• Обработано товаров: {stats.get('today_products', 0)}\n"
            f"• Обновлено цен: {stats.get('today_updates', 0)}\n\n"
            f"📊 <b>Всего:</b>\n"
            f"• Запусков парсинга: {stats.get('total_runs', 0)}\n"
            f"• Обработано товаров: {stats.get('total_products', 0)}\n"
            f"• Обновлено цен: {stats.get('total_updates', 0)}\n\n"
            f"⏱️ <b>Среднее время парсинга:</b> {stats.get('avg_time', 0):.1f} сек"
        )
        
        if query:
            await query.edit_message_text(stats_text, parse_mode='HTML')
        else:
            await update.message.reply_text(stats_text, parse_mode='HTML')
    
    async def _show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Показать справку"""
        await self.help_command(update, context)
    
    async def send_price_update_notification(self, site_name: str, product_name: str, old_price: float, new_price: float):
        """Отправить уведомление об изменении цены"""
        if not settings.TELEGRAM_ADMIN_ID:
            return
        
        message = format_price_message(site_name, product_name, old_price, new_price)
        
        try:
            # Здесь нужно будет передать context или использовать другой способ отправки
            logger.info(f"Уведомление об изменении цены: {message}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")
    
    async def send_error_notification(self, error_message: str):
        """Отправить уведомление об ошибке"""
        if not settings.TELEGRAM_ADMIN_ID:
            return
        
        error_text = f"❌ <b>Ошибка в системе</b>\n\n{error_message}"
        
        try:
            # Здесь нужно будет передать context или использовать другой способ отправки
            logger.error(f"Уведомление об ошибке: {error_text}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об ошибке: {e}") 