#!/bin/sh
# Собирает архив функции: api/, нужные части kb/, web/out, index.py, requirements.txt.
# Запуск из корня репозитория: sh infra/yc-function/build.sh  →  infra/yc-function/dist/navigator-fn.zip
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT="$ROOT/infra/yc-function/dist"
STAGE="$OUT/stage"
rm -rf "$OUT" && mkdir -p "$STAGE/kb/sources/cbr"
[ -d "$ROOT/web/out" ] || (cd "$ROOT" && make web)
cp "$ROOT/infra/yc-function/index.py" "$ROOT/infra/yc-function/requirements.txt" "$STAGE/"
rsync -a --exclude __pycache__ "$ROOT/api" "$STAGE/"
cp -R "$ROOT/kb/calendar" "$ROOT/kb/norms" "$ROOT/kb/templates" "$STAGE/kb/"
cp -R "$ROOT/kb/sources/cbr/templates" "$STAGE/kb/sources/cbr/"
mkdir -p "$STAGE/web" && cp -R "$ROOT/web/out" "$STAGE/web/"
(cd "$STAGE" && zip -qr "$OUT/navigator-fn.zip" .)
ls -lh "$OUT/navigator-fn.zip"
