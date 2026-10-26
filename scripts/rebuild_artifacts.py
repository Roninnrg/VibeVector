"""Пересобрать конспект, тезисы, ключевые слова и главы без повторного ASR.

Скрипт читает уже сохранённые реплики и их эмбеддинги из SQLite, поэтому
пересборка занимает секунды даже для длинных лекций. Полезен после изменения
алгоритмов в ``app/text.py`` и для демо-контента.

Запуск:
    python scripts/rebuild_artifacts.py
    python scripts/rebuild_artifacts.py demo-pythagoras demo-neural
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.text import build_chapters, keyword_weights, summarize  # noqa: E402


def rebuild_lecture(lecture_id: str, *, verbose: bool = True) -> dict:
    with db.db() as conn:
        lecture = conn.execute(
            "SELECT id, title, duration FROM lectures WHERE id=?", (lecture_id,)
        ).fetchone()
        if not lecture:
            raise SystemExit(f"Лекция не найдена: {lecture_id}")
        rows = conn.execute(
            "SELECT idx, start, end, text, vector, dim FROM segments "
            "WHERE lecture_id=? ORDER BY idx",
            (lecture_id,),
        ).fetchall()

    if not rows:
        raise SystemExit(f"У лекции {lecture_id} нет реплик — сначала обработайте видео.")

    cues = [
        {"idx": row["idx"], "start": float(row["start"]), "end": float(row["end"]), "text": row["text"]}
        for row in rows
    ]
    dim = max((int(row["dim"] or 0) for row in rows), default=0)
    vectors = np.zeros((len(rows), max(1, dim)), dtype=np.float32)
    for i, row in enumerate(rows):
        if row["vector"] and int(row["dim"] or 0) == dim:
            vector = np.frombuffer(row["vector"], dtype=np.float32).copy()
            if vector.shape[0] == dim:
                vectors[i] = vector
    vectors_source = vectors if dim else None

    texts = [cue["text"] for cue in cues]
    starts = [cue["start"] for cue in cues]
    ends = [cue["end"] for cue in cues]
    summary = summarize(texts, starts, ends)
    keywords = keyword_weights(texts, top_n=16)
    chapters = build_chapters(cues, vectors_source, duration=float(lecture["duration"] or cues[-1]["end"]))

    now = db.now_iso()
    with db.db() as conn:
        conn.execute(
            """UPDATE lectures SET summary=?, summary_points_json=?, outline_json=?,
               keywords_json=?, updated_at=? WHERE id=?""",
            (
                summary.text,
                json.dumps(summary.points, ensure_ascii=False),
                json.dumps(chapters, ensure_ascii=False),
                json.dumps(keywords, ensure_ascii=False),
                now,
                lecture_id,
            ),
        )
        conn.execute("DELETE FROM chapters WHERE lecture_id=?", (lecture_id,))
        for chapter in chapters:
            conn.execute(
                """INSERT INTO chapters
                   (lecture_id, idx, start, end, title, summary, keywords_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    lecture_id,
                    chapter["idx"],
                    chapter["start"],
                    chapter["end"],
                    chapter["title"],
                    chapter["summary"],
                    json.dumps(chapter["keywords"], ensure_ascii=False),
                ),
            )
    db.bump_index_version()

    if verbose:
        print(f"\n{lecture['title']}  [{lecture_id}]")
        print(f"  реплик: {len(cues)} · глав: {len(chapters)} · тезисов: {len(summary.points)}")
        print("  конспект:", summary.text[:280].replace("\n", " "), "…")
        for chapter in chapters:
            print(f"  · {chapter['start']:>6.1f}  {chapter['title']}")
    return {"lecture_id": lecture_id, "chapters": len(chapters), "points": len(summary.points)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересборка конспекта и структуры лекций.")
    parser.add_argument("lecture_ids", nargs="*", help="ID лекций; по умолчанию все готовые.")
    parser.add_argument("--quiet", action="store_true", help="Не печатать содержимое.")
    args = parser.parse_args()

    ids = args.lecture_ids
    if not ids:
        with db.db() as conn:
            ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM lectures WHERE status='ready' ORDER BY created_at"
                ).fetchall()
            ]
    if not ids:
        raise SystemExit("Готовых лекций нет.")

    print(f"База: {settings.db_path}")
    for lecture_id in ids:
        rebuild_lecture(lecture_id, verbose=not args.quiet)
    print(f"\nГотово: {len(ids)} лекц. Версия индекса → {db.index_version()}")


if __name__ == "__main__":
    main()
