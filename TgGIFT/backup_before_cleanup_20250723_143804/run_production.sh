#!/bin/bash

# ========================================
# TgGIFT Star Bot - Production Launcher
# ========================================

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для вывода
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка Python
check_python() {
    print_info "Проверка Python..."
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 не найден!"
        exit 1
    fi
    
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    print_success "Python $python_version найден"
}

# Проверка зависимостей
check_dependencies() {
    print_info "Проверка зависимостей..."
    
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt не найден!"
        exit 1
    fi
    
    # Проверяем основные зависимости
    python3 -c "import telegram, pyrogram, dotenv" 2>/dev/null || {
        print_warning "Зависимости не установлены. Устанавливаем..."
        pip3 install -r requirements.txt
    }
    
    print_success "Зависимости проверены"
}

# Проверка конфигурации
check_config() {
    print_info "Проверка конфигурации..."
    
    if [ ! -f ".env" ]; then
        print_error ".env файл не найден!"
        print_info "Скопируйте env_example.txt в .env и настройте переменные"
        exit 1
    fi
    
    # Проверяем обязательные переменные
    if ! grep -q "BOT_TOKEN=" .env || grep -q "BOT_TOKEN=your_bot_token_here" .env; then
        print_error "BOT_TOKEN не настроен в .env!"
        exit 1
    fi
    
    print_success "Конфигурация проверена"
}

# Проверка базы данных
check_database() {
    print_info "Проверка базы данных..."
    
    python3 -c "
from database import DatabaseManager
try:
    db = DatabaseManager()
    stats = db.get_database_stats()
    print(f'База данных: {stats.get(\"total_users\", 0)} пользователей')
except Exception as e:
    print(f'Ошибка БД: {e}')
    exit(1)
" || {
        print_warning "База данных не инициализирована. Инициализируем..."
        python3 -c "from database import DatabaseManager; DatabaseManager().init_database()"
    }
    
    print_success "База данных проверена"
}

# Проверка логов
check_logs() {
    print_info "Проверка логов..."
    
    log_dir="logs"
    if [ ! -d "$log_dir" ]; then
        mkdir -p "$log_dir"
        print_info "Создана директория логов: $log_dir"
    fi
    
    print_success "Логи готовы"
}

# Запуск бота
start_bot() {
    print_info "Запуск TgGIFT Star Bot..."
    
    # Проверяем, не запущен ли уже бот
    if pgrep -f "start_bot.py" > /dev/null; then
        print_warning "Бот уже запущен!"
        read -p "Остановить существующий процесс? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            pkill -f "start_bot.py"
            sleep 2
        else
            print_info "Выход"
            exit 0
        fi
    fi
    
    # Запускаем бота
    nohup python3 start_bot.py > logs/bot_$(date +%Y%m%d_%H%M%S).log 2>&1 &
    bot_pid=$!
    
    print_success "Бот запущен с PID: $bot_pid"
    print_info "Логи: logs/bot_*.log"
    print_info "Для остановки: ./stop_bot.sh"
}

# Основная функция
main() {
    echo "========================================"
    echo "🌟 TgGIFT Star Bot - Production Launcher"
    echo "========================================"
    echo
    
    check_python
    check_dependencies
    check_config
    check_database
    check_logs
    start_bot
    
    echo
    print_success "Бот успешно запущен!"
    echo
    echo "Полезные команды:"
    echo "  Просмотр логов: tail -f logs/bot_*.log"
    echo "  Остановка бота: ./stop_bot.sh"
    echo "  Статус бота: ps aux | grep start_bot.py"
    echo
}

# Обработка сигналов
trap 'print_info "Получен сигнал, завершение..."; exit 0' SIGINT SIGTERM

# Запуск
main "$@" 