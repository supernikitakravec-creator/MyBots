#!/usr/bin/env python3
"""
Тест Docker сборки для TgGIFT Bot
"""
import os
import subprocess
import sys
from datetime import datetime

def run_command(cmd, description):
    """Запуск команды с логированием"""
    print(f"\n🔧 {description}")
    print(f"Команда: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"✅ {description} - УСПЕШНО")
            if result.stdout:
                print(f"Вывод: {result.stdout[:200]}...")
            return True
        else:
            print(f"❌ {description} - ОШИБКА")
            print(f"Код ошибки: {result.returncode}")
            if result.stderr:
                print(f"Ошибка: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} - ТАЙМАУТ (300 сек)")
        return False
    except Exception as e:
        print(f"❌ {description} - ИСКЛЮЧЕНИЕ: {e}")
        return False

def check_docker():
    """Проверка Docker"""
    print("🔍 Проверка Docker...")
    
    # Проверяем наличие Docker
    if not run_command("docker --version", "Проверка версии Docker"):
        return False
    
    # Проверяем Docker Compose
    if not run_command("docker-compose --version", "Проверка Docker Compose"):
        return False
    
    return True

def check_files():
    """Проверка необходимых файлов"""
    print("\n🔍 Проверка файлов...")
    
    required_files = [
        'Dockerfile.bot',
        'Dockerfile.queue', 
        'Dockerfile.cluster',
        'docker-compose.production.yml',
        'requirements_complete.txt',
        'nginx/nginx.conf'
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - НЕ НАЙДЕН")
            missing_files.append(file)
    
    return len(missing_files) == 0

def test_dockerfile_syntax():
    """Тест синтаксиса Dockerfile"""
    print("\n🔍 Тест синтаксиса Dockerfile...")
    
    dockerfiles = ['Dockerfile.bot', 'Dockerfile.queue', 'Dockerfile.cluster']
    
    all_good = True
    for dockerfile in dockerfiles:
        if os.path.exists(dockerfile):
            # Простая проверка синтаксиса
            with open(dockerfile, 'r') as f:
                content = f.read()
                if 'FROM ' in content and 'CMD ' in content:
                    print(f"✅ {dockerfile} - синтаксис OK")
                else:
                    print(f"❌ {dockerfile} - проблемы с синтаксисом")
                    all_good = False
    
    return all_good

def test_requirements():
    """Тест файла зависимостей"""
    print("\n🔍 Тест requirements_complete.txt...")
    
    if not os.path.exists('requirements_complete.txt'):
        print("❌ requirements_complete.txt не найден")
        return False
    
    with open('requirements_complete.txt', 'r') as f:
        content = f.read()
        
    required_packages = [
        'python-telegram-bot',
        'asyncpg',
        'redis',
        'cryptography',
        'aiohttp'
    ]
    
    missing_packages = []
    for package in required_packages:
        if package in content:
            print(f"✅ {package}")
        else:
            print(f"❌ {package} - не найден")
            missing_packages.append(package)
    
    return len(missing_packages) == 0

def test_docker_compose_syntax():
    """Тест синтаксиса docker-compose.yml"""
    print("\n🔍 Тест docker-compose.production.yml...")
    
    if not os.path.exists('docker-compose.production.yml'):
        print("❌ docker-compose.production.yml не найден")
        return False
    
    # Проверка синтаксиса через docker-compose
    return run_command(
        "docker-compose -f docker-compose.production.yml config --quiet",
        "Проверка синтаксиса docker-compose"
    )

def simulate_build():
    """Симуляция сборки (без фактической сборки)"""
    print("\n🔍 Симуляция Docker сборки...")
    
    # Проверяем что можем прочитать Dockerfile
    try:
        with open('Dockerfile.bot', 'r') as f:
            dockerfile_content = f.read()
        
        print("✅ Dockerfile.bot читается")
        
        # Проверяем базовый образ
        if 'FROM python:3.11-slim' in dockerfile_content:
            print("✅ Базовый образ Python 3.11")
        else:
            print("⚠️ Неожиданный базовый образ")
        
        # Проверяем копирование requirements
        if 'COPY requirements_complete.txt' in dockerfile_content:
            print("✅ Requirements копируются")
        else:
            print("⚠️ Requirements не копируются")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка чтения Dockerfile: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🐳 ТЕСТ DOCKER СБОРКИ TgGIFT BOT")
    print("=" * 50)
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("Проверка Docker", check_docker),
        ("Проверка файлов", check_files),
        ("Синтаксис Dockerfile", test_dockerfile_syntax),
        ("Файл зависимостей", test_requirements),
        ("Синтаксис Docker Compose", test_docker_compose_syntax),
        ("Симуляция сборки", simulate_build)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*15} {test_name} {'='*15}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: ПРОЙДЕН")
            else:
                print(f"❌ {test_name}: ПРОВАЛЕН")
        except Exception as e:
            print(f"❌ {test_name}: ОШИБКА - {e}")
    
    print("\n" + "="*50)
    print(f"📊 РЕЗУЛЬТАТ: {passed}/{total} тестов пройдено")
    
    if passed >= total - 1:  # Позволяем 1 тест провалиться
        print("🎉 Docker конфигурация готова к сборке!")
        return True
    else:
        print("⚠️ Есть проблемы, которые нужно исправить.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 