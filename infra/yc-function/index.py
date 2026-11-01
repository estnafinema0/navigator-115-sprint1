"""Точка входа Yandex Cloud Functions: запрос API Gateway (payload 1.0) → FastAPI-приложение Навигатора.

Функция раздаёт и API, и собранный веб (web/out), как uvicorn локально. Модели на стенде нет:
OLLAMA_URL указывает на закрытый порт, разбор уходит на правила и интерфейс это показывает.
Тексты запросов не логируются и не сохраняются.
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "api"))
os.environ.setdefault("OLLAMA_URL", "http://127.0.0.1:9")
os.environ.setdefault("NAVIGATOR_LLM_TIMEOUT", "2")

import httpx  # noqa: E402

from navigator.app import app  # noqa: E402

TEXT_TYPES = ("text/", "application/json", "application/javascript", "image/svg+xml", "application/xml")


async def _call(event: dict) -> dict:
    method = event.get("httpMethod", "GET")
    path = event.get("path") or "/"
    params = event.get("multiValueQueryStringParameters") or event.get("queryStringParameters") or {}
    headers = {k: v for k, v in (event.get("headers") or {}).items() if k.lower() not in ("host", "content-length")}
    body = event.get("body") or ""
    raw = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode("utf-8")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://navigator") as client:
        r = await client.request(method, path, params=params, headers=headers, content=raw)
    ctype = r.headers.get("content-type", "")
    out_headers = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")}
    if ctype.startswith(TEXT_TYPES):
        return {"statusCode": r.status_code, "headers": out_headers, "body": r.text, "isBase64Encoded": False}
    return {"statusCode": r.status_code, "headers": out_headers, "body": base64.b64encode(r.content).decode(), "isBase64Encoded": True}


def handler(event, context):
    return asyncio.run(_call(event))
