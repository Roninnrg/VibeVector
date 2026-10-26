"""Асинхронный конвейер обработки лекции."""
from __future__ import annotations

import json
import logging
import math
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import numpy as np

from .. import db
from ..config import settings
from ..text import build_chapters, keyword_weights, summarize
from .asr import get_asr
from .embeddings import HashingEmbedder, get_embedder, set_embedder
from .llm import LLMClient
from .media import MediaError, extract_audio, make_thumbnail, probe, sanitize_filename, safe_unlink
from .search import get_search_service, reset_search_service

log = logging.getLogger(__name__)
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}


def _update(lecture_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = db.now_iso()
    columns = ", ".join(f"{key} = ?" for key in fields)
    with db.db() as conn:
        conn.execute(
            f"UPDATE lectures SET {columns} WHERE id = ?",
            (*fields.values(), lecture_id),
        )


class JobManager:
    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="vector-job")
        self._active: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, lecture_id: str, force: bool = False) -> bool:
        with self._lock:
            existing = self._active.get(lecture_id)
            if existing and not existing.done():
                return False
            if self._closed:
                return False
            future = self.executor.submit(self._run, lecture_id, force)
            self._active[lecture_id] = future
            future.add_done_callback(lambda _: self._forget(lecture_id))
        return True

    def _forget(self, lecture_id: str) -> None:
        with self._lock:
            self._active.pop(lecture_id, None)

    def _run(self, lecture_id: str, force: bool) -> None:
        try:
            process_lecture(lecture_id, force=force)
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка обработки лекции %s", lecture_id)
            _update(
                lecture_id,
                status="failed",
                stage="Ошибка",
                error=str(exc)[:1200],
                progress=0,
            )

    def recover(self) -> None:
        with db.db() as conn:
            rows = conn.execute(
                "SELECT id FROM lectures WHERE status IN ('queued', 'processing')"
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE lectures SET status='queued', stage='В очереди после перезапуска', progress=0, "
                    "updated_at=? WHERE id=?",
                    (db.now_iso(), row["id"]),
                )
        for row in rows:
            self.submit(row["id"])

    def shutdown(self) -> None:
        self._closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)

    def active(self) -> list[str]:
        with self._lock:
            return [key for key, future in self._active.items() if not future.done()]


MANAGER = JobManager(max_workers=1)


def _download_remote(lecture_id: str, url: str, progress: Callable[[int, str], None]) -> Path:
    try:
        import yt_dlp  # noqa: WPS433
    except Exception as exc:
        raise MediaError("yt-dlp не установлен. Выполните `pip install yt-dlp`.") from exc
    progress(2, "Скачиваем видео по ссылке")
    out_dir = Path(settings.media_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(status: dict) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            downloaded = status.get("downloaded_bytes") or 0
            if total:
                pct = int(downloaded / total * 100)
                progress(max(2, min(8, 2 + pct * 6 // 100)), f"Скачиваем видео · {pct}%")
        elif status.get("status") == "finished":
            progress(8, "Скачивание завершено")

    options = {
        "outtmpl": str(out_dir / f"{lecture_id}.%(ext)s"),
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/bv*[height<=720]+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "socket_timeout": 30,
        "progress_hooks": [hook],
        "restrictfilenames": True,
        "paths": {"home": str(out_dir)},
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        raise MediaError(f"Не удалось скачать видео: {str(exc)[:500]}") from exc
    candidates = sorted(out_dir.glob(f"{lecture_id}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise MediaError("Сервис не вернул медиафайл.")
    path = candidates[0]
    title = (info or {}).get("title")
    if title:
        _update(lecture_id, title=str(title)[:240])
    return path


def _progress_writer(lecture_id: str, start: int, span: int,
                     stage: str, min_interval: float = 0.8) -> Callable[[float], None]:
    last = {"time": 0.0, "value": -1}

    def callback(fraction: float) -> None:
        now = time.monotonic()
        value = int(start + max(0.0, min(1.0, fraction)) * span)
        if now - last["time"] < min_interval and value < 100:
            return
        if value == last["value"]:
            return
        last["time"] = now
        last["value"] = value
        _update(lecture_id, progress=value, stage=f"{stage} · {value}%")

    return callback


def process_lecture(lecture_id: str, force: bool = False) -> None:
    with db.db() as conn:
        row = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
        if not row:
            return
    lecture = dict(row)
    if lecture["status"] == "processing" and not force:
        # защита от параллельного запуска
        _update(lecture_id, stage="Обработка уже идёт")
        return

    _update(
        lecture_id,
        status="processing",
        stage="Проверяем файл",
        progress=1,
        error=None,
        summary=None,
        summary_points_json="[]",
        outline_json="[]",
        keywords_json="[]",
        llm_used=0,
    )
    with db.db() as conn:
        conn.execute("DELETE FROM segments WHERE lecture_id=?", (lecture_id,))
        conn.execute("DELETE FROM chapters WHERE lecture_id=?", (lecture_id,))
    db.bump_index_version()
    reset_search_service()

    media_path = lecture.get("media_path")
    source_url = lecture.get("source_url")
    try:
        if not media_path or not Path(media_path).exists():
            if source_url:
                media_path = str(_download_remote(lecture_id, source_url, lambda p, s: _update(
                    lecture_id, progress=p, stage=s,
                )))
                _update(lecture_id, media_path=media_path, media_size=Path(media_path).stat().st_size)
            else:
                raise MediaError("Файл лекции не найден на диске.")

        info = probe(media_path)
        duration = float(info["duration"])
        _update(
            lecture_id,
            duration=duration,
            media_size=Path(media_path).stat().st_size,
            media_mime=info["mime"],
            progress=4,
            stage="Проверяем файл · 4%",
            original_filename=lecture.get("original_filename") or sanitize_filename(Path(media_path).name),
        )

        thumb = Path(settings.thumb_dir) / f"{lecture_id}.jpg"
        if not lecture.get("thumbnail_path") or not Path(lecture["thumbnail_path"]).exists():
            thumb_path = make_thumbnail(media_path, thumb, at=min(5.0, max(1.0, duration / 8)))
            if thumb_path:
                _update(lecture_id, thumbnail_path=str(thumb_path))
        _update(lecture_id, progress=7, stage="Извлекаем аудио · 7%")

        audio_path = Path(settings.audio_dir) / f"{lecture_id}.wav"
        extract_audio(media_path, audio_path)
        _update(lecture_id, progress=12, stage="Распознаём речь · 12%")

        language = lecture.get("language") or None
        asr = get_asr()
        asr_result = asr.transcribe(
            audio_path,
            duration=duration,
            language=language if language and language != "auto" else None,
            on_progress=_progress_writer(lecture_id, 12, 55, "Распознаём речь"),
        )
        if not asr_result.cues:
            raise RuntimeError("Речь не распознана. Проверьте, что в видео есть звук.")
        cues = asr_result.cues
        for cue in cues:
            cue["start"] = max(0.0, min(float(cue["start"]), duration))
            cue["end"] = max(cue["start"] + 0.3, min(float(cue["end"]), duration))
        cues = [cue for cue in cues if cue["text"].strip()]

        _update(
            lecture_id,
            progress=70,
            stage="Строим семантический индекс · 70%",
            language=asr_result.language,
            asr_provider=asr_result.provider,
            duration=duration,
        )
        if not cues:
            raise RuntimeError("Не удалось получить текст лекции.")

        embedder = get_embedder()
        try:
            vectors = embedder.encode_documents([cue["text"] for cue in cues])
        except Exception as exc:  # noqa: BLE001
            log.exception("Эмбеддинги недоступны, переключаюсь на резерв: %s", exc)
            embedder = HashingEmbedder()
            set_embedder(embedder)
            vectors = embedder.encode_documents([cue["text"] for cue in cues])

        texts = [cue["text"] for cue in cues]
        starts = [cue["start"] for cue in cues]
        ends = [cue["end"] for cue in cues]
        summary = summarize(texts, starts, ends)
        keywords = keyword_weights(texts, top_n=16)
        chapters = build_chapters(cues, vectors, duration=duration)
        _update(lecture_id, progress=86, stage="Собираем конспект · 86%")

        summary_text = summary.text
        used_llm = False
        llm = LLMClient()
        if llm.ready:
            full_text = " ".join(texts)[:30000]
            improved = llm.improve_summary(full_text, summary_text)
            if improved and len(improved) > 80:
                summary_text = improved
                used_llm = True

        now = db.now_iso()
        with db.db() as conn:
            for idx, cue in enumerate(cues):
                vector = vectors[idx] if idx < len(vectors) else np.zeros(vectors.shape[1], dtype=np.float32)
                vector = np.asarray(vector, dtype=np.float32)
                conn.execute(
                    """INSERT INTO segments
                       (lecture_id, idx, start, end, text, lemmas, words_json, vector, dim, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        lecture_id,
                        idx,
                        round(float(cue["start"]), 3),
                        round(float(cue["end"]), 3),
                        cue["text"],
                        " ".join(_lemmas(cue["text"])),
                        json.dumps(cue.get("words") or [], ensure_ascii=False),
                        vector.tobytes(),
                        int(vector.shape[0]),
                        now,
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
            conn.execute(
                """UPDATE lectures SET status='ready', stage='Готово', progress=100,
                   summary=?, summary_points_json=?, outline_json=?, keywords_json=?,
                   embedding_provider=?, llm_used=?, processed_at=?, updated_at=?, error=NULL
                   WHERE id=?""",
                (
                    summary_text,
                    json.dumps(summary.points, ensure_ascii=False),
                    json.dumps(chapters, ensure_ascii=False),
                    json.dumps(keywords, ensure_ascii=False),
                    embedder.name,
                    1 if used_llm else 0,
                    now,
                    now,
                    lecture_id,
                ),
            )
        db.bump_index_version()
        get_search_service().rebuild()
        db.log_event("lecture_ready", lecture_id=lecture_id, cues=len(cues), llm=used_llm)
        safe_unlink(audio_path)
        log.info("Лекция %s готова: %s реплик, %.0f c", lecture_id, len(cues), duration)
    except Exception as exc:
        safe_unlink(Path(settings.audio_dir) / f"{lecture_id}.wav")
        _update(
            lecture_id,
            status="failed",
            stage="Ошибка",
            progress=0,
            error=str(exc)[:1500],
        )
        log.error("Лекция %s: %s\n%s", lecture_id, exc, traceback.format_exc()[:2000])
        raise


def _lemmas(text: str) -> list[str]:
    from ..text import lemmatize

    return lemmatize(text)


def reprocess(lecture_id: str) -> bool:
    with db.db() as conn:
        row = conn.execute("SELECT id FROM lectures WHERE id=?", (lecture_id,)).fetchone()
    if not row:
        return False
    _update(
        lecture_id,
        status="queued",
        stage="В очереди",
        progress=0,
        error=None,
        summary=None,
        summary_points_json="[]",
        outline_json="[]",
        keywords_json="[]",
    )
    return MANAGER.submit(lecture_id, force=True)


def pipeline_status() -> dict:
    return {
        "active": MANAGER.active(),
        "workers": 1,
        "ffmpeg": bool(settings.ffmpeg),
        "ffprobe": bool(settings.ffprobe),
    }
