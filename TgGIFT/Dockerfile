FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для безопасности
RUN groupadd -r tggift && useradd -r -g tggift tggift

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Создаем директории для данных и логов
RUN mkdir -p /app/data /app/logs && \
    chown -R tggift:tggift /app

# Переключаемся на пользователя tggift
USER tggift

# Устанавливаем переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Создаем volume для данных
VOLUME ["/app/data", "/app/logs"]

# Проверяем здоровье контейнера
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Открываем порт для health check (если понадобится)
EXPOSE 8080

# Запускаем бота
CMD ["python", "start_bot.py"] 