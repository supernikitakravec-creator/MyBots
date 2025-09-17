#!/usr/bin/env python3
"""
Скрипт для подключения депозитного аккаунта с улучшенной логикой отправки SMS
"""

import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import *
from config import DEPOSIT_ACCOUNTS
import os
from datetime import datetime, timedelta

# Настройка логирования без эмодзи
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('connect_account.log')
    ]
)
logger = logging.getLogger(__name__)

async def connect_specific_account(account_key: str):
    """Подключение конкретного депозитного аккаунта"""
    
    if account_key not in DEPOSIT_ACCOUNTS:
        logger.error(f"Аккаунт {account_key} не найден в конфигурации")
        return False
    
    account_config = DEPOSIT_ACCOUNTS[account_key]
    
    logger.info(f"=== ПОДКЛЮЧЕНИЕ АККАУНТА {account_key} ===")
    logger.info(f"Номер телефона: {account_config['phone']}")
    logger.info(f"API ID: {account_config['api_id']}")
    logger.info(f"API Hash: {account_config['api_hash'][:8]}...")
    
    # Проверяем файл сессии
    session_file = f"deposit_account_{account_key}.session"
    if os.path.exists(session_file):
        logger.info(f"Найден файл сессии: {session_file}")
        file_size = os.path.getsize(session_file)
        logger.info(f"Размер файла сессии: {file_size} байт")
        
        # Пытаемся подключиться с существующей сессией
        try:
            client = Client(
                name=f"deposit_account_{account_key}",
                api_id=account_config['api_id'],
                api_hash=account_config['api_hash'],
                phone_number=account_config['phone']
            )
            
            logger.info("Попытка подключения с существующей сессией...")
            await client.start()
            
            me = await client.get_me()
            logger.info(f"УСПЕШНО! Подключен как: @{me.username or me.first_name}")
            logger.info(f"ID: {me.id}")
            logger.info(f"Номер: {me.phone_number}")
            
            await client.stop()
            logger.info("Аккаунт успешно подключен!")
            return True
            
        except Exception as e:
            logger.warning(f"Ошибка подключения с сессией: {e}")
            logger.info("Удаляем поврежденную сессию...")
            try:
                os.remove(session_file)
                logger.info("Файл сессии удален")
            except:
                pass
    else:
        logger.info("Файл сессии НЕ найден")
    
    # Создаем новую сессию с улучшенной логикой
    logger.info("=== СОЗДАНИЕ НОВОЙ СЕССИИ ===")
    
    try:
        client = Client(
            name=f"deposit_account_{account_key}",
            api_id=account_config['api_id'],
            api_hash=account_config['api_hash'],
            phone_number=account_config['phone']
        )
        
        logger.info("Подключение к серверам Telegram...")
        await client.connect()
        
        logger.info("Отправка запроса на код подтверждения...")
        
        # Пытаемся отправить код через SMS
        try:
            sent_code = await client.send_code(account_config['phone'])
            
            logger.info("КОД ОТПРАВЛЕН!")
            logger.info(f"Тип отправки: {sent_code.type}")
            logger.info(f"Следующий тип: {sent_code.next_type}")
            logger.info(f"Таймаут: {sent_code.timeout} сек")
            
            # Показываем подсказку пользователю
            print(f"\n" + "="*50)
            print(f"КОД ОТПРАВЛЕН НА НОМЕР: {account_config['phone']}")
            print(f"Тип отправки: {sent_code.type}")
            
            if "SMS" in str(sent_code.type):
                print("📱 Код отправлен через SMS")
                print("💡 Проверьте входящие сообщения")
            elif "APP" in str(sent_code.type):
                print("📲 Код отправлен через Telegram приложение")
                print("💡 Откройте Telegram на этом номере")
            
            print("="*50)
            
            # Даем пользователю время найти код
            code = input(f"\n🔢 Введите код подтверждения для {account_config['phone']}: ").strip()
            
            if not code:
                logger.warning("Код не введен, прерываем подключение")
                await client.disconnect()
                return False
            
            # Авторизуемся
            logger.info("Авторизация с введенным кодом...")
            
            try:
                await client.sign_in(account_config['phone'], sent_code.phone_code_hash, code)
                
                # Получаем информацию о пользователе
                me = await client.get_me()
                
                logger.info("АВТОРИЗАЦИЯ УСПЕШНА!")
                logger.info(f"Подключен как: @{me.username or me.first_name}")
                logger.info(f"ID: {me.id}")
                logger.info(f"Номер: {me.phone_number}")
                
                await client.disconnect()
                
                print(f"\n✅ УСПЕХ! Аккаунт {account_key} успешно подключен!")
                print(f"👤 Пользователь: @{me.username or me.first_name}")
                print(f"🔢 ID: {me.id}")
                
                return True
                
            except PhoneCodeInvalid:
                logger.error("НЕВЕРНЫЙ КОД ПОДТВЕРЖДЕНИЯ")
                print("\n❌ Неверный код подтверждения!")
                print("💡 Попробуйте запустить скрипт еще раз")
                
            except PhoneCodeExpired:
                logger.error("КОД ПОДТВЕРЖДЕНИЯ ИСТЕК")
                print("\n⏰ Код подтверждения истек!")
                print("💡 Запустите скрипт еще раз для получения нового кода")
                
            except Exception as e:
                logger.error(f"Ошибка авторизации: {e}")
                print(f"\n❌ Ошибка авторизации: {e}")
                
        except FloodWait as e:
            wait_time = e.value
            logger.error(f"FLOOD WAIT: {wait_time} секунд")
            logger.error(f"Заблокирован до: {datetime.now() + timedelta(seconds=wait_time)}")
            
            print(f"\n🚫 ВРЕМЕННАЯ БЛОКИРОВКА!")
            print(f"⏰ Заблокирован на {wait_time} секунд")
            print(f"🕐 Попробуйте снова после: {datetime.now() + timedelta(seconds=wait_time)}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки кода: {e}")
            print(f"\n❌ Ошибка отправки кода: {e}")
            
        await client.disconnect()
        
    except ApiIdInvalid:
        logger.error("НЕВЕРНЫЙ API ID")
        print("\n❌ Неверный API ID! Проверьте данные на https://my.telegram.org")
        
    except ApiHashInvalid:
        logger.error("НЕВЕРНЫЙ API HASH")
        print("\n❌ Неверный API Hash! Проверьте данные на https://my.telegram.org")
        
    except PhoneNumberInvalid:
        logger.error("НЕВЕРНЫЙ НОМЕР ТЕЛЕФОНА")
        print(f"\n❌ Неверный номер телефона: {account_config['phone']}")
        print("💡 Проверьте формат: +7XXXXXXXXXX")
        
    except PhoneNumberBanned:
        logger.error("НОМЕР ЗАБЛОКИРОВАН")
        print(f"\n🚫 Номер {account_config['phone']} заблокирован в Telegram!")
        print("💡 Этот номер больше нельзя использовать для API")
        
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        print(f"\n❌ Неожиданная ошибка: {e}")
    
    return False

async def main():
    """Главная функция"""
    print("🚀 Скрипт подключения депозитного аккаунта")
    print("="*50)
    
    # Показываем доступные аккаунты
    print("Доступные аккаунты:")
    for key, config in DEPOSIT_ACCOUNTS.items():
        status = "✅ активен" if config['is_active'] else "❌ отключен"
        print(f"  {key}: {config['phone']} ({status})")
    
    # Просим выбрать аккаунт
    account_key = input(f"\nВведите ключ аккаунта для подключения (например, account_2): ").strip()
    
    if not account_key:
        print("❌ Ключ аккаунта не введен!")
        return
    
    if account_key not in DEPOSIT_ACCOUNTS:
        print(f"❌ Аккаунт {account_key} не найден!")
        return
    
    # Подключаем аккаунт
    success = await connect_specific_account(account_key)
    
    if success:
        print(f"\n🎉 Аккаунт {account_key} успешно подключен!")
        print("💡 Теперь можете запустить основного бота: python main_bot.py")
    else:
        print(f"\n❌ Не удалось подключить аккаунт {account_key}")
        print("💡 Проверьте логи в файле connect_account.log")

if __name__ == "__main__":
    asyncio.run(main()) 