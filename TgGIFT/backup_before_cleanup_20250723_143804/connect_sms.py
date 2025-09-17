#!/usr/bin/env python3
"""
Скрипт для принудительного запроса SMS кода
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
        logging.FileHandler('sms_connect.log')
    ]
)
logger = logging.getLogger(__name__)

async def request_sms_code(account_key: str):
    """Принудительный запрос SMS кода"""
    
    if account_key not in DEPOSIT_ACCOUNTS:
        print(f"❌ Аккаунт {account_key} не найден")
        return False
    
    account_config = DEPOSIT_ACCOUNTS[account_key]
    
    print(f"📱 Запрос SMS кода для: {account_config['phone']}")
    print(f"🔧 API ID: {account_config['api_id']}")
    
    try:
        client = Client(
            name=f"sms_temp_{account_key}",
            api_id=account_config['api_id'],
            api_hash=account_config['api_hash'],
            phone_number=account_config['phone']
        )
        
        print("🔗 Подключение к Telegram...")
        await client.connect()
        
        try:
            # Отправляем первый запрос (обычно APP)
            print("📞 Отправка первого запроса...")
            sent_code = await client.send_code(account_config['phone'])
            
            print(f"✅ Первый код отправлен: {sent_code.type}")
            
            # Ждем немного
            print("⏳ Ожидание 30 секунд перед запросом SMS...")
            await asyncio.sleep(30)
            
            # Запрашиваем следующий тип (должен быть SMS)
            print("📱 Запрос SMS кода...")
            
            try:
                # Пытаемся запросить следующий тип кода
                await client.resend_code(account_config['phone'], sent_code.phone_code_hash)
                print("✅ SMS код запрошен!")
                print("💡 Проверьте входящие SMS сообщения")
                
            except Exception as e:
                print(f"⚠️ Не удалось запросить SMS: {e}")
                print("💡 Попробуйте подождать еще и проверить Telegram приложение")
            
            # Даем время на получение SMS
            print("\n" + "="*50)
            print("⏰ Ожидание SMS кода...")
            print("💡 Проверьте входящие сообщения на номере")
            print("="*50)
            
            # Ждем ввода кода
            code = input(f"\n🔢 Введите код из SMS для {account_config['phone']}: ").strip()
            
            if code:
                try:
                    await client.sign_in(account_config['phone'], sent_code.phone_code_hash, code)
                    me = await client.get_me()
                    
                    print(f"\n🎉 УСПЕХ! Подключен как @{me.username or me.first_name}")
                    
                    await client.disconnect()
                    
                    # Переименовываем сессию для использования в основном боте
                    temp_session = f"sms_temp_{account_key}.session"
                    main_session = f"deposit_account_{account_key}.session"
                    
                    if os.path.exists(temp_session):
                        if os.path.exists(main_session):
                            os.remove(main_session)
                        os.rename(temp_session, main_session)
                        print(f"✅ Сессия сохранена как {main_session}")
                    
                    return True
                    
                except PhoneCodeInvalid:
                    print("❌ Неверный код!")
                except PhoneCodeExpired:
                    print("⏰ Код истек!")
                except Exception as e:
                    print(f"❌ Ошибка авторизации: {e}")
            else:
                print("❌ Код не введен")
                
        except FloodWait as e:
            print(f"\n🚫 FLOOD WAIT!")
            print(f"⏰ Заблокирован на {e.value} секунд")
            print(f"🕐 Попробуйте после: {datetime.now() + timedelta(seconds=e.value)}")
            
        except Exception as e:
            print(f"❌ Ошибка отправки кода: {e}")
            
        await client.disconnect()
        
        # Удаляем временную сессию если не удалось
        temp_session = f"sms_temp_{account_key}.session"
        if os.path.exists(temp_session):
            os.remove(temp_session)
            
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
    
    return False

async def main():
    print("📱 Скрипт запроса SMS кода")
    print("="*40)
    
    print("Доступные аккаунты:")
    for key, config in DEPOSIT_ACCOUNTS.items():
        print(f"  {key}: {config['phone']}")
    
    account_key = input("\nВведите ключ аккаунта: ").strip()
    
    if not account_key or account_key not in DEPOSIT_ACCOUNTS:
        print("❌ Неверный ключ аккаунта!")
        return
    
    success = await request_sms_code(account_key)
    
    if success:
        print("\n🎉 Аккаунт успешно подключен!")
        print("💡 Теперь можете запустить основного бота")
    else:
        print("\n❌ Не удалось подключить аккаунт")

if __name__ == "__main__":
    asyncio.run(main()) 