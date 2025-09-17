import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from loguru import logger
from config.settings import settings
from bot.handlers import BotHandlers

class TelegramBot:
    """Основной класс Telegram-бота"""
    
    def __init__(self, parser_manager, webasyst_api):
        self.parser_manager = parser_manager
        self.webasyst_api = webasyst_api
        self.handlers = BotHandlers(parser_manager, webasyst_api)
        self.application = None
        
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.error("Не указан токен Telegram-бота")
            raise ValueError("TELEGRAM_BOT_TOKEN не настроен")
    
    async def start(self):
        """Запуск бота"""
        try:
            # Создаем приложение
            self.application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
            
            # Регистрируем обработчики команд
            self._register_handlers()
            
            logger.info("Telegram-бот успешно запущен")
            
            # Запускаем планировщик парсинга в отдельной задаче
            self._start_scheduler()
            
            # Запускаем бота
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Держим бота запущенным - ждем завершения polling
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Получен сигнал прерывания")
            
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            raise
    
    def _register_handlers(self):
        """Регистрация обработчиков команд"""
        
        # Команды
        self.application.add_handler(CommandHandler("start", self.handlers.start_command))
        self.application.add_handler(CommandHandler("status", self.handlers.status_command))
        self.application.add_handler(CommandHandler("parse_now", self.handlers.parse_now_command))
        self.application.add_handler(CommandHandler("settings", self.handlers.settings_command))
        self.application.add_handler(CommandHandler("stats", self.handlers.stats_command))
        self.application.add_handler(CommandHandler("help", self.handlers.help_command))
        
        # Обработчики кнопок
        self.application.add_handler(CallbackQueryHandler(self.handlers.button_callback))
        
        logger.info("Обработчики команд зарегистрированы")
    
    def _start_scheduler(self):
        """Запуск планировщика автоматического парсинга"""
        try:
            # Запускаем планировщик в отдельной задаче
            asyncio.create_task(self._scheduler_loop())
            logger.info(f"Планировщик запущен с интервалом {settings.PARSING_INTERVAL_MINUTES} минут")
        except Exception as e:
            logger.error(f"Ошибка при запуске планировщика: {e}")
    
    async def _scheduler_loop(self):
        """Цикл планировщика"""
        while True:
            try:
                # Ждем указанный интервал
                await asyncio.sleep(settings.PARSING_INTERVAL_MINUTES * 60)
                
                # Запускаем автоматический парсинг
                logger.info("Запуск автоматического парсинга по расписанию")
                results = await self.parser_manager.run_parsing()
                
                if results:
                    # Отправляем уведомление о результатах
                    await self._send_parsing_results(results)
                
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                # Отправляем уведомление об ошибке
                await self.handlers.send_error_notification(f"Ошибка в планировщике: {str(e)}")
    
    async def _send_parsing_results(self, results):
        """Отправка результатов парсинга"""
        if not settings.TELEGRAM_ADMIN_ID:
            return
        
        try:
            total_updates = sum(r.get('updated_prices', 0) for r in results)
            
            if total_updates > 0:
                summary = (
                    f"📊 <b>Автоматический парсинг завершен</b>\n\n"
                    f"✅ Обработано сайтов: {len(results)}\n"
                    f"📈 Обновлено цен: {total_updates}\n"
                    f"⏰ Время: {self.parser_manager.get_last_parsing_time()}"
                )
                
                # Отправляем сообщение через бота
                await self._send_message_to_admin(summary)
                
                # Отправляем детали по каждому сайту
                for result in results:
                    if result.get('updated_prices', 0) > 0:
                        site_name = result.get('site_name', 'Неизвестный сайт')
                        await self._send_message_to_admin(
                            f"📈 <b>{site_name}</b>: обновлено {result['updated_prices']} цен"
                        )
            else:
                await self._send_message_to_admin("📊 Автоматический парсинг завершен. Изменений цен не найдено.")
                
        except Exception as e:
            logger.error(f"Ошибка при отправке результатов парсинга: {e}")
    
    async def _send_message_to_admin(self, message: str):
        """Отправка сообщения администратору"""
        try:
            if self.application and self.application.bot:
                await self.application.bot.send_message(
                    chat_id=settings.TELEGRAM_ADMIN_ID,
                    text=message,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения администратору: {e}")
    
    async def stop(self):
        """Остановка бота"""
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            logger.info("Telegram-бот остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")
    
    async def send_notification(self, message: str):
        """Отправка уведомления администратору"""
        await self._send_message_to_admin(message)
    
    async def send_price_update(self, site_name: str, product_name: str, old_price: float, new_price: float):
        """Отправка уведомления об изменении цены"""
        from utils.helpers import format_price_message
        
        message = format_price_message(site_name, product_name, old_price, new_price)
        await self._send_message_to_admin(message) 