# Навигатор-115: API и веб-интерфейс в одном контейнере. Для контура банка базовые образы
# заменяются на сертифицированные (Astra Linux / РЕД ОС), см. docs/adr/0001 (спринт 2).

# 1. Веб-интерфейс (Next.js) собирается в статику web/out
FROM node:22-slim AS web
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

# 2. API на FastAPI раздаёт и API, и собранную статику
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/api
WORKDIR /app
COPY pyproject.toml README.md ./
COPY api ./api
RUN pip install --no-cache-dir -e .
COPY kb ./kb
COPY --from=web /web/out ./web/out
COPY data/synthetic ./data/synthetic
EXPOSE 8000
CMD ["uvicorn", "navigator.app:app", "--host", "0.0.0.0", "--port", "8000"]
