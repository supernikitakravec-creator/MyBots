#!/bin/bash

# ========================================
# TgGIFT Star Bot - Graceful Stop Script
# ========================================

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Поиск процессов бота
find_bot_processes() {
    pgrep -f "start_bot.py" || echo ""
}

# Graceful остановка
graceful_stop() {
    local pids=$1
    local timeout=${2:-30}
    
    print_info "Отправляем SIGTERM процессам: $pids"
    
    for pid in $pids; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    
    # Ждем graceful shutdown
    local waited=0
    while [ $waited -lt $timeout ]; do
        local running_pids=$(find_bot_processes)
        if [ -z "$running_pids" ]; then
            print_success "Все процессы остановлены gracefully"
            return 0
        fi
        
        print_info "Ждем завершения процессов... ($waited/$timeout сек)"
        sleep 2
        waited=$((waited + 2))
    done
    
    print_warning "Timeout graceful shutdown, принудительная остановка"
    return 1
}

# Принудительная остановка
force_stop() {
    local pids=$1
    
    print_warning "Принудительная остановка процессов: $pids"
    
    for pid in $pids; do
        kill -KILL "$pid" 2>/dev/null || true
    done
    
    sleep 2
    
    local running_pids=$(find_bot_processes)
    if [ -z "$running_pids" ]; then
        print_success "Все процессы остановлены принудительно"
        return 0
    else
        print_error "Не удалось остановить процессы: $running_pids"
        return 1
    fi
}

# Основная функция
main() {
    echo "========================================"
    echo "🛑 TgGIFT Star Bot - Graceful Stop"
    echo "========================================"
    echo
    
    # Ищем процессы бота
    local bot_pids=$(find_bot_processes)
    
    if [ -z "$bot_pids" ]; then
        print_info "Процессы бота не найдены"
        exit 0
    fi
    
    print_info "Найдены процессы бота: $bot_pids"
    
    # Пытаемся graceful остановку
    if graceful_stop "$bot_pids" 30; then
        print_success "Бот остановлен gracefully"
        exit 0
    fi
    
    # Если graceful не сработал, принудительная остановка
    if force_stop "$bot_pids"; then
        print_success "Бот остановлен принудительно"
        exit 0
    else
        print_error "Не удалось остановить бота"
        exit 1
    fi
}

# Обработка сигналов
trap 'print_info "Получен сигнал, завершение..."; exit 0' SIGINT SIGTERM

# Запуск
main "$@" 