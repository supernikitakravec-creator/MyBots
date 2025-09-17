import telebot
import pandas as pd
import os
import logging
import json # Импортируем модуль json
from telebot import types, util
from config import BOT_TOKEN, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, DEMO_MODE, PAYMENT_DEMO_MODE, SUBSCRIPTION_PRICES
import time
import threading
import signal  # ИСПРАВЛЕНО: Перемещен импорт signal в начало
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
import uuid
import hashlib
import traceback
import base64
import string
import re
import copy
import shutil
import random

# --- Блокировка для thread-safe операций ---
# Используем реентерабельную блокировку, т.к. некоторые функции (например, schedule_save)
# вызываются внутри секций with data_lock: и сами используют блокировку
data_lock = threading.RLock()
processed_payments = set()  # Множество обработанных платежей
data_changed = False  # Флаг изменения данных
save_timer = None  # Таймер для отложенного сохранения
save_counter = 0  # Счетчик успешных сохранений

# --- Rate limiting ---
last_api_calls = {}  # Время последних API вызовов по пользователям
API_COOLDOWN = 2.0  # Минимальная задержка между API вызовами (секунды)
# ИСПРАВЛЕНО: Добавляем очистку старых записей
MAX_API_CACHE_SIZE = 1000  # Максимальный размер кэша

# --- Константы ---
ADMIN_ID = 592900565
ADMIN_ID_2 = 631600319  # Второй администратор
ADMIN_IDS = [ADMIN_ID, ADMIN_ID_2]  # Список всех админов
SUBSCRIPTION_PRICE = 2990.0  # Цена подписки в рублях
SUBSCRIPTION_DURATION_DAYS = 30  # Длительность подписки в днях

# --- Константы для промокодов ---
PROMO_CODE_LENGTH = 12  # Длина промокода
PROMO_CODE_PREFIX = "FIT"  # Префикс промокодов

# --- Кэш для оптимизации ---
workout_files_cache = {}  # Кэш файлов тренировок
last_cache_update = 0     # Время последнего обновления кэша
CACHE_TTL = 300          # Время жизни кэша (5 минут)
MAX_CACHE_SIZE = 500     # ИСПРАВЛЕНО: Ограничение размера кэша

# --- Настройка логирования ---
from logging.handlers import RotatingFileHandler

def _get_log_level_from_env():
    level_name = os.getenv('BOT_LOG_LEVEL', 'INFO').upper()
    return getattr(logging, level_name, logging.INFO)

LOG_LEVEL = _get_log_level_from_env()

logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# Форматтер с миллисекундами и потоком
_formatter = logging.Formatter(
    fmt='%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] [%(threadName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Ротация файла логов: до ~5 МБ, 5 файлов
file_handler = RotatingFileHandler('bot_app.log', maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(_formatter)
file_handler.setLevel(LOG_LEVEL)

console_handler = logging.StreamHandler()
console_handler.setFormatter(_formatter)
console_handler.setLevel(LOG_LEVEL)

# Сбрасываем базовые хендлеры и добавляем наши
for h in list(logger.handlers):
    logger.removeHandler(h)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Уменьшаем болтливость сторонних библиотек
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('telebot').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Утилиты маскировки
def mask_promo_code(code: str) -> str:
    try:
        code = (code or '').strip()
        if len(code) <= 5:
            return '***'
        return f"{code[:3]}***{code[-2:]}"
    except Exception:
        return '***'

# --- ФУНКЦИИ ДЛЯ ПОДПИСКИ И ЮКАССА ---
def create_payment(user_id, amount=SUBSCRIPTION_PRICE, duration_days=SUBSCRIPTION_DURATION_DAYS):
    """Создание платежа в Юкасса"""
    payment_id = str(uuid.uuid4())
    headers = {
        'Authorization': f'Basic {base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()}',
        'Content-Type': 'application/json',
        'Idempotence-Key': payment_id
    }
    
    data = {
        'amount': {
            'value': str(amount),
            'currency': 'RUB'
        },
        'confirmation': {
            'type': 'redirect',
            'return_url': f'https://t.me/DBLIFE_FIT_bot?start=payment_{payment_id}'
        },
        'capture': True,
        'description': f'Подписка на бота ({duration_days} дней)',
        'receipt': {
            'customer': {
                'email': 'client@example.com'
            },
            'items': [
                {
                    'description': f'Подписка на фитнес-бота ({duration_days} дней)',
                    'quantity': '1',
                    'amount': {
                        'value': str(amount),
                        'currency': 'RUB'
                    },
                    'vat_code': 1,  # НДС не облагается
                    'payment_subject': 'service',  # Тип предмета расчета - услуга
                    'payment_mode': 'full_payment'  # Способ расчета - полный расчет
                }
            ]
        },
        'metadata': {
            'user_id': str(user_id),
            'duration_days': str(duration_days)
        }
    }
    
    try:
        # ДИАГНОСТИКА: Логируем запрос (БЕЗ секретного ключа)
        logger.debug(f"YooKassa запрос: POST /v3/payments")
        logger.debug(f"Shop ID: {YOOKASSA_SHOP_ID}")
        logger.debug(f"Request data: {data}")
        
        response = requests.post(
            'https://api.yookassa.ru/v3/payments',
            headers=headers,
            json=data,
            timeout=(5, 15)  # 5 сек на подключение, 15 сек на ответ
        )
        
        # ДИАГНОСТИКА: Логируем ответ
        logger.debug(f"YooKassa ответ: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"YooKassa ошибка {response.status_code}: {response.text}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка HTTP при создании платежа: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Детали ответа YooKassa: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при создании платежа: {e}")
        return None

def check_payment_status(payment_id, user_id=None):
    """Проверка статуса платежа в Юкасса (с защитой от дублирования и rate limiting)"""
    # Rate limiting для API запросов с thread-safety
    if user_id:
        current_time = time.time()
        with data_lock:
            # ИСПРАВЛЕНО: Очистка старых записей для предотвращения утечек памяти
            if len(last_api_calls) > MAX_API_CACHE_SIZE:
                # Удаляем записи старше 1 часа
                cutoff_time = current_time - 3600
                last_api_calls = {k: v for k, v in last_api_calls.items() if v > cutoff_time}
            
            last_call = last_api_calls.get(user_id, 0)
            if current_time - last_call < API_COOLDOWN:
                logger.warning(f"Rate limit для пользователя {user_id}. Слишком частые запросы.")
                return False
            last_api_calls[user_id] = current_time
    
    # Проверяем, не был ли платеж уже обработан с thread-safety
    with data_lock:
        if payment_id in processed_payments:
            logger.warning(f"Платеж {payment_id} уже был обработан ранее")
            return True  # Возвращаем True, т.к. платеж успешен
            
        # ИСПРАВЛЕНО: Очистка старых обработанных платежей (хранить только последние 1000)
        if len(processed_payments) > 1000:
            # Очищаем половину самых старых записей (примерно)
            old_payments = list(processed_payments)[:500]
            processed_payments -= set(old_payments)
            logger.info(f"Очищено {len(old_payments)} старых записей о платежах")
    
    headers = {
        'Authorization': f'Basic {base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(
            f'https://api.yookassa.ru/v3/payments/{payment_id}',
            headers=headers,
            timeout=(5, 10)  # 5 сек на подключение, 10 сек на ответ
        )
        response.raise_for_status()
        payment_data = response.json()
        
        if payment_data['status'] == 'succeeded':
            # Добавляем платеж в список обработанных ДО активации подписки с thread-safety
            with data_lock:
                if payment_id in processed_payments:
                    logger.warning(f"Платеж {payment_id} был обработан во время проверки")
                    return True
                processed_payments.add(payment_id)
            
            try:
                user_id = int(payment_data['metadata']['user_id'])
                duration_days = int(payment_data['metadata'].get('duration_days', SUBSCRIPTION_DURATION_DAYS))
                activate_subscription(user_id, duration_days)
                logger.info(f"Платеж {payment_id} успешно обработан для пользователя {user_id}")
                return True
            except Exception as e:
                # Если произошла ошибка активации, удаляем платеж из обработанных с thread-safety
                with data_lock:
                    processed_payments.discard(payment_id)
                logger.error(f"Ошибка при активации подписки для платежа {payment_id}: {e}")
                return False
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка HTTP при проверке статуса платежа: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при проверке статуса платежа: {e}")
        return False

def activate_subscription(user_id, duration_days=SUBSCRIPTION_DURATION_DAYS):
    """Активация подписки пользователя (thread-safe)"""
    user_id_str = str(user_id)
    
    with data_lock:
        if 'users' not in app_data:
            app_data['users'] = {}
        if user_id_str not in app_data['users']:
            app_data['users'][user_id_str] = {}
        
        app_data['users'][user_id_str]['subscription_end'] = (
            datetime.now() + timedelta(days=duration_days)
        ).isoformat()
        
        # Сбрасываем флаги уведомлений при активации новой подписки
        if 'subscription_expired_notified' in app_data['users'][user_id_str]:
            del app_data['users'][user_id_str]['subscription_expired_notified']
        if 'subscription_warning_sent' in app_data['users'][user_id_str]:
            del app_data['users'][user_id_str]['subscription_warning_sent']
        
        subscription_end = app_data['users'][user_id_str]['subscription_end']
    
    save_user_data(force=True)  # Критично - сохраняем немедленно
    logger.info(f"Активирована подписка для пользователя {user_id_str} до {subscription_end}")

def revoke_subscription(user_id):
    """Деактивация подписки пользователя"""
    user_id_str = str(user_id)
    
    # ИСПРАВЛЕНО: Thread-safe операции с данными пользователя
    with data_lock:
        if user_id_str in app_data['users']:
            # Удаляем подписку
            if 'subscription_end' in app_data['users'][user_id_str]:
                del app_data['users'][user_id_str]['subscription_end']
            # Удаляем флаги уведомлений
            if 'subscription_expired_notified' in app_data['users'][user_id_str]:
                del app_data['users'][user_id_str]['subscription_expired_notified']
            if 'subscription_warning_sent' in app_data['users'][user_id_str]:
                del app_data['users'][user_id_str]['subscription_warning_sent']
            
    save_user_data(force=True)  # Критично - сохраняем немедленно
    logger.info(f"Подписка деактивирована для пользователя {user_id_str}")

def has_active_subscription(user_id_str, send_notifications=False):
    """Проверка наличия активной подписки (thread-safe)"""
    if not user_id_str:
        logger.warning("has_active_subscription вызвана с пустым user_id_str")
        return False
        
    with data_lock:
        user_data = app_data.get('users', {}).get(user_id_str)
        if user_data is None or 'subscription_end' not in user_data:
            return False
        
        try:
            subscription_end = datetime.fromisoformat(user_data['subscription_end'])
        except (ValueError, TypeError) as e:
            logger.error(f"Некорректная дата подписки для пользователя {user_id_str}: {user_data.get('subscription_end', 'None')} - {e}")
            return False
            
        current_time = datetime.now()
        
        # Если подписка истекла
        if current_time >= subscription_end:
            return False
        
        # Уведомления отправляем только при явном запросе и только один раз
        if send_notifications:
            days_left = (subscription_end - current_time).days
            
            # Проверяем на скорое истечение подписки (за 3 дня)
            if days_left <= 3 and days_left > 0:
                if not user_data.get('subscription_warning_sent', False):
                    # ИСПРАВЛЕНО: Создаем копию данных для безопасной передачи
                    user_data['subscription_warning_sent'] = True
                    subscription_end_copy = subscription_end
                    # ИСПРАВЛЕНО: Убираем создание отдельного потока - источник множественных процессов!
                    # Отправляем уведомление синхронно
                    schedule_save()  # Сначала планируем сохранение
                    try:
                        # Прямой вызов без создания потока
                        send_warning_notification(user_id_str, days_left, subscription_end_copy)
                    except Exception as e:
                        logger.error(f"Ошибка при отправке предупреждения пользователю {user_id_str}: {e}")
        
        return True

def send_warning_notification(user_id_str, days_left, subscription_end):
    """Отправка предупреждения об истечении подписки"""
    try:
        # ИСПРАВЛЕНО: Проверка корректности данных перед отправкой
        if not user_id_str or not user_id_str.isdigit():
            logger.error(f"Некорректный user_id_str для предупреждения: {user_id_str}")
            return
            
        if days_left < 0 or days_left > 30:
            logger.warning(f"Некорректное количество дней до истечения: {days_left} для пользователя {user_id_str}")
            return
        
        send_or_edit_message(
            chat_id=int(user_id_str),
            text=f"""⚠️ Ваша подписка истекает через {days_left} дн.!

📅 Подписка действует до: {subscription_end.strftime('%d.%m.%Y')}
💎 Для продления обратитесь к @M4IST или оформите новую подписку.

Не потеряйте доступ к функциям бота!""",
            parse_mode='Markdown',
            edit_mode=False
        )
        logger.info(f"Отправлено предупреждение о скором истечении подписки пользователю {user_id_str}")
        schedule_save()  # Отложенное сохранение для уведомлений
    except ValueError as e:
        logger.error(f"Ошибка в данных при отправке предупреждения пользователю {user_id_str}: {e}")
    except Exception as e:
        logger.warning(f"Не удалось отправить предупреждение пользователю {user_id_str}: {e}")

def send_expiry_notification(user_id_str, subscription_end):
    """Отправка уведомления об истечении подписки"""
    try:
        send_or_edit_message(
            chat_id=int(user_id_str),
            text="""⏰ Ваша подписка истекла!

🔒 Доступ к функциям бота ограничен.
💎 Для продления подписки обратитесь к @M4IST или оформите новую подписку.

Спасибо за использование нашего бота!""",
            parse_mode='Markdown',
            edit_mode=False
        )
        logger.info(f"Отправлено уведомление об истечении подписки пользователю {user_id_str}")
        
        # ИСПРАВЛЕНО: Безопасное уведомление админов с обработкой ошибок
        try:
            admin_text = f"""⏰ Истекла подписка!

👤 Пользователь: {user_id_str}
📅 Истекла: {subscription_end.strftime('%d.%m.%Y %H:%M')}
🔒 Доступ ограничен"""
            
            notify_all_admins(admin_text)
            logger.debug(f"Админы уведомлены об истечении подписки пользователя {user_id_str}")
        except Exception as e:
            logger.warning(f"Не удалось уведомить админов об истечении подписки пользователя {user_id_str}: {e}")
        
        schedule_save()  # Отложенное сохранение для уведомлений
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление об истечении пользователю {user_id_str}: {e}")

def check_subscription_access(user_id, feature=None):
    """Проверка доступа к функциям бота"""
    user_id_str = str(user_id)
    if is_admin(user_id):
        return True
    
    # ИСПРАВЛЕНО: Thread-safe чтение глобальной переменной DEMO_MODE
    demo_mode_active = False
    with data_lock:
        demo_mode_active = DEMO_MODE
    
    # В демо-режиме даем доступ всем (для демонстрации ЮКассе)
    if demo_mode_active:
        return True
    
    # Проверяем подписку с отправкой уведомлений при первом обращении
    if not has_active_subscription(user_id_str, send_notifications=True):
        # Проверяем, была ли подписка истекшей с thread-safety
        with data_lock:
            user_data = app_data.get('users', {}).get(user_id_str)
            if user_data and 'subscription_end' in user_data:
                try:
                    subscription_end = datetime.fromisoformat(user_data['subscription_end'])
                    if datetime.now() >= subscription_end:
                        # Отправляем уведомление об истечении только один раз
                        if not user_data.get('subscription_expired_notified', False):
                            user_data['subscription_expired_notified'] = True
                            try:
                                send_expiry_notification(user_id_str, subscription_end)
                            except Exception as e:
                                logger.error(f"Ошибка при отправке уведомления об истечении пользователю {user_id_str}: {e}")
                except ValueError:
                    pass
        
        # Отправляем сообщение о необходимости подписки
        send_or_edit_message(
            chat_id=user_id,
            text="""Для доступа к этой функции необходима активная подписка.
            
Вы можете получить подписку, обратившись к администратору (@M4IST).
""",
            parse_mode='Markdown',
            edit_mode=False # Отправляем новое сообщение, а не редактируем предыдущее
        )
        return False
    return True

# --- ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ---

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

def notify_all_admins(text, parse_mode=None, edit_mode=False):
    """Отправляет уведомление всем администраторам"""
    for admin_id in ADMIN_IDS:
        try:
            if parse_mode:
                send_or_edit_message(admin_id, text, parse_mode=parse_mode, edit_mode=edit_mode)
            else:
                bot.send_message(chat_id=admin_id, text=text)
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")

# --- ФУНКЦИИ ДЛЯ ПРОМОКОДОВ ---

def generate_promo_code():
    """Генерирует уникальный промокод"""
    # Создаем код из префикса + случайные символы
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=PROMO_CODE_LENGTH - len(PROMO_CODE_PREFIX)))
    return f"{PROMO_CODE_PREFIX}{random_part}"

def create_promo_codes(count=30, duration_days=SUBSCRIPTION_DURATION_DAYS):
    """Создает указанное количество промокодов (thread-safe)"""
    created_codes = []
    current_time = datetime.now().isoformat()
    
    with data_lock:
        if 'promo_codes' not in app_data:
            app_data['promo_codes'] = {}
        
        for _ in range(count):
            # Генерируем уникальный код
            attempts = 0
            while attempts < 100:  # Защита от бесконечного цикла
                code = generate_promo_code()
                if code not in app_data['promo_codes']:
                    app_data['promo_codes'][code] = {
                        'status': 'active',
                        'created_at': current_time,
                        'duration_days': duration_days,
                        'used_by': None,
                        'used_at': None
                    }
                    created_codes.append(code)
                    break
                attempts += 1
            else:
                logger.warning(f"Не удалось сгенерировать уникальный промокод после 100 попыток")
    
    schedule_save()
    logger.info(f"Создано {len(created_codes)} промокодов")
    return created_codes

def activate_promo_code(user_id, promo_code):
    """Активирует промокод для пользователя (thread-safe)"""
    try:
        logger.info(f"[activate_promo_code] Начинаем активацию промокода {promo_code} для пользователя {user_id}")
        user_id_str = str(user_id)
        promo_code = promo_code.upper().strip()  # Приводим к верхнему регистру и убираем пробелы
        logger.info(f"[activate_promo_code] Обработанный промокод: {mask_promo_code(promo_code)}, user_id_str: {user_id_str}")
        
        with data_lock:
            logger.info(f"[activate_promo_code] Получили блокировку данных")
            # Проверяем существование промокода
            promo_codes = app_data.get('promo_codes', {})
            logger.info(f"[activate_promo_code] Всего промокодов в системе: {len(promo_codes)}")
            # Не логируем полный список промокодов по соображениям безопасности
            
            if promo_code not in promo_codes:
                logger.warning(f"[activate_promo_code] Промокод {promo_code} не найден")
                return False, "Промокод не найден"
            
            promo_data = promo_codes[promo_code]
            logger.info(f"[activate_promo_code] Данные промокода: {promo_data}")
            
            # Проверяем статус промокода
            if promo_data['status'] != 'active':
                logger.warning(f"[activate_promo_code] Промокод {promo_code} имеет статус {promo_data['status']}")
                return False, "Промокод уже был использован"
            
            # УБРАНО: Проверка на ранее использованные промокоды
            # Теперь пользователи могут использовать несколько промокодов, время суммируется
            logger.info(f"[activate_promo_code] Разрешаем использование промокода (время будет суммироваться)")
            
            logger.info(f"[activate_promo_code] Все проверки пройдены, активируем подписку")
            # Активируем подписку
            duration_days = promo_data.get('duration_days', SUBSCRIPTION_DURATION_DAYS)
            logger.info(f"[activate_promo_code] Длительность подписки: {duration_days} дней")
            
            # УЛУЧШЕНО: Суммируем время подписки с существующей
            logger.info(f"[activate_promo_code] Активируем подписку с суммированием времени")
            
            # Создаем пользователя если не существует
            if 'users' not in app_data:
                app_data['users'] = {}
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
            
            # Проверяем существующую подписку
            current_subscription_end = None
            if 'subscription_end' in app_data['users'][user_id_str]:
                try:
                    current_subscription_end = datetime.fromisoformat(app_data['users'][user_id_str]['subscription_end'])
                    logger.info(f"[activate_promo_code] Текущая подписка до: {current_subscription_end}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[activate_promo_code] Ошибка парсинга даты подписки: {e}")
                    current_subscription_end = None
            
            # Вычисляем новую дату окончания подписки
            now = datetime.now()
            if current_subscription_end and current_subscription_end > now:
                # Суммируем с существующей активной подпиской
                new_subscription_end = current_subscription_end + timedelta(days=duration_days)
                logger.info(f"[activate_promo_code] Суммируем с активной подпиской: +{duration_days} дней")
            else:
                # Создаем новую подписку
                new_subscription_end = now + timedelta(days=duration_days)
                logger.info(f"[activate_promo_code] Создаем новую подписку на {duration_days} дней")
            
            # Устанавливаем новую дату окончания
            app_data['users'][user_id_str]['subscription_end'] = new_subscription_end.isoformat()
            
            # Сбрасываем флаги уведомлений при активации/продлении подписки
            if 'subscription_expired_notified' in app_data['users'][user_id_str]:
                del app_data['users'][user_id_str]['subscription_expired_notified']
            if 'subscription_warning_sent' in app_data['users'][user_id_str]:
                del app_data['users'][user_id_str]['subscription_warning_sent']
            
            subscription_end = app_data['users'][user_id_str]['subscription_end']
            logger.info(f"[activate_promo_code] Подписка активирована/продлена до {subscription_end}")
            
            # Помечаем промокод как использованный
            promo_data['status'] = 'used'
            promo_data['used_by'] = user_id_str
            promo_data['used_at'] = datetime.now().isoformat()
            logger.info(f"[activate_promo_code] Промокод помечен как использованный")
            
            # ИСПРАВЛЕНО: Устанавливаем флаг изменения данных без дополнительной блокировки
            global data_changed
            data_changed = True
            logger.info(f"[activate_promo_code] Флаг изменения данных установлен")
            
        # ИСПРАВЛЕНО: Сохраняем данные ПОСЛЕ выхода из блокировки
        logger.info(f"[activate_promo_code] Вышли из блокировки, сохраняем данные")
        save_user_data(force=True)
        logger.info(f"[activate_promo_code] Данные сохранены")
        logger.info(f"Промокод {promo_code} успешно активирован пользователем {user_id_str}")
        
        # Формируем сообщение в зависимости от того, была ли уже подписка
        if current_subscription_end and current_subscription_end > now:
            total_days = (new_subscription_end - now).days
            return True, f"Промокод активирован! Подписка продлена на {duration_days} дней. Всего дней: {total_days}."
        else:
            return True, f"Промокод активирован! Подписка выдана на {duration_days} дней."
            
    except Exception as e:
        logger.error(f"[activate_promo_code] ОШИБКА при активации промокода {promo_code} для пользователя {user_id}: {e}")
        logger.error(f"[activate_promo_code] Traceback: {traceback.format_exc()}")
        return False, "Ошибка при активации подписки"

def get_promo_codes_stats():
    """Возвращает статистику по промокодам (thread-safe)"""
    with data_lock:
        promo_codes = app_data.get('promo_codes', {})
        
        total = len(promo_codes)
        active = sum(1 for data in promo_codes.values() if data['status'] == 'active')
        used = sum(1 for data in promo_codes.values() if data['status'] == 'used')
        
        return {
            'total': total,
            'active': active,
            'used': used
        }

def list_promo_codes(status_filter=None):
    """Возвращает список промокодов с опциональной фильтрацией (thread-safe)"""
    with data_lock:
        promo_codes = app_data.get('promo_codes', {})
        
        if status_filter:
            filtered_codes = {code: data for code, data in promo_codes.items() 
                            if data['status'] == status_filter}
        else:
            filtered_codes = promo_codes.copy()
        
        return filtered_codes

def delete_promo_code(promo_code):
    """Удаляет промокод (thread-safe)"""
    promo_code = promo_code.upper().strip()
    
    with data_lock:
        if promo_code in app_data.get('promo_codes', {}):
            del app_data['promo_codes'][promo_code]
            schedule_save()
            return True
        return False


# --- Инициализация бота ---
# Получаем токен из config.py - импорт уже есть в начале файла

# ОТКЛЮЧЕНО: middleware может создавать множественные процессы
# telebot.apihelper.ENABLE_MIDDLEWARE = True
bot = telebot.TeleBot(BOT_TOKEN)
# Ограничим пул воркеров до 32 для устойчивости при нагрузке
try:
    bot.worker_pool = util.ThreadPool(32)
except Exception as e:
    logger.warning(f"Не удалось настроить пул воркеров: {e}")

# Путь к папке с тренировками (в той же директории что и бот)
training_programs_path = os.path.join(os.path.dirname(__file__), 'training_programs')
logger.info(f"Путь к тренировкам: {os.path.abspath(training_programs_path)}")

# --- Глобальные переменные ---
# Словарь для хранения всех данных приложения
app_data = {}

# --- Функции для сохранения/загрузки данных пользователей ---
USER_DATA_FILE = 'user_data.json' # Имя файла для сохранения/загрузки данных
BACKUPS_DIR = 'backups'  # Директория для резервных копий
BACKUP_EVERY = 50  # Делать резервную копию каждые N сохранений

def safe_answer_callback(callback_query_id, text=None):
    """Безопасный ответ на callback-запрос"""
    try:
        bot.answer_callback_query(callback_query_id=callback_query_id, text=text)
    except Exception as e:
        logger.error(f"Ошибка при ответе на callback-запрос {callback_query_id}: {e}")

def delete_previous_bot_message(chat_id):
    """Удаляет предыдущее сообщение, отправленное ботом в данном чате (thread-safe)."""
    chat_id_str = str(chat_id)
    message_id = None
    
    # Thread-safe чтение ID сообщения
    with data_lock:
        if (chat_id_str in app_data.get('user_last_bot_message_id', {}) and 
            app_data['user_last_bot_message_id'][chat_id_str] is not None):
            message_id = app_data['user_last_bot_message_id'][chat_id_str]
    
    if message_id:
        try:
            bot.delete_message(chat_id, message_id)
            logger.debug(f"Удалено предыдущее сообщение бота (ID: {message_id}) в чате {chat_id}.")
        except telebot.apihelper.ApiTelegramException as e:
            logger.warning(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {e}")
        
        # Thread-safe удаление записи
        with data_lock:
            if chat_id_str in app_data.get('user_last_bot_message_id', {}):
                del app_data['user_last_bot_message_id'][chat_id_str]
        schedule_save()

def send_or_edit_message(chat_id, text, parse_mode='HTML', reply_markup=None, message_type='text', photo=None, edit_mode=True):
    """Отправляет или редактирует сообщение бота, сохраняя ID последнего сообщения."""
    chat_id_str = str(chat_id)
    message = None
    
    # Проверяем, что текст не пустой
    if not text or text.strip() == '':
        logger.error(f"Попытка отправить пустое сообщение для chat_id {chat_id}")
        return None
    
    try:
        # Thread-safe проверка возможности редактирования
        message_id = None
        if edit_mode:
            with data_lock:
                if (chat_id_str in app_data.get('user_last_bot_message_id', {}) and 
                    app_data['user_last_bot_message_id'][chat_id_str] is not None):
                    message_id = app_data['user_last_bot_message_id'][chat_id_str]
        
        if message_id:
            try:
                if message_type == 'text':
                    message = bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                elif message_type == 'photo' and photo:
                    message = bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=text,
                        reply_markup=reply_markup
                    )
                logger.debug(f"Отредактировано сообщение (ID: {message_id}) в чате {chat_id}.")
            except telebot.apihelper.ApiTelegramException as e:
                el = str(e).lower()
                if any(phrase in el for phrase in ["too many requests", "retry after", "429"]):
                    # Обработка 429: небольшой бэкофф и повтор
                    retry_after = 1.0
                    m = re.search(r"retry_after(?:=|:)?\s*(\d+)", el)
                    if m:
                        try:
                            retry_after = min(3.0, float(m.group(1)))
                        except Exception:
                            retry_after = 1.0
                    time.sleep(retry_after)
                    try:
                        if message_type == 'text':
                            message = bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text=text,
                                parse_mode=parse_mode,
                                reply_markup=reply_markup
                            )
                        elif message_type == 'photo' and photo:
                            message = bot.edit_message_caption(
                                chat_id=chat_id,
                                message_id=message_id,
                                caption=text,
                                reply_markup=reply_markup
                            )
                        logger.debug(f"Повторное редактирование успешно после 429 (ID: {message_id}) в чате {chat_id}.")
                    except Exception as e2:
                        logger.warning(f"Повтор после 429 не удался: {e2}. Отправляю новое.")
                        message = _send_new_message(chat_id, text, parse_mode, reply_markup, message_type, photo)
                elif any(phrase in el for phrase in ["message to edit not found", "message is not modified", "chat not found", "message can't be edited", "bad request"]):
                    logger.warning(f"Не удалось отредактировать сообщение для chat_id {chat_id}: {e}. Отправляю новое.")
                    # Если редактирование не удалось (включая попытку редактирования документа), отправляем новое сообщение
                    message = _send_new_message(chat_id, text, parse_mode, reply_markup, message_type, photo)
                else:
                    logger.error(f"Ошибка Telegram API при редактировании сообщения для chat_id {chat_id}: {e}")
                    return None
        else:
            # Отправка нового сообщения
            message = _send_new_message(chat_id, text, parse_mode, reply_markup, message_type, photo)
            
    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Ошибка Telegram API для chat_id {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке сообщения для chat_id {chat_id}: {e}")
        return None

    # Thread-safe сохранение ID последнего сообщения
    if message and hasattr(message, 'message_id'):
        with data_lock:
            if 'user_last_bot_message_id' not in app_data:
                app_data['user_last_bot_message_id'] = {}
            app_data['user_last_bot_message_id'][chat_id_str] = message.message_id
        schedule_save()
    return message

def _send_new_message(chat_id, text, parse_mode, reply_markup, message_type, photo):
    """Вспомогательная функция для отправки нового сообщения"""
    try:
        if message_type == 'text':
            try:
                message = bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            except telebot.apihelper.ApiTelegramException as e:
                el = str(e).lower()
                if any(phrase in el for phrase in ["too many requests", "retry after", "429"]):
                    retry_after = 1.0
                    m = re.search(r"retry_after(?:=|:)?\s*(\d+)", el)
                    if m:
                        try:
                            retry_after = min(3.0, float(m.group(1)))
                        except Exception:
                            retry_after = 1.0
                    time.sleep(retry_after)
                    message = bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                else:
                    raise
        elif message_type == 'photo' and photo:
            try:
                message = bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            except telebot.apihelper.ApiTelegramException as e:
                el = str(e).lower()
                if any(phrase in el for phrase in ["too many requests", "retry after", "429"]):
                    retry_after = 1.0
                    m = re.search(r"retry_after(?:=|:)?\s*(\d+)", el)
                    if m:
                        try:
                            retry_after = min(3.0, float(m.group(1)))
                        except Exception:
                            retry_after = 1.0
                    time.sleep(retry_after)
                    message = bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                else:
                    raise
        else:
            logger.error(f"Неподдерживаемый тип сообщения: {message_type}")
            return None
        
        logger.debug(f"Отправлено новое сообщение (ID: {message.message_id}) в чате {chat_id}.")
        return message
    except Exception as e:
        logger.error(f"Ошибка при отправке нового сообщения в чат {chat_id}: {e}")
        return None

def load_user_data():
    """Загружает данные пользователей из файла (thread-safe)"""
    global app_data
    
    # Инициализируем структуру данных по умолчанию
    default_data = {
        'users': {},
        'user_last_bot_message_id': {},
        'workout_counters': {},
        'user_timers': {},
        'timer_threads': {},
        'user_workout_message_ids': {},
        'user_html_message_ids': {},  # Для отслеживания HTML файлов тренировок
        'promo_codes': {}  # Для хранения промокодов {код: {status: 'active/used', created_at: datetime, used_by: user_id, used_at: datetime}}
    }
    
    with data_lock:
        try:
            if os.path.exists(USER_DATA_FILE):
                with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    
                # Валидация и очистка загруженных данных
                if not isinstance(loaded_data, dict):
                    logger.warning("Загруженные данные не являются словарем, использую значения по умолчанию")
                    loaded_data = default_data.copy()
                
                # Проверяем и дополняем структуру данных
                for key, default_value in default_data.items():
                    if key not in loaded_data:
                        loaded_data[key] = default_value
                    elif not isinstance(loaded_data[key], type(default_value)):
                        logger.warning(f"Некорректный тип для {key}, сбрасываю к значению по умолчанию")
                        loaded_data[key] = default_value
                
                app_data = loaded_data
                logger.info(f"Данные пользователей успешно загружены. Пользователей: {len(app_data.get('users', {}))}")
            else:
                logger.info(f"Файл {USER_DATA_FILE} не найден, создаю новую структуру данных")
                app_data = default_data.copy()
                
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка JSON при чтении {USER_DATA_FILE}: {e}. Создаю резервную копию и новую структуру.")
            _backup_corrupted_file()
            app_data = default_data.copy()
            
        except (IOError, OSError) as e:
            logger.error(f"Ошибка файловой системы при загрузке {USER_DATA_FILE}: {e}")
            app_data = default_data.copy()
            
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке данных: {e}")
            app_data = default_data.copy()
    
    # Сохраняем инициализированную структуру
    save_user_data(force=True)

def _backup_corrupted_file():
    """Создает резервную копию поврежденного файла данных"""
    try:
        backup_name = f"{USER_DATA_FILE}.backup.{int(time.time())}"
        os.rename(USER_DATA_FILE, backup_name)
        logger.info(f"Поврежденный файл сохранен как {backup_name}")
    except Exception as e:
        logger.error(f"Не удалось создать резервную копию: {e}")

def cleanup_expired_subscriptions():
    """Очистка истекших подписок и отправка уведомлений (thread-safe)"""
    current_time = datetime.now()
    users_to_notify = []
    users_to_cleanup = []
    
    # Thread-safe сбор пользователей для обработки
    with data_lock:
        if 'users' not in app_data:
            return
            
        for user_id_str, user_data in app_data['users'].items():
            if 'subscription_end' in user_data:
                try:
                    subscription_end = datetime.fromisoformat(user_data['subscription_end'])
                    days_since_expiry = (current_time - subscription_end).days
                    
                    # Удаляем записи о подписке, которые истекли более 30 дней назад
                    if days_since_expiry > 30:
                        users_to_cleanup.append(user_id_str)
                        continue
                    
                    # Если подписка истекла, но уведомление еще не отправлено
                    if (current_time >= subscription_end and 
                        not user_data.get('subscription_expired_notified', False)):
                        users_to_notify.append((user_id_str, subscription_end))
                        
                except ValueError:
                    logger.error(f"Некорректная дата подписки для пользователя {user_id_str}")
                    users_to_cleanup.append(user_id_str)
    
    # Thread-safe отправка уведомлений и очистка старых флагов
    if users_to_notify:
        with data_lock:
            for user_id_str, subscription_end in users_to_notify:
                app_data['users'][user_id_str]['subscription_expired_notified'] = True
                # Очищаем старые флаги уведомлений для освобождения памяти
                if 'subscription_warning_sent' in app_data['users'][user_id_str]:
                    del app_data['users'][user_id_str]['subscription_warning_sent']
        
        # Отправляем уведомления синхронно (безопаснее)
        for user_id_str, subscription_end in users_to_notify:
            try:
                send_expiry_notification(user_id_str, subscription_end)
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления пользователю {user_id_str}: {e}")
    
    # Thread-safe очистка старых записей
    if users_to_cleanup:
        with data_lock:
            for user_id_str in users_to_cleanup:
                user_data = app_data['users'][user_id_str]
                # Очищаем все связанные с подпиской данные
                fields_to_remove = ['subscription_end', 'subscription_expired_notified', 'subscription_warning_sent']
                for field in fields_to_remove:
                    if field in user_data:
                        del user_data[field]
                logger.info(f"Очищена старая подписка для пользователя {user_id_str}")
        
        save_user_data(force=True)  # Критично - очистка данных
    
    if users_to_notify or users_to_cleanup:
        logger.info(f"Обработано подписок: уведомления - {len(users_to_notify)}, очистка - {len(users_to_cleanup)}")

def save_user_data(force=False):
    """Сохраняет данные пользователей в файл (thread-safe)"""
    global data_changed, save_counter
    
    with data_lock:
        if not force and not data_changed:
            return  # Нет изменений для сохранения
            
        try:
            # Атомарная запись: сначала во временный файл, затем os.replace
            tmp_path = f"{USER_DATA_FILE}.tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(app_data, f, ensure_ascii=False, indent=4)
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except Exception:
                    # fsync может быть недоступен на некоторых ФС; игнорируем
                    pass
            os.replace(tmp_path, USER_DATA_FILE)
            data_changed = False
            logger.debug("Данные пользователей успешно сохранены.")

            # Резервная копия по расписанию
            try:
                save_counter += 1
                if save_counter % BACKUP_EVERY == 0:
                    os.makedirs(BACKUPS_DIR, exist_ok=True)
                    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                    backup_path = os.path.join(BACKUPS_DIR, f"user_data-{timestamp}.json")
                    shutil.copyfile(USER_DATA_FILE, backup_path)
                    logger.info(f"Создана резервная копия данных: {backup_path}")
            except Exception as be:
                logger.warning(f"Не удалось создать резервную копию данных: {be}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")

def schedule_save():
    """Планирует отложенное сохранение данных (thread-safe)"""
    global save_timer, data_changed
    
    # Thread-safe операции с таймером
    with data_lock:
        data_changed = True
        
        # Отменяем предыдущий таймер, если он есть
        if save_timer is not None:
            try:
                save_timer.cancel()
            except Exception as e:
                logger.warning(f"Ошибка при отмене таймера: {e}")
            save_timer = None
        
        # Планируем сохранение через 3 секунды
        try:
            save_timer = threading.Timer(3.0, save_user_data)
            save_timer.daemon = True  # Демон-поток завершится с основным процессом
            save_timer.start()
        except Exception as e:
            logger.error(f"Ошибка при создании таймера сохранения: {e}")
            # Fallback - сохраняем немедленно
            save_user_data(force=True)

# ОТКЛЮЧЕНО: middleware может создавать множественные процессы  
# @bot.middleware_handler(update_types=['callback_query'])
# def callback_query_middleware(bot_instance, message):
#     try:
#         return message
#     except Exception as e:
#         logger.error(f"Ошибка в обработке callback-запроса: {e}")
#         return None
#
# @bot.middleware_handler(update_types=['message'])
# def message_middleware(bot_instance, message):
#     try:
#         return message
#     except Exception as e:
#         logger.error(f"Ошибка в обработке сообщения: {e}")
#         return None

def calculate_calories_and_macros(user_data):
    """Расчет калорий и КБЖУ на основе данных пользователя"""
    required_keys = ['weight', 'height', 'age', 'gender', 'activity_level', 'goal']
    
    # Проверяем, что все необходимые ключи присутствуют и их значения не None
    if not all(key in user_data and user_data[key] is not None for key in required_keys):
        logger.warning(f"Неполные данные для расчета калорий: {user_data}")
        return None

    # Дополнительная проверка на числовые значения для арифметических операций
    try:
        weight = float(user_data['weight'])
        height = float(user_data['height'])
        age = int(user_data['age'])
        
        # Проверяем разумные диапазоны значений
        if not (20 <= weight <= 500):
            logger.warning(f"Неразумный вес: {weight} кг для пользователя")
            return None
        if not (100 <= height <= 250):
            logger.warning(f"Неразумный рост: {height} см для пользователя")
            return None
        if not (10 <= age <= 120):
            logger.warning(f"Неразумный возраст: {age} лет для пользователя")
            return None
            
    except (ValueError, TypeError) as e:
        logger.error(f"Неверный тип данных для веса, роста или возраста: {user_data}. Ошибка: {e}")
        return None
        
    # Базовый обмен веществ (формула Миффлина-Сан Жеора)
    if user_data['gender'] == 'male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    # Коэффициенты активности
    activity_multipliers = {
        'sedentary': 1.2,      # Сидячий образ жизни
        'light': 1.375,        # Легкая активность
        'moderate': 1.55,      # Умеренная активность
        'active': 1.725,       # Высокая активность
        'very_active': 1.9     # Очень высокая активность
    }
    
    # Целевые коэффициенты
    goal_multipliers = {
        'lose': 0.85,          # Похудение
        'maintain': 1.0,       # Поддержание веса
        'gain': 1.15           # Набор массы
    }
    
    tdee = bmr * activity_multipliers.get(user_data['activity_level'], 1.2)
    target_calories = tdee * goal_multipliers.get(user_data['goal'], 1.0)
    
    # Расчет КБЖУ (белки, жиры, углеводы)
    # Пропорции в зависимости от цели
    if user_data['goal'] == 'lose':
        # Для похудения: больше белка, меньше углеводов
        protein_percent = 35
        fat_percent = 30
        carbs_percent = 35
    elif user_data['goal'] == 'gain':
        # Для набора массы: больше углеводов и белка
        protein_percent = 25
        fat_percent = 25
        carbs_percent = 50
    else:
        # Для поддержания веса: сбалансированное соотношение
        protein_percent = 30
        fat_percent = 25
        carbs_percent = 45
    
    # Расчет макронутриентов в граммах
    # Белки: 1г = 4 ккал
    # Жиры: 1г = 9 ккал
    # Углеводы: 1г = 4 ккал
    
    protein_calories = target_calories * protein_percent / 100
    fat_calories = target_calories * fat_percent / 100
    carbs_calories = target_calories * carbs_percent / 100
    
    protein_grams = protein_calories / 4
    fat_grams = fat_calories / 9
    carbs_grams = carbs_calories / 4
    
    # Альтернативный расчет белка на основе веса тела (более точный для спортсменов)
    protein_by_weight = weight * 1.8  # 1.8г белка на кг веса для активных людей
    
    # Используем больший из двух расчетов белка
    final_protein = max(protein_grams, protein_by_weight)
    
    return {
        'bmr': round(bmr),
        'tdee': round(tdee),
        'target_calories': round(target_calories),
        'protein': round(final_protein),
        'fat': round(fat_grams),
        'carbs': round(carbs_grams),
        'protein_calories': round(final_protein * 4),
        'fat_calories': round(fat_grams * 9),
        'carbs_calories': round(carbs_grams * 4)
    }

# Оставляем старую функцию для совместимости
def calculate_calories(user_data):
    """Расчет калорий (для обратной совместимости)"""
    result = calculate_calories_and_macros(user_data)
    if result:
        return {
            'bmr': result['bmr'],
            'tdee': result['tdee'],
            'target_calories': result['target_calories']
        }
    return None

def format_profile(user_data):
    """Форматирование профиля пользователя"""
    profile = f"👤 *Профиль пользователя*\n\n"
    
    # Базовая информация
    profile += f"Имя: {user_data.get('first_name', 'Не указано')}\n"
    profile += f"Пол: {user_data.get('gender', 'Не указан')}\n"
    profile += f"Уровень: {user_data.get('fitness_level', 'Не указан')}\n"
    
    # Дополнительная информация
    if 'weight' in user_data:
        profile += f"Вес: {user_data['weight']} кг\n"
    if 'height' in user_data:
        profile += f"Рост: {user_data['height']} см\n"
    if 'age' in user_data:
        profile += f"Возраст: {user_data['age']} лет\n"
    if 'activity_level' in user_data:
        activity_levels = {
            'sedentary': 'Сидячий образ жизни',
            'light': 'Легкая активность',
            'moderate': 'Умеренная активность',
            'active': 'Высокая активность',
            'very_active': 'Очень высокая активность'
        }
        profile += f"Уровень активности: {activity_levels.get(user_data['activity_level'], 'Не указан')}\n"
    if 'goal' in user_data:
        goals = {
            'lose': 'Похудение',
            'maintain': 'Поддержание веса',
            'gain': 'Набор массы'
        }
        profile += f"Цель: {goals.get(user_data['goal'], 'Не указана')}\n"
    
    # Расчет калорий и КБЖУ
    if 'weight' in user_data and \
            'height' in user_data and \
            'age' in user_data and \
            'gender' in user_data and \
            'activity_level' in user_data and \
            'goal' in user_data:
        macros = calculate_calories_and_macros(user_data)
        if macros:
            profile += f"\n📊 *Расчет питания:*\n"
            profile += f"Базовый обмен веществ: {macros['bmr']} ккал\n"
            profile += f"Суточная норма: {macros['tdee']} ккал\n"
            profile += f"Целевые калории: {macros['target_calories']} ккал\n\n"
            
            profile += f"🍗 *КБЖУ на день:*\n"
            profile += f"Белки: {macros['protein']}г ({macros['protein_calories']} ккал)\n"
            profile += f"Жиры: {macros['fat']}г ({macros['fat_calories']} ккал)\n"
            profile += f"Углеводы: {macros['carbs']}г ({macros['carbs_calories']} ккал)\n"
    else:
        profile += f"\n_Для расчета калорий и КБЖУ заполните все данные в профиле: вес, рост, возраст, пол, уровень активности и цель._\n"
    
    return profile

def create_profile_keyboard():
    """Создание клавиатуры для профиля"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("📏 Рост", callback_data="set_height"),
        types.InlineKeyboardButton("⚖️ Вес", callback_data="set_weight"),
        types.InlineKeyboardButton("🎂 Возраст", callback_data="set_age"),
        types.InlineKeyboardButton("👤 Пол", callback_data="set_gender"),
        types.InlineKeyboardButton("🎯 Цель", callback_data="set_goal"),
        types.InlineKeyboardButton("🏃 Активность", callback_data="set_activity"),
        types.InlineKeyboardButton("💪 Уровень", callback_data="set_fitness_level"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    ]
    keyboard.add(*buttons)
    return keyboard

def create_activity_keyboard():
    """Создание клавиатуры для выбора уровня активности"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("Сидячий образ жизни", callback_data="activity_sedentary"),
        types.InlineKeyboardButton("Легкая активность", callback_data="activity_light"),
        types.InlineKeyboardButton("Умеренная активность", callback_data="activity_moderate"),
        types.InlineKeyboardButton("Высокая активность", callback_data="activity_active"),
        types.InlineKeyboardButton("Очень высокая активность", callback_data="activity_very_active"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile")
    ]
    keyboard.add(*buttons)
    return keyboard

def create_goal_keyboard():
    """Создание клавиатуры для выбора цели"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("Похудение", callback_data="goal_lose"),
        types.InlineKeyboardButton("Поддержание веса", callback_data="goal_maintain"),
        types.InlineKeyboardButton("Набор массы", callback_data="goal_gain"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile")
    ]
    keyboard.add(*buttons)
    return keyboard

def create_gender_keyboard():
    """Создание клавиатуры для выбора пола"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("Мужской", callback_data="gender_male"),
        types.InlineKeyboardButton("Женский", callback_data="gender_female"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile")
    ]
    keyboard.add(*buttons)
    return keyboard

def create_fitness_level_keyboard():
    """Создание клавиатуры для выбора уровня подготовки"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("Начинающий", callback_data="level_novice"),
        types.InlineKeyboardButton("Продвинутый", callback_data="level_advanced"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile")
    ]
    keyboard.add(*buttons)
    return keyboard

def create_timer_keyboard():
    """Создание клавиатуры для таймера"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("⏱ 30 сек", callback_data="timer_30"),
        types.InlineKeyboardButton("⏱ 1 мин", callback_data="timer_60"),
        types.InlineKeyboardButton("⏱ 2 мин", callback_data="timer_120"),
        types.InlineKeyboardButton("⏱ 3 мин", callback_data="timer_180"),
        types.InlineKeyboardButton("⏱ 5 мин", callback_data="timer_300"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="timer_cancel"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    ]
    keyboard.add(*buttons)
    return keyboard

def timer_function(chat_id, duration, message_id):
    """Функция обратного отсчета для таймера (thread-safe)"""
    chat_id_str = str(chat_id)
    timer_active = True
    
    try:
        for i in range(duration, -1, -1):
            # Thread-safe проверка активности таймера
            with data_lock:
                if (chat_id_str not in app_data.get('user_timers', {}) or 
                    not app_data['user_timers'][chat_id_str].get('active', False)):
                    timer_active = False
            
            if not timer_active:
                logger.debug(f"Таймер: Обнаружена остановка таймера для chat_id: {chat_id_str}.")
                return
            
            if i > 0:
                # Обновляем сообщение с таймером
                text = f"Осталось: {i} секунд..."
                reply_markup = types.InlineKeyboardMarkup(row_width=1)
                reply_markup.add(types.InlineKeyboardButton("🛑 Остановить таймер", callback_data="stop_timer"))
                try:
                    send_or_edit_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        edit_mode=True # Редактируем существующее сообщение
                    )
                except Exception as e:
                    logger.error(f"Таймер: Ошибка при обновлении сообщения для chat_id {chat_id}: {e}")
                    break
                time.sleep(1)
            else:
                # ИСПРАВЛЕНО: Убираем двойную отправку сообщений
                try:
                    send_or_edit_message(
                        chat_id=chat_id,
                        text="⏰ Время вышло! 🔔",
                        reply_markup=create_main_keyboard(),
                        edit_mode=True # Редактируем существующее сообщение
                    )
                except Exception as e:
                    logger.error(f"Таймер: Ошибка при отправке финального сообщения для chat_id {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Таймер: Произошла общая ошибка в timer_function для chat_id {chat_id_str}: {e}")
    finally:
        # Гарантированная thread-safe очистка состояния таймера
        with data_lock:
            if 'user_timers' in app_data and chat_id_str in app_data['user_timers']:
                app_data['user_timers'][chat_id_str]['active'] = False
            if 'timer_threads' in app_data and chat_id_str in app_data['timer_threads']:
                del app_data['timer_threads'][chat_id_str]
        logger.debug(f"Таймер: Состояние таймера для chat_id {chat_id_str} сброшено.")
        schedule_save()  # Сохраняем изменения состояния

def get_cached_workout_files():
    """Возвращает кэшированный список файлов тренировок (thread-safe)"""
    global workout_files_cache, last_cache_update
    
    current_time = time.time()
    
    # Thread-safe проверка и обновление кэша
    with data_lock:
        # Обновляем кэш если он устарел или пустой
        if (current_time - last_cache_update > CACHE_TTL or 
            not workout_files_cache):
            
            try:
                # ИСПРАВЛЕНО: Очистка старого кэша перед обновлением
                old_cache_size = len(workout_files_cache)
                workout_files_cache.clear()
                
                if not os.path.exists(training_programs_path):
                    logger.warning(f"Директория тренировок не найдена: {training_programs_path}")
                    return workout_files_cache
                
                for filename in os.listdir(training_programs_path):
                    if filename.endswith('.txt'):
                        # Парсим имя файла: level_gender_number.txt
                        parts = filename.replace('.txt', '').split('_')
                        if len(parts) >= 3:
                            level = parts[0]    # novice/advanced
                            gender = parts[1]   # male/female  
                            number = '_'.join(parts[2:])  # может быть составным
                            
                            key = f"{level}_{gender}"
                            if key not in workout_files_cache:
                                workout_files_cache[key] = []
                            
                            # ИСПРАВЛЕНО: Ограничение размера кэша для предотвращения утечек памяти
                            if len(workout_files_cache[key]) < MAX_CACHE_SIZE:
                                workout_files_cache[key].append({
                                    'filename': filename,
                                    'number': number,
                                    'full_path': os.path.join(training_programs_path, filename)
                                })
                            else:
                                logger.warning(f"Достигнут лимит кэша для категории {key}: {MAX_CACHE_SIZE}")
                
                # Сортируем файлы по номеру для каждой категории
                for key in workout_files_cache:
                    workout_files_cache[key].sort(key=lambda x: x['number'])
                
                last_cache_update = current_time
                logger.debug(f"Кэш тренировок обновлен. Категорий: {len(workout_files_cache)}, старый размер: {old_cache_size}")
                
            except Exception as e:
                logger.error(f"Ошибка при обновлении кэша тренировок: {e}")
                workout_files_cache = {}
    
    return workout_files_cache

def get_workout_markdown(file_path):
    """Читает файл тренировки и возвращает его содержимое в формате Markdown"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        logger.error(f"Ошибка при чтении файла тренировки {file_path}: {e}")
        return None

def validate_user_input(field, value):
    """Централизованная валидация пользовательского ввода"""
    try:
        if field == 'height':
            height = float(value)
            if not (100 <= height <= 250):
                return False, "Рост должен быть от 100 до 250 см"
            return True, height
            
        elif field == 'weight':
            weight = float(value)
            if not (20 <= weight <= 500):
                return False, "Вес должен быть от 20 до 500 кг"
            return True, weight
            
        elif field == 'age':
            age = int(value)
            if not (10 <= age <= 120):
                return False, "Возраст должен быть от 10 до 120 лет"
            return True, age
            
        else:
            return False, f"Неизвестное поле: {field}"
            
    except (ValueError, TypeError) as e:
        return False, f"Некорректное значение: {str(e)}"

# --- ОБРАБОТЧИК КНОПКИ ПОДПИСКИ ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        user_id = message.chat.id
        user_id_str = str(user_id)
        logger.info(f"Обработка команды /start от пользователя {user_id_str}")
        
        # Thread-safe инициализация данных пользователя, если их нет
        with data_lock:
            if 'users' not in app_data:
                app_data['users'] = {}
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {
                    'first_name': message.from_user.first_name,
                    'last_name': message.from_user.last_name,
                    'username': message.from_user.username
                }
                schedule_save()
                logger.info(f"Новый пользователь зарегистрирован: {user_id_str}")

        # Удаляем предыдущее сообщение пользователя (команду /start)
        try:
            bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение пользователя: {e}")

        welcome_text = f"Привет, *{message.from_user.first_name}*! 👋\nЯ твой персональный фитнес-помощник."
        
        # Используем send_or_edit_message для отправки или редактирования сообщения
        send_or_edit_message(
            chat_id=user_id,
            text=welcome_text,
            reply_markup=create_main_keyboard(),
            edit_mode=True # Редактируем предыдущее сообщение при повторном старте
        )
        logger.info(f"Команда /start успешно обработана для пользователя {user_id_str}")
        
    except Exception as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в handle_start для пользователя {message.chat.id}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        try:
            bot.send_message(message.chat.id, "❌ Произошла ошибка при запуске бота. Попробуйте позже.")
        except Exception as send_error:
            logger.error(f"Не удалось отправить сообщение об ошибке в handle_start: {send_error}")

@bot.callback_query_handler(func=lambda call: call.data == 'subscription')
def handle_subscription(call):
    user_id = call.message.chat.id
    user_id_str = str(user_id)
    # УБРАНО: load_user_data() уже вызывается при запуске бота
    
    # ИСПРАВЛЕНО: Thread-safe проверка наличия подписки БЕЗ DEADLOCK
    subscription_status_text = ""
    
    # Сначала проверяем подписку БЕЗ дополнительного lock
    has_subscription = has_active_subscription(user_id_str)
    
    if has_subscription:
        with data_lock:
            if user_id_str in app_data['users'] and 'subscription_end' in app_data['users'][user_id_str]:
                try:
                    subscription_end = datetime.fromisoformat(app_data['users'][user_id_str]['subscription_end'])
                    days_left = (subscription_end - datetime.now()).days
                    subscription_status_text = f"✅ У вас активная подписка до {subscription_end.strftime('%d.%m.%Y')} ({days_left} дн.)"
                except (ValueError, KeyError) as e:
                    logger.error(f"Ошибка при обработке даты подписки для пользователя {user_id_str}: {e}")
                    subscription_status_text = "✅ У вас активная подписка"
            else:
                subscription_status_text = "✅ У вас активная подписка"
    else:
        subscription_status_text = "❌ У вас нет активной подписки"
    
    # Создаем клавиатуру с кнопками для покупки подписки
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("1 месяц - 2990₽", callback_data="buy_sub_1"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    
    # Отправляем сообщение с информацией о подписке
    send_or_edit_message(
        chat_id=user_id,
        text=f"💎 *Управление подпиской*\n\n{subscription_status_text}\n\nВыберите срок подписки или обратитесь к администратору (@M4IST) для активации:",
        parse_mode='Markdown',
        reply_markup=keyboard,
        edit_mode=True # Это меню, поэтому редактируем предыдущее сообщение
    )
    safe_answer_callback(call.id) # Закрываем callback-запрос

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_sub_'))
def handle_buy_subscription_buttons(call):
    user_id = call.message.chat.id
    
    # Извлекаем количество месяцев из callback_data
    try:
        months = int(call.data.split('_')[2])
        price = SUBSCRIPTION_PRICES.get(months, 2990)
    except (IndexError, ValueError):
        months = 1
        price = 2990
    
    if PAYMENT_DEMO_MODE:
        # Демо-режим для ЮКассы - показываем процесс оплаты
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("💳 Оплатить картой", callback_data=f"demo_pay_{months}_{price}"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="subscription")
        )
        
        send_or_edit_message(
            chat_id=user_id,
            text=f"""💎 Подписка на {months} мес. - {price}₽

🔒 Безопасная оплата через ЮКасса
✅ Мгновенная активация подписки
🎯 Доступ ко всем функциям бота

Выберите способ оплаты:""",
            parse_mode='Markdown',
            reply_markup=keyboard,
            edit_mode=True
        )
        safe_answer_callback(call.id)
    else:
        # Реальный режим - создаем платеж через ЮКассу
        if YOOKASSA_SHOP_ID == 'ВАШИ_РЕАЛЬНЫЕ_КЛЮЧИ_ЗДЕСЬ' or YOOKASSA_SECRET_KEY == 'ВАШИ_РЕАЛЬНЫЕ_КЛЮЧИ_ЗДЕСЬ':
            # Ключи не настроены
            safe_answer_callback(call.id, "Оплата временно недоступна. Обратитесь к администратору.")
            send_or_edit_message(
                chat_id=user_id,
                text="""⚠️ Оплата временно недоступна
                
Администратор еще не настроил платежи.
Пожалуйста, обратитесь к @M4IST для получения подписки.
""",
                parse_mode='Markdown',
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔙 Назад", callback_data="subscription")
                ),
                edit_mode=True
            )
        else:
            # Создаем реальный платеж
            duration_days = months * 30  # Переводим месяцы в дни
            payment_data = create_payment(user_id, price, duration_days)
            
            if payment_data and 'confirmation' in payment_data:
                # Платеж создан успешно
                payment_url = payment_data['confirmation']['confirmation_url']
                payment_id = payment_data['id']
                
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    types.InlineKeyboardButton("💳 Оплатить", url=payment_url),
                    types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_payment_{payment_id}"),
                    types.InlineKeyboardButton("🔙 Назад", callback_data="subscription")
                )
                
                send_or_edit_message(
                    chat_id=user_id,
                    text=f"""💎 Оплата подписки

📋 Детали заказа:
• Подписка: {months} мес.
• Сумма: {price}₽
• ID платежа: {payment_id[:10]}...

🔒 Безопасная оплата через ЮКасса

После оплаты нажмите "Проверить оплату" для активации подписки.""",
                    parse_mode='Markdown',
                    reply_markup=keyboard,
                    edit_mode=True
                )
                safe_answer_callback(call.id, "Платеж создан. Перейдите по ссылке для оплаты.")
            else:
                # Ошибка создания платежа
                safe_answer_callback(call.id, "Ошибка создания платежа. Попробуйте позже.")
                send_or_edit_message(
                    chat_id=user_id,
                    text="""❌ Ошибка создания платежа
                    
Не удалось создать платеж. Пожалуйста, попробуйте позже.
Если проблема повторяется, обратитесь к @M4IST
""",
                    parse_mode='Markdown',
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("🔙 Назад", callback_data="subscription")
                    ),
                    edit_mode=True
                )

@bot.callback_query_handler(func=lambda call: call.data.startswith('demo_pay_'))
def handle_demo_payment(call):
    """Обработчик демо-оплаты для ЮКассы"""
    user_id = call.message.chat.id
    
    try:
        parts = call.data.split('_')
        months = int(parts[2])
        price = int(parts[3])
    except (IndexError, ValueError):
        months = 1
        price = 2990
    
    # Показываем "процесс оплаты"
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"demo_confirm_{months}"),
        types.InlineKeyboardButton("❌ Отменить", callback_data="subscription")
    )
    
    send_or_edit_message(
        chat_id=user_id,
        text=f"""💳 Оплата подписки

📋 Детали заказа:
• Подписка: {months} мес.
• Сумма: {price}₽
• Способ оплаты: Банковская карта

🔒 Безопасная оплата обеспечивается ЮКасса

⚠️ ДЕМО-РЕЖИМ: Это демонстрация для модерации ЮКассы.
Реальная оплата будет доступна после одобрения.""",
        parse_mode='Markdown',
        reply_markup=keyboard,
        edit_mode=True
    )
    safe_answer_callback(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('demo_confirm_'))
def handle_demo_confirm(call):
    """Обработчик подтверждения демо-оплаты"""
    user_id = call.message.chat.id
    
    try:
        months = int(call.data.split('_')[2])
    except (IndexError, ValueError):
        months = 1
    
    send_or_edit_message(
        chat_id=user_id,
        text=f"""✅ Демо-оплата успешна!

🎉 Подписка на {months} мес. активирована
📅 Действует до: (демо-режим)

⚠️ Это демонстрация для модерации ЮКассы.
Для получения реальной подписки обратитесь к @M4IST

Спасибо за использование нашего бота!""",
        parse_mode='Markdown',
        reply_markup=create_main_keyboard(),
        edit_mode=True
    )
    safe_answer_callback(call.id, "Демо-оплата завершена!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('check_payment_'))
def handle_check_payment(call):
    """Обработчик проверки реального платежа"""
    user_id = call.message.chat.id
    
    try:
        payment_id = call.data.replace('check_payment_', '')
        
        # Проверяем статус платежа с rate limiting
        payment_success = check_payment_status(payment_id, user_id)
        
        if payment_success:
            send_or_edit_message(
                chat_id=user_id,
                text="""✅ Оплата успешна!

🎉 Ваша подписка активирована!
📅 Теперь у вас есть доступ ко всем функциям бота.

Спасибо за покупку!""",
                parse_mode='Markdown',
                reply_markup=create_main_keyboard(),
                edit_mode=True
            )
            safe_answer_callback(call.id, "Подписка активирована!")
            
            # Уведомляем админов о новой оплате
            try:
                admin_text = f"""💰 Новая оплата!

👤 Пользователь: {user_id}
💳 Платеж: {payment_id}
✅ Подписка активирована"""
                
                notify_all_admins(admin_text)
            except Exception as e:
                logger.warning(f"Не удалось уведомить админа о платеже: {e}")
                
        else:
            send_or_edit_message(
                chat_id=user_id,
                text="""⏳ Платеж еще не обработан

Платеж может обрабатываться до 15 минут.
Попробуйте проверить еще раз через несколько минут.

Если проблема сохраняется, обратитесь к @M4IST""",
                parse_mode='Markdown',
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_payment_{payment_id}"),
                    types.InlineKeyboardButton("🔙 Назад", callback_data="subscription")
                ),
                edit_mode=True
            )
            safe_answer_callback(call.id, "Платеж еще не обработан")
            
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")
        send_or_edit_message(
            chat_id=user_id,
            text="""❌ Ошибка проверки платежа

Произошла ошибка при проверке платежа.
Пожалуйста, обратитесь к @M4IST""",
            parse_mode='Markdown',
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 Назад", callback_data="subscription")
            ),
            edit_mode=True
        )
        safe_answer_callback(call.id, "Ошибка проверки платежа")

@bot.message_handler(commands=['grant_sub'])
def grant_subscription_command(message):
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            send_or_edit_message(message.chat.id, "Использование: /grant_sub <user_id> [duration_days]", edit_mode=True)
            return
        
        target_user_id = int(parts[1])
        duration_days = SUBSCRIPTION_DURATION_DAYS
        if len(parts) > 2:
            duration_days = int(parts[2])
            
        activate_subscription(target_user_id, duration_days)
        send_or_edit_message(message.chat.id, f"Подписка выдана пользователю {target_user_id} на {duration_days} дней.", edit_mode=True)
        try: # Добавляем try-except для отправки сообщения пользователю, так как он может быть заблокирован
            send_or_edit_message(target_user_id, f"Администратор выдал вам подписку на {duration_days} дней!", edit_mode=False)
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {target_user_id} о выдаче подписки: {e}")
    except ValueError:
        send_or_edit_message(message.chat.id, "Неверный User ID или длительность. Пожалуйста, введите число.", edit_mode=True)
    except Exception as e:
        logger.error(f"Ошибка при выдаче подписки: {e}")
        send_or_edit_message(message.chat.id, f"Произошла ошибка при выдаче подписки: {e}", edit_mode=True)

@bot.message_handler(commands=['revoke_sub'])
def revoke_subscription_command(message):
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            send_or_edit_message(message.chat.id, "Использование: /revoke_sub <user_id>", edit_mode=True)
            return
        
        target_user_id = int(parts[1])
        revoke_subscription(target_user_id)
        send_or_edit_message(message.chat.id, f"Подписка отозвана у пользователя {target_user_id}.", edit_mode=True)
        try: # Добавляем try-except для отправки сообщения пользователю
            send_or_edit_message(target_user_id, "Ваша подписка была отозвана администратором.", edit_mode=False)
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {target_user_id} об отзыве подписки: {e}")
    except ValueError:
        send_or_edit_message(message.chat.id, "Неверный User ID. Пожалуйста, введите число.", edit_mode=True)
    except Exception as e:
        logger.error(f"Ошибка при отзыве подписки: {e}")
        send_or_edit_message(message.chat.id, f"Произошла ошибка при отзыве подписки: {e}", edit_mode=True)

@bot.message_handler(commands=['checkpay'])
def check_payment(message):
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    send_or_edit_message(message.chat.id, "Функция проверки платежей через Юкасса временно отключена для пользователей. Используйте /grant_sub для ручной выдачи подписки.", edit_mode=True)

@bot.message_handler(commands=['addsub'])
def admin_add_subscription(message):
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    send_or_edit_message(message.chat.id, "Используйте команду /grant_sub <user_id> [duration_days] для выдачи подписки.", edit_mode=True)

@bot.message_handler(commands=['delsub'])
def admin_del_subscription(message):
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    send_or_edit_message(message.chat.id, "Используйте команду /revoke_sub <user_id> для отзыва подписки.", edit_mode=True)

@bot.message_handler(commands=['demo_mode'])
def toggle_demo_mode(message):
    """Переключение демо-режима (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    # ИСПРАВЛЕНО: Thread-safe изменение глобальных переменных
    global DEMO_MODE, PAYMENT_DEMO_MODE
    
    try:
        parts = message.text.split()
        if len(parts) > 1:
            if parts[1].lower() == 'on':
                # Thread-safe изменение глобальных переменных
                with data_lock:
                    DEMO_MODE = True
                    PAYMENT_DEMO_MODE = True
                send_or_edit_message(message.chat.id, "✅ Демо-режим ВКЛЮЧЕН\n• Все пользователи имеют доступ\n• Показываются кнопки оплаты", edit_mode=True)
                logger.info("Демо-режим включен через команду")
            elif parts[1].lower() == 'off':
                # Thread-safe изменение глобальных переменных
                with data_lock:
                    DEMO_MODE = False  
                    PAYMENT_DEMO_MODE = False
                send_or_edit_message(message.chat.id, "❌ Демо-режим ВЫКЛЮЧЕН\n• Проверка подписки активна\n• Реальные платежи", edit_mode=True)
                logger.info("Демо-режим выключен через команду")
            else:
                send_or_edit_message(message.chat.id, "Использование: /demo_mode on|off", edit_mode=True)
        else:
            # Thread-safe чтение глобальных переменных
            with data_lock:
                status = "ВКЛЮЧЕН" if DEMO_MODE else "ВЫКЛЮЧЕН"
            send_or_edit_message(message.chat.id, f"Текущий статус демо-режима: {status}\nИспользование: /demo_mode on|off", edit_mode=True)
    except Exception as e:
        logger.error(f"Ошибка при переключении демо-режима: {e}")
        send_or_edit_message(message.chat.id, f"Ошибка: {e}", edit_mode=True)

@bot.message_handler(commands=['check_subs'])
def check_all_subscriptions(message):
    """Проверка всех подписок (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        if 'users' not in app_data or not app_data['users']:
            send_or_edit_message(message.chat.id, "Нет зарегистрированных пользователей.", edit_mode=True)
            return
        
        current_time = datetime.now()
        active_subs = []
        expired_subs = []
        no_subs = []
        
        for user_id_str, user_data in app_data['users'].items():
            if 'subscription_end' in user_data:
                try:
                    subscription_end = datetime.fromisoformat(user_data['subscription_end'])
                    if current_time < subscription_end:
                        days_left = (subscription_end - current_time).days
                        active_subs.append(f"• {user_id_str}: до {subscription_end.strftime('%d.%m.%Y')} ({days_left} дн.)")
                    else:
                        days_expired = (current_time - subscription_end).days
                        expired_subs.append(f"• {user_id_str}: истекла {subscription_end.strftime('%d.%m.%Y')} ({days_expired} дн. назад)")
                except Exception as e:
                    expired_subs.append(f"• {user_id_str}: ошибка данных")
            else:
                no_subs.append(f"• {user_id_str}")
        
        result = "📊 Статус подписок:\n\n"
        
        if active_subs:
            result += f"✅ Активные ({len(active_subs)}):\n" + "\n".join(active_subs) + "\n\n"
        
        if expired_subs:
            result += f"⏰ Истекшие ({len(expired_subs)}):\n" + "\n".join(expired_subs) + "\n\n"
        
        if no_subs:
            result += f"❌ Без подписки ({len(no_subs)}):\n" + "\n".join(no_subs[:10])  # Показываем первых 10
            if len(no_subs) > 10:
                result += f"\n... и еще {len(no_subs) - 10}"
        
        send_or_edit_message(message.chat.id, result, edit_mode=True)
        
    except Exception as e:
        logger.error(f"Ошибка при проверке подписок: {e}")
        send_or_edit_message(message.chat.id, f"Ошибка: {e}", edit_mode=True)

@bot.message_handler(commands=['cleanup_subs'])
def manual_cleanup_subscriptions(message):
    """Ручная очистка истекших подписок (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        cleanup_expired_subscriptions()
        send_or_edit_message(message.chat.id, "✅ Очистка истекших подписок выполнена.", edit_mode=True)
    except Exception as e:
        logger.error(f"Ошибка при очистке подписок: {e}")
        send_or_edit_message(message.chat.id, f"Ошибка: {e}", edit_mode=True)

@bot.message_handler(commands=['admin_help'])
def admin_help(message):
    """Справка по админским командам (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    help_text = """🔧 *Админские команды:*

**Управление подписками:**
• `/grant_sub <user_id> [days]` - выдать подписку
• `/revoke_sub <user_id>` - отозвать подписку
• `/check_subs` - посмотреть все подписки
• `/cleanup_subs` - очистить старые подписки

**Управление промокодами:**
• `/create_promo [count] [days]` - создать промокоды
• `/promo_stats` - статистика промокодов
• `/list_promo [active|used]` - список промокодов
• `/delete_promo <код>` - удалить промокод

**Настройки бота:**
• `/demo_mode on|off` - переключить демо-режим
• `/admin_help` - эта справка

**Информация:**
В демо-режиме все пользователи имеют доступ к функциям.
В обычном режиме работает проверка подписки и реальные платежи через ЮКассу.

**Автоматические уведомления:**
• За 3 дня до истечения подписки
• При истечении подписки
• При новых оплатах"""
    
    send_or_edit_message(message.chat.id, help_text, parse_mode='Markdown', edit_mode=True)

# --- АДМИНСКИЕ КОМАНДЫ ДЛЯ ПРОМОКОДОВ ---

@bot.message_handler(commands=['create_promo'])
def create_promo_command(message):
    """Создание промокодов (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        parts = message.text.split()
        count = 30  # По умолчанию 30 кодов
        duration_days = SUBSCRIPTION_DURATION_DAYS  # По умолчанию 30 дней
        
        if len(parts) > 1:
            count = int(parts[1])
        if len(parts) > 2:
            duration_days = int(parts[2])
            
        if count <= 0 or count > 100:
            send_or_edit_message(message.chat.id, "Количество промокодов должно быть от 1 до 100.", edit_mode=True)
            return
            
        if duration_days <= 0 or duration_days > 365:
            send_or_edit_message(message.chat.id, "Длительность подписки должна быть от 1 до 365 дней.", edit_mode=True)
            return
        
        # Создаем промокоды
        created_codes = create_promo_codes(count, duration_days)
        
        if created_codes:
            # Формируем сообщение с кодами
            codes_text = "\n".join([f"• `{code}`" for code in created_codes])
            response_text = f"""✅ *Создано {len(created_codes)} промокодов*

**Длительность подписки:** {duration_days} дней

**Промокоды:**
{codes_text}

*Промокоды можно скопировать и отправить пользователям.*"""
            
            send_or_edit_message(message.chat.id, response_text, parse_mode='Markdown', edit_mode=True)
            logger.info(f"Админ создал {len(created_codes)} промокодов на {duration_days} дней")
        else:
            send_or_edit_message(message.chat.id, "Ошибка при создании промокодов.", edit_mode=True)
            
    except ValueError:
        send_or_edit_message(message.chat.id, "Неверные параметры. Используйте: /create_promo [количество] [дни]", edit_mode=True)
    except Exception as e:
        logger.error(f"Ошибка при создании промокодов: {e}")
        send_or_edit_message(message.chat.id, f"Произошла ошибка: {e}", edit_mode=True)

@bot.message_handler(commands=['promo_stats'])
def promo_stats_command(message):
    """Статистика промокодов (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        stats = get_promo_codes_stats()
        
        response_text = f"""📊 *Статистика промокодов*

**Всего создано:** {stats['total']}
**Активных:** {stats['active']}
**Использованных:** {stats['used']}

**Процент использования:** {(stats['used'] / stats['total'] * 100) if stats['total'] > 0 else 0:.1f}%"""
        
        send_or_edit_message(message.chat.id, response_text, parse_mode='Markdown', edit_mode=True)
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики промокодов: {e}")
        send_or_edit_message(message.chat.id, f"Произошла ошибка: {e}", edit_mode=True)

@bot.message_handler(commands=['list_promo'])
def list_promo_command(message):
    """Список промокодов (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        parts = message.text.split()
        status_filter = None
        
        if len(parts) > 1:
            status_filter = parts[1].lower()
            if status_filter not in ['active', 'used']:
                send_or_edit_message(message.chat.id, "Используйте: /list_promo [active|used]", edit_mode=True)
                return
        
        promo_codes = list_promo_codes(status_filter)
        
        if not promo_codes:
            filter_text = f" ({status_filter})" if status_filter else ""
            send_or_edit_message(message.chat.id, f"Промокоды{filter_text} не найдены.", edit_mode=True)
            return
        
        # Формируем список
        codes_list = []
        for code, data in sorted(promo_codes.items()):
            status_emoji = "✅" if data['status'] == 'active' else "❌"
            created_date = datetime.fromisoformat(data['created_at']).strftime('%d.%m.%Y')
            
            if data['status'] == 'used':
                used_date = datetime.fromisoformat(data['used_at']).strftime('%d.%m.%Y')
                codes_list.append(f"{status_emoji} `{code}` - {created_date} → {used_date} (ID: {data['used_by']})")
            else:
                codes_list.append(f"{status_emoji} `{code}` - {created_date}")
        
        # Разбиваем на части, если список слишком длинный
        max_codes_per_message = 20
        for i in range(0, len(codes_list), max_codes_per_message):
            chunk = codes_list[i:i + max_codes_per_message]
            filter_text = f" ({status_filter})" if status_filter else ""
            
            response_text = f"""📋 *Промокоды{filter_text}* (часть {i//max_codes_per_message + 1})

{chr(10).join(chunk)}

*Формат: статус код - дата создания [→ дата использования (ID пользователя)]*"""
            
            send_or_edit_message(message.chat.id, response_text, parse_mode='Markdown', edit_mode=True)
            
    except Exception as e:
        logger.error(f"Ошибка при получении списка промокодов: {e}")
        send_or_edit_message(message.chat.id, f"Произошла ошибка: {e}", edit_mode=True)

@bot.message_handler(commands=['delete_promo'])
def delete_promo_command(message):
    """Удаление промокода (только для админа)"""
    if not is_admin(message.chat.id):
        send_or_edit_message(message.chat.id, "У вас нет прав для выполнения этой команды.", edit_mode=True)
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            send_or_edit_message(message.chat.id, "Использование: /delete_promo <код>", edit_mode=True)
            return
        
        promo_code = parts[1].upper().strip()
        
        if delete_promo_code(promo_code):
            send_or_edit_message(message.chat.id, f"✅ Промокод `{promo_code}` удален.", parse_mode='Markdown', edit_mode=True)
            logger.info(f"Админ удалил промокод {promo_code}")
        else:
            send_or_edit_message(message.chat.id, f"❌ Промокод `{promo_code}` не найден.", parse_mode='Markdown', edit_mode=True)
            
    except Exception as e:
        logger.error(f"Ошибка при удалении промокода: {e}")
        send_or_edit_message(message.chat.id, f"Произошла ошибка: {e}", edit_mode=True)

# --- ПОЛЬЗОВАТЕЛЬСКАЯ КОМАНДА ДЛЯ ПРОМОКОДОВ ---

@bot.message_handler(commands=['promo'])
def promo_command(message):
    """Активация промокода пользователем"""
    user_id = message.chat.id
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            send_or_edit_message(user_id, """🎟️ *Активация промокода*

Для активации промокода используйте:
`/promo ВАШ_ПРОМОКОД`

**Пример:**
`/promo FIT123ABC456`

*Промокод активирует подписку на 1 месяц.*""", parse_mode='Markdown', edit_mode=True)
            return
        
        promo_code = parts[1].upper().strip()
        
        # УБРАНО: Проверка активной подписки - промокоды теперь суммируются
        user_id_str = str(user_id)
        logger.info(f"Команда /promo от пользователя {user_id_str}, промокод: {promo_code}")
        
        # Активируем промокод
        success, message_text = activate_promo_code(user_id, promo_code)
        
        if success:
            response_text = f"""🎉 *{message_text}*

✅ Подписка активирована!
📅 Теперь у вас есть доступ ко всем функциям бота.

Используйте главное меню для начала тренировок."""
            
            # Уведомляем админов
            try:
                admin_text = f"""🎟️ *Промокод активирован*

**Пользователь:** {user_id}
**Промокод:** `{promo_code}`
**Время:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
                
                notify_all_admins(admin_text, parse_mode='Markdown', edit_mode=False)
            except Exception as e:
                logger.warning(f"Не удалось уведомить админа об активации промокода: {e}")
                
        else:
            response_text = f"❌ *Ошибка активации*\n\n{message_text}"
        
        send_or_edit_message(user_id, response_text, parse_mode='Markdown', edit_mode=True)
        
    except Exception as e:
        logger.error(f"Ошибка при активации промокода пользователем {user_id}: {e}")
        send_or_edit_message(user_id, "Произошла ошибка при активации промокода. Попробуйте позже.", edit_mode=True)

def create_main_keyboard():
    """Создание главной клавиатуры"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("💪 Тренировки", callback_data="workouts"),
        types.InlineKeyboardButton("⏱ Таймер", callback_data="timer"),
        types.InlineKeyboardButton("👤 Мой профиль", callback_data="my_profile"),
        types.InlineKeyboardButton("📊 Калькулятор КБЖУ", callback_data="calories"),
        types.InlineKeyboardButton("🎟️ Промокод", callback_data="promo_input"),
        types.InlineKeyboardButton("💎 Подписка", callback_data="subscription")
    ]
    keyboard.add(*buttons)
    return keyboard

def create_calories_keyboard():
    """Создание клавиатуры для калькулятора калорий"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("🔄 Пересчитать КБЖУ", callback_data="calc_calories"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    ]
    keyboard.add(*buttons)
    return keyboard

# --- Функции для работы с тренировками ---
@bot.callback_query_handler(func=lambda call: call.data == 'workouts')
def handle_workouts_button(call):
    user_id = call.from_user.id
    user_id_str = str(user_id)

    # Проверка подписки
    if not check_subscription_access(user_id):
        # check_subscription_access уже отправляет сообщение о необходимости подписки
        return
    
    # ИСПРАВЛЕНО: Thread-safe получение данных пользователя
    user_data = None
    with data_lock:
        if user_id_str in app_data.get('users', {}):
            user_data = app_data['users'][user_id_str].copy()  # Безопасная копия
    
    if not user_data or 'fitness_level' not in user_data or 'gender' not in user_data:
        safe_answer_callback(call.id, "Пожалуйста, заполните ваш профиль в разделе \"Мой профиль\".")
        send_or_edit_message(
            call.message.chat.id, 
            "Для подбора тренировок мне нужны данные вашего профиля: уровень подготовки и пол.", 
            parse_mode="Markdown",
            edit_mode=True # Это информационное сообщение в интерфейсе
        )
        return

    fitness_level = user_data['fitness_level']
    gender = user_data['gender']

    # Используем кэш для получения списка тренировок
    workout_cache = get_cached_workout_files()
    cache_key = f"{fitness_level}_{gender}"
    
    found_workouts = []
    if cache_key in workout_cache:
        for workout_info in workout_cache[cache_key]:
            # Проверяем существование HTML файла
            html_file_path = workout_info['full_path'].replace('.txt', '.html')
            if os.path.exists(html_file_path):
                found_workouts.append((workout_info['number'], html_file_path))
        logger.info(f"Найдено тренировок из кэша для {cache_key}: {len(found_workouts)}")
    else:
        logger.warning(f"Категория тренировок не найдена в кэше: {cache_key}")

    if found_workouts:
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        for workout_number, workout_file in found_workouts:
            callback_data = f"workout_select_{fitness_level}_{gender}_{workout_number}"
            keyboard.add(types.InlineKeyboardButton(f"Тренировка #{workout_number}", callback_data=callback_data))
        
        keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        send_or_edit_message(
            call.message.chat.id, 
            "Выберите тренировку:", 
            parse_mode="Markdown", 
            reply_markup=keyboard,
            edit_mode=True # Это меню, поэтому редактируем предыдущее сообщение
        )
    else:
        safe_answer_callback(call.id, "К сожалению, тренировки не найдены для вашего уровня и пола.")
        send_or_edit_message(
            call.message.chat.id, 
            "К сожалению, тренировки не найдены для вашего уровня и пола. Пожалуйста, проверьте свой профиль или попробуйте позже.", 
            parse_mode="Markdown",
            edit_mode=True # Это сообщение об ошибке, заменяем предыдущее
        )
    safe_answer_callback(call.id) # Закрываем callback-запрос

@bot.callback_query_handler(func=lambda call: call.data.startswith('workout_select_'))
def handle_workout_selection(call):
    """Оптимизированный обработчик выбора тренировки с кэшированием"""
    user_id = call.from_user.id
    user_id_str = str(user_id)
    
    if not check_subscription_access(user_id):
        safe_answer_callback(call.id)
        return

    try:
        # Ожидаем формат callback_data: workout_select_{level}_{gender}_{number}
        parts = call.data.split('_')
        if len(parts) >= 5:  # workout_select_level_gender_number
            level = parts[2]
            gender = parts[3]
            workout_number = '_'.join(parts[4:])  # может быть составным номером
            
            # Используем кэш для поиска файлов
            workout_cache = get_cached_workout_files()
            cache_key = f"{level}_{gender}"
            
            if cache_key in workout_cache:
                # Ищем нужную тренировку в кэше
                workout_file = None
                for cached_workout in workout_cache[cache_key]:
                    if cached_workout['number'] == workout_number:
                        workout_file = cached_workout
                        break
                
                if workout_file:
                    txt_file_path = workout_file['full_path']
                    html_file_path = txt_file_path.replace('.txt', '.html')
                    
                    logger.info(f"Найдена тренировка в кэше: {txt_file_path}")
                    
                    # Проверяем существование HTML файла
                    if os.path.exists(html_file_path):
                        # Читаем текстовое описание
                        txt_content = get_workout_markdown(txt_file_path)
                        if txt_content is None:
                            txt_content = "Описание тренировки недоступно"
                        
                        # Создаем клавиатуру
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🔙 Назад к тренировкам", callback_data="workouts"))
                        keyboard.add(types.InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main"))
                        
                        # Отправляем текстовое описание
                        message_text = f"🏋️ *Тренировка #{workout_number}*\n\n{txt_content.strip()}"
                        send_or_edit_message(
                            chat_id=call.message.chat.id,
                            text=message_text,
                            parse_mode="Markdown",
                            reply_markup=keyboard,
                            edit_mode=True
                        )
                        
                        # ИСПРАВЛЕНО: Удаляем предыдущий HTML файл перед отправкой нового
                        chat_id_str = str(call.message.chat.id)
                        
                        # Получаем id предыдущего HTML сообщения thread-safe
                        prev_html_id = None
                        with data_lock:
                            if (chat_id_str in app_data.get('user_html_message_ids', {}) and 
                                app_data['user_html_message_ids'][chat_id_str] is not None):
                                prev_html_id = app_data['user_html_message_ids'][chat_id_str]

                        # Удаляем предыдущее сообщение вне блокировки
                        if prev_html_id is not None:
                            try:
                                bot.delete_message(call.message.chat.id, prev_html_id)
                                logger.debug(f"Удален предыдущий HTML файл (ID: {prev_html_id})")
                            except Exception as e:
                                logger.warning(f"Не удалось удалить предыдущий HTML файл {prev_html_id}: {e}")
                        
                        # Отправляем новый HTML файл
                        try:
                            with open(html_file_path, 'rb') as html_file:
                                html_message = bot.send_document(
                                    chat_id=call.message.chat.id,
                                    document=html_file,
                                    caption="📋 Подробная тренировка (HTML файл)"
                                )
                                # Сохраняем ID нового HTML файла для последующего удаления (thread-safe)
                                with data_lock:
                                    if 'user_html_message_ids' not in app_data:
                                        app_data['user_html_message_ids'] = {}
                                    app_data['user_html_message_ids'][chat_id_str] = html_message.message_id
                                schedule_save()
                                
                            logger.info(f"Отправлена тренировка {workout_number} пользователю {user_id_str}")
                        except Exception as e:
                            logger.error(f"Ошибка отправки HTML файла: {e}")
                            # Ошибка не критична, основное текстовое сообщение уже отправлено
                    else:
                        logger.warning(f"HTML файл не найден: {html_file_path}")
                        send_or_edit_message(
                            chat_id=call.message.chat.id,
                            text="❌ Подробная тренировка недоступна.",
                            parse_mode="Markdown",
                            edit_mode=True
                        )
                else:
                    logger.warning(f"Тренировка не найдена в кэше: {level}_{gender}_{workout_number}")
                    send_or_edit_message(
                        chat_id=call.message.chat.id,
                        text="❌ Запрошенная тренировка не найдена.",
                        parse_mode="Markdown",
                        edit_mode=True
                    )
            else:
                logger.warning(f"Категория тренировок не найдена в кэше: {cache_key}")
                send_or_edit_message(
                    chat_id=call.message.chat.id,
                    text="❌ Тренировки для выбранной категории не найдены.",
                    parse_mode="Markdown",
                    edit_mode=True
                )
        else:
            logger.warning(f"Некорректный callback_data: {call.data}")
            send_or_edit_message(
                chat_id=call.message.chat.id,
                text="❌ Некорректный запрос тренировки.",
                parse_mode="Markdown",
                edit_mode=True
            )

    except Exception as e:
        logger.error(f"Ошибка в handle_workout_selection: {e}")
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text="❌ Произошла ошибка при загрузке тренировки. Попробуйте еще раз.",
            parse_mode="Markdown",
            edit_mode=True
        )
    finally:
        safe_answer_callback(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'my_profile')
def handle_my_profile_button(call):
    """Обработчик кнопки профиля"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
                schedule_save()
            user_data_copy = app_data['users'][user_id_str].copy()  # Создаем копию для безопасного чтения
        
        profile_text = format_profile(user_data_copy)
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=profile_text,
            reply_markup=create_profile_keyboard(),
            edit_mode=True # Это профиль, редактируем предыдущее сообщение
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в обработчике профиля: {e}")
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text="Произошла ошибка при загрузке профиля. Пожалуйста, попробуйте позже.",
            edit_mode=True # Это сообщение об ошибке, заменяем предыдущее
        )

@bot.callback_query_handler(func=lambda call: call.data == 'timer')
def handle_timer_button(call):
    user_id = call.from_user.id
    
    if not check_subscription_access(user_id):
        return

    send_or_edit_message(
        chat_id=call.message.chat.id,
        text="Выберите продолжительность таймера:",
        reply_markup=create_timer_keyboard()
    )
    safe_answer_callback(call.id) # Закрываем callback-запрос

@bot.callback_query_handler(func=lambda call: call.data.startswith('timer_') and call.data != 'timer_cancel')
def handle_timer_selection(call):
    user_id = call.from_user.id
    user_id_str = str(user_id)
    
    if not check_subscription_access(user_id):
        safe_answer_callback(call.id)
        return

    duration = 0
    try:
        duration = int(call.data.split('_')[1])
    except ValueError:
        logger.error(f"Таймер: Неверный формат callback_data для таймера: {call.data}")
        safe_answer_callback(call.id, "Ошибка: неверный формат таймера.")
        return

    # Thread-safe остановка предыдущего таймера и запуск нового
    with data_lock:
        if user_id_str in app_data.get('user_timers', {}) and app_data['user_timers'][user_id_str].get('active', False):
            app_data['user_timers'][user_id_str]['active'] = False
            logger.info(f"Таймер: Предыдущий таймер для {user_id_str} остановлен.")
            
        if 'user_timers' not in app_data:
            app_data['user_timers'] = {}
        if 'timer_threads' not in app_data:
            app_data['timer_threads'] = {}
            
        app_data['user_timers'][user_id_str] = {'active': True, 'message_id': call.message.message_id}
    
    schedule_save()

    # Запускаем таймер в новой нити (thread-safe + демон)
    timer_thread = threading.Thread(target=timer_function, args=(user_id, duration, call.message.message_id))
    timer_thread.daemon = True  # Демон-поток завершится с основным процессом
    with data_lock:
        app_data['timer_threads'][user_id_str] = timer_thread
    timer_thread.start()
    
    safe_answer_callback(call.id, f"Таймер запущен на {duration} секунд.")

@bot.callback_query_handler(func=lambda call: call.data == 'stop_timer')
def handle_stop_timer(call):
    user_id = call.from_user.id
    user_id_str = str(user_id)

    timer_was_active = False
    
    # Thread-safe остановка таймера
    with data_lock:
        if (user_id_str in app_data.get('user_timers', {}) and 
            app_data['user_timers'][user_id_str].get('active', False)):
            app_data['user_timers'][user_id_str]['active'] = False
            timer_was_active = True
            logger.info(f"Таймер: Таймер для {user_id_str} остановлен пользователем.")
            
            # Очищаем завершенные потоки
            if user_id_str in app_data.get('timer_threads', {}):
                thread = app_data['timer_threads'][user_id_str]
                if not thread.is_alive():
                    del app_data['timer_threads'][user_id_str]
    
    # Дополнительная задержка для завершения цикла в timer_function
    time.sleep(0.1)
    
    if timer_was_active:
        send_or_edit_message(
            chat_id=user_id,
            text="🛑 Таймер остановлен.",
            reply_markup=create_main_keyboard(),
            edit_mode=True
        )
    else:
        send_or_edit_message(
            chat_id=user_id,
            text="У вас нет активного таймера.",
            reply_markup=create_main_keyboard(),
            edit_mode=True
        )
    
    schedule_save()
    safe_answer_callback(call.id, "Таймер остановлен.")

@bot.callback_query_handler(func=lambda call: call.data == 'timer_cancel')
def handle_timer_cancel(call):
    user_id = call.from_user.id
    user_id_str = str(user_id)
    
    # Thread-safe остановка и очистка таймера
    with data_lock:
        if (user_id_str in app_data.get('user_timers', {}) and 
            app_data['user_timers'][user_id_str].get('active', False)):
            app_data['user_timers'][user_id_str]['active'] = False
            logger.info(f"Таймер: Таймер для {user_id_str} отменен пользователем.")
            
        # Очищаем данные таймера
        if user_id_str in app_data.get('user_timers', {}):
            del app_data['user_timers'][user_id_str]
        if user_id_str in app_data.get('timer_threads', {}):
            del app_data['timer_threads'][user_id_str]
    
    # Даем немного времени потоку на завершение
    time.sleep(0.1)
    schedule_save()
    
    send_or_edit_message(
        chat_id=user_id,
        text="Действие отменено.",
        reply_markup=create_main_keyboard(),
        edit_mode=True
    )
    safe_answer_callback(call.id, "Отменено.")

@bot.callback_query_handler(func=lambda call: call.data == 'calories')
def handle_calories_button(call):
    """Обработчик кнопки калькулятора калорий"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        if not check_subscription_access(user_id, 'calories'):
            return
        
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
                schedule_save()
            user_data = app_data['users'][user_id_str].copy()  # Создаем копию для безопасного чтения
        required_fields = ['weight', 'height', 'age', 'gender', 'activity_level', 'goal']
        
        if not all(field in user_data for field in required_fields):
            send_or_edit_message(
                chat_id=call.message.chat.id,
                text="Для расчета калорий и КБЖУ необходимо заполнить все данные в профиле.",
                reply_markup=create_profile_keyboard(),
                edit_mode=True # Это сообщение об ошибке, заменяем предыдущее
            )
        else:
            macros = calculate_calories_and_macros(user_data)
            if macros:
                text = f"""📊 *Расчет питания:*

Базовый обмен веществ: {macros['bmr']} ккал
Суточная норма: {macros['tdee']} ккал
Целевые калории: {macros['target_calories']} ккал

🍗 *КБЖУ на день:*
• Белки: {macros['protein']}г ({macros['protein_calories']} ккал)
• Жиры: {macros['fat']}г ({macros['fat_calories']} ккал)  
• Углеводы: {macros['carbs']}г ({macros['carbs_calories']} ккал)

💡 *Рекомендации:*
Распределите эти макронутриенты на 4-6 приемов пищи в течение дня."""
                
                send_or_edit_message(
                    chat_id=call.message.chat.id,
                    text=text,
                    reply_markup=create_calories_keyboard(),
                    edit_mode=True # Это результат, редактируем предыдущее сообщение
                )
        
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в обработчике калькулятора калорий: {e}")
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text="Произошла ошибка при расчете калорий. Пожалуйста, попробуйте позже.",
            edit_mode=True # Это сообщение об ошибке, заменяем предыдущее
        )

# --- Обработчик кнопки промокода ---

@bot.callback_query_handler(func=lambda call: call.data == 'promo_input')
def handle_promo_input_button(call):
    """Обработчик кнопки ввода промокода"""
    user_id = call.from_user.id
    user_id_str = str(user_id)
    
    # УБРАНО: Проверка активной подписки - теперь промокоды суммируются
    logger.info(f"Пользователь {user_id} запросил ввод промокода (время будет суммироваться с текущей подпиской)")
    
    # Показываем интерфейс ввода промокода
    send_or_edit_message(
        chat_id=call.message.chat.id,
        text="""🎟️ *Активация промокода*

Введите ваш промокод в следующем сообщении.

**Формат промокода:** FIT123ABC456

**Что дает промокод:**
✅ Подписка на 1 месяц (суммируется с текущей)
✅ Доступ ко всем тренировкам
✅ Персональный калькулятор КБЖУ
✅ Таймер для тренировок

*Каждый промокод можно использовать только один раз, но вы можете использовать несколько разных промокодов.*""",
        parse_mode='Markdown',
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        ),
        edit_mode=True
    )
    
    # Устанавливаем флаг ожидания ввода промокода
    with data_lock:
        if user_id_str not in app_data.get('users', {}):
            app_data.setdefault('users', {})[user_id_str] = {}
        app_data['users'][user_id_str]['awaiting_promo_input'] = True
    schedule_save()
    
    safe_answer_callback(call.id)

# --- Обработчики callback-запросов для профиля ---

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def handle_back_to_main(call):
    """Обработчик возврата в главное меню"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        chat_id_str = str(call.message.chat.id)
        
        # Thread-safe остановка активного таймера, если он есть
        html_id_to_delete = None
        with data_lock:
            if user_id_str in app_data.get('user_timers', {}) and app_data['user_timers'][user_id_str].get('active', False):
                app_data['user_timers'][user_id_str]['active'] = False
            # Получаем html_id для удаления вне блокировки
            if (chat_id_str in app_data.get('user_html_message_ids', {}) and 
                app_data['user_html_message_ids'][chat_id_str] is not None):
                html_id_to_delete = app_data['user_html_message_ids'][chat_id_str]
                # Сразу сбрасываем, чтобы не держать ссылку
                app_data['user_html_message_ids'][chat_id_str] = None
        
        # Удаляем HTML сообщение вне блокировки
        if html_id_to_delete is not None:
            try:
                bot.delete_message(call.message.chat.id, html_id_to_delete)
                logger.debug(f"Удален HTML файл при возврате в главное меню (ID: {html_id_to_delete})")
            except Exception as e:
                logger.warning(f"Не удалось удалить HTML файл {html_id_to_delete}: {e}")
        
        schedule_save()
        
        welcome_text = f"Привет, *{call.from_user.first_name}*! 👋\nЯ твой персональный фитнес-помощник."
        
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=welcome_text,
            reply_markup=create_main_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_main: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_profile')
def handle_back_to_profile(call):
    """Обработчик возврата в профиль"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
                schedule_save()
            user_data_copy = app_data['users'][user_id_str].copy()  # Создаем копию для безопасного чтения
        
        profile_text = format_profile(user_data_copy)
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=profile_text,
            reply_markup=create_profile_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_profile: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith('gender_'))
def handle_gender_selection(call):
    """Обработчик выбора пола"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        gender = call.data.split('_')[1]  # male или female
        
        # ИСПРАВЛЕНО: Thread-safe изменение данных пользователя
        with data_lock:
            if 'users' not in app_data:
                app_data['users'] = {}
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
            app_data['users'][user_id_str]['gender'] = gender
            # Создаем копию для безопасного использования вне lock
            user_data_copy = app_data['users'][user_id_str].copy()
        schedule_save()
        
        # Возвращаемся в профиль
        profile_text = format_profile(user_data_copy)
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=profile_text,
            reply_markup=create_profile_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id, f"Пол: {'Мужской' if gender == 'male' else 'Женский'}")
    except Exception as e:
        logger.error(f"Ошибка в handle_gender_selection: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith('level_'))
def handle_fitness_level_selection(call):
    """Обработчик выбора уровня подготовки"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        level = call.data.split('_')[1]  # novice или advanced
        
        # ИСПРАВЛЕНО: Thread-safe изменение данных пользователя
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
            app_data['users'][user_id_str]['fitness_level'] = level
            # Создаем копию для безопасного использования вне lock
            user_data_copy = app_data['users'][user_id_str].copy()
        schedule_save()
        
        # Возвращаемся в профиль
        profile_text = format_profile(user_data_copy)
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=profile_text,
            reply_markup=create_profile_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id, f"Уровень: {'Начинающий' if level == 'novice' else 'Продвинутый'}")
    except Exception as e:
        logger.error(f"Ошибка в handle_fitness_level_selection: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith('activity_'))
def handle_activity_selection(call):
    """Обработчик выбора уровня активности"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        activity = call.data.split('_')[1]  # sedentary, light, moderate, active, very_active
        
        # ИСПРАВЛЕНО: Thread-safe изменение данных пользователя
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
            app_data['users'][user_id_str]['activity_level'] = activity
            # Создаем копию для безопасного использования вне lock
            user_data_copy = app_data['users'][user_id_str].copy()
        schedule_save()
        
        # Возвращаемся в профиль
        profile_text = format_profile(user_data_copy)
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=profile_text,
            reply_markup=create_profile_keyboard(),
            edit_mode=True
        )
        
        activity_names = {
            'sedentary': 'Сидячий образ жизни',
            'light': 'Легкая активность',
            'moderate': 'Умеренная активность',
            'active': 'Высокая активность',
            'very_active': 'Очень высокая активность'
        }
        safe_answer_callback(call.id, f"Активность: {activity_names.get(activity, activity)}")
    except Exception as e:
        logger.error(f"Ошибка в handle_activity_selection: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith('goal_'))
def handle_goal_selection(call):
    """Обработчик выбора цели"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        goal = call.data.split('_')[1]  # lose, maintain, gain
        
        # ИСПРАВЛЕНО: Thread-safe изменение данных пользователя
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
            app_data['users'][user_id_str]['goal'] = goal
            # Создаем копию для безопасного использования вне lock
            user_data_copy = app_data['users'][user_id_str].copy()
        schedule_save()
        
        # Возвращаемся в профиль
        profile_text = format_profile(user_data_copy)
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=profile_text,
            reply_markup=create_profile_keyboard(),
            edit_mode=True
        )
        
        goal_names = {
            'lose': 'Похудение',
            'maintain': 'Поддержание веса',
            'gain': 'Набор массы'
        }
        safe_answer_callback(call.id, f"Цель: {goal_names.get(goal, goal)}")
    except Exception as e:
        logger.error(f"Ошибка в handle_goal_selection: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'calc_calories')
def handle_calc_calories(call):
    """Обработчик расчета калорий"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
                schedule_save()
            user_data = app_data['users'][user_id_str].copy()  # Создаем копию для безопасного чтения
        required_fields = ['weight', 'height', 'age', 'gender', 'activity_level', 'goal']
        
        if not all(field in user_data for field in required_fields):
            send_or_edit_message(
                chat_id=call.message.chat.id,
                text="Для расчета калорий и КБЖУ необходимо заполнить все данные в профиле.",
                reply_markup=create_profile_keyboard(),
                edit_mode=True
            )
        else:
            macros = calculate_calories_and_macros(user_data)
            if macros:
                text = f"""📊 *Расчет питания:*

Базовый обмен веществ: {macros['bmr']} ккал
Суточная норма: {macros['tdee']} ккал
Целевые калории: {macros['target_calories']} ккал

🍗 *КБЖУ на день:*
• Белки: {macros['protein']}г ({macros['protein_calories']} ккал)
• Жиры: {macros['fat']}г ({macros['fat_calories']} ккал)  
• Углеводы: {macros['carbs']}г ({macros['carbs_calories']} ккал)

💡 *Рекомендации:*
Распределите эти макронутриенты на 4-6 приемов пищи в течение дня."""
                
                send_or_edit_message(
                    chat_id=call.message.chat.id,
                    text=text,
                    reply_markup=create_calories_keyboard(),
                    edit_mode=True
                )
            else:
                send_or_edit_message(
                    chat_id=call.message.chat.id,
                    text="Ошибка при расчете калорий и КБЖУ. Проверьте данные в профиле.",
                    reply_markup=create_calories_keyboard(),
                    edit_mode=True
                )
        
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_calc_calories: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

# Обработчики для ввода данных профиля
@bot.callback_query_handler(func=lambda call: call.data in ['set_height', 'set_weight', 'set_age'])
def handle_profile_input_requests(call):
    """Обработчик запросов на ввод данных профиля"""
    try:
        user_id = call.from_user.id
        user_id_str = str(user_id)
        
        field_map = {
            'set_height': ('height', 'рост в сантиметрах (например, 170)'),
            'set_weight': ('weight', 'вес в килограммах (например, 70)'),
            'set_age': ('age', 'возраст в годах (например, 25)')
        }
        
        field, description = field_map[call.data]
        
        # Thread-safe сохранение информации о том, что пользователь ожидает ввода
        with data_lock:
            if user_id_str not in app_data['users']:
                app_data['users'][user_id_str] = {}
            app_data['users'][user_id_str]['awaiting_input'] = field
        schedule_save()
        
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text=f"Введите ваш {description}:",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("❌ Отмена", callback_data="back_to_profile")
            ),
            edit_mode=True
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_profile_input_requests: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'set_goal')
def handle_set_goal(call):
    """Обработчик установки цели"""
    try:
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text="Выберите вашу цель:",
            reply_markup=create_goal_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_set_goal: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'set_activity')
def handle_set_activity(call):
    """Обработчик установки уровня активности"""
    try:
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text="Выберите ваш уровень активности:",
            reply_markup=create_activity_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_set_activity: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'set_gender')
def handle_set_gender(call):
    """Обработчик установки пола"""
    try:
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text="Выберите ваш пол:",
            reply_markup=create_gender_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_set_gender: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'set_fitness_level')
def handle_set_fitness_level(call):
    """Обработчик установки уровня подготовки"""
    try:
        send_or_edit_message(
            chat_id=call.message.chat.id,
            text="Выберите ваш уровень подготовки:",
            reply_markup=create_fitness_level_keyboard(),
            edit_mode=True
        )
        safe_answer_callback(call.id)
    except Exception as e:
        logger.error(f"Ошибка в handle_set_fitness_level: {e}")
        safe_answer_callback(call.id, "Произошла ошибка")

# Обработчик текстовых сообщений для ввода данных профиля
@bot.message_handler(func=lambda message: True)
def handle_profile_input(message):
    """Обработчик ввода данных профиля"""
    try:
        user_id = message.from_user.id
        user_id_str = str(user_id)
        
        # Удаляем сообщение пользователя
        try:
            bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
        
        # ИСПРАВЛЕНО: Thread-safe проверка ожидания ввода
        awaiting_input_field = None
        awaiting_promo_input = False
        with data_lock:
            if user_id_str in app_data.get('users', {}):
                if 'awaiting_input' in app_data['users'][user_id_str]:
                    awaiting_input_field = app_data['users'][user_id_str]['awaiting_input']
                if 'awaiting_promo_input' in app_data['users'][user_id_str]:
                    awaiting_promo_input = app_data['users'][user_id_str]['awaiting_promo_input']
        
        if awaiting_input_field:
            try:
                # Используем централизованную валидацию
                is_valid, result = validate_user_input(awaiting_input_field, message.text)
                if is_valid:
                    # ИСПРАВЛЕНО: Thread-safe обновление данных пользователя
                    with data_lock:
                        if user_id_str not in app_data.get('users', {}):
                            app_data.setdefault('users', {})[user_id_str] = {}
                        app_data['users'][user_id_str][awaiting_input_field] = result
                        # Удаляем флаг ожидания ввода
                        if 'awaiting_input' in app_data['users'][user_id_str]:
                            del app_data['users'][user_id_str]['awaiting_input']
                        # Создаем копию для безопасного использования
                        user_data_copy = app_data['users'][user_id_str].copy()
                    schedule_save()
                else:
                    raise ValueError(result)
                
                # Возвращаемся в профиль
                profile_text = format_profile(user_data_copy)
                send_or_edit_message(
                    chat_id=user_id,
                    text=profile_text,
                    reply_markup=create_profile_keyboard(),
                    edit_mode=True
                )
                
            except ValueError as e:
                send_or_edit_message(
                    chat_id=user_id,
                    text=f"Ошибка: {str(e)}. Попробуйте еще раз.",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("❌ Отмена", callback_data="back_to_profile")
                    ),
                    edit_mode=True
                )
        elif awaiting_promo_input:
            # Обработка ввода промокода
            try:
                logger.info(f"Начинаем обработку промокода от пользователя {user_id}")
                promo_code = message.text.upper().strip()
                logger.info(f"Промокод получен: {mask_promo_code(promo_code)}")
                
                # Убираем флаг ожидания ввода
                with data_lock:
                    if user_id_str in app_data.get('users', {}):
                        if 'awaiting_promo_input' in app_data['users'][user_id_str]:
                            del app_data['users'][user_id_str]['awaiting_promo_input']
                logger.info(f"Флаг awaiting_promo_input убран для пользователя {user_id}")
                schedule_save()
                
                # Активируем промокод
                logger.info(f"Вызываем activate_promo_code для пользователя {user_id} с кодом {mask_promo_code(promo_code)}")
                success, message_text = activate_promo_code(user_id, promo_code)
                logger.info(f"Результат активации: success={success}, message={message_text}")
                
                if success:
                    response_text = f"""🎉 *{message_text}*

✅ Подписка активирована!
📅 Теперь у вас есть доступ ко всем функциям бота.

Используйте главное меню для начала тренировок."""
                    logger.info(f"Подготовлен success response для пользователя {user_id}")
                    
                    # Уведомляем админов
                    try:
                        admin_text = f"""🎟️ *Промокод активирован*

**Пользователь:** {user_id}
**Промокод:** `{mask_promo_code(promo_code)}`
**Время:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
                        logger.info(f"Уведомляем админов об активации промокода {mask_promo_code(promo_code)}")
                        notify_all_admins(admin_text, parse_mode='Markdown', edit_mode=False)
                    except Exception as e:
                        logger.warning(f"Не удалось уведомить админов об активации промокода: {e}")
                        
                else:
                    response_text = f"❌ *Ошибка активации*\n\n{message_text}"
                    logger.info(f"Подготовлен error response для пользователя {user_id}: {message_text}")
                
                logger.info(f"Отправляем ответ пользователю {user_id}")
                send_or_edit_message(
                    chat_id=user_id,
                    text=response_text,
                    parse_mode='Markdown',
                    reply_markup=create_main_keyboard(),
                    edit_mode=True
                )
                logger.info(f"Ответ отправлен пользователю {user_id}")
                
            except Exception as e:
                logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в обработке промокода для пользователя {user_id}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                try:
                    send_or_edit_message(
                        chat_id=user_id,
                        text="❌ Произошла ошибка при обработке промокода. Попробуйте позже.",
                        reply_markup=create_main_keyboard(),
                        edit_mode=True
                    )
                except Exception as send_error:
                    logger.error(f"Не удалось отправить сообщение об ошибке: {send_error}")
        elif isinstance(message.text, str) and message.text.strip():
            # Автораспознавание промокода в любом текстовом сообщении
            try:
                raw_text = message.text.strip()
                promo_code_candidate = raw_text.upper()
                is_promo_like = (
                    promo_code_candidate.startswith(PROMO_CODE_PREFIX)
                    and len(promo_code_candidate) == PROMO_CODE_LENGTH
                    and promo_code_candidate[len(PROMO_CODE_PREFIX):].isalnum()
                )

                if is_promo_like:
                    logger.info(f"Обнаружен промокод в обычном сообщении от пользователя {user_id}: {promo_code_candidate}")
                    success, message_text = activate_promo_code(user_id, promo_code_candidate)

                    if success:
                        response_text = f"""🎉 *{message_text}*

✅ Подписка активирована!
📅 Теперь у вас есть доступ ко всем функциям бота.

Используйте главное меню для начала тренировок."""

                        # Уведомляем админов
                        try:
                            admin_text = f"""🎟️ *Промокод активирован*

**Пользователь:** {user_id}
**Промокод:** `{promo_code_candidate}`
**Время:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
                            notify_all_admins(admin_text, parse_mode='Markdown', edit_mode=False)
                        except Exception as e:
                            logger.warning(f"Не удалось уведомить админов (авто): {e}")
                    else:
                        response_text = f"❌ *Ошибка активации*\n\n{message_text}"

                    send_or_edit_message(
                        chat_id=user_id,
                        text=response_text,
                        parse_mode='Markdown',
                        reply_markup=create_main_keyboard(),
                        edit_mode=True
                    )
                    return  # Уже обработали как промокод
            except Exception as e:
                logger.error(f"Ошибка автообработки промокода у пользователя {user_id}: {e}")
        else:
            # ИСПРАВЛЕНО: Thread-safe создание/проверка профиля пользователя
            user_data = None
            with data_lock:
                if user_id_str not in app_data.get('users', {}):
                    app_data.setdefault('users', {})[user_id_str] = {
                        'first_name': message.from_user.first_name,
                        'username': message.from_user.username
                    }
                    schedule_save()
                user_data = app_data['users'][user_id_str].copy()  # Создаем копию для безопасного чтения
            
            if 'gender' not in user_data or 'fitness_level' not in user_data:
                send_or_edit_message(
                    chat_id=user_id,
                    text="Для начала работы с ботом выберите ваш пол:",
                    reply_markup=create_gender_keyboard(),
                    edit_mode=False
                )
            else:
                # Показываем главное меню
                welcome_text = f"Привет, *{message.from_user.first_name}*! 👋\nЯ твой персональный фитнес-помощник."
                send_or_edit_message(
                    chat_id=user_id,
                    text=welcome_text,
                    reply_markup=create_main_keyboard(),
                    edit_mode=False
                )
    except Exception as e:
        logger.error(f"Ошибка в handle_profile_input: {e}")

# --- Глобальный обработчик ошибок ---
def global_exception_handler(exception):
    """Глобальный обработчик необработанных исключений"""
    logger.error(f"ГЛОБАЛЬНАЯ ОШИБКА: {exception}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Пытаемся уведомить админов об ошибке
    try:
        error_text = f"""🚨 *КРИТИЧЕСКАЯ ОШИБКА БОТА*

**Ошибка:** {str(exception)[:200]}
**Время:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

Бот продолжает работу, но требует внимания!"""
        
        notify_all_admins(error_text, parse_mode='Markdown', edit_mode=False)
    except Exception as notify_error:
        logger.error(f"Не удалось уведомить админов об ошибке: {notify_error}")

# --- Запуск бота ---
def graceful_shutdown():
    """Корректное завершение работы бота"""
    global save_timer
    
    logger.info("Инициирую корректное завершение работы...")
    
    # Останавливаем все активные таймеры пользователей
    with data_lock:
        if 'user_timers' in app_data:
            for user_id_str in app_data['user_timers']:
                if app_data['user_timers'][user_id_str].get('active', False):
                    app_data['user_timers'][user_id_str]['active'] = False
                    logger.debug(f"Остановлен таймер для пользователя {user_id_str}")
    
    # Отменяем таймер отложенного сохранения
    if save_timer is not None:
        try:
            save_timer.cancel()
            logger.debug("Таймер сохранения отменен")
        except Exception as e:
            logger.warning(f"Ошибка при отмене таймера сохранения: {e}")
        save_timer = None
    
    # Принудительно сохраняем данные
    try:
        save_user_data(force=True)
        logger.info("Данные сохранены.")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")
    
    logger.info("Бот остановлен.")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"Получен сигнал {signum}, завершаю работу...")
    graceful_shutdown()
    exit(0)

if __name__ == "__main__":
    # ИСПРАВЛЕНО: signal уже импортирован в начале файла
    
    # Регистрируем обработчики для корректного завершения
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        load_user_data()
        # УБИРАЕМ автоматическую очистку при запуске - она создает потоки
        # cleanup_expired_subscriptions()  # Отключено во избежание создания лишних потоков
        logger.info("Бот запущен...")
        
        # Основной цикл с обработкой ошибок
        while True:
            try:
                bot.infinity_polling(none_stop=True, timeout=60, skip_pending=True)
            except Exception as polling_error:
                logger.error(f"Ошибка в polling: {polling_error}")
                global_exception_handler(polling_error)
                
                # Пауза перед перезапуском polling
                logger.info("Перезапуск polling через 5 секунд...")
                time.sleep(5)
                continue
                
    except KeyboardInterrupt:
        graceful_shutdown()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        global_exception_handler(e)
        graceful_shutdown()