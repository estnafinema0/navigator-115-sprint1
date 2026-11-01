# Навигатор-115 — команды разработки.
# Цели, помеченные (TODO: <дата>), появятся по плану PROMPT.md, разд. 15.1.

PY      ?= .venv/bin/python
PIP     ?= .venv/bin/pip
export PYTHONPATH := api

.PHONY: help setup test lint corpus synth gold-check corpus-stats check eval demo demo-local attacks web

help:
	@echo "make setup        — venv и зависимости"
	@echo "make test         — юнит-тесты"
	@echo "make lint         — ruff"
	@echo "make corpus       — data/real/corpus.jsonl из таблицы корпуса"
	@echo "make gold-check   — проверка gold-разметки (схема, цитаты, смещения)"
	@echo "make corpus-stats — доли элементов E1–E9 по корпусу → reports/corpus-compliance.md"
	@echo "make check        — всё, что крутится в CI"
	@echo "make demo         — docker compose: api + db + ollama (первый запуск качает модель ~5 ГБ) → http://localhost:8000"
	@echo "make demo-local   — то же без Docker: локальный Ollama + uvicorn → http://localhost:8000"
	@echo "make web          — собрать веб-интерфейс (Node ≥20.9) в web/out; без сборки раздаётся web-legacy/"
	@echo "make eval PREDICTOR=gold|empty — каркас eval M1 (rules/llm — с 23.10) → reports/eval-YYYY-MM-DD-<predictor>.md"
	@echo "make synth        — синтетика с эталоном → data/synthetic/synth-v1.jsonl"
	@echo "make attacks      — граница 115-ФЗ: атаки на обход и ложные отказы → reports/attacks-YYYY-MM-DD.md"

setup:
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[dev]"

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check api scripts tests eval

corpus:
	$(PY) scripts/build_corpus.py

gold-check:
	$(PY) scripts/gold_check.py

synth:
	$(PY) scripts/synth.py --n 150 --seed 20261021

corpus-stats:
	$(PY) scripts/corpus_stats.py

check: lint test gold-check attacks

demo:
	docker compose up --build -d
	@echo "Навигатор-115: http://localhost:8000 · API: http://localhost:8000/docs"

web:
	cd web && npm ci && npm run build

demo-local:
	$(PY) -m uvicorn navigator.app:app --port 8000

eval:
	$(PY) eval/run_eval.py --predictor $(or $(PREDICTOR),gold)

attacks:
	$(PY) eval/run_attacks.py
