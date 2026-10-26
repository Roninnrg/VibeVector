"""Работа с медиа: ffprobe, извлечение аудио, превью,Range-отдача."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import settings


class MediaError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return bool(settings.ffmpeg and settings.ffprobe)


def _run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise MediaError("ffmpeg не найден. Запустите `python scripts/setup_tools.py`.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Обработка медиа заняла слишком много времени.") from exc


def probe(path: str | Path) -> dict:
    ffprobe = settings.ffprobe
    if not ffprobe:
        raise MediaError("ffprobe не найден. Запустите `python scripts/setup_tools.py`.")
    result = _run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        timeout=60,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace")[:500]
        raise MediaError(f"Не удалось прочитать медиафайл: {message}")
    try:
        data = json.loads(result.stdout.decode("utf-8", "replace"))
    except ValueError as exc:
        raise MediaError("ffprobe вернул некорректный ответ.") from exc
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video and not audio:
        raise MediaError("В файле не найдено видео или аудио.")
    duration = float(data.get("format", {}).get("duration") or 0)
    if duration <= 0:
        durations = [float(s.get("duration") or 0) for s in streams]
        duration = max(durations or [0])
    if duration <= 0:
        raise MediaError("Не удалось определить длительность файла.")
    if duration > settings.max_duration_sec:
        raise MediaError(
            f"Файл длиннее {settings.max_duration_sec // 3600} ч. "
            "Разделите лекцию на части."
        )
    mime = "video/mp4"
    fmt = (data.get("format", {}).get("format_name") or "").lower()
    if "webm" in fmt:
        mime = "video/webm"
    elif audio and not video:
        mime = "audio/mpeg" if "mp3" in fmt else "audio/mp4"
    return {
        "duration": round(duration, 3),
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
        "video_codec": (video or {}).get("codec_name"),
        "audio_codec": (audio or {}).get("codec_name"),
        "has_video": bool(video),
        "has_audio": bool(audio),
        "format": fmt,
        "mime": mime,
        "size": int(data.get("format", {}).get("size") or 0),
    }


def extract_audio(source: str | Path, destination: str | Path, on_progress=None) -> Path:
    """Извлекает нормализованный mono WAV 16 kHz для распознавания речи."""
    ffmpeg = settings.ffmpeg
    if not ffmpeg:
        raise MediaError("ffmpeg не найден. Запустите `python scripts/setup_tools.py`.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            "-af", "highpass=f=60,lowpass=f=7800",
            str(destination),
        ],
        timeout=900,
    )
    if result.returncode != 0 or not destination.exists():
        message = result.stderr.decode("utf-8", "replace")[:700]
        raise MediaError(f"Не удалось извлечь аудиодорожку: {message}")
    return destination


def make_thumbnail(source: str | Path, destination: str | Path, at: float = 3.0) -> Path | None:
    ffmpeg = settings.ffmpeg
    if not ffmpeg:
        return None
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{max(0.0, at):.2f}", "-i", str(source),
            "-frames:v", "1", "-vf", "scale=960:-2:force_original_aspect_ratio=decrease",
            "-q:v", "3", str(destination),
        ],
        timeout=90,
    )
    if result.returncode != 0 or not destination.exists():
        return None
    return destination


def sanitize_filename(name: str, fallback: str = "lecture") -> str:
    name = Path(name or "").name
    name = re.sub(r"[^\w.\- ()]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or fallback


def safe_unlink(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def safe_rmtree(path: str | Path | None) -> None:
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def media_type_for(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    mapping = {
        ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
        ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav",
        ".ogg": "audio/ogg", ".opus": "audio/ogg",
    }
    return mapping.get(suffix, "application/octet-stream")


def iter_file(path: Path, start: int = 0, end: int | None = None, chunk_size: int = 1024 * 256):
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = None if end is None else end - start + 1
        while True:
            size = chunk_size if remaining is None else min(chunk_size, remaining)
            if size <= 0:
                break
            data = handle.read(size)
            if not data:
                break
            yield data
            if remaining is not None:
                remaining -= len(data)
                if remaining <= 0:
                    break


def disk_usage() -> dict:
    total, used, free = shutil.disk_usage(settings.data_dir)
    return {"total": total, "used": used, "free": free}


def temp_path(suffix: str = "") -> Path:
    handle, name = tempfile.mkstemp(suffix=suffix, dir=str(settings.data_dir))
    os.close(handle)
    return Path(name)
