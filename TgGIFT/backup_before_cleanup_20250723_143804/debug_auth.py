#!/usr/bin/env python3
"""
Детальная отладка авторизации Pyrogram
"""

import asyncio
import logging
import sys
from pathlib import Path
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded, FloodWait, PhoneNumberInvalid,
    PhoneCodeInvalid, PhoneCodeExpired, PhoneNumberUnoccupied,
    ApiIdInvalid, AccessTokenInvalid, AuthKeyUnregistered
)

# Настройка детального логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('pyrogram_auth_debug.log')
    ]
)
logger = logging.getLogger(__name__)

async def test_basic_connection():
    """Базовая проверка подключения к Telegram"""
    print("🔍 Тест 1: Базовое подключение к Telegram API")
    print("-" * 50)
    
    try:
        from config import API_ID, API_HASH, PHONE_NUMBER
        
        print(f"📱 Номер телефона: {PHONE_NUMBER}")
        print(f"🔑 API_ID: {API_ID}")
        print(f"🔑 API_HASH: {API_HASH[:10]}...")
        
        # Проверяем формат номера
        if not PHONE_NUMBER.startswith('+'):
            print("⚠️ Номер телефона должен начинаться с '+'")
            print("   Пример: +79123456789")
            return False
            
        # Проверяем длину номера
        if len(PHONE_NUMBER) < 10:
            print("⚠️ Номер телефона слишком короткий")
            return False
            
        print("✅ Формат данных корректный")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

async def test_pyrogram_auth():
    """Детальная проверка авторизации через Pyrogram"""
    print("\n🔍 Тест 2: Детальная авторизация Pyrogram")
    print("-" * 50)
    
    try:
        from config import API_ID, API_HASH, PHONE_NUMBER
        
        # Удаляем старую сессию если есть
        session_file = Path("test_auth_session.session")
        if session_file.exists():
            session_file.unlink()
            print("🗑️ Старая тестовая сессия удалена")
        
        # Создаем клиент с детальным логированием
        app = Client(
            "test_auth_session",
            api_id=API_ID,
            api_hash=API_HASH,
            phone_number=PHONE_NUMBER,
            workdir=".",
            test_mode=False  # Важно: используем production сервера
        )
        
        print("📡 Подключаемся к Telegram...")
        
        @app.on_message()
        async def message_handler(client, message):
            """Обработчик для получения кода из сообщений"""
            print(f"📨 Получено сообщение: {message.text[:50]}...")
        
        # Пробуем подключиться
        try:
            await app.start()
            print("✅ Успешное подключение!")
            
            # Получаем информацию об аккаунте
            me = await app.get_me()
            print(f"👤 Аккаунт: {me.first_name} (@{me.username})")
            print(f"🆔 ID: {me.id}")
            
            await app.stop()
            
        except SessionPasswordNeeded:
            print("🔐 Требуется двухфакторная аутентификация (2FA)")
            print("   Добавьте пароль в настройки или отключите 2FA")
            
        except PhoneNumberInvalid:
            print("❌ Неверный формат номера телефона")
            print("   Проверьте что номер начинается с '+' и содержит код страны")
            
        except PhoneNumberUnoccupied:
            print("❌ Номер телефона не зарегистрирован в Telegram")
            
        except ApiIdInvalid:
            print("❌ Неверный API_ID или API_HASH")
            print("   Проверьте данные на https://my.telegram.org")
            
        except FloodWait as e:
            print(f"⏳ Слишком много попыток. Подождите {e.value} секунд")
            
        except Exception as e:
            print(f"❌ Ошибка авторизации: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

async def test_alternative_auth():
    """Альтернативный метод авторизации"""
    print("\n🔍 Тест 3: Альтернативная авторизация")
    print("-" * 50)
    
    try:
        from config import API_ID, API_HASH, PHONE_NUMBER
        
        # Используем другие параметры
        app = Client(
            "alternative_session",
            api_id=int(API_ID),
            api_hash=API_HASH,
            phone_number=PHONE_NUMBER,
            force_sms=True,  # Принудительно запрашиваем SMS
            hide_password=False
        )
        
        print("📡 Пробуем альтернативный метод...")
        
        # Ручная авторизация
        await app.connect()
        
        # Отправляем код
        sent_code = await app.send_code(PHONE_NUMBER)
        print(f"📤 Код отправлен. Тип: {sent_code.type}")
        print(f"📱 Хеш: {sent_code.phone_code_hash[:10]}...")
        
        # Ждем ввод кода
        code = input("Введите код из SMS: ")
        
        # Авторизуемся
        try:
            await app.sign_in(PHONE_NUMBER, sent_code.phone_code_hash, code)
            print("✅ Авторизация успешна!")
        except Exception as e:
            print(f"❌ Ошибка авторизации: {e}")
            
        await app.disconnect()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

async def check_telegram_servers():
    """Проверка доступности серверов Telegram"""
    print("\n🔍 Тест 4: Проверка серверов Telegram")
    print("-" * 50)
    
    try:
        import socket
        
        # Список DC серверов Telegram
        servers = [
            ("149.154.175.50", 443),   # DC1
            ("149.154.167.51", 443),   # DC2
            ("149.154.175.100", 443),  # DC3
            ("149.154.167.91", 443),   # DC4
            ("91.108.56.130", 443),    # DC5
        ]
        
        for ip, port in servers:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((ip, port))
                sock.close()
                
                if result == 0:
                    print(f"✅ DC {ip}:{port} - доступен")
                else:
                    print(f"❌ DC {ip}:{port} - недоступен")
                    
            except Exception as e:
                print(f"❌ DC {ip}:{port} - ошибка: {e}")
                
    except Exception as e:
        print(f"❌ Ошибка проверки серверов: {e}")

def check_possible_issues():
    """Проверка возможных проблем"""
    print("\n📋 Возможные причины проблемы с SMS:")
    print("-" * 50)
    
    print("1. 🚫 Telegram временно заблокировал отправку SMS")
    print("   - Слишком много попыток за короткое время")
    print("   - Решение: подождать 1-24 часа")
    print()
    print("2. 📱 Проблемы с номером телефона")
    print("   - Номер заблокирован для SMS")
    print("   - Неверный формат номера")
    print("   - Номер не зарегистрирован в Telegram")
    print()
    print("3. 🔑 Проблемы с API credentials")
    print("   - Неверные API_ID или API_HASH")
    print("   - API ключи заблокированы")
    print("   - Решение: создать новое приложение на my.telegram.org")
    print()
    print("4. 🔐 Двухфакторная аутентификация")
    print("   - На аккаунте включена 2FA")
    print("   - Решение: временно отключить или добавить пароль")
    print()
    print("5. 🌐 Сетевые проблемы")
    print("   - Блокировка Telegram в регионе")
    print("   - Проблемы с прокси/VPN")
    print()
    print("6. 📲 Альтернативные способы получения кода")
    print("   - Telegram Desktop")
    print("   - Другое устройство с этим номером")
    print("   - Web Telegram")

async def main():
    """Главная функция"""
    print("🔧 ДЕТАЛЬНАЯ ДИАГНОСТИКА АВТОРИЗАЦИИ PYROGRAM")
    print("=" * 60)
    
    # Запускаем тесты
    if await test_basic_connection():
        await test_pyrogram_auth()
        # await test_alternative_auth()  # Раскомментируйте для альтернативного метода
        await check_telegram_servers()
    
    check_possible_issues()
    
    print("\n" + "=" * 60)
    print("📋 РЕКОМЕНДАЦИИ:")
    print("1. Проверьте логи в файле: pyrogram_auth_debug.log")
    print("2. Попробуйте через 1-2 часа если SMS не приходит")
    print("3. Используйте VPN если Telegram заблокирован")
    print("4. Проверьте код в Telegram Desktop")

if __name__ == "__main__":
    asyncio.run(main()) 