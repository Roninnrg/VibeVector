"""Восстановление демонстрационных лекций из ``demo/lectures.json``.

Не требует сети, ffmpeg и Whisper: реплики, конспект, главы и векторы уже
посчитаны. Медиа и превью копируются в ``data/``. Скрипт идемпотентен: уже
существующие лекции пропускаются.

Запуск:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --force
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402

DEMO_DIR = ROOT / "demo"
MANIFEST = DEMO_DIR / "lectures.json"


def _place(source_dir: Path, filename: str | None, target_dir: Path) -> Path | None:
    if not filename:
        return None
    source = source_dir / filename
    if not source.exists():
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / filename
    if not destination.exists() or destination.stat().st_size != source.stat().st_size:
        shutil.copy2(source, destination)
    return destination


def seed_lecture(payload: dict, force: bool = False) -> bool:
    lecture_id = payload["id"]
    with db.db() as conn:
        existing = conn.execute(
            "SELECT id FROM lectures WHERE id=?", (lecture_id,)
        ).fetchone()
        if existing and not force:
            print(f"  · уже есть: {payload['title']} [{lecture_id}]")
            return False
        if existing:
            conn.execute("DELETE FROM lectures WHERE id=?", (lecture_id,))

    media_path = _place(DEMO_DIR / "media", payload.get("media_file"), settings.media_dir)
    if payload.get("media_file") and not media_path:
        raise SystemExit(
            f"Нет файла demo/media/{payload['media_file']}. "
            "Запустите scripts/make_demo.py или scripts/export_demo.py."
        )
    thumbnail_path = _place(
        DEMO_DIR / "thumbnails", payload.get("thumbnail_file"), settings.thumb_dir
    )
    now = db.now_iso()
    created = payload.get("created_at") or now
    processed = payload.get("processed_at") or now

    with db.db() as conn:
        conn.execute(
            """INSERT INTO lectures
               (id, title, description, source_type, source_url, original_filename,
                media_path, media_mime, media_size, duration, thumbnail_path, language,
                status, stage, progress, error, summary, summary_points_json,
                outline_json, keywords_json, asr_provider, embedding_provider, llm_used,
                views, created_at, updated_at, processed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lecture_id,
                payload["title"],
                payload.get("description") or "",
                payload.get("source_type") or "upload",
                payload.get("source_url"),
                payload.get("original_filename"),
                str(media_path) if media_path else None,
                payload.get("media_mime") or "video/mp4",
                media_path.stat().st_size if media_path else 0,
                float(payload.get("duration") or 0),
                str(thumbnail_path) if thumbnail_path else None,
                payload.get("language"),
                "ready",
                "Готово",
                100,
                None,
                payload.get("summary"),
                json.dumps(payload.get("summary_points") or [], ensure_ascii=False),
                json.dumps(payload.get("chapters") or [], ensure_ascii=False),
                json.dumps(payload.get("keywords") or [], ensure_ascii=False),
                payload.get("asr_provider"),
                payload.get("embedding_provider"),
                1 if payload.get("llm_used") else 0,
                0,
                created,
                now,
                processed,
            ),
        )
        for segment in payload.get("segments") or []:
            vector = (
                base64.b64decode(segment["vector_b64"])
                if segment.get("vector_b64") else b""
            )
            conn.execute(
                """INSERT INTO segments
                   (lecture_id, idx, start, end, text, lemmas, words_json, vector, dim, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    lecture_id,
                    int(segment["idx"]),
                    float(segment["start"]),
                    float(segment["end"]),
                    segment["text"],
                    segment.get("lemmas") or "",
                    json.dumps(segment.get("words") or [], ensure_ascii=False),
                    vector,
                    int(segment.get("dim") or 0),
                    now,
                ),
            )
        for chapter in payload.get("chapters") or []:
            conn.execute(
                """INSERT INTO chapters
                   (lecture_id, idx, start, end, title, summary, keywords_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    lecture_id,
                    int(chapter["idx"]),
                    float(chapter["start"]),
                    float(chapter["end"]),
                    chapter["title"],
                    chapter.get("summary") or "",
                    json.dumps(chapter.get("keywords") or [], ensure_ascii=False),
                ),
            )
    print(
        f"  + {payload['title']} [{lecture_id}]: "
        f"{len(payload.get('segments') or [])} реплик, "
        f"{len(payload.get('chapters') or [])} глав"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Восстановление демо-лекций.")
    parser.add_argument("--force", action="store_true", help="Перезаписать существующие лекции.")
    args = parser.parse_args()

    if not MANIFEST.exists():
        raise SystemExit(
            f"Нет манифеста {MANIFEST}. Он создаётся командой scripts/export_demo.py."
        )
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lectures = data.get("lectures") or []
    if not lectures:
        raise SystemExit("В demo/lectures.json нет лекций.")

    db.init_db()
    settings.ensure_dirs()
    print(f"База: {settings.db_path}")
    added = 0
    for payload in lectures:
        added += int(seed_lecture(payload, force=args.force))
    if added:
        db.bump_index_version()
    print(f"\nГотово: добавлено {added} из {len(lectures)}. Версия индекса → {db.index_version()}")


if __name__ == "__main__":
    main()
