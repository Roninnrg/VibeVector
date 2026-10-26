#!/usr/bin/env bash
# «Вектор» — запуск одной командой (Linux / macOS).
#
#   ./run.sh              первый запуск: venv, зависимости, ffmpeg, модели, демо
#   ./run.sh --fast       без скачивания моделей (демо-лекции работают сразу)
#   ./run.sh --port 8080  другой порт
#   ./run.sh --no-browser не открывать браузер
#
# После первого запуска повторный старт занимает пару секунд: все проверки
# идемпотентны и пропускают уже установленное.

set -euo pipefail

cd "$(dirname "$0")"

PORT=8000
FAST=0
OPEN_BROWSER=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast) FAST=1 ;;
    --port) PORT="${2:?--port требует значение}"; shift ;;
    --no-browser) OPEN_BROWSER=0 ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Неизвестный аргумент: $1" >&2; exit 1 ;;
  esac
  shift
done

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH=.
export VECTOR_PORT="$PORT"

step() { printf '\n==> %s\n' "$1"; }

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  if command -v python3 >/dev/null 2>&1; then
    BASE_PYTHON=python3
  elif command -v python >/dev/null 2>&1; then
    BASE_PYTHON=python
  else
    echo "Python 3.10+ не найден. Установите python3 и повторите запуск." >&2
    exit 1
  fi
  step "Создаю виртуальное окружение .venv"
  "$BASE_PYTHON" -m venv .venv

  step "Устанавливаю зависимости"
  .venv/bin/python -m pip install --upgrade pip --quiet
  .venv/bin/python -m pip install -r requirements.txt
  PYTHON=".venv/bin/python"
fi

step "Проверяю ffmpeg / ffprobe"
"$PYTHON" scripts/setup_tools.py

if [[ "$FAST" == "1" ]]; then
  printf '  · режим --fast: модели не скачиваются, доступны только демо-лекции\n'
  printf '    для загрузки новых видео запустите scripts/download_models.py\n'
else
  step "Проверяю офлайн-модели (Whisper + эмбеддинги, ~1.2 ГБ при первом запуске)"
  "$PYTHON" scripts/download_models.py
fi

if [[ ! -f "data/vector.db" ]]; then
  step "Готовлю демонстрационные лекции"
  "$PYTHON" scripts/seed_demo.py
else
  printf '  · база data/vector.db уже есть\n'
fi

URL="http://127.0.0.1:$PORT"
step "Запускаю «Вектор» на $URL"
printf '  Ctrl+C — остановить сервер\n'

if [[ "$OPEN_BROWSER" == "1" ]]; then
  (
    sleep 2
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$URL" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
      open "$URL" >/dev/null 2>&1 || true
    fi
  ) &
fi

exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
