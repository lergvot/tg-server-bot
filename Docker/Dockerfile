# Docker/Dockerfile
FROM python:3.13-slim AS builder

# Устанавливаем build-зависимости (нужны только для компиляции пакетов)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Устанавливаем Python пакеты в пользовательскую директорию
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# Финальный образ (runtime)
FROM python:3.13-slim

# Создаем non-root пользователя для безопасности
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Копируем установленные Python пакеты из builder-стадии
COPY --from=builder /root/.local /home/appuser/.local

# Обновляем PATH для локальных пакетов пользователя
ENV PATH=/home/appuser/.local/bin:$PATH

WORKDIR /app

# Копируем исходный код и назначаем права
COPY . .
RUN chown -R appuser:appuser /app

# Переключаемся на non-root пользователя
USER appuser

# Создаем директорию для логов
RUN mkdir -p /app/logs

CMD ["python3", "bot.py"]
