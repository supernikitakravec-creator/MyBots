#!/usr/bin/env python3
"""
Менеджер депозитных аккаунтов для покупки подарков
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from pyrogram import Client
from pyrogram.errors import FloodWait, SessionPasswordNeeded, PhoneNumberInvalid, PhoneCodeInvalid, PhoneCodeExpired
from config import DEPOSIT_ACCOUNTS, STARS_SYSTEM, AUTO_PURCHASE_SETTINGS
import os

logger = logging.getLogger(__name__)

class DepositAccountsManager:
    """Менеджер депозитных аккаунтов"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.accounts = {}  # Подключенные клиенты
        self.account_stats = {}  # Статистика аккаунтов
        
        # Инициализируем статистику
        for account_key in DEPOSIT_ACCOUNTS:
            self.account_stats[account_key] = {
                'daily_purchases': 0,
                'last_purchase_time': None,
                'stars_balance': 0,
                'last_balance_check': None,
                'is_connected': False,
                'last_error': None
            }
        
        logger.info("Менеджер депозитных аккаунтов инициализирован")
    
    async def initialize_accounts(self):
        """Инициализация всех депозитных аккаунтов"""
        logger.info("🏦 Инициализация депозитных аккаунтов...")
        
        total_accounts = len(DEPOSIT_ACCOUNTS)
        active_accounts = sum(1 for config in DEPOSIT_ACCOUNTS.values() if config['is_active'])
        
        logger.info(f"📊 Всего аккаунтов: {total_accounts}, активных: {active_accounts}")
        
        for account_key, account_config in DEPOSIT_ACCOUNTS.items():
            if not account_config['is_active']:
                logger.info(f"⚠️ Аккаунт {account_key} отключен в конфигурации")
                continue
            
            logger.info(f"🔄 Инициализация аккаунта {account_key}...")
            logger.info(f"📱 Номер: {account_config['phone']}")
            logger.info(f"🔧 API ID: {account_config['api_id']}")
            
            try:
                await self._connect_account(account_key, account_config)
                logger.info(f"✅ Аккаунт {account_key} успешно инициализирован")
                
            except Exception as e:
                logger.error(f"❌ Не удалось инициализировать аккаунт {account_key}: {e}")
                self.account_stats[account_key]['last_error'] = str(e)
        
        # Подсчитываем успешно подключенные аккаунты
        connected_count = sum(1 for stats in self.account_stats.values() if stats['is_connected'])
        
        logger.info(f"📈 Итого подключено аккаунтов: {connected_count}/{active_accounts}")
        
        if connected_count == 0:
            logger.warning("⚠️ НИ ОДИН депозитный аккаунт не подключен!")
            logger.warning("💡 Бот будет работать в ограниченном режиме без автопокупок")
        elif connected_count < active_accounts:
            logger.warning(f"⚠️ Подключено только {connected_count} из {active_accounts} аккаунтов")
        else:
            logger.info("🎉 Все депозитные аккаунты успешно подключены!")
        
        # Запускаем фоновые задачи
        asyncio.create_task(self._monitor_accounts())
        asyncio.create_task(self._balance_monitor())
    
    async def _connect_account(self, account_key: str, account_config: Dict):
        """Подключение к депозитному аккаунту"""
        try:
            client = Client(
                name=f"deposit_account_{account_key}",
                api_id=account_config['api_id'],
                api_hash=account_config['api_hash'],
                phone_number=account_config['phone']
            )
            
            logger.info(f"🔗 Подключение к аккаунту {account_key} ({account_config['phone']})...")
            logger.info(f"🔧 Используем API ID: {account_config['api_id']}")
            logger.info(f"🔧 Используем API Hash: {account_config['api_hash'][:8]}...")
            
            # Проверяем, есть ли уже сессия
            session_file = f"deposit_account_{account_key}.session"
            if os.path.exists(session_file):
                logger.info(f"📁 Найден файл сессии: {session_file}")
            else:
                logger.info(f"📁 Файл сессии не найден, будет создан новый")
            
            await client.start()
            
            # Получаем информацию о себе
            me = await client.get_me()
            logger.info(f"✅ Подключен депозитный аккаунт {account_key}: @{me.username or me.first_name}")
            logger.info(f"👤 ID пользователя: {me.id}")
            logger.info(f"📞 Номер телефона: {me.phone_number}")
            
            self.accounts[account_key] = client
            self.account_stats[account_key]['is_connected'] = True
            self.account_stats[account_key]['last_error'] = None
            
            # Проверяем баланс Stars
            await self._check_stars_balance(account_key)
            
        except FloodWait as e:
            wait_time = e.value
            logger.error(f"🚫 FloodWait для аккаунта {account_key}: {wait_time} секунд")
            logger.error(f"⏰ Аккаунт {account_key} заблокирован до: {datetime.now() + timedelta(seconds=wait_time)}")
            logger.error(f"📱 Номер телефона: {account_config['phone']}")
            
            self.account_stats[account_key]['is_connected'] = False
            self.account_stats[account_key]['last_error'] = f"FloodWait: {wait_time}s до {datetime.now() + timedelta(seconds=wait_time)}"
            
            # Ждем указанное время
            logger.info(f"⏳ Ожидание {wait_time} секунд для аккаунта {account_key}...")
            await asyncio.sleep(wait_time)
            
            # Пытаемся подключиться снова
            logger.info(f"🔄 Повторная попытка подключения аккаунта {account_key}...")
            await self._connect_account(account_key, account_config)
            
        except SessionPasswordNeeded:
            logger.error(f"🔐 Для аккаунта {account_key} требуется пароль двухфакторной аутентификации")
            logger.error(f"📱 Номер: {account_config['phone']}")
            logger.error(f"💡 Отключите 2FA или добавьте пароль в конфигурацию")
            
            self.account_stats[account_key]['is_connected'] = False
            self.account_stats[account_key]['last_error'] = "Требуется пароль 2FA"
            
        except PhoneNumberInvalid:
            logger.error(f"📞 Некорректный номер телефона для аккаунта {account_key}: {account_config['phone']}")
            logger.error(f"💡 Проверьте формат номера (должен быть +7XXXXXXXXXX)")
            self.account_stats[account_key]['is_connected'] = False
            self.account_stats[account_key]['last_error'] = "Некорректный номер телефона"
            
        except PhoneCodeInvalid:
            logger.error(f"🔢 Неверный код подтверждения для аккаунта {account_key}")
            logger.error(f"📱 Номер: {account_config['phone']}")
            logger.error(f"💡 Попробуйте запросить код повторно")
            self.account_stats[account_key]['is_connected'] = False
            self.account_stats[account_key]['last_error'] = "Неверный код подтверждения"
            
        except PhoneCodeExpired:
            logger.error(f"⏰ Код подтверждения истек для аккаунта {account_key}")
            logger.error(f"📱 Номер: {account_config['phone']}")
            logger.error(f"💡 Запросите новый код подтверждения")
            self.account_stats[account_key]['is_connected'] = False
            self.account_stats[account_key]['last_error'] = "Код подтверждения истек"
            
        except Exception as e:
            error_message = str(e).lower()
            logger.error(f"❌ Ошибка подключения аккаунта {account_key}: {e}")
            logger.error(f"📱 Номер: {account_config['phone']}")
            logger.error(f"🔧 API ID: {account_config['api_id']}")
            
            # Анализируем тип ошибки
            if "phone_number_banned" in error_message:
                logger.error(f"🚫 НОМЕР ТЕЛЕФОНА ЗАБЛОКИРОВАН в Telegram!")
                logger.error(f"💡 Этот номер больше нельзя использовать для Telegram API")
            elif "api_id_invalid" in error_message:
                logger.error(f"🔧 НЕВЕРНЫЙ API ID! Проверьте my.telegram.org")
            elif "api_hash_invalid" in error_message:
                logger.error(f"🔧 НЕВЕРНЫЙ API HASH! Проверьте my.telegram.org")
            elif "phone_number_occupied" in error_message:
                logger.error(f"📱 Номер уже используется другим приложением")
            elif "timeout" in error_message:
                logger.error(f"⏰ Таймаут подключения к серверам Telegram")
            
            self.account_stats[account_key]['is_connected'] = False
            self.account_stats[account_key]['last_error'] = str(e)
            raise
    
    async def _check_stars_balance(self, account_key: str) -> int:
        """Проверка баланса Stars на аккаунте"""
        try:
            client = self.accounts.get(account_key)
            if not client:
                return 0
            
            # Здесь должен быть код для получения баланса Stars
            # Пока возвращаем тестовое значение
            # TODO: Реализовать получение реального баланса Stars
            
            balance = 1000  # Тестовое значение
            self.account_stats[account_key]['stars_balance'] = balance
            self.account_stats[account_key]['last_balance_check'] = datetime.now()
            
            logger.info(f"Баланс Stars аккаунта {account_key}: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"Ошибка проверки баланса Stars {account_key}: {e}")
            return 0
    
    async def _monitor_accounts(self):
        """Мониторинг состояния аккаунтов"""
        while True:
            try:
                for account_key in self.accounts:
                    if not self.account_stats[account_key]['is_connected']:
                        continue
                    
                    # Проверяем подключение
                    try:
                        client = self.accounts[account_key]
                        await client.get_me()
                    except Exception as e:
                        logger.warning(f"Потеряно подключение к аккаунту {account_key}: {e}")
                        self.account_stats[account_key]['is_connected'] = False
                        self.account_stats[account_key]['last_error'] = str(e)
                        
                        # Пытаемся переподключиться
                        try:
                            account_config = DEPOSIT_ACCOUNTS[account_key]
                            await self._connect_account(account_key, account_config)
                        except Exception as reconnect_error:
                            logger.error(f"Не удалось переподключить аккаунт {account_key}: {reconnect_error}")
                
                # Сброс дневной статистики в полночь
                now = datetime.now()
                if now.hour == 0 and now.minute == 0:
                    for account_key in self.account_stats:
                        self.account_stats[account_key]['daily_purchases'] = 0
                
                await asyncio.sleep(300)  # Проверяем каждые 5 минут
                
            except Exception as e:
                logger.error(f"Ошибка мониторинга аккаунтов: {e}")
                await asyncio.sleep(60)
    
    async def _balance_monitor(self):
        """Мониторинг баланса Stars"""
        while True:
            try:
                for account_key in self.accounts:
                    if not self.account_stats[account_key]['is_connected']:
                        continue
                    
                    # Проверяем баланс каждые 30 минут
                    last_check = self.account_stats[account_key]['last_balance_check']
                    if not last_check or (datetime.now() - last_check).total_seconds() > 1800:
                        balance = await self._check_stars_balance(account_key)
                        
                        # Если баланс низкий, уведомляем админа
                        if balance < AUTO_PURCHASE_SETTINGS['balance_reserve']:
                            await self._notify_low_balance(account_key, balance)
                
                await asyncio.sleep(600)  # Проверяем каждые 10 минут
                
            except Exception as e:
                logger.error(f"Ошибка мониторинга баланса: {e}")
                await asyncio.sleep(60)
    
    async def _notify_low_balance(self, account_key: str, balance: int):
        """Уведомление о низком балансе"""
        try:
            account_config = DEPOSIT_ACCOUNTS[account_key]
            message = (
                f"⚠️ Низкий баланс Stars!\n\n"
                f"Аккаунт: {account_config['name']}\n"
                f"Баланс: {balance} ⭐\n"
                f"Требуется пополнение для продолжения автопокупок"
            )
            
            # Здесь должна быть отправка уведомления админу
            logger.warning(f"Низкий баланс на аккаунте {account_key}: {balance} Stars")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о низком балансе: {e}")
    
    def _get_best_account_for_purchase(self) -> Optional[str]:
        """Выбор лучшего аккаунта для покупки"""
        best_account = None
        best_score = -1
        
        for account_key, stats in self.account_stats.items():
            if not stats['is_connected']:
                continue
            
            account_config = DEPOSIT_ACCOUNTS[account_key]
            if not account_config['is_active']:
                continue
            
            # Проверяем дневной лимит
            if stats['daily_purchases'] >= account_config['max_daily_purchases']:
                continue
            
            # Проверяем баланс Stars
            if stats['stars_balance'] < AUTO_PURCHASE_SETTINGS['balance_reserve']:
                continue
            
            # Рассчитываем оценку аккаунта
            score = 100
            score -= stats['daily_purchases'] * 10  # Меньше покупок = лучше
            score += stats['stars_balance'] / 100   # Больше баланс = лучше
            
            # Проверяем время последней покупки (cooldown)
            if stats['last_purchase_time']:
                time_since_last = (datetime.now() - stats['last_purchase_time']).total_seconds()
                if time_since_last < AUTO_PURCHASE_SETTINGS['cooldown_between_purchases']:
                    continue
            
            if score > best_score:
                best_score = score
                best_account = account_key
        
        return best_account
    
    async def purchase_gift(self, gift_info: Dict, user_id: int, recipient_id: int = None) -> Dict[str, Any]:
        """Покупка подарка через депозитный аккаунт"""
        try:
            # Валидация входных данных
            if not isinstance(user_id, int) or user_id <= 0:
                return {"success": False, "error": "Некорректный ID пользователя"}
            
            if recipient_id is not None and (not isinstance(recipient_id, int) or recipient_id <= 0):
                return {"success": False, "error": "Некорректный ID получателя"}
            
            if not isinstance(gift_info, dict):
                return {"success": False, "error": "Некорректная информация о подарке"}
            
            # Проверяем обязательные поля подарка
            required_fields = ['gift_id', 'name', 'price_stars']
            for field in required_fields:
                if field not in gift_info:
                    return {"success": False, "error": f"Отсутствует поле {field} в информации о подарке"}
            
            # Валидация цены подарка
            price_stars = gift_info['price_stars']
            if not isinstance(price_stars, int) or price_stars <= 0 or price_stars > 100000:
                return {"success": False, "error": f"Некорректная цена подарка: {price_stars}"}
            
            # Выбираем лучший аккаунт
            account_key = self._get_best_account_for_purchase()
            if not account_key:
                return {
                    "success": False,
                    "error": "Нет доступных депозитных аккаунтов"
                }
            
            client = self.accounts.get(account_key)
            if not client:
                return {"success": False, "error": f"Аккаунт {account_key} не подключен"}
            
            account_config = DEPOSIT_ACCOUNTS[account_key]
            
            # Проверяем баланс Stars
            current_balance = await self._check_stars_balance(account_key)
            required_stars = gift_info['price_stars']
            
            if current_balance < required_stars:
                return {
                    "success": False,
                    "error": f"Недостаточно Stars на аккаунте {account_key}: {current_balance} < {required_stars}"
                }
            
            # Выполняем покупку подарка
            result = await self._execute_gift_purchase(
                client, gift_info, user_id, recipient_id or user_id
            )
            
            if result['success']:
                # Обновляем статистику аккаунта
                self.account_stats[account_key]['daily_purchases'] += 1
                self.account_stats[account_key]['last_purchase_time'] = datetime.now()
                self.account_stats[account_key]['stars_balance'] -= required_stars
                
                # Записываем покупку в БД
                commission = int(required_stars * STARS_SYSTEM['commission_rate'])
                success = self.db_manager.record_gift_purchase(
                    user_id=user_id,
                    recipient_id=recipient_id or user_id,
                    gift_id=gift_info['gift_id'],
                    gift_name=gift_info['name'],
                    points_spent=result['points_spent'],
                    stars_spent=required_stars,
                    commission_amount=commission,
                    telegram_gift_id=result.get('telegram_gift_id'),
                    purchase_method='auto'
                )
                
                if success:
                    logger.info(f"Подарок {gift_info['name']} куплен аккаунтом {account_key} для пользователя {user_id}")
                else:
                    logger.error(f"Не удалось записать покупку в БД для пользователя {user_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка покупки подарка: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}
    
    async def _execute_gift_purchase(self, client: Client, gift_info: Dict, 
                                   user_id: int, recipient_id: int) -> Dict[str, Any]:
        """Выполнение покупки подарка"""
        try:
            # Здесь должна быть логика покупки подарка через Telegram API
            # Пока возвращаем тестовый результат
            
            # TODO: Реализовать реальную покупку подарков
            
            # Имитируем задержку покупки
            await asyncio.sleep(2)
            
            # Рассчитываем стоимость в баллах с комиссией
            stars_cost = gift_info['price_stars']
            rub_cost = stars_cost * 2  # Примерный курс Stars к рублям
            commission = rub_cost * STARS_SYSTEM['commission_rate']
            points_cost = int(rub_cost + commission)
            
            return {
                "success": True,
                "telegram_gift_id": f"gift_{int(datetime.now().timestamp())}",
                "points_spent": points_cost,
                "stars_spent": stars_cost,
                "commission": int(commission)
            }
            
        except FloodWait as e:
            logger.warning(f"FloodWait при покупке подарка: {e.value} секунд")
            await asyncio.sleep(e.value)
            return {"success": False, "error": f"FloodWait: {e.value} сек"}
            
        except Exception as e:
            logger.error(f"Ошибка выполнения покупки подарка: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_auto_purchases(self, new_gifts: List[Dict]) -> List[Dict]:
        """Обработка автопокупок для новых подарков"""
        results = []
        
        try:
            # Получаем VIP пользователей с включенной автопокупкой
            vip_users = self.db_manager.get_vip_users_with_auto_buy()
            
            for gift in new_gifts:
                for user in vip_users:
                    # Проверяем, подходит ли подарок под настройки пользователя
                    if self._should_auto_buy_gift(gift, user):
                        # Проверяем баланс баллов
                        points_balance = self.db_manager.get_stars_balance(user['user_id'])
                        
                        # Рассчитываем стоимость
                        stars_cost = gift['price_stars']
                        rub_cost = stars_cost * 2
                        commission = rub_cost * STARS_SYSTEM['commission_rate']
                        total_points_cost = int(rub_cost + commission)
                        
                        # Применяем VIP скидку
                        if user['subscription_type'] == 'vip':
                            vip_discount = 0.20  # 20% скидка для VIP
                            total_points_cost = int(total_points_cost * (1 - vip_discount))
                        
                        if points_balance >= total_points_cost:
                            # Резервируем баллы
                            reservation_id = self.db_manager.reserve_points(
                                user['user_id'], 
                                total_points_cost, 
                                f"Автопокупка подарка {gift['name']}"
                            )
                            
                            if reservation_id:
                                # Покупаем подарок
                                purchase_result = await self.purchase_gift(
                                    gift, user['user_id'], user['user_id']
                                )
                                
                                if purchase_result['success']:
                                    # Подтверждаем списание баллов
                                    self.db_manager.confirm_points_reservation(reservation_id)
                                    
                                    results.append({
                                        "user_id": user['user_id'],
                                        "gift_name": gift['name'],
                                        "status": "purchased",
                                        "points_spent": total_points_cost,
                                        "stars_spent": stars_cost
                                    })
                                else:
                                    # Отменяем резервирование
                                    self.db_manager.cancel_points_reservation(reservation_id)
                                    
                                    results.append({
                                        "user_id": user['user_id'],
                                        "gift_name": gift['name'],
                                        "status": "failed",
                                        "reason": purchase_result.get('error', 'Неизвестная ошибка')
                                    })
                            
                            # Пауза между покупками
                            await asyncio.sleep(AUTO_PURCHASE_SETTINGS['cooldown_between_purchases'])
        
        except Exception as e:
            logger.error(f"Ошибка обработки автопокупок: {e}")
        
        return results
    
    def _should_auto_buy_gift(self, gift: Dict, user: Dict) -> bool:
        """Проверка, должен ли подарок быть куплен автоматически"""
        try:
            # Проверяем цену
            if gift['price_stars'] > user['max_price_stars']:
                return False
            
            # Проверяем тираж (если есть информация)
            if gift.get('edition_size') and gift['edition_size'] > user['max_edition_size']:
                return False
            
            # Проверяем категории (если настроены)
            if user['preferred_categories']:
                gift_category = gift.get('category', '').lower()
                if gift_category not in [cat.lower() for cat in user['preferred_categories']]:
                    return False
            
            # Проверяем дневной лимит пользователя
            today = datetime.now().date()
            daily_purchases = self._get_user_daily_purchases(user['user_id'], today)
            if daily_purchases >= user['daily_limit']:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки автопокупки: {e}")
            return False
    
    def _get_user_daily_purchases(self, user_id: int, date) -> int:
        """Получение количества покупок пользователя за день"""
        try:
            # Здесь должен быть запрос к БД для подсчета покупок за день
            # Пока возвращаем 0
            return 0
        except Exception as e:
            logger.error(f"Ошибка получения дневных покупок: {e}")
            return 0
    
    def get_accounts_status(self) -> Dict[str, Any]:
        """Получение статуса всех аккаунтов"""
        status = {}
        
        for account_key, stats in self.account_stats.items():
            account_config = DEPOSIT_ACCOUNTS[account_key]
            
            status[account_key] = {
                "name": account_config['name'],
                "is_active": account_config['is_active'],
                "is_connected": stats['is_connected'],
                "daily_purchases": stats['daily_purchases'],
                "max_daily_purchases": account_config['max_daily_purchases'],
                "stars_balance": stats['stars_balance'],
                "last_error": stats['last_error'],
                "last_balance_check": stats['last_balance_check']
            }
        
        return status
    
    async def disconnect_all(self):
        """Отключение всех аккаунтов"""
        logger.info("Отключение всех депозитных аккаунтов...")
        
        for account_key, client in self.accounts.items():
            try:
                await client.stop()
                logger.info(f"Аккаунт {account_key} отключен")
            except Exception as e:
                logger.error(f"Ошибка отключения аккаунта {account_key}: {e}")
        
        self.accounts.clear()
        
        for account_key in self.account_stats:
            self.account_stats[account_key]['is_connected'] = False 