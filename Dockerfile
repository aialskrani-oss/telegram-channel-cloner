FROM python:3.12-slim

LABEL description="بوت نسخ قنوات تيليجرام — Bot API"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

VOLUME ["/data"]

CMD ["python", "-m", "app.main"]
