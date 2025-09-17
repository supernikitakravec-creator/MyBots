#!/usr/bin/env python3
"""
Диагностика проблем с SMS кодами для депозитных аккаунтов
"""

import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import *
from config import DEPOSIT_ACCOUNTS
import os
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('sms_diagnosis.log')
    ]
)
logger = logging.getLogger(__name__)

async def diagnose_account(account_key: str, account_config: dict):
    """Диагностика одного аккаунта"""
    logger.info(f"\n{'='*50}")
    logger.info(f"🔍 ДИАГНОСТИКА АККАУНТА: {account_key}")
    logger.info(f"{'='*50}")
    
    logger.info(f"📱 Номер телефона: {account_config['phone']}")
    logger.info(f"🔧 API ID: {account_config['api_id']}")
    logger.info(f"🔧 API Hash: {account_config['api_hash'][:8]}...")
    logger.info(f"📊 Активен: {account_config['is_active']}")
    
    # Проверяем файл сессии
    session_file = f"deposit_account_{account_key}.session"
    if os.path.exists(session_file):
        logger.info(f"📁 ✅ Найден файл сессии: {session_file}")
        file_size = os.path.getsize(session_file)
        logger.info(f"📁 Размер файла сессии: {file_size} байт")
        
        # Если файл сессии существует, пытаемся подключиться без авторизации
        try:
            client = Client(
                name=f"deposit_account_{account_key}",
                api_id=account_config['api_id'],
                api_hash=account_config['api_hash'],
                phone_number=account_config['phone']
            )
            
            logger.info("🔄 Попытка подключения с существующей сессией...")
            await client.start()
            
            me = await client.get_me()
            logger.info(f"✅ УСПЕШНО! Подключен как: @{me.username or me.first_name}")
            logger.info(f"👤 ID: {me.id}")
            logger.info(f"📞 Номер: {me.phone_number}")
            logger.info(f"🌐 DC: {me.dc_id}")
            
            await client.stop()
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения с сессией: {e}")
            logger.info("🗑️ Удаляем поврежденную сессию...")
            try:
                os.remove(session_file)
                logger.info("✅ Файл сессии удален")
            except:
                pass
    else:
        logger.info(f"📁 ❌ Файл сессии НЕ найден")
    
    # Пытаемся создать новую сессию
    logger.info("🆕 Создание новой сессии...")
    
    try:
        client = Client(
            name=f"deposit_account_{account_key}",
            api_id=account_config['api_id'],
            api_hash=account_config['api_hash'],
            phone_number=account_config['phone']
        )
        
        logger.info("📞 Отправка запроса на код подтверждения...")
        
        # Пытаемся подключиться
        await client.connect()
        
        # Отправляем код
        sent_code = await client.send_code(account_config['phone'])
        
        logger.info("✅ Код отправлен!")
        logger.info(f"📧 Тип: {sent_code.type}")
        logger.info(f"🔢 Длина кода: {sent_code.code_length if hasattr(sent_code, 'code_length') else 'неизвестно'}")
        logger.info(f"⏰ Следующий тип через: {sent_code.next_type}")
        logger.info(f"⏱️ Таймаут: {sent_code.timeout} сек")
        
        # Даем пользователю возможность ввести код
        print(f"\n🔢 Введите код подтверждения для {account_config['phone']}: ", end="")
        code = input().strip()
        
        if code:
            try:
                await client.sign_in(account_config['phone'], sent_code.phone_code_hash, code)
                me = await client.get_me()
                logger.info(f"✅ АВТОРИЗАЦИЯ УСПЕШНА! @{me.username or me.first_name}")
                
                await client.disconnect()
                return True
                
            except PhoneCodeInvalid:
                logger.error("❌ Неверный код подтверждения")
            except PhoneCodeExpired:
                logger.error("❌ Код подтверждения истек")
            except Exception as e:
                logger.error(f"❌ Ошибка авторизации: {e}")
        else:
            logger.info("⏭️ Код не введен, пропускаем авторизацию")
            
        await client.disconnect()
        
    except FloodWait as e:
        logger.error(f"🚫 FLOOD WAIT: {e.value} секунд")
        logger.error(f"⏰ Заблокирован до: {datetime.now() + timedelta(seconds=e.value)}")
        return False
        
    except PhoneNumberInvalid:
        logger.error("❌ НЕВЕРНЫЙ НОМЕР ТЕЛЕФОНА")
        logger.error("💡 Проверьте формат: +7XXXXXXXXXX")
        return False
        
    except ApiIdInvalid:
        logger.error("❌ НЕВЕРНЫЙ API ID")
        logger.error("💡 Проверьте данные на https://my.telegram.org")
        return False
        
    except ApiHashInvalid:
        logger.error("❌ НЕВЕРНЫЙ API HASH")  
        logger.error("💡 Проверьте данные на https://my.telegram.org")
        return False
        
    except PhoneNumberBanned:
        logger.error("🚫 НОМЕР ЗАБЛОКИРОВАН В TELEGRAM")
        logger.error("💡 Этот номер больше нельзя использовать")
        return False
        
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        logger.error(f"🔍 Тип ошибки: {type(e).__name__}")
        return False
    
    return False

async def main():
    """Главная функция диагностики"""
    logger.info("🚀 Запуск диагностики SMS проблем...")
    logger.info(f"⏰ Время: {datetime.now()}")
    
    total_accounts = len(DEPOSIT_ACCOUNTS)
    active_accounts = sum(1 for config in DEPOSIT_ACCOUNTS.values() if config['is_active'])
    
    logger.info(f"📊 Всего аккаунтов: {total_accounts}")
    logger.info(f"📊 Активных аккаунтов: {active_accounts}")
    
    results = {}
    
    for account_key, account_config in DEPOSIT_ACCOUNTS.items():
        if not account_config['is_active']:
            logger.info(f"⏭️ Пропускаем неактивный аккаунт: {account_key}")
            continue
            
        success = await diagnose_account(account_key, account_config)
        results[account_key] = success
        
        # Пауза между аккаунтами
        await asyncio.sleep(2)
    
    # Итоговый отчет
    logger.info(f"\n{'='*50}")
    logger.info("📋 ИТОГОВЫЙ ОТЧЕТ")
    logger.info(f"{'='*50}")
    
    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful
    
    logger.info(f"✅ Успешно: {successful}")
    logger.info(f"❌ Неудачно: {failed}")
    
    for account_key, success in results.items():
        status = "✅" if success else "❌"
        logger.info(f"{status} {account_key}")
    
    if failed > 0:
        logger.warning("\n💡 РЕКОМЕНДАЦИИ:")
        logger.warning("1. Проверьте правильность API данных на https://my.telegram.org")
        logger.warning("2. Убедитесь что номера не заблокированы")
        logger.warning("3. Попробуйте использовать Telegram Desktop для получения кода")
        logger.warning("4. Проверьте интернет-соединение")
        logger.warning("5. Подождите некоторое время если есть FloodWait")

if __name__ == "__main__":
    asyncio.run(main()) 