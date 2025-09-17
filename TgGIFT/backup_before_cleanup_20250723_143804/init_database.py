#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import logging
from datetime import datetime
from database import DatabaseManager

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Инициализация базы данных"""
    logger.info("🚀 Начинаем инициализацию базы данных...")
    
    try:
        # Создаем менеджер базы данных
        db_manager = DatabaseManager()
        
        # Инициализируем базу данных
        logger.info("📊 Создание таблиц...")
        db_manager.init_database()
        
        # Проверяем созданные таблицы
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            logger.info(f"✅ Создано таблиц: {len(tables)}")
            for table in tables:
                logger.info(f"  📋 {table[0]}")
        
        # Создаем тестового пользователя
        logger.info("👤 Создание тестового пользователя...")
        test_user_id = 123456789
        success = db_manager.register_user(test_user_id, "testuser")
        if success:
            logger.info(f"✅ Тестовый пользователь {test_user_id} создан")
            
            # Добавляем тестовые баллы
            success = db_manager.add_points(test_user_id, 1000, "test", "Тестовые баллы")
            if success:
                balance = db_manager.get_points_balance(test_user_id)
                logger.info(f"💰 Баланс тестового пользователя: {balance} баллов")
        
        logger.info("🎉 База данных успешно инициализирована!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        raise

if __name__ == "__main__":
    main() 