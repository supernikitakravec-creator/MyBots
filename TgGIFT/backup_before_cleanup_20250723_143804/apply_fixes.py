#!/usr/bin/env python3
"""
Скрипт для применения всех исправлений TgGIFT Star Bot
"""

import os
import shutil
import sys
from datetime import datetime

def create_backup(file_path):
    """Создание резервной копии файла"""
    if os.path.exists(file_path):
        backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(file_path, backup_path)
        print(f"✅ Создана резервная копия: {backup_path}")
        return True
    return False

def apply_fixes():
    """Применение всех исправлений"""
    print("🔧 Применение исправлений TgGIFT Star Bot...")
    
    # Список файлов для замены
    fixes = [
        {
            'original': 'account_manager.py',
            'fixed': 'account_manager_fixed.py',
            'description': 'Исправление FloodWait проблемы'
        },
        {
            'original': 'database.py',
            'fixed': 'database_optimized.py',
            'description': 'Оптимизация базы данных'
        }
    ]
    
    applied_fixes = 0
    
    for fix in fixes:
        original_file = fix['original']
        fixed_file = fix['fixed']
        description = fix['description']
        
        print(f"\n📝 {description}")
        print(f"   Файл: {original_file} -> {fixed_file}")
        
        # Проверяем существование исправленного файла
        if not os.path.exists(fixed_file):
            print(f"❌ Исправленный файл не найден: {fixed_file}")
            continue
        
        # Создаем резервную копию оригинального файла
        if create_backup(original_file):
            # Заменяем файл
            try:
                shutil.copy2(fixed_file, original_file)
                print(f"✅ Файл успешно заменен: {original_file}")
                applied_fixes += 1
            except Exception as e:
                print(f"❌ Ошибка замены файла {original_file}: {e}")
        else:
            print(f"⚠️  Оригинальный файл не найден: {original_file}")
    
    print(f"\n📊 Результат: {applied_fixes}/{len(fixes)} исправлений применено")
    
    if applied_fixes == len(fixes):
        print("✅ Все исправления применены успешно!")
        return True
    else:
        print("⚠️  Не все исправления были применены")
        return False

def verify_fixes():
    """Проверка применения исправлений"""
    print("\n🔍 Проверка применения исправлений...")
    
    # Проверяем ключевые изменения
    checks = [
        {
            'file': 'account_manager.py',
            'check': 'max_retries = 1',
            'description': 'Исправление повторных попыток'
        },
        {
            'file': 'database.py',
            'check': 'connection_pool',
            'description': 'Пул соединений'
        }
    ]
    
    all_good = True
    
    for check in checks:
        file_path = check['file']
        search_text = check['check']
        description = check['description']
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if search_text in content:
                        print(f"✅ {description}: OK")
                    else:
                        print(f"❌ {description}: НЕ НАЙДЕНО")
                        all_good = False
            except Exception as e:
                print(f"❌ Ошибка чтения {file_path}: {e}")
                all_good = False
        else:
            print(f"❌ Файл не найден: {file_path}")
            all_good = False
    
    return all_good

def main():
    """Главная функция"""
    print("🚀 TgGIFT Star Bot - Применение исправлений")
    print("=" * 50)
    
    # Проверяем, что мы в правильной директории
    if not os.path.exists('start_bot.py'):
        print("❌ Скрипт должен запускаться из корневой директории проекта")
        sys.exit(1)
    
    # Применяем исправления
    if apply_fixes():
        # Проверяем результат
        if verify_fixes():
            print("\n🎉 Все исправления применены и проверены!")
            print("\n📋 Следующие шаги:")
            print("1. Дождитесь снятия FloodWait (после 16:55)")
            print("2. Запустите: py start_bot.py")
            print("3. Проверьте логи на наличие ошибок")
            print("4. Протестируйте основные функции")
        else:
            print("\n⚠️  Исправления применены, но есть проблемы с проверкой")
    else:
        print("\n❌ Не удалось применить все исправления")
        sys.exit(1)

if __name__ == "__main__":
    main() 