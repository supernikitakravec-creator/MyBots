#!/usr/bin/env python3
"""
Скрипт с низкоуровневыми методами для принудительной отправки кода через приложение
"""

import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import *
from pyrogram.raw import functions, types
from config import DEPOSIT_ACCOUNTS
import os
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app_lowlevel.log')
    ]
)
logger = logging.getLogger(__name__)

async def send_app_code_lowlevel(account_key: str):
    """Отправка кода через приложение с низкоуровневыми методами"""
    
    if account_key not in DEPOSIT_ACCOUNTS:
        print(f"❌ Аккаунт {account_key} не найден")
        return False
    
    account_config = DEPOSIT_ACCOUNTS[account_key]
    
    print(f"📱 Низкоуровневый запрос APP кода для: {account_config['phone']}")
    print(f"🔧 API ID: {account_config['api_id']}")
    
    try:
        client = Client(
            name=f"app_lowlevel_{account_key}",
            api_id=account_config['api_id'],
            api_hash=account_config['api_hash'],
            phone_number=account_config['phone']
        )
        
        print("🔗 Подключение к Telegram...")
        await client.connect()
        
        try:
            phone = account_config['phone']
            
            # Метод 1: Стандартный запрос
            print("📞 Метод 1: Стандартный запрос кода...")
            try:
                sent_code = await client.send_code(phone)
                print(f"✅ Стандартный код отправлен: {sent_code.type}")
                
                # Проверяем детали
                print(f"🔍 Детали отправки:")
                print(f"   - Тип: {sent_code.type}")
                print(f"   - Следующий тип: {sent_code.next_type}")
                print(f"   - Таймаут: {sent_code.timeout}")
                print(f"   - Hash: {sent_code.phone_code_hash[:10]}...")
                
            except Exception as e:
                print(f"❌ Стандартный метод не работает: {e}")
                sent_code = None
            
            # Метод 2: Низкоуровневый запрос через raw API
            if not sent_code:
                print("📞 Метод 2: Низкоуровневый raw API запрос...")
                try:
                    # Используем raw функцию auth.sendCode
                    result = await client.invoke(
                        functions.auth.SendCode(
                            phone_number=phone,
                            api_id=account_config['api_id'],
                            api_hash=account_config['api_hash'],
                            settings=types.CodeSettings(
                                allow_flashcall=False,
                                current_number=False,
                                allow_app_hash=True,
                                allow_missed_call=False,
                                allow_firebase=False
                            )
                        )
                    )
                    
                    print(f"✅ Raw API код отправлен!")
                    print(f"🔍 Raw результат: {result}")
                    
                    # Создаем объект sent_code из raw результата
                    class RawSentCode:
                        def __init__(self, raw_result):
                            self.phone_code_hash = raw_result.phone_code_hash
                            self.type = raw_result.type
                            self.next_type = getattr(raw_result, 'next_type', None)
                            self.timeout = getattr(raw_result, 'timeout', None)
                    
                    sent_code = RawSentCode(result)
                    
                except Exception as e:
                    print(f"❌ Raw API метод не работает: {e}")
            
            # Метод 3: Принудительный APP запрос
            if not sent_code:
                print("📞 Метод 3: Принудительный APP запрос...")
                try:
                    result = await client.invoke(
                        functions.auth.SendCode(
                            phone_number=phone,
                            api_id=account_config['api_id'],
                            api_hash=account_config['api_hash'],
                            settings=types.CodeSettings(
                                allow_flashcall=False,
                                current_number=True,  # Принудительно через текущий номер
                                allow_app_hash=True,  # Разрешаем APP
                                allow_missed_call=False,
                                allow_firebase=True   # Включаем Firebase для push
                            )
                        )
                    )
                    
                    print(f"✅ Принудительный APP код отправлен!")
                    sent_code = RawSentCode(result)
                    
                except Exception as e:
                    print(f"❌ Принудительный APP не работает: {e}")
            
            if sent_code:
                print("\n" + "="*60)
                print(f"📲 КОД ОТПРАВЛЕН В TELEGRAM ПРИЛОЖЕНИЕ!")
                print(f"📱 Номер: {phone}")
                print(f"🔍 Тип отправки: {sent_code.type}")
                print("="*60)
                
                print("\n💡 ИНСТРУКЦИЯ ПО ПОИСКУ КОДА:")
                print("1. Откройте Telegram на номере", phone)
                print("2. Проверьте 'Сохраненные сообщения' (Saved Messages)")
                print("3. Проверьте чат 'Telegram' или системные уведомления")
                print("4. Посмотрите на главный экран - может быть всплывающее окно")
                print("5. Проверьте уведомления телефона")
                print("6. Попробуйте перезапустить Telegram")
                
                # Даем больше времени на поиск
                print("\n⏰ У вас есть время найти код...")
                print("💡 Код обычно состоит из 5-6 цифр")
                
                code = input(f"\n🔢 Введите код из Telegram приложения для {phone}: ").strip()
                
                if code:
                    try:
                        print("🔐 Авторизация...")
                        
                        if hasattr(sent_code, 'phone_code_hash'):
                            # Стандартная авторизация
                            await client.sign_in(phone, sent_code.phone_code_hash, code)
                        else:
                            # Raw авторизация
                            await client.invoke(
                                functions.auth.SignIn(
                                    phone_number=phone,
                                    phone_code_hash=sent_code.phone_code_hash,
                                    phone_code=code
                                )
                            )
                        
                        me = await client.get_me()
                        
                        print(f"\n🎉 УСПЕШНАЯ АВТОРИЗАЦИЯ!")
                        print(f"👤 Пользователь: @{me.username or me.first_name}")
                        print(f"🔢 ID: {me.id}")
                        print(f"📞 Номер: {me.phone_number}")
                        
                        await client.disconnect()
                        
                        # Переименовываем сессию
                        temp_session = f"app_lowlevel_{account_key}.session"
                        main_session = f"deposit_account_{account_key}.session"
                        
                        if os.path.exists(temp_session):
                            if os.path.exists(main_session):
                                os.remove(main_session)
                            os.rename(temp_session, main_session)
                            print(f"✅ Сессия сохранена как {main_session}")
                        
                        return True
                        
                    except PhoneCodeInvalid:
                        print("❌ Неверный код подтверждения!")
                    except PhoneCodeExpired:
                        print("⏰ Код подтверждения истек!")
                    except Exception as e:
                        print(f"❌ Ошибка авторизации: {e}")
                        logger.error(f"Auth error: {e}")
                else:
                    print("❌ Код не введен")
            else:
                print("❌ Не удалось отправить код ни одним методом!")
                
        except FloodWait as e:
            print(f"\n🚫 FLOOD WAIT ОБНАРУЖЕН!")
            print(f"⏰ Заблокирован на {e.value} секунд")
            print(f"🕐 Попробуйте после: {datetime.now() + timedelta(seconds=e.value)}")
            
        except Exception as e:
            print(f"❌ Общая ошибка отправки: {e}")
            logger.error(f"General error: {e}")
            
        await client.disconnect()
        
        # Удаляем временную сессию при неудаче
        temp_session = f"app_lowlevel_{account_key}.session"
        if os.path.exists(temp_session):
            os.remove(temp_session)
            
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logger.error(f"Critical error: {e}")
    
    return False

async def main():
    print("📲 Низкоуровневый скрипт отправки APP кода")
    print("="*50)
    
    print("Доступные аккаунты:")
    for key, config in DEPOSIT_ACCOUNTS.items():
        print(f"  {key}: {config['phone']}")
    
    account_key = input("\nВведите ключ аккаунта: ").strip()
    
    if not account_key or account_key not in DEPOSIT_ACCOUNTS:
        print("❌ Неверный ключ аккаунта!")
        return
    
    success = await send_app_code_lowlevel(account_key)
    
    if success:
        print("\n🎉 Аккаунт успешно подключен!")
        print("💡 Теперь можете запустить основного бота")
    else:
        print("\n❌ Не удалось подключить аккаунт")
        print("💡 Проверьте логи в app_lowlevel.log")

if __name__ == "__main__":
    asyncio.run(main()) 