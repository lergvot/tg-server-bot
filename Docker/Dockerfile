# Dockerfile
FROM python:3.13.9-slim AS builder

# Устанавливаем зависимости для сборки
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    python3-dev \
    build-essential \
    curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt


# Финальный образ
FROM python:3.13.9-slim

# Копируем установленные зависимости из builder-стадии
COPY --from=builder /root/.local /root/.local

RUN apt-get update && apt-get install -y --no-install-recommends

# Обновляем PATH для локальных пакетов
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

CMD ["python3", "bot.py"]
