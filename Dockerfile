FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖先行，最大化利用构建缓存
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .

# collectstatic 到 /app/staticfiles，由 nginx 卷直出
RUN SECRET_KEY=dummy python manage.py collectstatic --noinput --clear

EXPOSE 8000
CMD ["sh", "-c", "uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
