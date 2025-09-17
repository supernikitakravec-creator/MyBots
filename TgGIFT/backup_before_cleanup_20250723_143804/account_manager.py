#!/usr/bin/env python3
"""
Исправленная система управления аккаунтом для автоматических покупок подарков
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from pyrogram import Client
from pyrogram.errors import FloodWait, UserNotParticipant, SessionPasswordNeeded
from config import API_ID, API_HASH, PHONE_NUMBER, COMMISSION_PERCENT, QUEUE_SETTINGS
from database import DatabaseManager

logger = logging.getLogger(__name__)

class AccountManager:
    """Менеджер управляемого аккаунта"""
    
    def __init__(self):
        self.api_id = API_ID
        self.api_hash = API_HASH
        self.phone_number = PHONE_NUMBER
        self.client = None
        self.db_manager = DatabaseManager()
        self.is_connected = False
        self.is_shutting_down = False
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Уменьшаем количество попыток
        self.max_retries = 1  # Только 1 попытка вместо 3
        self.retry_delay = 300  # 5 минут между попытками вместо 2 секунд
        self.connection_timeout = 60  # 60 секунд вместо 30
        
        # Защита от флуда
        self.last_connection_attempt = 0
        self.min_connection_interval = 300  # Минимум 5 минут между попытками подключения
        
        if not all([self.api_id, self.api_hash, self.phone_number]):
            logger.error("Не установлены настройки управляемого аккаунта!")
            raise ValueError("API_ID, API_HASH, PHONE_NUMBER обязательны")
    
    async def connect(self):
        """Подключение к аккаунту БЕЗ повторных попыток при FloodWait"""
        try:
            # Проверяем, прошло ли достаточно времени с последней попытки
            current_time = time.time()
            if current_time - self.last_connection_attempt < self.min_connection_interval:
                wait_time = self.min_connection_interval - (current_time - self.last_connection_attempt)
                logger.warning(f"Слишком рано для повторной попытки. Подождите {wait_time:.0f} секунд")
                return False
            
            self.last_connection_attempt = current_time
            
            if self.is_connected:
                logger.info("Аккаунт уже подключен")
                return True
                
            # Проверяем существование сессии
            import os
            session_file = "gift_bot_account.session"
            if not os.path.exists(session_file):
                logger.warning("Файл сессии не найден. Требуется первичная авторизация")
                # НЕ пытаемся создать новую сессию автоматически
                return False
            
            self.client = Client(
                "gift_bot_account",
                api_id=self.api_id,
                api_hash=self.api_hash,
                phone_number=self.phone_number,
                workdir=".",
                no_updates=True  # Отключаем обновления для экономии ресурсов
            )
            
            # Одна попытка подключения
            await asyncio.wait_for(
                self.client.start(),
                timeout=self.connection_timeout
            )
            
            self.is_connected = True
            logger.info("Управляемый аккаунт подключен успешно")
            
            # Получаем информацию об аккаунте
            try:
                me = await self.client.get_me()
                logger.info(f"[Управляемый аккаунт] Имя: {me.first_name}, Username: @{me.username}, ID: {me.id}")
            except Exception as e:
                logger.warning(f"Не удалось получить информацию об аккаунте: {e}")
            
            # Запускаем обработчик входящих подарков
            @self.client.on_message()
            async def gift_handler(client, message):
                await self._gift_handler(client, message)
            
            logger.info("Обработчик входящих подарков запущен")
            return True
            
        except SessionPasswordNeeded:
            logger.error("Требуется двухфакторная аутентификация. Настройте пароль или отключите 2FA")
            self.is_connected = False
            return False
            
        except FloodWait as e:
            wait_time = e.value
            logger.error(f"FLOOD_WAIT: Telegram требует подождать {wait_time} секунд")
            logger.error("НЕ делаем повторных попыток чтобы избежать увеличения блокировки")
            # НЕ делаем повторную попытку!
            self.is_connected = False
            return False
            
        except asyncio.TimeoutError:
            logger.error(f"Таймаут подключения ({self.connection_timeout} сек)")
            self.is_connected = False
            return False
            
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """Отключение от аккаунта"""
        if self.client and self.is_connected:
            try:
                await asyncio.wait_for(
                    self.client.stop(),
                    timeout=10.0
                )
                self.is_connected = False
                logger.info("Управляемый аккаунт отключен")
            except Exception as e:
                logger.error(f"Ошибка отключения аккаунта: {e}")
    
    def calculate_commission_amount(self, amount: int) -> int:
        """Расчет суммы с комиссией"""
        commission = int(amount * COMMISSION_PERCENT / 100)
        return amount + commission
    
    async def process_balance_topup(self, user_id: int, requested_amount: int) -> Dict:
        """Обработка пополнения баланса"""
        try:
            if not self.is_connected:
                return {
                    'success': False,
                    'error': 'Аккаунт не подключен'
                }
            
            # Валидация входных данных
            if not isinstance(requested_amount, int) or requested_amount <= 0:
                return {
                    'success': False,
                    'error': 'Некорректная сумма пополнения'
                }
            
            # Рассчитываем сумму с комиссией
            total_amount = self.calculate_commission_amount(requested_amount)
            commission = total_amount - requested_amount
            
            # Проверяем, есть ли у пользователя активная подписка
            subscription = self.db_manager.get_user_subscription(user_id)
            if not subscription:
                return {
                    'success': False,
                    'error': 'У вас нет активной подписки'
                }
            
            # Получаем информацию о пользователе
            user_info = self.db_manager.get_user_info(user_id)
            if not user_info:
                return {
                    'success': False,
                    'error': 'Пользователь не найден'
                }
            
            return {
                'success': True,
                'user_id': user_id,
                'requested_amount': requested_amount,
                'total_amount': total_amount,
                'commission': commission,
                'commission_percent': COMMISSION_PERCENT,
                'user_name': user_info.get('first_name', 'Пользователь'),
                'subscription_type': subscription['type']
            }
            
        except Exception as e:
            logger.error(f"Ошибка обработки пополнения баланса: {e}")
            return {
                'success': False,
                'error': 'Произошла ошибка при обработке запроса'
            }
    
    async def _send_gift_to_user(self, user_id: int, gift_code: str) -> Dict:
        """Отправка купленного подарка пользователю"""
        try:
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🎁 Получить подарок",
                    url=f"https://t.me/fragment_bot?start=gift_{gift_code}"
                )]
            ])
            
            await self.client.send_message(
                user_id,
                "🎁 **Ваш подарок готов!**\n\n"
                "Для получения подарка:\n"
                "1. Нажмите кнопку ниже\n"
                "2. Следуйте инструкциям бота\n"
                "3. Подтвердите получение\n\n"
                "⚠️ Важно: подарок действителен ограниченное время!",
                reply_markup=keyboard
            )
            
            logger.info(f"Подарок {gift_code} - инструкции отправлены пользователю {user_id}")
            
            return {
                'success': True,
                'message': 'Инструкции по получению подарка отправлены'
            }
            
        except Exception as e:
            logger.error(f"Ошибка отправки подарка пользователю {user_id}: {e}")
            return {
                'success': False,
                'error': f'Не удалось отправить подарок: {str(e)}'
            }
    
    async def buy_gift_for_user(self, user_id: int, gift_url: str, gift_name: str, 
                               price_stars: int) -> Dict:
        """Покупка подарка для пользователя"""
        try:
            if not self.is_connected:
                return {
                    'success': False,
                    'error': 'Аккаунт не подключен'
                }
            
            # Валидация входных данных
            if not isinstance(price_stars, int) or price_stars <= 0:
                return {
                    'success': False,
                    'error': 'Некорректная цена подарка'
                }
            
            # Проверяем баланс пользователя
            user_balance = self.db_manager.get_balance(user_id)
            if user_balance < price_stars:
                return {
                    'success': False,
                    'error': f'Недостаточно средств. Баланс: {user_balance}⭐, требуется: {price_stars}⭐'
                }
            
            # Проверяем подписку
            subscription = self.db_manager.get_user_subscription(user_id)
            if not subscription or subscription['type'] != 'vip':
                return {
                    'success': False,
                    'error': 'У вас нет активной VIP подписки'
                }
            
            # Покупаем подарок БЕЗ повторных попыток
            purchase_result = await self._purchase_gift_once(gift_url, gift_name, price_stars)
            
            if purchase_result['success']:
                # Записываем покупку
                success = self.db_manager.record_purchase(user_id, purchase_result['gift_id'], price_stars)
                
                if not success:
                    return {
                        'success': False,
                        'error': 'Ошибка записи покупки в базу данных'
                    }
                
                # Отправляем подарок
                send_result = await self._send_gift_to_user(user_id, purchase_result.get('gift_code', ''))
                
                if not send_result['success']:
                    logger.error(f"Не удалось отправить подарок пользователю {user_id}: {send_result['error']}")
                
                # Уведомляем пользователя
                await self._notify_user_about_purchase(user_id, gift_name, price_stars)
                
                return {
                    'success': True,
                    'message': f'Подарок "{gift_name}" успешно куплен и отправлен!',
                    'gift_id': purchase_result['gift_id'],
                    'price_stars': price_stars
                }
            else:
                return purchase_result
                
        except Exception as e:
            logger.error(f"Ошибка покупки подарка для пользователя {user_id}: {e}")
            return {
                'success': False,
                'error': 'Произошла ошибка при покупке подарка'
            }
    
    async def _purchase_gift_once(self, gift_url: str, gift_name: str, price_stars: int) -> Dict:
        """Покупка подарка БЕЗ повторных попыток"""
        try:
            # Извлекаем данные из URL
            import re
            match = re.search(r't\.me/([^/?]+)\?start=gift_(\w+)', gift_url)
            if not match:
                logger.error(f"Неверный формат URL подарка: {gift_url}")
                return {
                    'success': False,
                    'error': 'Неверный формат ссылки на подарок'
                }
            
            bot_username = match.group(1)
            gift_code = match.group(2)
            
            # Отправляем команду
            bot = await self.client.get_users(bot_username)
            await self.client.send_message(bot.id, f"/start gift_{gift_code}")
            
            # Ждем ответ
            await asyncio.sleep(2)
            
            # Обрабатываем ответ
            async for message in self.client.get_chat_history(bot.id, limit=1):
                if message.reply_markup and message.reply_markup.inline_keyboard:
                    for row in message.reply_markup.inline_keyboard:
                        for button in row:
                            if button.callback_data and ('buy' in button.text.lower() or 'купить' in button.text.lower()):
                                await message.click(button.callback_data)
                                await asyncio.sleep(3)
                                
                                # Подтверждаем покупку
                                async for confirm_msg in self.client.get_chat_history(bot.id, limit=1):
                                    if confirm_msg.reply_markup and confirm_msg.reply_markup.inline_keyboard:
                                        for confirm_row in confirm_msg.reply_markup.inline_keyboard:
                                            for confirm_btn in confirm_row:
                                                if confirm_btn.callback_data and ('confirm' in confirm_btn.text.lower() or 'подтвердить' in confirm_btn.text.lower()):
                                                    await confirm_msg.click(confirm_btn.callback_data)
                                                    await asyncio.sleep(2)
                                                    
                                                    gift_id = f"gift_{gift_code}_{int(time.time())}"
                                                    logger.info(f"Подарок {gift_name} успешно куплен за {price_stars} звезд")
                                                    
                                                    return {
                                                        'success': True,
                                                        'gift_id': gift_id,
                                                        'gift_code': gift_code,
                                                        'message': f'Подарок "{gift_name}" куплен успешно'
                                                    }
            
            return {
                'success': False,
                'error': 'Не удалось найти кнопку покупки'
            }
            
        except FloodWait as e:
            logger.error(f"FloodWait при покупке: {e.value} секунд. НЕ делаем повторную попытку!")
            return {
                'success': False,
                'error': f'Telegram заблокировал операцию. Попробуйте позже'
            }
            
        except Exception as e:
            logger.error(f"Ошибка покупки подарка: {e}")
            return {
                'success': False,
                'error': f'Не удалось купить подарок: {str(e)}'
            }
    
    async def _notify_user_about_purchase(self, user_id: int, gift_name: str, price_stars: int):
        """Уведомление пользователя о покупке"""
        try:
            self.db_manager.add_notification(
                user_id,
                f"✅ Подарок '{gift_name}' успешно куплен за {price_stars} ⭐!\n"
                f"Проверьте личные сообщения от @{self.phone_number} для получения подарка.",
                'purchase_success'
            )
            
            logger.info(f"Уведомление о покупке {gift_name} сохранено для пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения уведомления для пользователя {user_id}: {e}")
    
    async def get_account_balance(self) -> int:
        """Получение баланса управляемого аккаунта"""
        try:
            if not self.is_connected:
                return 0
            
            # TODO: Реализовать получение реального баланса
            return 10000  # Заглушка
            
        except Exception as e:
            logger.error(f"Ошибка получения баланса аккаунта: {e}")
            return 0
    
    async def check_gift_availability(self, gift_url: str) -> Dict:
        """Проверка доступности подарка"""
        try:
            if not self.is_connected:
                return {
                    'available': False,
                    'error': 'Аккаунт не подключен'
                }
            
            # TODO: Реализовать проверку доступности
            await asyncio.sleep(0.5)
            
            return {
                'available': True,
                'price_stars': 500,
                'name': 'Тестовый подарок'
            }
            
        except Exception as e:
            logger.error(f"Ошибка проверки доступности подарка: {e}")
            return {
                'available': False,
                'error': 'Ошибка проверки доступности'
            }
    
    async def process_queue_purchases(self, available_gifts: List[Dict]) -> List[Dict]:
        """Обработка покупок для очереди пользователей"""
        results = []
        
        try:
            if not self.is_connected:
                logger.error("Аккаунт не подключен для обработки очереди")
                return results
            
            # Проверяем очередь
            queue = self.db_manager.get_purchase_queue()
            if len(queue) > QUEUE_SETTINGS['max_queue_size']:
                logger.warning(f"Очередь превышает лимит: {len(queue)} > {QUEUE_SETTINGS['max_queue_size']}")
                return results
            
            for gift in available_gifts:
                if self.is_shutting_down:
                    logger.info("Остановка обработки очереди из-за shutdown")
                    break
                
                gift_purchased = False
                
                for user in queue:
                    if self.is_shutting_down:
                        break
                    
                    # Проверяем лимиты
                    if user['current_gifts_bought'] >= user['gifts_per_round']:
                        continue
                    
                    # Проверяем баланс
                    if user['balance_stars'] < gift['price_stars']:
                        await self._notify_insufficient_balance(user['user_id'], gift['name'], gift['price_stars'])
                        continue
                    
                    # Покупаем подарок
                    purchase_result = await self.buy_gift_for_user(
                        user['user_id'], 
                        gift['url'], 
                        gift['name'], 
                        gift['price_stars']
                    )
                    
                    if purchase_result['success']:
                        results.append({
                            'user_id': user['user_id'],
                            'gift_name': gift['name'],
                            'price_stars': gift['price_stars'],
                            'status': 'purchased'
                        })
                        gift_purchased = True
                        break
                    else:
                        logger.warning(f"Не удалось купить подарок для пользователя {user['user_id']}: {purchase_result['error']}")
                
                if not gift_purchased:
                    results.append({
                        'gift_name': gift['name'],
                        'status': 'not_purchased',
                        'reason': 'Нет подходящих пользователей в очереди'
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка обработки очереди покупок: {e}")
            return results
    
    async def _notify_insufficient_balance(self, user_id: int, gift_name: str, required_stars: int):
        """Уведомление о недостатке средств"""
        try:
            user_balance = self.db_manager.get_balance(user_id)
            
            self.db_manager.add_notification(
                user_id,
                f"❌ Недостаточно средств для покупки '{gift_name}'\n"
                f"Требуется: {required_stars}⭐, ваш баланс: {user_balance}⭐",
                'insufficient_balance'
            )
            
            logger.info(f"Пользователь {user_id} уведомлен о недостатке средств")
            
        except Exception as e:
            logger.error(f"Ошибка уведомления о недостатке средств: {e}")
    
    async def health_check(self) -> Dict:
        """Проверка здоровья аккаунта"""
        try:
            if not self.is_connected:
                return {
                    'status': 'disconnected',
                    'error': 'Аккаунт не подключен'
                }
            
            me = await self.client.get_me()
            
            return {
                'status': 'healthy',
                'account_name': f"{me.first_name} (@{me.username})",
                'account_id': me.id
            }
            
        except Exception as e:
            logger.error(f"Ошибка health check: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        await self.disconnect()
    
    async def _gift_handler(self, client, message):
        """Обработка входящих подарков на управляемый аккаунт"""
        try:
            # Проверяем, что это подарок звездами
            if hasattr(message, 'gift') and message.gift:
                from_user = message.from_user
                user_id = from_user.id
                username = from_user.username or ''
                stars_amount = getattr(message.gift, 'star_count', 0)
                
                logger.info(f"[Подарок] Получен подарок от {user_id} (@{username}) на {stars_amount} ⭐")
                
                # Регистрируем пользователя
                self.db_manager.register_user(user_id, username, from_user.first_name, from_user.last_name)
                
                # Проверяем подписку
                subscription = self.db_manager.get_user_subscription(user_id)
                
                if not subscription:
                    # Покупка подписки
                    if stars_amount >= 1299:
                        subscription_type = 'vip'
                    elif stars_amount >= 699:
                        subscription_type = 'basic'
                    else:
                        logger.info(f"[Подарок] Недостаточно звезд для подписки: {stars_amount}")
                        return
                    
                    self.db_manager.activate_subscription(user_id, subscription_type)
                    logger.info(f"[Подарок] Подписка {subscription_type} активирована для {user_id}")
                else:
                    # Пополнение баланса (только для VIP)
                    if subscription['type'] == 'vip':
                        self.db_manager.update_balance(
                            user_id,
                            stars_amount,
                            'balance_topup',
                            'Пополнение баланса через подарок'
                        )
                        logger.info(f"[Подарок] Баланс пополнен на {stars_amount} для {user_id}")
                    else:
                        logger.info(f"[Подарок] Пополнение баланса доступно только для VIP. Пользователь {user_id}")
                        
        except Exception as e:
            logger.error(f"Ошибка обработки входящего подарка: {e}") 