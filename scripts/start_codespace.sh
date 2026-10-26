#!/usr/bin/env bash
# Идемпотентный запуск «Вектора» в GitHub Codespace.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3.12}"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "Устанавливаю ffmpeg…"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg
fi

if [ ! -x .venv/bin/python ]; then
  echo "Создаю виртуальное окружение…"
  "$PYTHON" -m venv .venv
fi

echo "Проверяю зависимости…"
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

if [ ! -f data/models/whisper-small/model.bin ]; then
  echo "Скачиваю модели…"
  .venv/bin/python scripts/download_models.py
fi

if [ ! -f data/vector.db ] || [ ! -f data/media/demo-pythagoras.mp4 ]; then
  echo "Засеваю демо-лекции…"
  .venv/bin/python scripts/seed_demo.py
fi

if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo "«Вектор» уже запущен на порту 8000."
  exit 0
fi

echo "Запускаю uvicorn…"
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/vector.log 2>&1 &
echo $! > /tmp/vector.pid

for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "Готово: http://127.0.0.1:8000"
    exit 0
  fi
  sleep 1
done

echo "Сервер не поднялся. Лог:" >&2
tail -50 /tmp/vector.log >&2
exit 1
