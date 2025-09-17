#!/usr/bin/env python3
"""
Скрипт мониторинга состояния и производительности TgGIFT Star Bot
"""

import psutil
import asyncio
import time
import os
from datetime import datetime
from database import DatabaseManager
from config import DATABASE_PATH, LOGGING_CONFIG

class SystemMonitor:
    """Мониторинг системы"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.process = psutil.Process()
        self.start_time = time.time()
    
    def get_memory_usage(self):
        """Получение использования памяти"""
        memory_info = self.process.memory_info()
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,  # Resident Set Size
            'vms_mb': memory_info.vms / 1024 / 1024,  # Virtual Memory Size
            'percent': self.process.memory_percent()
        }
    
    def get_cpu_usage(self):
        """Получение использования CPU"""
        return {
            'percent': self.process.cpu_percent(interval=1),
            'num_threads': self.process.num_threads()
        }
    
    def get_io_stats(self):
        """Получение статистики IO"""
        io = self.process.io_counters()
        return {
            'read_mb': io.read_bytes / 1024 / 1024,
            'write_mb': io.write_bytes / 1024 / 1024,
            'read_count': io.read_count,
            'write_count': io.write_count
        }
    
    def get_database_size(self):
        """Получение размера базы данных"""
        if os.path.exists(DATABASE_PATH):
            size_bytes = os.path.getsize(DATABASE_PATH)
            return size_bytes / 1024 / 1024  # MB
        return 0
    
    def get_log_file_size(self):
        """Получение размера лог-файла"""
        log_file = LOGGING_CONFIG['file']
        if os.path.exists(log_file):
            size_bytes = os.path.getsize(log_file)
            return size_bytes / 1024 / 1024  # MB
        return 0
    
    def get_uptime(self):
        """Получение времени работы"""
        uptime_seconds = time.time() - self.start_time
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        return f"{hours}h {minutes}m {seconds}s"
    
    async def check_database_health(self):
        """Проверка здоровья базы данных"""
        try:
            # Тестовый запрос
            stats = self.db.get_database_stats()
            
            # Проверяем время отклика
            start = time.time()
            self.db.get_balance(1)  # Тестовый запрос
            response_time = (time.time() - start) * 1000  # мс
            
            return {
                'status': 'healthy',
                'response_time_ms': round(response_time, 2),
                'stats': stats
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def check_memory_leaks(self):
        """Проверка на утечки памяти"""
        memory = self.get_memory_usage()
        warnings = []
        
        # Предупреждение при использовании > 500MB
        if memory['rss_mb'] > 500:
            warnings.append(f"Высокое использование памяти: {memory['rss_mb']:.1f} MB")
        
        # Предупреждение при > 80% памяти
        if memory['percent'] > 80:
            warnings.append(f"Критическое использование памяти: {memory['percent']:.1f}%")
        
        return warnings
    
    def check_performance_issues(self):
        """Проверка проблем производительности"""
        warnings = []
        
        # CPU
        cpu = self.get_cpu_usage()
        if cpu['percent'] > 80:
            warnings.append(f"Высокая загрузка CPU: {cpu['percent']:.1f}%")
        
        # Threads
        if cpu['num_threads'] > 50:
            warnings.append(f"Много потоков: {cpu['num_threads']}")
        
        # Database size
        db_size = self.get_database_size()
        if db_size > 100:  # MB
            warnings.append(f"Большой размер БД: {db_size:.1f} MB")
        
        # Log size
        log_size = self.get_log_file_size()
        if log_size > 50:  # MB
            warnings.append(f"Большой размер логов: {log_size:.1f} MB")
        
        return warnings
    
    async def generate_report(self):
        """Генерация отчета о состоянии системы"""
        print("=" * 70)
        print(f"📊 ОТЧЕТ О СОСТОЯНИИ СИСТЕМЫ - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Uptime
        print(f"⏱️  Время работы: {self.get_uptime()}")
        print()
        
        # Memory
        memory = self.get_memory_usage()
        print("💾 ПАМЯТЬ:")
        print(f"   RSS: {memory['rss_mb']:.1f} MB")
        print(f"   VMS: {memory['vms_mb']:.1f} MB")
        print(f"   Использование: {memory['percent']:.1f}%")
        print()
        
        # CPU
        cpu = self.get_cpu_usage()
        print("🖥️  ПРОЦЕССОР:")
        print(f"   Загрузка: {cpu['percent']:.1f}%")
        print(f"   Потоков: {cpu['num_threads']}")
        print()
        
        # IO
        io = self.get_io_stats()
        print("💿 ДИСКОВЫЕ ОПЕРАЦИИ:")
        print(f"   Прочитано: {io['read_mb']:.1f} MB ({io['read_count']} операций)")
        print(f"   Записано: {io['write_mb']:.1f} MB ({io['write_count']} операций)")
        print()
        
        # Database
        db_health = await self.check_database_health()
        print("🗄️  БАЗА ДАННЫХ:")
        print(f"   Статус: {db_health['status']}")
        if db_health['status'] == 'healthy':
            print(f"   Время отклика: {db_health['response_time_ms']} мс")
            print(f"   Размер: {self.get_database_size():.1f} MB")
            stats = db_health['stats']
            print(f"   Пользователей: {stats.get('total_users', 0)}")
            print(f"   Активных подписок: {stats.get('active_subscriptions', 0)}")
            print(f"   В очереди: {stats.get('queue_size', 0)}")
            print(f"   Подарков: {stats.get('available_gifts', 0)}")
        else:
            print(f"   Ошибка: {db_health.get('error', 'Unknown')}")
        print()
        
        # Files
        print("📁 ФАЙЛЫ:")
        print(f"   Размер логов: {self.get_log_file_size():.1f} MB")
        print()
        
        # Warnings
        memory_warnings = self.check_memory_leaks()
        perf_warnings = self.check_performance_issues()
        all_warnings = memory_warnings + perf_warnings
        
        if all_warnings:
            print("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
            for warning in all_warnings:
                print(f"   • {warning}")
        else:
            print("✅ Проблем не обнаружено")
        
        print("=" * 70)
    
    async def continuous_monitoring(self, interval: int = 300):
        """Непрерывный мониторинг с интервалом (по умолчанию 5 минут)"""
        print(f"🔍 Запуск непрерывного мониторинга (интервал: {interval} сек)")
        print("Нажмите Ctrl+C для остановки")
        print()
        
        try:
            while True:
                await self.generate_report()
                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            print("\n⏹️  Мониторинг остановлен")

async def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Мониторинг TgGIFT Star Bot')
    parser.add_argument('--continuous', '-c', action='store_true', 
                       help='Непрерывный мониторинг')
    parser.add_argument('--interval', '-i', type=int, default=300,
                       help='Интервал мониторинга в секундах (по умолчанию: 300)')
    
    args = parser.parse_args()
    
    monitor = SystemMonitor()
    
    if args.continuous:
        await monitor.continuous_monitoring(args.interval)
    else:
        await monitor.generate_report()

if __name__ == "__main__":
    asyncio.run(main()) 