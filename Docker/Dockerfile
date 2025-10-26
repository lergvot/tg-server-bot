FROM python:3.13.9-slim

WORKDIR /app

# Установка Docker CLI для мониторинга контейнеров
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "bot.py"]
