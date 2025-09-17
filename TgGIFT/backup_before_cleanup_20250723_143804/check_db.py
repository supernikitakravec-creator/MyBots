#!/usr/bin/env python3
"""
Быстрая проверка состояния базы данных
"""
import sqlite3
import os

def check_database():
    print("🔍 Проверка базы данных...")
    
    # Проверяем файл базы данных
    if not os.path.exists('gift_bot.db'):
        print("❌ Файл gift_bot.db не найден!")
        return False
    
    try:
        conn = sqlite3.connect('gift_bot.db')
        print("✅ База данных доступна")
        
        # Получаем список таблиц
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"📊 Найдено таблиц: {len(tables)}")
        
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  - {table}: {count} записей")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return False

if __name__ == "__main__":
    check_database() 