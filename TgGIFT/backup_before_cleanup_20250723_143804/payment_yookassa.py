#!/usr/bin/env python3
"""
Модуль для работы с ЮКассой - подписки и пополнение баллов
"""

import logging
import uuid
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import aiohttp
from yookassa import Configuration, Payment
from config import YOOKASSA_CONFIG, SUBSCRIPTION_CONFIGS, STARS_SYSTEM, ADMIN_ID

logger = logging.getLogger(__name__)

class YooKassaPaymentHandler:
    """Обработчик платежей ЮКассы"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.account_id = YOOKASSA_CONFIG['shop_id']
        self.secret_key = YOOKASSA_CONFIG['secret_key']
        self.webhook_url = YOOKASSA_CONFIG['webhook_url']
        self.return_url = YOOKASSA_CONFIG['return_url']
        self.test_mode = YOOKASSA_CONFIG['test_mode']
        
        # Настраиваем ЮКассу
        if self.account_id and self.secret_key:
            Configuration.account_id = self.account_id
            Configuration.secret_key = self.secret_key
            logger.info(f"ЮКасса инициализирована (тест: {self.test_mode})")
        else:
            logger.error("ЮКасса не настроена - отсутствуют ключи!")
            
        # Базовый URL API
        self.api_url = "https://api.yookassa.ru/v3"
        
        # Настройка аутентификации
        import base64
        credentials = f"{self.account_id}:{self.secret_key}"
        self.auth_header = base64.b64encode(credentials.encode()).decode()
        
        logger.info(f"ЮКасса инициализирована (тест: {self.test_mode})")
    
    def _get_headers(self, idempotence_key: str = None) -> Dict[str, str]:
        """Получение заголовков для API запросов"""
        headers = {
            'Authorization': f'Basic {self.auth_header}',
            'Content-Type': 'application/json'
        }
        
        if idempotence_key:
            headers['Idempotence-Key'] = idempotence_key
        
        return headers
    
    async def create_subscription_payment(self, user_id: int, subscription_type: str) -> Dict[str, Any]:
        """Создание платежа для покупки подписки"""
        try:
            # Проверяем тип подписки
            if subscription_type not in SUBSCRIPTION_CONFIGS:
                return {"success": False, "error": "Неизвестный тип подписки"}
            
            config = SUBSCRIPTION_CONFIGS[subscription_type]
            amount = config['price_rub']
            
            # Генерируем уникальный ключ идемпотентности
            idempotence_key = str(uuid.uuid4())
            
            # Данные для платежа
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": self.return_url
                },
                "capture": True,
                "description": f"Подписка {subscription_type.upper()} на 30 дней",
                "metadata": {
                    "user_id": str(user_id),
                    "payment_type": "subscription",
                    "subscription_type": subscription_type,
                    "duration_days": str(config['duration_days'])
                },
                "receipt": {
                    "customer": {
                        "email": "user@example.com"
                    },
                    "items": [{
                        "description": f"Подписка {subscription_type.upper()} на 30 дней",
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{amount:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_subject": "service",
                        "payment_mode": "full_payment"
                    }]
                }
            }
            
            # Создаем платеж через библиотеку
            payment = Payment.create(payment_data, idempotence_key)
            
            if payment.status == 'pending':
                # Сохраняем платеж в БД
                success = self.db_manager.save_payment_info(
                    user_id=user_id,
                    payment_id=payment.id,
                    payment_type='subscription',
                    amount=float(amount),
                    currency='RUB',
                    metadata={
                        'subscription_type': subscription_type,
                        'duration_days': config['duration_days']
                    }
                )
                
                if success:
                    logger.info(f"Создан платеж подписки {payment.id} для пользователя {user_id}")
                    return {
                        "success": True,
                        "payment_id": payment.id,
                        "payment_url": payment.confirmation.confirmation_url,
                        "amount": amount,
                        "subscription_type": subscription_type
                    }
                else:
                    return {"success": False, "error": "Ошибка сохранения платежа"}
            else:
                return {"success": False, "error": f"Ошибка создания платежа: {payment.status}"}
                
        except Exception as e:
            logger.error(f"Ошибка создания платежа подписки: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}
    
    async def create_points_topup_payment(self, user_id: int, amount_rub: float) -> Dict[str, Any]:
        """Создание платежа для пополнения баллов"""
        try:
            # Проверяем, что пользователь VIP
            subscription = self.db_manager.get_user_subscription(user_id)
            if not subscription or not subscription.get('is_active') or subscription.get('type') != 'vip':
                return {"success": False, "error": "Пополнение баллов доступно только VIP пользователям"}
            
            # Проверяем минимальную сумму
            if amount_rub < STARS_SYSTEM['min_topup_rub']:
                return {
                    "success": False, 
                    "error": f"Минимальная сумма пополнения: {STARS_SYSTEM['min_topup_rub']}₽"
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
            
            # Генерируем уникальный ключ идемпотентности
            idempotence_key = str(uuid.uuid4())
            
            # Данные для платежа
            payment_data = {
                "amount": {
                    "value": f"{amount_rub:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": self.return_url
                },
                "capture": True,
                "description": f"Пополнение баллов: {total_points} баллов",
                "metadata": {
                    "user_id": str(user_id),
                    "payment_type": "points_topup",
                    "base_points": str(base_points),
                    "bonus_points": str(bonus_points),
                    "total_points": str(total_points),
                    "amount_rub": str(amount_rub)
                },
                "receipt": {
                    "customer": {
                        "email": "user@example.com"
                    },
                    "items": [{
                        "description": f"Внутренние баллы: {total_points} шт.",
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{amount_rub:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_subject": "service",
                        "payment_mode": "full_payment"
                    }]
                }
            }
            
            # Создаем платеж через библиотеку
            payment = Payment.create(payment_data, idempotence_key)
            
            if payment.status == 'pending':
                # Сохраняем платеж в БД
                success = self.db_manager.save_payment_info(
                    user_id=user_id,
                    payment_id=payment.id,
                    payment_type='points_topup',
                    amount=amount_rub,
                    currency='RUB',
                    metadata={
                        'base_points': base_points,
                        'bonus_points': bonus_points,
                        'total_points': total_points,
                        'amount_rub': amount_rub
                    }
                )
                
                if success:
                    logger.info(f"Создан платеж пополнения {payment.id} для пользователя {user_id}")
                    return {
                        "success": True,
                        "payment_id": payment.id,
                        "payment_url": payment.confirmation.confirmation_url,
                        "amount_rub": amount_rub,
                        "base_points": base_points,
                        "bonus_points": bonus_points,
                        "total_points": total_points
                    }
                else:
                    return {"success": False, "error": "Ошибка сохранения платежа"}
            else:
                return {"success": False, "error": f"Ошибка создания платежа: {payment.status}"}
                
        except Exception as e:
            logger.error(f"Ошибка создания платежа пополнения: {e}")
            return {"success": False, "error": "Внутренняя ошибка сервера"}
    
    async def handle_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка webhook от ЮКассы"""
        try:
            # Валидация входных данных
            if not isinstance(webhook_data, dict):
                logger.error("Webhook данные не являются словарем")
                return {"success": False, "error": "Некорректные данные"}
            
            event_type = webhook_data.get('event')
            payment_data = webhook_data.get('object', {})
            
            # Проверка типа события
            if not isinstance(event_type, str):
                logger.error("Отсутствует или некорректный тип события")
                return {"success": False, "error": "Некорректный тип события"}
            
            if event_type != 'payment.succeeded':
                logger.info(f"Получен webhook с событием: {event_type}")
                return {"success": True, "message": "Событие обработано"}
            
            # Валидация payment_data
            if not isinstance(payment_data, dict):
                logger.error("Отсутствуют данные о платеже")
                return {"success": False, "error": "Отсутствуют данные о платеже"}
            
            payment_id = payment_data.get('id')
            if not payment_id or not isinstance(payment_id, str):
                logger.error("Webhook без корректного payment_id")
                return {"success": False, "error": "Отсутствует payment_id"}
            
            # Проверка длины payment_id (защита от атак)
            if len(payment_id) > 100:
                logger.error(f"Слишком длинный payment_id: {len(payment_id)}")
                return {"success": False, "error": "Некорректный payment_id"}
            
            # Получаем информацию о платеже из БД
            payment_info = self.db_manager.get_payment_info(payment_id)
            if not payment_info:
                logger.warning(f"Платеж {payment_id} не найден в БД")
                return {"success": False, "error": "Платеж не найден"}
            
            if payment_info['status'] == 'completed':
                logger.info(f"Платеж {payment_id} уже обработан")
                return {"success": True, "message": "Платеж уже обработан"}
            
            # Дополнительная проверка суммы платежа
            webhook_amount = payment_data.get('amount', {}).get('value')
            if webhook_amount:
                try:
                    webhook_amount_float = float(webhook_amount)
                    db_amount_float = float(payment_info['amount'])
                    
                    # Проверяем, что суммы совпадают (с допуском 0.01)
                    if abs(webhook_amount_float - db_amount_float) > 0.01:
                        logger.error(f"Несоответствие сумм: webhook={webhook_amount_float}, db={db_amount_float}")
                        return {"success": False, "error": "Несоответствие суммы платежа"}
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка валидации суммы: {e}")
                    return {"success": False, "error": "Некорректная сумма"}
            
            # Обновляем статус платежа
            self.db_manager.update_payment_status(payment_id, 'completed')
            
            user_id = payment_info['user_id']
            payment_type = payment_info['payment_type']
            
            # Валидация user_id
            if not isinstance(user_id, int) or user_id <= 0:
                logger.error(f"Некорректный user_id в платеже: {user_id}")
                return {"success": False, "error": "Некорректный пользователь"}
            
            if payment_type == 'subscription':
                # Активируем подписку
                metadata = payment_info['metadata']
                subscription_type = metadata.get('subscription_type')
                
                # Валидация типа подписки
                if subscription_type not in ['basic', 'vip']:
                    logger.error(f"Некорректный тип подписки: {subscription_type}")
                    return {"success": False, "error": "Некорректный тип подписки"}
                
                success = self.db_manager.activate_subscription(user_id, subscription_type)
                if success:
                    logger.info(f"Подписка {subscription_type} активирована для пользователя {user_id}")
                    return {
                        "success": True,
                        "message": "Подписка активирована",
                        "user_id": user_id,
                        "subscription_type": subscription_type
                    }
                else:
                    logger.error(f"Ошибка активации подписки для пользователя {user_id}")
                    return {"success": False, "error": "Ошибка активации подписки"}
            
            elif payment_type == 'points_topup':
                # Начисляем баллы
                metadata = payment_info['metadata']
                total_points = metadata.get('total_points', 0)
                
                # Валидация количества баллов
                try:
                    total_points = int(total_points)
                    if total_points <= 0 or total_points > 10000000:  # Максимум 10 млн баллов за раз
                        logger.error(f"Некорректное количество баллов: {total_points}")
                        return {"success": False, "error": "Некорректное количество баллов"}
                except (ValueError, TypeError):
                    logger.error(f"Не удалось конвертировать количество баллов: {total_points}")
                    return {"success": False, "error": "Некорректное количество баллов"}
                
                success = self.db_manager.add_points(
                    user_id=user_id,
                    amount=total_points,
                    source='yookassa',
                    description=f"Пополнение через ЮКассу: {payment_info['amount']}₽",
                    metadata={
                        'payment_id': payment_id,
                        'base_points': metadata.get('base_points'),
                        'bonus_points': metadata.get('bonus_points')
                    }
                )
                
                if success:
                    logger.info(f"Начислено {total_points} баллов пользователю {user_id}")
                    return {
                        "success": True,
                        "message": "Баллы начислены",
                        "user_id": user_id,
                        "points_added": total_points
                    }
                else:
                    logger.error(f"Ошибка начисления баллов пользователю {user_id}")
                    return {"success": False, "error": "Ошибка начисления баллов"}
            
            else:
                logger.warning(f"Неизвестный тип платежа: {payment_type}")
                return {"success": False, "error": "Неизвестный тип платежа"}
        
        except Exception as e:
            logger.error(f"Ошибка обработки webhook: {e}")
            return {"success": False, "error": "Ошибка обработки webhook"}
    
    async def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Проверка статуса платежа"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/payments/{payment_id}",
                    headers=self._get_headers()
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        return {
                            "success": True,
                            "status": result.get('status'),
                            "paid": result.get('paid', False),
                            "amount": result.get('amount', {}),
                            "metadata": result.get('metadata', {})
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка проверки платежа: {response.status} - {error_text}")
                        return {"success": False, "error": f"Ошибка API: {response.status}"}
        
        except Exception as e:
            logger.error(f"Ошибка проверки статуса платежа: {e}")
            return {"success": False, "error": "Ошибка проверки платежа"}
    
    async def refund_payment(self, payment_id: str, amount: float = None, reason: str = None) -> Dict[str, Any]:
        """Возврат платежа"""
        try:
            idempotence_key = str(uuid.uuid4())
            
            refund_data = {
                "payment_id": payment_id
            }
            
            if amount:
                refund_data["amount"] = {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                }
            
            if reason:
                refund_data["description"] = reason
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/refunds",
                    headers=self._get_headers(idempotence_key),
                    json=refund_data
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Возврат создан: {result['id']}")
                        return {
                            "success": True,
                            "refund_id": result['id'],
                            "status": result.get('status'),
                            "amount": result.get('amount', {})
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка создания возврата: {response.status} - {error_text}")
                        return {"success": False, "error": f"Ошибка API: {response.status}"}
        
        except Exception as e:
            logger.error(f"Ошибка возврата платежа: {e}")
            return {"success": False, "error": "Ошибка возврата"} 