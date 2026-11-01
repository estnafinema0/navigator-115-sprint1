# Стенд в Yandex Cloud: Cloud Functions + API Gateway

Публичный стенд спринта 1 (гейт G4 открыт капитаном 01.11.2026). Хостинг в РФ (ru-central1). Модели на стенде нет: разбор идёт правилами, интерфейс показывает «Модель недоступна, текст разобран правилами». Тексты запросов не логируются и не сохраняются.

| Ресурс | Имя | Оплата |
|---|---|---|
| Cloud Functions, Python 3.12, 512 МБ, 30 с, публичная | `navigator-115` (`d4epg3e50ekhs50h7h65`) | грант «все сервисы» |
| API Gateway | `navigator-115`, спецификация `apigw.yaml` | грант «API Gateway и AI Studio» |

Облако `cloud-lizaalexanyan`, каталог `default`.

## Обновить стенд

```bash
sh infra/yc-function/build.sh        # → infra/yc-function/dist/navigator-fn.zip (≈1 МБ)
```

Консоль → Cloud Functions → `navigator-115` → Редактор → ZIP-архив → загрузить архив, точка входа `index.handler` → «Сохранить изменения». Шлюз менять не нужно.

`index.py` переводит событие API Gateway (payload 1.0) в запрос к FastAPI через `httpx.ASGITransport`; бинарные ответы (DOCX) уходят в base64.
