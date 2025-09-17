#!/usr/bin/env python3
"""
Скрипт очистки директории для продакшена TgGIFT Bot
"""
import os
import shutil
import sys
from datetime import datetime

# ФАЙЛЫ И ПАПКИ КОТОРЫЕ НУЖНЫ ДЛЯ ПРОДАКШЕНА
PRODUCTION_REQUIRED = {
    # Основные исполняемые файлы
    'main_bot.py',
    'main_bot_integrated.py',  # Интегрированная версия
    'start_bot.py',
    'config.py',
    
    # Модули системы
    'database_adapter_simple.py',
    'database_postgres.py',
    'gift_monitor.py',
    'payment_yookassa.py',
    'payment_ton.py',
    'deposit_accounts_manager.py',
    
    # Кэширование и Redis
    'redis_cache.py',
    'database_adapter_cached.py',
    
    # Мониторинг
    'metrics_collector.py',
    'health_monitor.py',
    'alert_system.py',
    'enhanced_logging.py',
    
    # Отказоустойчивость
    'backup_manager.py',
    'graceful_shutdown.py',
    'auto_recovery.py',
    'circuit_breaker.py',
    
    # Безопасность
    'encryption_manager.py',
    'auth_manager.py',
    'security_audit.py',
    
    # Масштабирование
    'load_balancer.py',
    'message_queue.py',
    'worker_manager.py',
    'cluster_manager.py',
    
    # Docker и конфигурация
    'Dockerfile.bot',
    'Dockerfile.queue',
    'Dockerfile.cluster',
    'Dockerfile',  # Основной Dockerfile
    'docker-compose.production.yml',
    'docker-compose.yml',
    
    # Requirements
    'requirements_complete.txt',
    'requirements_redis.txt',
    'requirements_monitoring.txt',
    'requirements_postgres.txt',
    'requirements.txt',
    
    # Конфигурация и среда
    'env_production_final.txt',
    'env_production_example.txt',
    '.env',  # Текущий env файл
    '.gitignore',
    
    # Документация - ВСЯ НУЖНА!
    'DEPLOYMENT_CHECKLIST.md',
    'COMPLETE_SETUP_GUIDE.md',
    'README.md',
    'SERVER_REQUIREMENTS.md',
    'MONITORING_SETUP.md',
    'REDIS_SETUP.md',
    'RESILIENCE_SETUP.md',
    'SCALING_SETUP.md',
    'SECURITY_SETUP.md',
    'SECURITY_AUDIT_REPORT.md',
    'POSTGRES_MIGRATION_GUIDE.md',
    
    # Русская документация (может пригодиться)
    'КРИТИЧЕСКИ_ВАЖНЫЕ_ПРОВЕРКИ.md',
    'ПЛАН_ЗАПУСКА_ПРОДАКШН.md',
    'НОВАЯ_СИСТЕМА_ГОТОВА.md',
    'СИСТЕМА_ВНУТРЕННИХ_БАЛЛОВ.md',
    'СХЕМА_ПОКУПКИ_ПОДАРКОВ.md',
    
    # Nginx
    'nginx/',
    
    # Инициализация
    'init_database.py',
    
    # Базы данных (нужны для миграции)
    'gift_bot.db',
    'tggift_bot.db',
    
    # Файлы сессий депозитных аккаунтов (КРИТИЧНО!)
    'deposit_account_account_1.session',
    'deposit_account_account_2.session',
    
    # Скрипты управления
    'run_production.sh',
    'stop_bot.sh',
    'tggift-bot.service',
}

# ФАЙЛЫ КОТОРЫЕ МОЖНО УДАЛИТЬ (НЕ НУЖНЫ ДЛЯ ПРОДАКШЕНА)
FILES_TO_REMOVE = {
    # Тестовые и отладочные файлы
    'test_bot_functions.py',
    'test_docker_build.py',
    'test_new_system.py',
    'check_db.py',
    'cleanup_production.py',  # Этот же скрипт
    
    # Отладочные файлы
    'debug_auth.py',
    'diagnose_sms.py',
    'check_session.py',
    
    # Подключение аккаунтов (уже не нужно)
    'connect_app_lowlevel.py',
    'connect_sms.py',
    'connect_deposit_account.py',
    
    # Миграция (уже выполнена)
    'migrate_to_postgres.py',
    'migration.log',
    
    # Старые системы
    'account_manager.py',  # Заменен на deposit_accounts_manager
    'database.py',  # Заменен на database_postgres
    'database_adapter.py',  # Заменен на database_adapter_simple
    
    # Исправления (уже применены)
    'apply_critical_fixes.py',
    'apply_fixes.py',
    
    # Инициализация новой системы (уже выполнена)
    'init_new_system.py',
    
    # Фрагмент менеджер (не используется)
    'fragment_stars_manager.py',
    
    # Альтернативные запуски
    'start_bot_no_account.py',
    
    # Конфигурации других систем
    'config_postgres.py',
    'env_postgres.txt',
    'env_example.txt',  # Заменен на env_production_final.txt
}

# ДИРЕКТОРИИ КОТОРЫЕ МОЖНО УДАЛИТЬ
DIRS_TO_REMOVE = {
    '__pycache__',
    'backup_20250716_204740',
    'backup_20250719_165844_before_new_system',
    'production',  # Старая продакшен папка
    'logs',  # Локальные логи
}

# ФАЙЛЫ С РАСШИРЕНИЯМИ КОТОРЫЕ МОЖНО УДАЛИТЬ
EXTENSIONS_TO_REMOVE = {
    '.log',
    '.backup',
    '.session-journal',  # Оставляем только .session файлы
    '.db-shm',
    '.db-wal',
}

def analyze_directory():
    """Анализ текущей директории"""
    print("🔍 АНАЛИЗ ДИРЕКТОРИИ")
    print("=" * 50)
    
    all_files = []
    all_dirs = []
    
    for item in os.listdir('.'):
        if os.path.isfile(item):
            all_files.append(item)
        elif os.path.isdir(item):
            all_dirs.append(item)
    
    print(f"📁 Всего файлов: {len(all_files)}")
    print(f"📂 Всего директорий: {len(all_dirs)}")
    
    # Анализ файлов
    production_files = []
    remove_files = []
    unknown_files = []
    
    for file in all_files:
        if file in PRODUCTION_REQUIRED:
            production_files.append(file)
        elif file in FILES_TO_REMOVE:
            remove_files.append(file)
        elif any(file.endswith(ext) for ext in EXTENSIONS_TO_REMOVE):
            remove_files.append(file)
        else:
            unknown_files.append(file)
    
    print(f"\n✅ Файлы для продакшена: {len(production_files)}")
    print(f"🗑️ Файлы к удалению: {len(remove_files)}")
    print(f"❓ Неизвестные файлы: {len(unknown_files)}")
    
    return production_files, remove_files, unknown_files, all_dirs

def show_cleanup_plan(production_files, remove_files, unknown_files, all_dirs):
    """Показать план очистки"""
    print("\n📋 ПЛАН ОЧИСТКИ")
    print("=" * 50)
    
    print("\n✅ ОСТАВЛЯЕМ (продакшен файлы):")
    for file in sorted(production_files):
        print(f"  ✅ {file}")
    
    print(f"\n🗑️ УДАЛЯЕМ ФАЙЛЫ ({len(remove_files)}):")
    for file in sorted(remove_files):
        print(f"  🗑️ {file}")
    
    print(f"\n🗑️ УДАЛЯЕМ ДИРЕКТОРИИ:")
    for dir_name in sorted(all_dirs):
        if dir_name in DIRS_TO_REMOVE:
            print(f"  🗑️ {dir_name}/")
    
    if unknown_files:
        print(f"\n❓ НЕИЗВЕСТНЫЕ ФАЙЛЫ (требуют ручной проверки):")
        for file in sorted(unknown_files):
            print(f"  ❓ {file}")

def create_backup():
    """Создать бэкап перед очисткой"""
    backup_name = f"backup_before_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n💾 Создание бэкапа: {backup_name}")
    
    try:
        os.makedirs(backup_name)
        
        # Копируем все файлы
        for item in os.listdir('.'):
            if item != backup_name and not item.startswith('backup_'):
                src = item
                dst = os.path.join(backup_name, item)
                
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                elif os.path.isdir(src):
                    shutil.copytree(src, dst)
        
        print(f"✅ Бэкап создан: {backup_name}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
        return False

def perform_cleanup(remove_files, dirs_to_remove):
    """Выполнить очистку"""
    print("\n🧹 ВЫПОЛНЕНИЕ ОЧИСТКИ")
    print("=" * 30)
    
    removed_files = 0
    removed_dirs = 0
    
    # Удаляем файлы
    for file in remove_files:
        try:
            if os.path.exists(file):
                os.remove(file)
                print(f"🗑️ Удален файл: {file}")
                removed_files += 1
        except Exception as e:
            print(f"❌ Ошибка удаления {file}: {e}")
    
    # Удаляем директории
    for dir_name in dirs_to_remove:
        try:
            if os.path.exists(dir_name) and os.path.isdir(dir_name):
                shutil.rmtree(dir_name)
                print(f"🗑️ Удалена директория: {dir_name}/")
                removed_dirs += 1
        except Exception as e:
            print(f"❌ Ошибка удаления {dir_name}: {e}")
    
    print(f"\n📊 РЕЗУЛЬТАТ ОЧИСТКИ:")
    print(f"  🗑️ Удалено файлов: {removed_files}")
    print(f"  🗑️ Удалено директорий: {removed_dirs}")

def main():
    """Основная функция"""
    print("🧹 ОЧИСТКА ДИРЕКТОРИИ ДЛЯ ПРОДАКШЕНА")
    print("=" * 50)
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Анализ
    production_files, remove_files, unknown_files, all_dirs = analyze_directory()
    
    # План очистки
    show_cleanup_plan(production_files, remove_files, unknown_files, all_dirs)
    
    # Проверка неизвестных файлов
    if unknown_files:
        print(f"\n⚠️ ВНИМАНИЕ: Найдено {len(unknown_files)} неизвестных файлов!")
        print("Проверьте их вручную перед очисткой.")
        
        response = input("\nПродолжить очистку? (y/N): ").lower()
        if response != 'y':
            print("Очистка отменена.")
            return False
    
    # Создаем бэкап
    if not create_backup():
        print("❌ Не удалось создать бэкап. Очистка отменена.")
        return False
    
    # Подтверждение очистки
    print(f"\n⚠️ ВНИМАНИЕ: Будет удалено {len(remove_files)} файлов и {len([d for d in all_dirs if d in DIRS_TO_REMOVE])} директорий!")
    response = input("Выполнить очистку? (y/N): ").lower()
    
    if response == 'y':
        dirs_to_remove = [d for d in all_dirs if d in DIRS_TO_REMOVE]
        perform_cleanup(remove_files, dirs_to_remove)
        
        print("\n🎉 ОЧИСТКА ЗАВЕРШЕНА!")
        print("Директория готова для продакшена.")
        return True
    else:
        print("Очистка отменена.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 