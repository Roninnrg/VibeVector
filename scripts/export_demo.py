"""Экспорт готовых демо-лекций в переносимый каталог ``demo/``.

Скрипт выгружает метаданные, реплики, главы и векторы в JSON, а также
копирует медиа и превью. Пригодится, чтобы отдать репозиторий без тяжёлых
моделей и без БД: ``scripts/seed_demo.py`` восстановит демо на новой машине.

Запуск:
    python scripts/export_demo.py
    python scripts/export_demo.py demo-pythagoras demo-neural
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402

DEFAULT_IDS = ["demo-pythagoras", "demo-neural"]
DEMO_DIR = ROOT / "demo"


def _copy(source: str | None, subdir: str) -> str | None:
    if not source:
        return None
    path = Path(source)
    if not path.exists():
        # БД могла приехать с другой машины: ищем файл по имени в data/.
        fallback_dir = settings.media_dir if subdir == "media" else settings.thumb_dir
        fallback = Path(fallback_dir) / path.name
        if not fallback.exists():
            return None
        path = fallback
    destination = DEMO_DIR / subdir / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination.name


def export_lecture(lecture_id: str) -> dict | None:
    with db.db() as conn:
        row = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
        if not row:
            print(f"  ! лекция не найдена: {lecture_id}")
            return None
        lecture = dict(row)
        segments = [
            dict(item)
            for item in conn.execute(
                "SELECT idx, start, end, text, lemmas, words_json, vector, dim "
                "FROM segments WHERE lecture_id=? ORDER BY idx",
                (lecture_id,),
            ).fetchall()
        ]
        chapters = [
            dict(item)
            for item in conn.execute(
                "SELECT idx, start, end, title, summary, keywords_json "
                "FROM chapters WHERE lecture_id=? ORDER BY idx",
                (lecture_id,),
            ).fetchall()
        ]

    segments_payload = []
    for segment in segments:
        vector_b64 = (
            base64.b64encode(segment.pop("vector")).decode("ascii")
            if segment.get("vector") else None
        )
        segment["words"] = db.json_load(segment.pop("words_json", "[]"), [])
        segment["vector_b64"] = vector_b64
        segments_payload.append(segment)

    for chapter in chapters:
        chapter["keywords"] = db.json_load(chapter.pop("keywords_json", "[]"), [])
    chapter_payload = chapters

    media_file = _copy(lecture.get("media_path"), "media")
    thumbnail_file = _copy(lecture.get("thumbnail_path"), "thumbnails")

    payload = {
        "id": lecture["id"],
        "title": lecture["title"],
        "description": lecture.get("description") or "",
        "source_type": lecture.get("source_type") or "upload",
        "source_url": lecture.get("source_url"),
        "original_filename": lecture.get("original_filename"),
        "media_file": media_file,
        "media_mime": lecture.get("media_mime") or "video/mp4",
        "thumbnail_file": thumbnail_file,
        "duration": lecture.get("duration") or 0,
        "language": lecture.get("language"),
        "status": "ready",
        "summary": lecture.get("summary"),
        "summary_points": db.json_load(lecture.get("summary_points_json"), []),
        "keywords": db.json_load(lecture.get("keywords_json"), []),
        "asr_provider": lecture.get("asr_provider"),
        "embedding_provider": lecture.get("embedding_provider"),
        "llm_used": bool(lecture.get("llm_used")),
        "created_at": lecture.get("created_at"),
        "processed_at": lecture.get("processed_at"),
        "segments": segments_payload,
        "chapters": chapter_payload,
    }
    print(
        f"  · {lecture['title']} [{lecture_id}]: "
        f"{len(segments_payload)} реплик, {len(chapter_payload)} глав"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Экспорт демо-лекций в demo/.")
    parser.add_argument("lecture_ids", nargs="*", help="ID лекций (по умолчанию две демо).")
    args = parser.parse_args()
    ids = args.lecture_ids or DEFAULT_IDS

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    lectures = [item for item in (export_lecture(lecture_id) for lecture_id in ids) if item]
    if not lectures:
        raise SystemExit("Нечего экспортировать: готовых демо-лекций нет.")

    output = {
        "format": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lectures": lectures,
    }
    target = DEMO_DIR / "lectures.json"
    target.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"\nГотово: {target} ({size_mb:.2f} МБ), лекций: {len(lectures)}")


if __name__ == "__main__":
    main()
