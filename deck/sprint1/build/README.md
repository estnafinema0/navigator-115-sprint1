# Сборка дека спринта 1

Дек собирается кодом на официальном шаблоне `deck/template/Akademiya_Fintekha_template.pptx` (python-pptx). Источники чисел: `docs/sprint1/numbers.md` и `deck/sprint1/notes-v2.md`.

| Файл | Что делает |
|---|---|
| `build_v2.py` | собирает 12 слайдов v2; скриншот слайда 4 берёт из `design/shots/1440-03-razbor-kartochka-v2.png` и обрезает сверху без искажения пропорций |
| `lib.py` | карточки, бейджи, типографика (неразрывные пробелы), логотип из шаблона |
| `metrics.py` | ширины глифов Inter для проверки переполнения |
| `check.py` | QA: переполнение текста по метрикам Inter, рост таблиц, границы, контраст WCAG AA на известных заливках, длинное тире, стоп-слова |
| `pdf_export.py` | PDF через конвертер R7-Office (`x2t_params.sh`) и PNG-превью (`render.py`) |
| `preview-v2.png` | сетка превью всех слайдов v2 |

## Зависимости (в репозиторий не кладём)

- Python 3 с `python-pptx`, `Pillow`, `fonttools`, `pypdfium2`.
- Метрики Inter: пакет `@fontsource/inter@5.1.0` (OFL), распакованный в `deck/sprint1/build/inter/package` (`npm pack @fontsource/inter@5.1.0 && tar xzf fontsource-inter-5.1.0.tgz -C inter`), или в переменной `INTER_DIR` путь к папке, внутри которой лежит `package/`.
- Для PDF: установленный R7-Office (macOS, `/Applications/R7-Office.app`); пути меняются переменными `X2T_DIR` и `R7_ALLFONTS`.

## Команда

```bash
cd deck/sprint1/build
python build_v2.py ../../template/Akademiya_Fintekha_template.pptx ../navigator-115-sprint1-v2.pptx
python check.py ../navigator-115-sprint1-v2.pptx          # ждём «NO PROBLEMS»
python pdf_export.py ../navigator-115-sprint1-v2.pptx ../navigator-115-sprint1-v2.pdf /tmp/deck-png preview-v2.png
```

Третий аргумент `build_v2.py` (необязательный): другой путь к скриншоту.

## Шрифт в PDF

В pptx шрифт Inter (встроен в шаблон). Конвертер x2t встроенные шрифты не читает, а Inter в системе не установлен, поэтому `pdf_export.py` делает копию с Arial (ширина 0,94 от Inter; Inter SemiBold и Medium → Arial Bold, 0,99). Всё, что помещается в Inter, помещается и в PDF. Для финальной загрузки лучше экспортировать PDF из PowerPoint со встроенным Inter.
