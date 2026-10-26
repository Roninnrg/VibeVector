"""HTTP API «Вектор»."""
from __future__ import annotations

import json
import logging
import mimetypes
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .services import media
from .services.asr import asr_status
from .services.embeddings import embedding_status
from .services.llm import llm_status
from .services.pipeline import MANAGER, pipeline_status, reprocess
from .services.qa import get_qa_service
from .services.search import get_search_service
from .text import (
    cues_to_srt,
    cues_to_vtt,
    format_timestamp,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
VIMEO_HOSTS = {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}


class ImportRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: str = Field(default="", max_length=240)
    language: str = Field(default="auto", max_length=8)


class LectureUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=3000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=800)
    limit: int = Field(default=5, ge=3, le=8)


def _get_lecture(lecture_id: str) -> dict:
    with db.db() as conn:
        row = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Лекция не найдена.")
    return db.lecture_public(dict(row))


def _counts(lecture_id: str) -> dict:
    with db.db() as conn:
        segments = conn.execute(
            "SELECT COUNT(*) AS c FROM segments WHERE lecture_id=?", (lecture_id,)
        ).fetchone()["c"]
        chapters = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters WHERE lecture_id=?", (lecture_id,)
        ).fetchone()["c"]
    return {"segments_count": int(segments), "chapters_count": int(chapters)}


@router.get("/lectures")
def list_lectures(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    with db.db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM lectures WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM lectures ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        counts = {
            row["lecture_id"]: row["c"]
            for row in conn.execute(
                "SELECT lecture_id, COUNT(*) AS c FROM segments GROUP BY lecture_id"
            ).fetchall()
        }
    items = []
    for row in rows:
        item = db.lecture_public(dict(row))
        item["segments_count"] = int(counts.get(item["id"], 0))
        item["chapters_count"] = len(item.get("chapters") or [])
        items.append(item)
    return {"items": items, "count": len(items)}


@router.get("/lectures/{lecture_id}")
def get_lecture(lecture_id: str) -> dict:
    lecture = _get_lecture(lecture_id)
    lecture.update(_counts(lecture_id))
    with db.db() as conn:
        conn.execute(
            "UPDATE lectures SET views = views + 1 WHERE id=?", (lecture_id,)
        )
        chapters = conn.execute(
            "SELECT idx, start, end, title, summary, keywords_json FROM chapters "
            "WHERE lecture_id=? ORDER BY idx",
            (lecture_id,),
        ).fetchall()
    if chapters:
        lecture["chapters"] = [
            {
                "idx": row["idx"],
                "start": row["start"],
                "end": row["end"],
                "title": row["title"],
                "summary": row["summary"],
                "keywords": db.json_load(row["keywords_json"], []),
            }
            for row in chapters
        ]
    return lecture


@router.get("/lectures/{lecture_id}/transcript")
def get_transcript(
    lecture_id: str,
    words: bool = Query(default=False),
) -> dict:
    _get_lecture(lecture_id)
    with db.db() as conn:
        rows = conn.execute(
            "SELECT id, idx, start, end, text, words_json FROM segments "
            "WHERE lecture_id=? ORDER BY idx",
            (lecture_id,),
        ).fetchall()
    cues = []
    for row in rows:
        cue = {
            "id": row["id"],
            "idx": row["idx"],
            "start": row["start"],
            "end": row["end"],
            "text": row["text"],
        }
        if words:
            cue["words"] = db.json_load(row["words_json"], [])
        cues.append(cue)
    return {"lecture_id": lecture_id, "cues": cues, "count": len(cues)}


@router.get("/lectures/{lecture_id}/subtitles.{fmt}")
def subtitles(lecture_id: str, fmt: str, download: bool = Query(default=False)) -> Response:
    _get_lecture(lecture_id)
    with db.db() as conn:
        rows = conn.execute(
            "SELECT start, end, text FROM segments WHERE lecture_id=? ORDER BY idx",
            (lecture_id,),
        ).fetchall()
    cues = [dict(row) for row in rows]
    if fmt.lower() == "vtt":
        content = cues_to_vtt(cues)
        media_type = "text/vtt; charset=utf-8"
        filename = f"{lecture_id}.vtt"
    elif fmt.lower() == "srt":
        content = cues_to_srt(cues)
        media_type = "application/x-subrip; charset=utf-8"
        filename = f"{lecture_id}.srt"
    else:
        raise HTTPException(400, "Поддерживаются форматы vtt и srt.")
    headers = {"Content-Disposition": f"{'attachment' if download else 'inline'}; filename={filename}"}
    return Response(content, media_type=media_type, headers=headers)


@router.get("/lectures/{lecture_id}/thumbnail")
def thumbnail(lecture_id: str) -> FileResponse:
    with db.db() as conn:
        row = conn.execute(
            "SELECT thumbnail_path FROM lectures WHERE id=?", (lecture_id,)
        ).fetchone()
    if not row or not row["thumbnail_path"] or not Path(row["thumbnail_path"]).exists():
        raise HTTPException(404, "Превью ещё не готово.")
    return FileResponse(
        row["thumbnail_path"],
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/lectures/{lecture_id}/media")
def stream_media(lecture_id: str, request: Request):
    with db.db() as conn:
        row = conn.execute(
            "SELECT media_path, media_mime FROM lectures WHERE id=?", (lecture_id,)
        ).fetchone()
    if not row or not row["media_path"] or not Path(row["media_path"]).exists():
        raise HTTPException(404, "Медиафайл не найден.")
    path = Path(row["media_path"])
    size = path.stat().st_size
    mime = row["media_mime"] or media.media_type_for(path)
    range_header = request.headers.get("range")
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
        "Content-Disposition": "inline",
    }
    if not range_header:
        return StreamingResponse(
            media.iter_file(path),
            media_type=mime,
            headers={**headers, "Content-Length": str(size)},
        )
    match = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
    if not match:
        raise HTTPException(416, "Некорректный Range.")
    start_raw, end_raw = match.groups()
    if start_raw:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    else:
        suffix = int(end_raw or 0)
        start = max(0, size - suffix)
        end = size - 1
    if start >= size or end < start:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    end = min(end, size - 1)
    length = end - start + 1
    return StreamingResponse(
        media.iter_file(path, start, end),
        status_code=206,
        media_type=mime,
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        },
    )


@router.head("/lectures/{lecture_id}/media")
def stream_media_head(lecture_id: str):
    with db.db() as conn:
        row = conn.execute(
            "SELECT media_path, media_mime FROM lectures WHERE id=?", (lecture_id,)
        ).fetchone()
    if not row or not row["media_path"] or not Path(row["media_path"]).exists():
        raise HTTPException(404, "Медиафайл не найден.")
    path = Path(row["media_path"])
    return Response(
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(path.stat().st_size),
            "Content-Type": row["media_mime"] or media.media_type_for(path),
        }
    )


@router.post("/lectures/upload", status_code=202)
async def upload_lecture(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    description: str = Form(default=""),
    language: str = Form(default="auto"),
) -> dict:
    filename = media.sanitize_filename(file.filename or "lecture", "lecture")
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_media_ext:
        raise HTTPException(
            422,
            "Неподдерживаемый формат. Загрузите MP4, WebM, MOV, MKV, MP3, M4A или WAV.",
        )
    lecture_id = uuid.uuid4().hex[:16]
    destination = Path(settings.media_dir) / f"{lecture_id}{suffix}"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with open(destination, "wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        413, f"Файл больше {settings.max_upload_mb} МБ."
                    )
                handle.write(chunk)
    except HTTPException:
        media.safe_unlink(destination)
        raise
    except Exception as exc:
        media.safe_unlink(destination)
        raise HTTPException(500, f"Не удалось сохранить файл: {exc}") from exc
    finally:
        await file.close()

    if size == 0:
        media.safe_unlink(destination)
        raise HTTPException(422, "Файл пустой.")
    try:
        info = media.probe(destination)
    except media.MediaError as exc:
        media.safe_unlink(destination)
        raise HTTPException(422, str(exc)) from exc

    clean_title = (title or Path(filename).stem).strip()[:240] or "Без названия"
    language = (language or "auto").strip()[:8]
    now = db.now_iso()
    with db.db() as conn:
        conn.execute(
            """INSERT INTO lectures
               (id, title, description, source_type, original_filename, media_path, media_mime,
                media_size, duration, language, status, stage, progress, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lecture_id, clean_title, description.strip()[:3000], "upload", filename,
                str(destination), info["mime"], size, info["duration"],
                None if language == "auto" else language,
                "queued", "В очереди", 0, now, now,
            ),
        )
    MANAGER.submit(lecture_id)
    return _get_lecture(lecture_id)


def _validate_import_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(422, "Ссылка должна начинаться с http:// или https://")
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS and host not in VIMEO_HOSTS:
        raise HTTPException(422, "Поддерживаются ссылки YouTube и Vimeo.")
    return url.strip()


@router.post("/lectures/import", status_code=202)
def import_lecture(payload: ImportRequest) -> dict:
    url = _validate_import_url(payload.url)
    lecture_id = uuid.uuid4().hex[:16]
    host = (urlparse(url).hostname or "").lower()
    title = payload.title.strip()[:240] or (
        "Лекция с YouTube" if host in YOUTUBE_HOSTS else "Лекция с Vimeo"
    )
    now = db.now_iso()
    with db.db() as conn:
        conn.execute(
            """INSERT INTO lectures
               (id, title, description, source_type, source_url, language,
                status, stage, progress, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lecture_id, title, "", "url", url,
                None if payload.language == "auto" else payload.language,
                "queued", "В очереди", 0, now, now,
            ),
        )
    MANAGER.submit(lecture_id)
    return _get_lecture(lecture_id)


@router.patch("/lectures/{lecture_id}")
def update_lecture(lecture_id: str, payload: LectureUpdate) -> dict:
    _get_lecture(lecture_id)
    fields = {}
    if payload.title is not None:
        fields["title"] = payload.title.strip()[:240]
    if payload.description is not None:
        fields["description"] = payload.description.strip()[:3000]
    if fields:
        fields["updated_at"] = db.now_iso()
        columns = ", ".join(f"{key}=?" for key in fields)
        with db.db() as conn:
            conn.execute(
                f"UPDATE lectures SET {columns} WHERE id=?",
                (*fields.values(), lecture_id),
            )
        db.bump_index_version()
    return _get_lecture(lecture_id)


@router.delete("/lectures/{lecture_id}")
def delete_lecture(lecture_id: str) -> dict:
    lecture = _get_lecture(lecture_id)
    if lecture["status"] == "processing":
        raise HTTPException(409, "Дождитесь завершения обработки перед удалением.")
    with db.db() as conn:
        conn.execute("DELETE FROM lectures WHERE id=?", (lecture_id,))
    media.safe_unlink(lecture.get("media_path"))
    media.safe_unlink(lecture.get("thumbnail_path"))
    media.safe_unlink(Path(settings.audio_dir) / f"{lecture_id}.wav")
    db.bump_index_version()
    get_search_service().rebuild()
    return {"deleted": True, "id": lecture_id}


@router.post("/lectures/{lecture_id}/reprocess", status_code=202)
def reprocess_lecture(lecture_id: str) -> dict:
    lecture = _get_lecture(lecture_id)
    if lecture["status"] == "processing":
        raise HTTPException(409, "Обработка уже идёт.")
    if not reprocess(lecture_id):
        raise HTTPException(500, "Не удалось запустить обработку.")
    return _get_lecture(lecture_id)


@router.get("/lectures/{lecture_id}/export")
def export_lecture(lecture_id: str) -> Response:
    lecture = _get_lecture(lecture_id)
    with db.db() as conn:
        cues = conn.execute(
            "SELECT start, end, text FROM segments WHERE lecture_id=? ORDER BY idx",
            (lecture_id,),
        ).fetchall()
    lines = [f"# {lecture['title']}", ""]
    meta = []
    if lecture.get("duration"):
        meta.append(f"Длительность: {format_timestamp(lecture['duration'])}")
    if lecture.get("language"):
        meta.append(f"Язык: {lecture['language']}")
    if meta:
        lines += [" · ".join(meta), ""]
    if lecture.get("description"):
        lines += [lecture["description"], ""]
    if lecture.get("summary"):
        lines += ["## Конспект", "", lecture["summary"], ""]
    points = lecture.get("summary_points") or []
    if points:
        lines += ["## Ключевые тезисы", ""]
        for point in points:
            lines.append(f"- **[{format_timestamp(point.get('start', 0))}]** {point.get('text', '')}")
        lines.append("")
    chapters = lecture.get("chapters") or []
    if chapters:
        lines += ["## Структура лекции", ""]
        for chapter in chapters:
            lines.append(f"### [{format_timestamp(chapter.get('start', 0))}] {chapter.get('title', '')}")
            if chapter.get("summary"):
                lines.append(chapter["summary"])
            lines.append("")
    if cues:
        lines += ["## Расшифровка", ""]
        for cue in cues:
            lines.append(f"**[{format_timestamp(cue['start'])}]** {cue['text']}")
            lines.append("")
    content = "\n".join(lines).strip() + "\n"
    filename = re.sub(r"[^\w\-]+", "_", lecture["title"], flags=re.UNICODE)[:80] or "lecture"
    encoded = quote(f"{filename}.md")
    return Response(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=lecture.md; filename*=UTF-8''{encoded}"
        },
    )


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=500),
    lecture_id: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
    min_score: float | None = Query(default=None, ge=0, le=1),
) -> dict:
    service = get_search_service()
    return service.search(q, lecture_id=lecture_id, limit=limit, min_score=min_score)


@router.get("/search/suggest")
def suggest(q: str = Query(default="", max_length=100)) -> dict:
    return {"items": get_search_service().suggest(q)}


@router.post("/lectures/{lecture_id}/ask")
def ask(lecture_id: str, payload: AskRequest) -> dict:
    _get_lecture(lecture_id)
    service = get_qa_service(get_search_service())
    try:
        return service.ask(lecture_id, payload.question, limit=payload.limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/stats")
def stats() -> dict:
    with db.db() as conn:
        lecture_stats = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS ready,
                      SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) AS processing,
                      SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                      COALESCE(SUM(duration), 0) AS duration,
                      COALESCE(SUM(views), 0) AS views
               FROM lectures"""
        ).fetchone()
        segment_count = conn.execute("SELECT COUNT(*) AS c FROM segments").fetchone()["c"]
        chapter_count = conn.execute("SELECT COUNT(*) AS c FROM chapters").fetchone()["c"]
        queries = conn.execute(
            """SELECT query, COUNT(*) AS c FROM events
               WHERE kind='search' AND query IS NOT NULL AND query != ''
               GROUP BY lower(query) ORDER BY c DESC LIMIT 6"""
        ).fetchall()
        languages = conn.execute(
            """SELECT language, COUNT(*) AS c FROM lectures
               WHERE language IS NOT NULL GROUP BY language ORDER BY c DESC"""
        ).fetchall()
    duration = float(lecture_stats["duration"] or 0)
    return {
        "lectures": int(lecture_stats["total"] or 0),
        "ready": int(lecture_stats["ready"] or 0),
        "processing": int(lecture_stats["processing"] or 0),
        "failed": int(lecture_stats["failed"] or 0),
        "segments": int(segment_count),
        "chapters": int(chapter_count),
        "hours": round(duration / 3600, 2),
        "duration": round(duration, 1),
        "views": int(lecture_stats["views"] or 0),
        "trending": [{"query": row["query"], "count": row["c"]} for row in queries],
        "languages": [{"language": row["language"], "count": row["c"]} for row in languages],
        "disk": media.disk_usage(),
        "db_size": Path(settings.db_path).stat().st_size if Path(settings.db_path).exists() else 0,
    }


@router.get("/health")
def health() -> dict:
    warnings = []
    try:
        with db.db() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
        warnings.append("База данных недоступна.")
    ffmpeg_ok = bool(settings.ffmpeg and settings.ffprobe)
    if not ffmpeg_ok:
        warnings.append("ffmpeg/ffprobe не найдены: загрузка видео не будет работать.")
    asr = asr_status()
    if not asr["model_present"]:
        warnings.append("Модель Whisper ещё не скачана: первый запуск потребует интернет.")
    embedding = embedding_status()
    if not embedding["model_present"] and settings.embedding_backend in {"auto", "model2vec", "local"}:
        warnings.append("Модель эмбеддингов не найдена: используется лексический резерв.")
    llm = llm_status()
    return {
        "status": "ok" if db_ok and ffmpeg_ok else "degraded",
        "version": settings.version,
        "db": {"ok": db_ok, "path": str(settings.db_path)},
        "ffmpeg": ffmpeg_ok,
        "asr": asr,
        "embeddings": embedding,
        "llm": llm,
        "pipeline": pipeline_status(),
        "warnings": warnings,
        "time": int(time.time()),
    }


@router.get("/diagnostics/ffmpeg")
def ffmpeg_version() -> dict:
    if not settings.ffmpeg:
        raise HTTPException(503, "ffmpeg не найден.")
    try:
        result = subprocess.run(
            [settings.ffmpeg, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc
    line = result.stdout.decode("utf-8", "replace").splitlines()[0] if result.stdout else ""
    return {"ok": result.returncode == 0, "version": line}


@router.get("/meta")
def meta() -> dict:
    return {
        **settings.public_dict(),
        "capabilities": {
            "upload": True,
            "youtube_import": True,
            "vimeo_import": True,
            "semantic_search": True,
            "qa": True,
            "export_markdown": True,
            "subtitles_vtt": True,
            "llm": settings.llm_ready,
        },
    }
