"""Починка путей к медиа после переноса проекта на другую машину.

Если в БД остались абсолютные пути вида ``C:\\Users\\...``, а файлы лежат в
``data/media`` и ``data/thumbnails``, скрипт находит их по имени и обновляет
записи. Запуск:
    python scripts/repair_paths.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> None:
    changed = 0
    with db.db() as conn:
        rows = conn.execute(
            "SELECT id, media_path, thumbnail_path FROM lectures"
        ).fetchall()
        for row in rows:
            updates: dict[str, str] = {}
            for column, directory in (
                ("media_path", settings.media_dir),
                ("thumbnail_path", settings.thumb_dir),
            ):
                value = row[column]
                if not value or Path(value).exists():
                    continue
                candidate = Path(directory) / Path(value).name
                if candidate.exists():
                    updates[column] = str(candidate.resolve())
            if not updates:
                continue
            columns = ", ".join(f"{key}=?" for key in updates)
            conn.execute(
                f"UPDATE lectures SET {columns} WHERE id=?",
                (*updates.values(), row["id"]),
            )
            changed += 1
            print(f"  · {row['id']}: " + ", ".join(updates))
    print(f"Обновлено записей: {changed}")


if __name__ == "__main__":
    main()
