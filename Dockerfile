# Mifgash, local run for judges: docker compose up (see README, "Run with Docker").
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MIFGASH_STATIC_ROOT=/app/staticfiles
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# collectstatic needs no database and no real keys; a build-time dummy key passes the settings check.
RUN MIFGASH_SECRET_KEY=build-only-dummy-key-0123456789abcdef python manage.py collectstatic --noinput \
    && chmod +x docker/entrypoint.sh
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["web"]
