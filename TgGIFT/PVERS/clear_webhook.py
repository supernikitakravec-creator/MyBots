#!/usr/bin/env python3
"""
Скрипт для очистки webhook Telegram бота
"""
import asyncio
import os
from telegram import Bot

async def clear_webhook():
    """Очистка webhook"""
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        print("❌ BOT_TOKEN не найден в переменных окружения")
        return
    
    try:
        bot = Bot(token=bot_token)
        
        # Получаем информацию о текущем webhook
        webhook_info = await bot.get_webhook_info()
        print(f"📊 Текущий webhook: {webhook_info.url}")
        print(f"📊 Pending updates: {webhook_info.pending_update_count}")
        
        # Удаляем webhook и очищаем pending updates
        result = await bot.delete_webhook(drop_pending_updates=True)
        
        if result:
            print("✅ Webhook успешно удален")
            print("✅ Pending updates очищены")
        else:
            print("❌ Ошибка удаления webhook")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(clear_webhook()) 
 
 
 