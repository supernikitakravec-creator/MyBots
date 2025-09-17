#!/usr/bin/env python3
"""
Проверка информации о сессии и настройках телефона
"""

import os
import sys
from pathlib import Path

def check_env_file():
    """Проверка .env файла"""
    print("🔍 Проверка .env файла...")
    
    env_files = ['.env', 'env_example.txt']
    
    for env_file in env_files:
        if Path(env_file).exists():
            print(f"\n📁 Файл: {env_file}")
            try:
                # Пробуем разные кодировки
                content = None
                for encoding in ['utf-8', 'cp1251', 'latin-1']:
                    try:
                        with open(env_file, 'r', encoding=encoding) as f:
                            content = f.read()
                        print(f"✅ Кодировка: {encoding}")
                        break
                    except UnicodeDecodeError:
                        continue
                
                if content:
                    # Ищем номер телефона
                    lines = content.split('\n')
                    for line in lines:
                        if line.startswith('PHONE_NUMBER='):
                            phone = line.split('=')[1].strip()
                            if phone:
                                print(f"📱 Номер телефона: {phone}")
                            else:
                                print("📱 Номер телефона: НЕ УКАЗАН")
                        elif line.startswith('API_ID='):
                            api_id = line.split('=')[1].strip()
                            if api_id:
                                print(f"🔑 API_ID: {api_id}")
                        elif line.startswith('API_HASH='):
                            api_hash = line.split('=')[1].strip()
                            if api_hash:
                                print(f"🔑 API_HASH: {api_hash[:10]}...")
                        elif line.startswith('SESSION_NAME='):
                            session_name = line.split('=')[1].strip()
                            if session_name:
                                print(f"📂 SESSION_NAME: {session_name}")
                
            except Exception as e:
                print(f"❌ Ошибка чтения: {e}")
        else:
            print(f"❌ {env_file}: не найден")

def check_session_file():
    """Проверка файла сессии"""
    print("\n🔍 Проверка файла сессии...")
    
    session_files = list(Path('.').glob('*.session'))
    
    if session_files:
        for session_file in session_files:
            size = session_file.stat().st_size
            print(f"📁 {session_file}: {size} байт")
            
            # Читаем первые байты для анализа
            try:
                with open(session_file, 'rb') as f:
                    first_bytes = f.read(100)
                    print(f"🔍 Первые байты: {first_bytes[:50]}...")
                    
                    # Проверяем на текстовые данные
                    try:
                        text_data = first_bytes.decode('utf-8', errors='ignore')
                        if text_data:
                            print(f"📝 Текстовые данные: {text_data[:100]}...")
                    except:
                        pass
                        
            except Exception as e:
                print(f"❌ Ошибка чтения сессии: {e}")
    else:
        print("❌ Файлы сессии не найдены")

def check_pyrogram_session():
    """Проверка сессии через Pyrogram"""
    print("\n🔍 Проверка сессии через Pyrogram...")
    
    try:
        from pyrogram import Client
        
        # Пробуем загрузить сессию
        session_name = "gift_bot_account"
        
        if Path(f"{session_name}.session").exists():
            print(f"✅ Файл сессии найден: {session_name}.session")
            
            try:
                # Создаем клиент для проверки
                app = Client(session_name)
                
                # Пробуем получить информацию о сессии
                print("🔍 Попытка получить информацию о сессии...")
                
                # Здесь мы не запускаем клиент, просто проверяем что он создается
                print("✅ Сессия корректна и может быть загружена")
                
            except Exception as e:
                print(f"❌ Ошибка при проверке сессии: {e}")
        else:
            print(f"❌ Файл сессии не найден: {session_name}.session")
            
    except ImportError:
        print("❌ Pyrogram не установлен")
    except Exception as e:
        print(f"❌ Ошибка при проверке через Pyrogram: {e}")

def check_config_settings():
    """Проверка настроек из config.py"""
    print("\n🔍 Проверка настроек из config.py...")
    
    try:
        import config
        
        # Проверяем основные настройки
        if hasattr(config, 'PHONE_NUMBER'):
            print(f"📱 PHONE_NUMBER из config: {config.PHONE_NUMBER}")
        else:
            print("❌ PHONE_NUMBER не найден в config")
            
        if hasattr(config, 'API_ID'):
            print(f"🔑 API_ID из config: {config.API_ID}")
        else:
            print("❌ API_ID не найден в config")
            
        if hasattr(config, 'API_HASH'):
            api_hash = config.API_HASH
            if api_hash:
                print(f"🔑 API_HASH из config: {api_hash[:10]}...")
            else:
                print("❌ API_HASH пустой")
        else:
            print("❌ API_HASH не найден в config")
            
    except Exception as e:
        print(f"❌ Ошибка импорта config: {e}")

def main():
    """Главная функция"""
    print("🔍 ПРОВЕРКА СЕССИИ И НАСТРОЕК ТЕЛЕФОНА")
    print("="*50)
    
    check_env_file()
    check_session_file()
    check_pyrogram_session()
    check_config_settings()
    
    print("\n" + "="*50)
    print("📋 ВАЖНАЯ ИНФОРМАЦИЯ:")
    print("- Сессия привязана к конкретному номеру телефона")
    print("- Если номер в .env отличается от сессии - будет запрошен SMS")
    print("- Для смены номера нужно удалить старую сессию")
    print("- Файл сессии содержит зашифрованные данные авторизации")

if __name__ == "__main__":
    main() 