#!/usr/bin/env python3
"""
Модуль для работы с TON платежами
"""

import logging
import asyncio
import json
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
import aiohttp
from config import TON_WALLETS, SUBSCRIPTION_CONFIGS, STARS_SYSTEM

logger = logging.getLogger(__name__)

class TONPaymentHandler:
    """Обработчик TON платежей"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.wallets = TON_WALLETS
        
        # API для работы с TON
        self.ton_api_base = "https://toncenter.com/api/v2"
        self.ton_api_key = None  # Можно добавить API ключ для увеличения лимитов
        
        # Курс TON к рублю (обновляется автоматически)
        self.ton_rub_rate = 350.0  # Примерный курс, будет обновляться
        
        logger.info("TON Payment Handler инициализирован")
    
    async def get_ton_price(self) -> float:
        """Получение актуального курса TON"""
        try:
            async with aiohttp.ClientSession() as session:
                # Используем CoinGecko API для получения курса TON
                async with session.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=rub"
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        rate = data.get('the-open-network', {}).get('rub', self.ton_rub_rate)
                        self.ton_rub_rate = rate
                        logger.info(f"Обновлен курс TON: {rate:.2f} ₽")
                        return rate
                    else:
                        logger.warning(f"Не удалось получить курс TON: {response.status}")
                        return self.ton_rub_rate
        except Exception as e:
            logger.error(f"Ошибка получения курса TON: {e}")
            return self.ton_rub_rate
    
    def _get_active_wallet(self, wallet_key: str = None) -> Dict[str, Any]:
        """Получение активного кошелька"""
        if wallet_key and wallet_key in self.wallets:
            wallet = self.wallets[wallet_key]
            if wallet['is_active']:
                return wallet
        
        # Ищем первый активный кошелек
        for key, wallet in self.wallets.items():
            if wallet['is_active']:
                return wallet
        
        raise ValueError("Нет активных TON кошельков")
    
    def get_available_wallets(self) -> List[Dict[str, Any]]:
        """Получение списка доступных кошельков"""
        available_wallets = []
        for key, wallet in self.wallets.items():
            if wallet['is_active']:
                available_wallets.append({
                    'key': key,
                    'name': wallet['name'],
                    'address': wallet['address']
                })
        return available_wallets
    
    def _generate_payment_comment(self, user_id: int, payment_type: str, payment_id: str) -> str:
        """Генерация комментария для платежа"""
        return f"TgGift_{payment_type}_{user_id}_{payment_id}"
    
    def _create_ton_link(self, wallet_address: str, amount_ton: float, comment: str) -> str:
        """Создание TON ссылки для платежа"""
        # Конвертируем TON в нанотоны (1 TON = 10^9 nanoTON)
        amount_nano = int(amount_ton * 1_000_000_000)
        
        # Создаем TON ссылку
        ton_link = f"ton://transfer/{wallet_address}?amount={amount_nano}&text={comment}"
        
        return ton_link
    
    def _generate_qr_code(self, data: str) -> str:
        """Генерация QR кода в base64"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            # Создаем изображение
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Конвертируем в base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/png;base64,{img_base64}"
        except Exception as e:
            logger.error(f"Ошибка генерации QR кода: {e}")
            return None
    
    async def create_subscription_payment(self, user_id: int, subscription_type: str) -> Dict[str, Any]:
        """Создание TON платежа за подписку"""
        try:
            if subscription_type not in SUBSCRIPTION_CONFIGS:
                return {"success": False, "error": "Неизвестный тип подписки"}
            
            config = SUBSCRIPTION_CONFIGS[subscription_type]
            amount_ton = config['price_ton']
            
            # Получаем активный кошелек
            wallet = self._get_active_wallet()
            
            # Генерируем ID платежа
            payment_id = f"sub_{user_id}_{int(datetime.now().timestamp())}"
            
            # Создаем комментарий
            comment = self._generate_payment_comment(user_id, 'subscription', payment_id)
            
            # Создаем TON ссылку
            ton_link = self._create_ton_link(wallet['address'], amount_ton, comment)
            
            # Генерируем QR код
            qr_code = self._generate_qr_code(ton_link)
            
            # Сохраняем информацию о платеже
            self.db_manager.save_payment_info(
                user_id=user_id,
                payment_id=payment_id,
                payment_type='subscription',
                amount=amount_ton,
                currency='TON',
                status='pending',
                metadata={
                    'subscription_type': subscription_type,
                    'wallet_address': wallet['address'],
                    'comment': comment,
                    'ton_link': ton_link
                }
            )
            
            return {
                "success": True,
                "payment_id": payment_id,
                "amount_ton": amount_ton,
                "wallet_address": wallet['address'],
                "comment": comment,
                "ton_link": ton_link,
                "qr_code": qr_code,
                "wallet_name": wallet['name']
            }
        
        except Exception as e:
            logger.error(f"Ошибка создания TON платежа подписки: {e}")
            return {"success": False, "error": "Ошибка создания платежа"}
    
    async def create_points_topup_payment(self, user_id: int, amount_rub: float) -> Dict[str, Any]:
        """Создание TON платежа для пополнения баллов"""
        try:
            # Проверяем, что пользователь VIP
            subscription = self.db_manager.get_user_subscription(user_id)
            if not subscription or subscription['type'] != 'vip':
                return {"success": False, "error": "Пополнение баллов доступно только VIP пользователям"}
            
            # Проверяем минимальную сумму
            if amount_rub < STARS_SYSTEM['min_topup_rub']:
                return {
                    "success": False, 
                    "error": f"Минимальная сумма пополнения: {STARS_SYSTEM['min_topup_rub']}₽"
                }
            
            # Получаем курс TON
            ton_rate = await self.get_ton_price()
            amount_ton = amount_rub / ton_rate
            
            # Проверяем минимальную сумму в TON
            if amount_ton < STARS_SYSTEM['min_topup_ton']:
                return {
                    "success": False,
                    "error": f"Минимальная сумма в TON: {STARS_SYSTEM['min_topup_ton']:.3f} TON"
                }
            
            # Рассчитываем количество баллов и бонус
            conversion_rate = STARS_SYSTEM['conversion_rates']['RUB']
            base_points = int(amount_rub * conversion_rate)
            
            # Вычисляем бонус
            bonus_percent = 0
            for threshold, bonus in sorted(STARS_SYSTEM['topup_bonuses'].items()):
                if base_points >= threshold:
                    bonus_percent = bonus
            
            bonus_points = int(base_points * bonus_percent)
            total_points = base_points + bonus_points
            
            # Получаем активный кошелек
            wallet = self._get_active_wallet()
            
            # Генерируем ID платежа
            payment_id = f"points_{user_id}_{int(datetime.now().timestamp())}"
            
            # Создаем комментарий
            comment = self._generate_payment_comment(user_id, 'points', payment_id)
            
            # Создаем TON ссылку
            ton_link = self._create_ton_link(wallet['address'], amount_ton, comment)
            
            # Генерируем QR код
            qr_code = self._generate_qr_code(ton_link)
            
            # Сохраняем информацию о платеже
            self.db_manager.save_payment_info(
                user_id=user_id,
                payment_id=payment_id,
                payment_type='points_topup',
                amount=amount_ton,
                currency='TON',
                status='pending',
                metadata={
                    'amount_rub': amount_rub,
                    'ton_rate': ton_rate,
                    'base_points': base_points,
                    'bonus_points': bonus_points,
                    'total_points': total_points,
                    'bonus_percent': bonus_percent,
                    'wallet_address': wallet['address'],
                    'comment': comment,
                    'ton_link': ton_link
                }
            )
            
            return {
                "success": True,
                "payment_id": payment_id,
                "amount_ton": round(amount_ton, 6),
                "amount_rub": amount_rub,
                "ton_rate": ton_rate,
                "wallet_address": wallet['address'],
                "comment": comment,
                "ton_link": ton_link,
                "qr_code": qr_code,
                "base_points": base_points,
                "bonus_points": bonus_points,
                "total_points": total_points,
                "bonus_percent": int(bonus_percent * 100),
                "wallet_name": wallet['name']
            }
        
        except Exception as e:
            logger.error(f"Ошибка создания TON платежа пополнения: {e}")
            return {"success": False, "error": "Ошибка создания платежа"}
    
    async def create_stars_topup_payment(self, user_id: int, stars_amount: int, username: str = None, wallet_key: str = None) -> Dict[str, Any]:
        """Создание TON платежа для пополнения Stars"""
        try:
            # Проверяем, что пользователь VIP
            subscription = self.db_manager.get_user_subscription(user_id)
            if not subscription or subscription['type'] != 'vip':
                return {"success": False, "error": "Пополнение Stars доступно только VIP пользователям"}
            
            # Проверяем минимальное количество Stars
            min_stars = STARS_SYSTEM.get('min_stars_topup', 100)
            if stars_amount < min_stars:
                return {
                    "success": False, 
                    "error": f"Минимальное количество Stars: {min_stars}"
                }
            
            # Рассчитываем стоимость в рублях (1 Star ≈ 2 рубля)
            stars_rub_rate = STARS_SYSTEM.get('stars_rub_rate', 2.0)
            amount_rub = stars_amount * stars_rub_rate
            
            # Получаем курс TON
            ton_rate = await self.get_ton_price()
            amount_ton = amount_rub / ton_rate
            
            # Проверяем минимальную сумму в TON
            min_ton = STARS_SYSTEM.get('min_topup_ton', 0.1)
            if amount_ton < min_ton:
                return {
                    "success": False,
                    "error": f"Минимальная сумма в TON: {min_ton:.3f} TON"
                }
            
            # Получаем активный кошелек
            wallet = self._get_active_wallet(wallet_key)
            
            # Генерируем ID платежа
            payment_id = f"stars_{user_id}_{int(datetime.now().timestamp())}"
            
            # Создаем комментарий
            comment = self._generate_payment_comment(user_id, 'stars', payment_id)
            
            # Создаем TON ссылку
            ton_link = self._create_ton_link(wallet['address'], amount_ton, comment)
            
            # Генерируем QR код
            qr_code = self._generate_qr_code(ton_link)
            
            # Сохраняем информацию о платеже
            self.db_manager.save_payment_info(
                user_id=user_id,
                payment_id=payment_id,
                payment_type='stars_topup',
                amount=amount_ton,
                currency='TON',
                status='pending',
                metadata={
                    'stars_amount': stars_amount,
                    'amount_rub': amount_rub,
                    'ton_rate': ton_rate,
                    'stars_rub_rate': stars_rub_rate,
                    'wallet_address': wallet['address'],
                    'comment': comment,
                    'ton_link': ton_link,
                    'username': username
                }
            )
            
            return {
                "success": True,
                "payment_id": payment_id,
                "amount_ton": round(amount_ton, 6),
                "amount_rub": amount_rub,
                "ton_rate": ton_rate,
                "wallet_address": wallet['address'],
                "comment": comment,
                "ton_link": ton_link,
                "qr_code": qr_code,
                "stars_amount": stars_amount,
                "stars_rub_rate": stars_rub_rate,
                "wallet_name": wallet['name'],
                "username": username
            }
        
        except Exception as e:
            logger.error(f"Ошибка создания TON платежа Stars: {e}")
            return {"success": False, "error": "Ошибка создания платежа"}

    async def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Проверка статуса TON платежа"""
        try:
            # Получаем информацию о платеже из БД
            payment_info = self.db_manager.get_payment_info(payment_id)
            if not payment_info:
                return {"success": False, "error": "Платеж не найден"}
            
            if payment_info['status'] == 'completed':
                return {"success": True, "status": "completed", "message": "Платеж уже обработан"}
            
            metadata = payment_info['metadata']
            wallet_address = metadata['wallet_address']
            comment = metadata['comment']
            expected_amount = payment_info['amount']
            
            # Проверяем транзакции на кошельке
            transactions = await self._get_wallet_transactions(wallet_address)
            
            for tx in transactions:
                # Проверяем комментарий и сумму
                if (tx.get('comment') == comment and 
                    abs(tx.get('amount', 0) - expected_amount) < 0.001):  # Допуск 0.001 TON
                    
                    # Платеж найден, обрабатываем
                    await self._process_ton_payment(payment_info, tx)
                    
                    return {
                        "success": True,
                        "status": "completed",
                        "transaction_hash": tx.get('hash'),
                        "amount": tx.get('amount')
                    }
            
            return {"success": True, "status": "pending", "message": "Платеж не найден"}
        
        except Exception as e:
            logger.error(f"Ошибка проверки TON платежа: {e}")
            return {"success": False, "error": "Ошибка проверки платежа"}
    
    async def _get_wallet_transactions(self, wallet_address: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение транзакций кошелька"""
        try:
            params = {
                'address': wallet_address,
                'limit': limit,
                'to_lt': 0,
                'archival': 'false'
            }
            
            if self.ton_api_key:
                params['api_key'] = self.ton_api_key
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ton_api_base}/getTransactions",
                    params=params
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok'):
                            transactions = []
                            for tx in data.get('result', []):
                                # Извлекаем нужную информацию
                                in_msg = tx.get('in_msg', {})
                                if in_msg:
                                    amount_nano = int(in_msg.get('value', 0))
                                    amount_ton = amount_nano / 1_000_000_000
                                    
                                    comment = ""
                                    if in_msg.get('message'):
                                        try:
                                            # Декодируем комментарий из base64
                                            comment_b64 = in_msg['message']
                                            comment = base64.b64decode(comment_b64).decode('utf-8', errors='ignore')
                                        except:
                                            pass
                                    
                                    transactions.append({
                                        'hash': tx.get('transaction_id', {}).get('hash'),
                                        'amount': amount_ton,
                                        'comment': comment,
                                        'timestamp': tx.get('utime', 0),
                                        'source': in_msg.get('source', '')
                                    })
                            
                            return transactions
                        else:
                            logger.error(f"TON API ошибка: {data}")
                            return []
                    else:
                        logger.error(f"Ошибка запроса к TON API: {response.status}")
                        return []
        
        except Exception as e:
            logger.error(f"Ошибка получения транзакций TON: {e}")
            return []
    
    async def _process_ton_payment(self, payment_info: Dict, transaction: Dict):
        """Обработка подтвержденного TON платежа"""
        try:
            payment_id = payment_info['payment_id']
            user_id = payment_info['user_id']
            payment_type = payment_info['payment_type']
            
            # Обновляем статус платежа
            self.db_manager.update_payment_status(payment_id, 'completed')
            
            if payment_type == 'subscription':
                # Активируем подписку
                metadata = payment_info['metadata']
                subscription_type = metadata.get('subscription_type')
                
                success = self.db_manager.activate_subscription(user_id, subscription_type)
                if success:
                    logger.info(f"TON: Подписка {subscription_type} активирована для пользователя {user_id}")
                else:
                    logger.error(f"TON: Ошибка активации подписки для пользователя {user_id}")
            
            elif payment_type == 'points_topup':
                # Начисляем баллы
                metadata = payment_info['metadata']
                total_points = int(metadata.get('total_points', 0))
                
                success = self.db_manager.add_points(
                    user_id=user_id,
                    amount=total_points,
                    source='ton',
                    description=f"Пополнение через TON: {payment_info['amount']:.6f} TON",
                    metadata={
                        'payment_id': payment_id,
                        'transaction_hash': transaction.get('hash'),
                        'base_points': metadata.get('base_points'),
                        'bonus_points': metadata.get('bonus_points'),
                        'amount_rub': metadata.get('amount_rub'),
                        'ton_rate': metadata.get('ton_rate')
                    }
                )
                
                if success:
                    logger.info(f"TON: Начислено {total_points} баллов пользователю {user_id}")
                else:
                    logger.error(f"TON: Ошибка начисления баллов пользователю {user_id}")
        
        except Exception as e:
            logger.error(f"Ошибка обработки TON платежа: {e}")
    
    async def start_payment_monitor(self):
        """Запуск мониторинга TON платежей"""
        logger.info("Запуск мониторинга TON платежей...")
        
        while True:
            try:
                # Получаем все pending TON платежи
                pending_payments = await self.db_manager.get_pending_payments('TON')
                
                for payment in pending_payments:
                    # Проверяем каждый платеж
                    result = await self.check_payment_status(payment['payment_id'])
                    
                    if result.get('success') and result.get('status') == 'completed':
                        logger.info(f"TON платеж {payment['payment_id']} обработан")
                
                # Пауза между проверками
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
            
            except Exception as e:
                logger.error(f"Ошибка мониторинга TON платежей: {e}")
                await asyncio.sleep(60)  # При ошибке ждем минуту 