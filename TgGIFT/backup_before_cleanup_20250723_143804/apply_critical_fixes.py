#!/usr/bin/env python3
"""
Скрипт для применения критических исправлений к TgGIFT Star Bot
"""

import os
import shutil
import sys
from datetime import datetime

def backup_files():
    """Создание резервных копий файлов"""
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        'main_bot.py',
        'database.py',
        'account_manager.py'
    ]
    
    for file in files_to_backup:
        if os.path.exists(file):
            shutil.copy2(file, os.path.join(backup_dir, file))
            print(f"✅ Создана резервная копия: {file}")
    
    print(f"📁 Резервные копии сохранены в: {backup_dir}")
    return backup_dir

def apply_fixes():
    """Применение исправлений"""
    fixes = [
        ('main_bot_fixed.py', 'main_bot.py'),
        ('database_optimized.py', 'database.py'),
        ('account_manager_fixed.py', 'account_manager.py')
    ]
    
    for source, target in fixes:
        if os.path.exists(source):
            shutil.copy2(source, target)
            print(f"✅ Применено исправление: {source} -> {target}")
        else:
            print(f"❌ Файл исправления не найден: {source}")

def verify_fixes():
    """Проверка применения исправлений"""
    print("\n🔍 Проверка исправлений...")
    
    # Проверяем основные файлы
    required_files = ['main_bot.py', 'database.py', 'account_manager.py']
    
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ Файл существует: {file}")
        else:
            print(f"❌ Файл отсутствует: {file}")
    
    # Проверяем размеры файлов
    file_sizes = {
        'main_bot.py': 25000,  # Примерный размер в байтах
        'database.py': 30000,
        'account_manager.py': 15000
    }
    
    for file, expected_size in file_sizes.items():
        if os.path.exists(file):
            actual_size = os.path.getsize(file)
            if actual_size > expected_size * 0.8:  # 80% от ожидаемого размера
                print(f"✅ Размер файла корректный: {file} ({actual_size} байт)")
            else:
                print(f"⚠️ Размер файла подозрительно мал: {file} ({actual_size} байт)")

def main():
    """Основная функция"""
    print("🚨 ПРИМЕНЕНИЕ КРИТИЧЕСКИХ ИСПРАВЛЕНИЙ")
    print("=" * 50)
    
    # Проверяем наличие исправленных файлов
    fixed_files = ['main_bot_fixed.py', 'database_optimized.py', 'account_manager_fixed.py']
    missing_files = [f for f in fixed_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"❌ Отсутствуют файлы исправлений: {missing_files}")
        print("Пожалуйста, убедитесь, что все исправленные файлы созданы.")
        return False
    
    # Создаем резервные копии
    backup_dir = backup_files()
    
    # Применяем исправления
    print("\n🔧 Применение исправлений...")
    apply_fixes()
    
    # Проверяем результат
    verify_fixes()
    
    print("\n✅ ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ УСПЕШНО!")
    print(f"📁 Резервные копии: {backup_dir}")
    print("\n🚀 Следующие шаги:")
    print("1. Запустите тесты: python test_key_functions.py")
    print("2. Проверьте graceful shutdown: Ctrl+C")
    print("3. Запустите бота: python start_bot.py")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1) 