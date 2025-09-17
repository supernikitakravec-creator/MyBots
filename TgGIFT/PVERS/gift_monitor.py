#!/usr/bin/env python3
"""
Система мониторинга новых подарков в Telegram
"""

import asyncio
import logging
import re
import requests
import time
from datetime import datetime
from typing import Dict, List, Optional
from config import MONITORING_URLS, MONITORING_INTERVAL, GIFT_CHECK_INTERVAL, NOTIFICATION_SETTINGS, QUEUE_SETTINGS
from database import DatabaseManager

logger = logging.getLogger(__name__)

class GiftMonitor:
    """Мониторинг новых подарков"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.deposit_manager = None  # Менеджер депозитных аккаунтов (будет использоваться для мониторинга)
        self.monitoring_urls = MONITORING_URLS
        self.known_gifts = set()
        self.is_running = False
        self.is_shutting_down = False
        
        # Контроль нагрузки
        self.last_check_time = 0
        self.check_count = 0
        self.max_checks_per_hour = 240  # Максимум 240 проверок в час (каждые 15 сек)
        self.min_check_interval = 15  # Минимум 15 секунд между проверками
        self.current_interval = MONITORING_INTERVAL  # Текущий интервал
        self.flood_wait_count = 0  # Счетчик FloodWait ошибок
        
        # Rate limiting для уведомлений
        self.notification_count = 0
        self.last_notification_reset = time.time()
        
        # Храним последние ошибки мониторинга
        self.last_errors = []
        
        # Загружаем известные подарки из базы данных
        self._load_known_gifts()
    
    def _load_known_gifts(self):
        """Загрузка известных подарков из базы данных"""
        try:
            gifts = self.db_manager.get_available_gifts()
            self.known_gifts = {gift['gift_id'] for gift in gifts}
            logger.info(f"Загружено {len(self.known_gifts)} известных подарков")
        except Exception as e:
            logger.error(f"Ошибка загрузки известных подарков: {e}")
    
    def _add_error(self, error_msg: str):
        """Добавить ошибку в last_errors (максимум 10)"""
        self.last_errors.append(f"{datetime.now().strftime('%H:%M:%S')}: {error_msg}")
        if len(self.last_errors) > 10:
            self.last_errors = self.last_errors[-10:]
    
    def _check_rate_limit(self) -> bool:
        """Проверка rate limit для мониторинга"""
        current_time = time.time()
        
        # Сброс счетчика каждый час
        if current_time - self.last_notification_reset > 3600:
            self.check_count = 0
            self.notification_count = 0
            self.last_notification_reset = current_time
        
        # Проверяем лимит проверок
        if self.check_count >= self.max_checks_per_hour:
            logger.warning("Достигнут лимит проверок в час")
            return False
        
        # Проверяем минимальный интервал
        if current_time - self.last_check_time < self.min_check_interval:
            return False
        
        return True
    
    def _check_notification_limit(self) -> bool:
        """Проверка лимита уведомлений"""
        current_time = time.time()
        
        # Сброс счетчика каждый час
        if current_time - self.last_notification_reset > 3600:
            self.notification_count = 0
            self.last_notification_reset = current_time
        
        return self.notification_count < NOTIFICATION_SETTINGS['max_notifications_per_hour']
    
    def _adjust_interval(self, increase: bool = False):
        """Динамическая регулировка интервала проверок"""
        if increase:
            # Увеличиваем интервал при ошибках
            self.current_interval = min(self.current_interval * 2, 300)  # Максимум 5 минут
            self.flood_wait_count += 1
            logger.warning(f"Увеличен интервал до {self.current_interval} сек (FloodWait: {self.flood_wait_count})")
        else:
            # Постепенно уменьшаем интервал обратно
            if self.flood_wait_count > 0 and self.current_interval > MONITORING_INTERVAL:
                self.current_interval = max(self.current_interval * 0.9, MONITORING_INTERVAL)
                if self.current_interval == MONITORING_INTERVAL:
                    self.flood_wait_count = 0
                    logger.info(f"Интервал восстановлен до {self.current_interval} сек")
    
    async def start_monitoring(self):
        """Запуск мониторинга"""
        if self.is_running:
            logger.warning("Мониторинг уже запущен")
            return
        
        self.is_running = True
        logger.info("Запуск мониторинга подарков...")
        
        try:
            # Ждем инициализации депозитных аккаунтов
            if not self.deposit_manager:
                logger.warning("Менеджер депозитных аккаунтов не установлен")
                logger.info("Мониторинг будет работать только через веб-скрапинг")
            else:
                logger.info("Используем депозитные аккаунты для мониторинга подарков")
            
            while self.is_running and not self.is_shutting_down:
                try:
                    # Проверяем rate limit
                    if not self._check_rate_limit():
                        await asyncio.sleep(60)  # Ждем минуту
                        continue
                    
                    self.last_check_time = time.time()
                    self.check_count += 1
                    
                    # Проверяем новые подарки
                    new_gifts = await self._check_new_gifts()
                    
                    # Успешная проверка - постепенно уменьшаем интервал
                    self._adjust_interval(increase=False)
                    
                    if new_gifts:
                        logger.info(f"Найдено {len(new_gifts)} новых подарков")
                        
                        # Добавляем подарки в базу данных
                        for gift in new_gifts:
                            self.db_manager.add_gift(
                                gift['gift_id'],
                                gift['name'],
                                gift['price_stars'],
                                gift['url']
                            )
                        
                        # Уведомляем пользователей о новых подарках (с лимитом)
                        if self._check_notification_limit():
                            await self._notify_users_about_new_gifts(new_gifts)
                            self.notification_count += len(new_gifts)
                        else:
                            warn = "Достигнут лимит уведомлений в час"
                            logger.warning(warn)
                            self._add_error(warn)
                        
                        # Обрабатываем покупки для VIP пользователей через депозитные аккаунты
                        if self.deposit_manager:
                            await self._process_vip_purchases(new_gifts)
                        else:
                            logger.info("Пропускаем VIP покупки - менеджер депозитных аккаунтов не подключен")
                    
                    # Ждем следующей проверки с динамическим интервалом
                    await asyncio.sleep(self.current_interval)
                    
                except asyncio.CancelledError:
                    logger.info("Мониторинг отменен")
                    break
                except Exception as e:
                    err = f"Ошибка в цикле мониторинга: {e}"
                    logger.error(err)
                    self._add_error(err)
                    await asyncio.sleep(60)  # Ждем минуту перед повтором
                    
        except Exception as e:
            err = f"Критическая ошибка мониторинга: {e}"
            logger.error(err)
            self._add_error(err)
        finally:
            self.is_running = False
            logger.info("Мониторинг остановлен")
    
    async def stop_monitoring(self):
        """Остановка мониторинга"""
        self.is_shutting_down = True
        self.is_running = False
        logger.info("Запрошена остановка мониторинга")
    
    async def _check_new_gifts(self) -> List[Dict]:
        """Проверка новых подарков через депозитные аккаунты"""
        new_gifts = []
        
        try:
            # Получаем список подарков через депозитные аккаунты
            new_gifts = await self._get_telegram_gifts()
            
            # Фильтруем только новые подарки
            filtered_gifts = []
            for gift in new_gifts:
                if gift['gift_id'] not in self.known_gifts:
                    filtered_gifts.append(gift)
                    self.known_gifts.add(gift['gift_id'])
            
            return filtered_gifts
            
        except Exception as e:
            logger.error(f"Ошибка проверки новых подарков: {e}")
            return []
    
    async def _get_telegram_gifts(self) -> List[Dict]:
        """Получение списка подарков через Telegram API"""
        try:
            gifts = []
            
            # Используем депозитные аккаунты для поиска подарков
            if not self.deposit_manager:
                logger.warning("Менеджер депозитных аккаунтов не доступен для поиска подарков")
                return []
            
            # Получаем активные депозитные аккаунты
            deposit_accounts = self.deposit_manager.accounts
            if not deposit_accounts:
                logger.warning("Нет активных депозитных аккаунтов для мониторинга")
                return []
            
            # Используем первый доступный аккаунт для мониторинга
            client = None
            for account_key, account_client in deposit_accounts.items():
                if account_client and self.deposit_manager.account_stats[account_key]['is_connected']:
                    client = account_client
                    logger.debug(f"Используем депозитный аккаунт {account_key} для мониторинга")
                    break
            
            if not client:
                logger.warning("Нет подключенных депозитных аккаунтов для мониторинга")
                return []
            
            # Метод 1: Проверяем каналы с подарками из конфигурации
            from config import GIFT_CHANNELS
            
            for channel in GIFT_CHANNELS:
                try:
                    # Получаем последние сообщения из канала
                    async for message in client.get_chat_history(channel, limit=20):
                        # Проверяем, содержит ли сообщение информацию о подарке
                        gift_info = self._extract_gift_from_message(message)
                        if gift_info:
                            gifts.append(gift_info)
                            
                except Exception as e:
                    logger.debug(f"Не удалось получить сообщения из {channel}: {e}")
                    continue
            
            # Метод 2: Проверяем бота Fragment
            try:
                fragment_bot = '@fragment_bot'
                
                # Отправляем команду для получения списка подарков
                await client.send_message(fragment_bot, "/gifts")
                
                # Ждем ответ
                await asyncio.sleep(2)
                
                # Получаем ответ бота
                async for message in client.get_chat_history(fragment_bot, limit=5):
                    if message.reply_markup and message.reply_markup.inline_keyboard:
                        # Парсим кнопки с подарками
                        for row in message.reply_markup.inline_keyboard:
                            for button in row:
                                if button.url and 'gift' in button.url:
                                    gift_info = self._parse_gift_button(button, message.text)
                                    if gift_info:
                                        gifts.append(gift_info)
                    
                    # Проверяем текст сообщения на наличие подарков
                    gift_info = self._extract_gift_from_message(message)
                    if gift_info:
                        gifts.append(gift_info)
                        
            except Exception as e:
                logger.debug(f"Не удалось получить подарки от Fragment бота: {e}")
            
            # Метод 3: Проверка официальных подарков Telegram Stars
            try:
                # Получаем информацию о доступных подарках через MTProto API
                from pyrogram.raw import functions, types
                
                # Проверяем доступные стикеры/подарки
                try:
                    # Получаем featured стикеры (часто содержат подарки)
                    featured = await client.invoke(
                        functions.messages.GetFeaturedStickers(hash=0)
                    )
                    
                    if hasattr(featured, 'sets'):
                        for sticker_set in featured.sets:
                            if hasattr(sticker_set, 'title') and ('gift' in sticker_set.title.lower() or 'подарок' in sticker_set.title.lower()):
                                # Это может быть подарок
                                gift_id = f"sticker_gift_{sticker_set.id}"
                                gift_name = sticker_set.title
                                
                                # Стандартная цена для стикер-подарков
                                price_stars = 50
                                
                                gifts.append({
                                    'gift_id': gift_id,
                                    'name': gift_name,
                                    'price_stars': price_stars,
                                    'url': f"https://t.me/addstickers/{sticker_set.short_name}",
                                    'source': 'telegram_featured'
                                })
                                
                except Exception as e:
                    logger.debug(f"Не удалось получить featured стикеры: {e}")
                
                # Проверяем Premium подарки
                try:
                    # Это пример - реальный API может отличаться
                    premium_gifts = await client.invoke(
                        functions.payments.GetPremiumGiftCodeOptions(
                            boost_peer=await client.resolve_peer("me")
                        )
                    )
                    
                    if hasattr(premium_gifts, 'options'):
                        for option in premium_gifts.options:
                            gift_id = f"premium_gift_{option.months}m"
                            gift_name = f"Telegram Premium {option.months} месяцев"
                            price_stars = option.amount // 100  # Конвертируем из копеек в звезды
                            
                            gifts.append({
                                'gift_id': gift_id,
                                'name': gift_name,
                                'price_stars': price_stars,
                                'url': f"https://t.me/premium_bot?start=gift_{gift_id}",
                                'source': 'telegram_premium'
                            })
                            
                except Exception as e:
                    logger.debug(f"Не удалось получить Premium подарки: {e}")
                    
            except Exception as e:
                logger.debug(f"Не удалось получить официальные подарки: {e}")
            
            # Метод 4: Глобальный поиск подарков в Telegram
            try:
                # Поисковые запросы для подарков
                search_queries = [
                    "telegram gift stars",
                    "подарок звезды телеграм",
                    "new telegram gifts",
                    "fragment gift"
                ]
                
                for query in search_queries:
                    try:
                        # Используем глобальный поиск
                        from pyrogram.raw import functions
                        
                        search_result = await client.invoke(
                            functions.messages.SearchGlobal(
                                q=query,
                                offset_date=0,
                                offset_peer=await client.resolve_peer("me"),
                                offset_id=0,
                                limit=10
                            )
                        )
                        
                        if hasattr(search_result, 'messages'):
                            for msg in search_result.messages:
                                # Конвертируем raw сообщение в обычное
                                try:
                                    message = await client.get_messages(
                                        msg.peer_id.channel_id if hasattr(msg.peer_id, 'channel_id') else msg.peer_id.user_id,
                                        msg.id
                                    )
                                    gift_info = self._extract_gift_from_message(message)
                                    if gift_info:
                                        gifts.append(gift_info)
                                except Exception:
                                    pass  # Игнорируем ошибки конвертации отдельных сообщений
                                    
                    except Exception as e:
                        logger.debug(f"Ошибка глобального поиска '{query}': {e}")
                        
            except Exception as e:
                logger.debug(f"Не удалось выполнить глобальный поиск: {e}")
            
            # Удаляем дубликаты
            unique_gifts = []
            seen_ids = set()
            for gift in gifts:
                if gift['gift_id'] not in seen_ids:
                    seen_ids.add(gift['gift_id'])
                    unique_gifts.append(gift)
            
            logger.info(f"Найдено {len(unique_gifts)} уникальных подарков через депозитные аккаунты")
            return unique_gifts
            
        except Exception as e:
            logger.error(f"Ошибка получения подарков через депозитные аккаунты: {e}")
            return []
    
    def _extract_gift_from_message(self, message) -> Optional[Dict]:
        """Извлечение информации о подарке из сообщения"""
        try:
            if not message or not message.text:
                return None
            
            text = message.text
            
            # Паттерны для поиска подарков
            
            # Ищем упоминания подарков
            gift_patterns = [
                r'🎁\s*([^\n]+?)\s*[-–]\s*(\d+)\s*⭐',  # 🎁 Название - 100 ⭐
                r'Gift:\s*([^\n]+?)\s*\((\d+)\s*stars?\)',  # Gift: Название (100 stars)
                r'([^\n]+?)\s*:\s*(\d+)\s*звезд',  # Название: 100 звезд
            ]
            
            for pattern in gift_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    gift_name = match.group(1).strip()
                    price_stars = int(match.group(2))
                    
                    # Генерируем ID из названия
                    gift_id = re.sub(r'[^\w\s-]', '', gift_name.lower()).replace(' ', '_')
                    
                    # Проверяем наличие ссылки
                    gift_url = None
                    if message.entities:
                        for entity in message.entities:
                            if entity.type == "text_link" and entity.url:
                                if 'gift' in entity.url or 'fragment' in entity.url:
                                    gift_url = entity.url
                                    break
                    
                    # Если нет ссылки, генерируем стандартную
                    if not gift_url:
                        gift_url = f"https://t.me/fragment_bot?start=gift_{gift_id}"
                    
                    return {
                        'gift_id': gift_id,
                        'name': gift_name,
                        'price_stars': price_stars,
                        'url': gift_url,
                        'source': 'telegram',
                        'message_id': message.id if hasattr(message, 'id') else None
                    }
            
            return None
            
        except Exception as e:
            logger.debug(f"Ошибка извлечения подарка из сообщения: {e}")
            return None
    
    def _parse_gift_button(self, button, message_text: str) -> Optional[Dict]:
        """Парсинг информации о подарке из inline кнопки"""
        try:
            if not button.text or not button.url:
                return None
            
            # Извлекаем название из текста кнопки
            gift_name = button.text.strip()
            
            # Извлекаем ID из URL
            gift_id_match = re.search(r'gift[/_-]?(\w+)', button.url, re.IGNORECASE)
            if gift_id_match:
                gift_id = gift_id_match.group(1)
            else:
                gift_id = re.sub(r'[^\w\s-]', '', gift_name.lower()).replace(' ', '_')
            
            # Ищем цену в тексте сообщения или кнопки
            price_stars = 100  # Цена по умолчанию
            
            # Проверяем текст кнопки на наличие цены
            price_match = re.search(r'(\d+)\s*⭐', button.text)
            if price_match:
                price_stars = int(price_match.group(1))
            else:
                # Ищем цену в тексте сообщения
                if message_text:
                    price_match = re.search(rf'{re.escape(gift_name)}.*?(\d+)\s*⭐', message_text)
                    if price_match:
                        price_stars = int(price_match.group(1))
            
            return {
                'gift_id': gift_id,
                'name': gift_name,
                'price_stars': price_stars,
                'url': button.url,
                'source': 'telegram_button'
            }
            
        except Exception as e:
            logger.debug(f"Ошибка парсинга кнопки подарка: {e}")
            return None
    
    async def _scrape_gifts_from_url(self, url: str) -> List[Dict]:
        """Скрапинг подарков с Fragment.com"""
        try:
            from bs4 import BeautifulSoup
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Добавляем таймаут и retry логику
            for attempt in range(3):
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    break
                except requests.RequestException as e:
                    if attempt == 2:  # Последняя попытка
                        logger.error(f"Не удалось получить данные с {url} после 3 попыток: {e}")
                        # Увеличиваем интервал при сетевых ошибках
                        if "429" in str(e) or "Too Many Requests" in str(e):
                            self._adjust_interval(increase=True)
                        return []
                    await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
            
            # Парсим HTML с помощью BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            gifts = []
            
            # Ищем подарки на странице
            # Fragment обычно использует таблицы или карточки для отображения NFT/подарков
            gift_elements = soup.find_all(['div', 'tr', 'article'], class_=lambda x: x and any(keyword in x.lower() for keyword in ['gift', 'nft', 'item', 'card']))
            
            if not gift_elements:
                # Альтернативный поиск по ссылкам
                gift_links = soup.find_all('a', href=lambda x: x and ('gift' in x or 'nft' in x))
                
                for link in gift_links:
                    try:
                        gift_url = link.get('href', '')
                        if not gift_url.startswith('http'):
                            gift_url = f"https://fragment.com{gift_url}"
                        
                        # Извлекаем ID из URL
                        gift_id_match = re.search(r'gift[/_-]?(\w+)', gift_url, re.IGNORECASE)
                        if gift_id_match:
                            gift_id = gift_id_match.group(1)
                        else:
                            gift_id = gift_url.split('/')[-1]
                        
                        # Ищем название
                        gift_name = link.get_text(strip=True) or f"Gift {gift_id}"
                        
                        # Ищем цену (обычно рядом с названием)
                        price_element = link.find_next(['span', 'div'], text=re.compile(r'\d+'))
                        if price_element:
                            price_match = re.search(r'(\d+)', price_element.text)
                            price_stars = int(price_match.group(1)) if price_match else 100
                        else:
                            price_stars = 100  # Цена по умолчанию
                        
                        # Преобразуем в ссылку для бота
                        telegram_gift_url = f"https://t.me/fragment_bot?start=gift_{gift_id}"
                        
                        gifts.append({
                            'gift_id': gift_id,
                            'name': gift_name,
                            'price_stars': price_stars,
                            'url': telegram_gift_url,
                            'fragment_url': gift_url
                        })
                    except Exception as e:
                        logger.debug(f"Ошибка парсинга подарка: {e}")
                        continue
            else:
                # Парсим найденные элементы
                for element in gift_elements:
                    try:
                        # Извлекаем данные из элемента
                        name_elem = element.find(['h3', 'h4', 'span'], class_=lambda x: x and 'name' in x.lower())
                        price_elem = element.find(['span', 'div'], class_=lambda x: x and 'price' in x.lower())
                        link_elem = element.find('a', href=True)
                        
                        if not link_elem:
                            continue
                        
                        gift_url = link_elem.get('href', '')
                        if not gift_url.startswith('http'):
                            gift_url = f"https://fragment.com{gift_url}"
                        
                        gift_id = gift_url.split('/')[-1]
                        gift_name = name_elem.get_text(strip=True) if name_elem else f"Gift {gift_id}"
                        
                        if price_elem:
                            price_match = re.search(r'(\d+)', price_elem.text)
                            price_stars = int(price_match.group(1)) if price_match else 100
                        else:
                            price_stars = 100
                        
                        telegram_gift_url = f"https://t.me/fragment_bot?start=gift_{gift_id}"
                        
                        gifts.append({
                            'gift_id': gift_id,
                            'name': gift_name,
                            'price_stars': price_stars,
                            'url': telegram_gift_url,
                            'fragment_url': gift_url
                        })
                    except Exception as e:
                        logger.debug(f"Ошибка парсинга элемента: {e}")
                        continue
            
            # Восстанавливаем интервал при успешном парсинге
            if gifts:
                self._adjust_interval(increase=False)
            
            logger.info(f"Найдено {len(gifts)} подарков на {url}")
            return gifts
            
        except Exception as e:
            logger.error(f"Ошибка скрапинга подарков с {url}: {e}")
            return []
    
    async def _notify_users_about_new_gifts(self, new_gifts: List[Dict]):
        """Уведомление пользователей о новых подарках"""
        try:
            # Проверяем лимит уведомлений
            if not self._check_notification_limit():
                logger.warning("Достигнут лимит уведомлений в час")
                return
            
            # Получаем всех пользователей с активными подписками
            # Это будет реализовано в основном боте
            
            for gift in new_gifts:
                logger.info(f"Новый подарок: {gift['name']} - {gift['price_stars']}⭐")
                
                # Здесь должна быть отправка уведомлений пользователям
                # await self._send_gift_notification(user_id, gift)
                
        except Exception as e:
            logger.error(f"Ошибка уведомления о новых подарках: {e}")
    
    async def _process_vip_purchases(self, new_gifts: List[Dict]):
        """Обработка покупок для VIP пользователей"""
        try:
            # Используем новый менеджер депозитных аккаунтов
            if not self.deposit_manager:
                logger.warning("Менеджер депозитных аккаунтов не инициализирован")
                return
            
            # Проверяем размер очереди
            queue = self.db_manager.get_purchase_queue()
            if len(queue) > QUEUE_SETTINGS['max_queue_size']:
                logger.warning(f"Очередь превышает лимит: {len(queue)} > {QUEUE_SETTINGS['max_queue_size']}")
                return
            
            # Обрабатываем автопокупки через новую систему
            purchase_results = await self.deposit_manager.process_auto_purchases(new_gifts)
            
            for result in purchase_results:
                if result['status'] == 'purchased':
                    logger.info(f"Подарок {result['gift_name']} автоматически куплен для пользователя {result['user_id']}")
                    
                    # Отправляем уведомление пользователю о покупке
                    await self._notify_user_purchase(
                        result['user_id'],
                        result['gift_name'],
                        result['points_spent'],
                        result['stars_spent']
                    )
                else:
                    logger.warning(f"Не удалось купить подарок {result['gift_name']} для пользователя {result['user_id']}: {result.get('reason', 'Неизвестная ошибка')}")
                    
        except Exception as e:
            logger.error(f"Ошибка обработки VIP покупок: {e}")
    
    async def _send_gift_notification(self, user_id: int, gift: Dict):
        """Отправка уведомления о подарке пользователю"""
        try:
            # Здесь должна быть отправка уведомления через бота
            # Это будет реализовано в основном боте
            
            notification_text = f"""
🎁 **Новый подарок!**

📦 {gift['name']}
⭐ Цена: {gift['price_stars']} звезд
🔗 Ссылка: {gift['url']}

💡 VIP пользователи получат автоматическую покупку!
            """
            
            logger.info(f"Уведомление отправлено пользователю {user_id} о подарке {gift['name']}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    async def _notify_user_purchase(self, user_id: int, gift_name: str, points_spent: int, stars_spent: int):
        """Уведомление пользователя о покупке подарка"""
        try:
            notification_text = f"""
✅ **Подарок куплен автоматически!**

🎁 {gift_name}
💎 Потрачено баллов: {points_spent:,}
⭐ Стоимость: {stars_spent} Stars

Подарок уже отправлен на ваш аккаунт!
            """
            
            logger.info(f"Уведомление о покупке отправлено пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка уведомления о покупке для пользователя {user_id}: {e}")
    
    def set_deposit_manager(self, deposit_manager):
        """Установка менеджера депозитных аккаунтов"""
        self.deposit_manager = deposit_manager
        logger.info("Менеджер депозитных аккаунтов подключен к мониторингу")
    
    async def get_recent_gifts(self, limit: int = 10) -> List[Dict]:
        """Получение недавних подарков"""
        try:
            gifts = self.db_manager.get_available_gifts()
            return gifts[:limit]
        except Exception as e:
            logger.error(f"Ошибка получения недавних подарков: {e}")
            return []
    
    async def search_gifts(self, query: str) -> List[Dict]:
        """Поиск подарков по запросу"""
        try:
            gifts = self.db_manager.get_available_gifts()
            
            # Простой поиск по названию
            filtered_gifts = []
            query_lower = query.lower()
            
            for gift in gifts:
                if query_lower in gift['name'].lower():
                    filtered_gifts.append(gift)
            
            return filtered_gifts
            
        except Exception as e:
            logger.error(f"Ошибка поиска подарков: {e}")
            return []
    
    async def get_gift_info(self, gift_id: str) -> Optional[Dict]:
        """Получение информации о подарке"""
        try:
            gifts = self.db_manager.get_available_gifts()
            
            for gift in gifts:
                if gift['gift_id'] == gift_id:
                    return gift
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о подарке {gift_id}: {e}")
            return None
    
    async def check_gift_availability(self, gift_url: str) -> Dict:
        """Проверка доступности подарка через депозитные аккаунты"""
        try:
            if self.deposit_manager:
                # Используем первый доступный депозитный аккаунт для проверки
                for account_key, client in self.deposit_manager.accounts.items():
                    if client and self.deposit_manager.account_stats[account_key]['is_connected']:
                        # Здесь должна быть логика проверки доступности через депозитный аккаунт
                        # Пока возвращаем заглушку
                        return {
                            'available': True,
                            'message': f'Проверено через депозитный аккаунт {account_key}'
                        }
                
                return {
                    'available': False,
                    'error': 'Нет подключенных депозитных аккаунтов'
                }
            else:
                return {
                    'available': False,
                    'error': 'Менеджер депозитных аккаунтов не инициализирован'
                }
                
        except Exception as e:
            logger.error(f"Ошибка проверки доступности подарка: {e}")
            return {
                'available': False,
                'error': 'Ошибка проверки доступности'
            } 