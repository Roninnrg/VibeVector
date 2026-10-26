"""Общая настройка тестов: изолированная БД, быстрый эмбеддер, без сети."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import wave
from pathlib import Path

import numpy as np
import pytest

# Переменные должны быть выставлены до первого импорта app.config.
TEST_ROOT = Path(tempfile.mkdtemp(prefix="vector-tests-"))
os.environ["VECTOR_DATA_DIR"] = str(TEST_ROOT)
os.environ["VECTOR_DB"] = str(TEST_ROOT / "test.db")
os.environ["EMBEDDING_BACKEND"] = "hashing"
os.environ["LLM_ENABLED"] = "0"
os.environ["SEED_DEMO"] = "0"
os.environ["LOG_LEVEL"] = "WARNING"

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.services.embeddings import HashingEmbedder, set_embedder  # noqa: E402
from app.services.search import reset_search_service  # noqa: E402
from app.text import lemmatize  # noqa: E402

TABLES = ("segments", "chapters", "events", "lectures")


@pytest.fixture(scope="session", autouse=True)
def _environment():
    settings.ensure_dirs()
    db.init_db()
    yield
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_state():
    with db.db() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("UPDATE app_meta SET value='1' WHERE key='index_version'")
    set_embedder(HashingEmbedder())
    reset_search_service()
    yield
    reset_search_service()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder()


def make_wav(path: Path, seconds: float = 1.0, rate: int = 16000,
             channels: int = 1, width: int = 2) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames * channels)
    return path


def insert_lecture(
    lecture_id: str = "test-lecture",
    title: str = "Тестовая лекция",
    cues: list[dict] | None = None,
    status: str = "ready",
    duration: float | None = None,
) -> dict:
    """Создаёт лекцию с сегментами, главами и готовым индексом."""
    cues = cues or [
        {"start": 0.0, "end": 6.0, "text": "Сегодня мы разберём теорему Пифагора."},
        {"start": 6.0, "end": 14.0, "text": "Квадрат гипотенузы равен сумме квадратов катетов."},
        {"start": 14.0, "end": 23.0, "text": "Теорема работает только для прямоугольных треугольников."},
    ]
    duration = duration if duration is not None else float(cues[-1]["end"] if cues else 0)
    now = db.now_iso()
    embedder = HashingEmbedder()
    vectors = embedder.encode_documents([cue["text"] for cue in cues])
    with db.db() as conn:
        conn.execute(
            """INSERT INTO lectures
               (id, title, description, source_type, duration, status, stage, progress,
                summary, summary_points_json, outline_json, keywords_json,
                embedding_provider, created_at, updated_at, processed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lecture_id, title, "Описание тестовой лекции.", "upload", duration,
                status, "Готово" if status == "ready" else "Ошибка",
                100 if status == "ready" else 0,
                cues[0]["text"] if cues else None,
                json.dumps(
                    [{"text": cue["text"], "start": cue["start"], "end": cue["end"]} for cue in cues[:2]],
                    ensure_ascii=False,
                ),
                json.dumps([], ensure_ascii=False),
                json.dumps([{"term": "теорема", "lemma": "теорема", "count": 2, "score": 10.0}],
                           ensure_ascii=False),
                embedder.name, now, now, now,
            ),
        )
        for idx, cue in enumerate(cues):
            vector = vectors[idx] if idx < len(vectors) else np.zeros(embedder.dim, dtype=np.float32)
            conn.execute(
                """INSERT INTO segments
                   (lecture_id, idx, start, end, text, lemmas, words_json, vector, dim, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    lecture_id, idx, cue["start"], cue["end"], cue["text"],
                    " ".join(lemmatize(cue["text"])), "[]",
                    np.asarray(vector, dtype=np.float32).tobytes(), embedder.dim, now,
                ),
            )
        if cues:
            conn.execute(
                """INSERT INTO chapters
                   (lecture_id, idx, start, end, title, summary, keywords_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (lecture_id, 0, cues[0]["start"], cues[-1]["end"],
                 "Введение", cues[0]["text"], "[]"),
            )
    db.bump_index_version()
    return {"id": lecture_id, "duration": duration, "cues": cues}
