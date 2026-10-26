"""Распознавание речи: faster-whisper + аккуратная нарезка на субтитры.

На Python 3.15 у PyAV пока нет колёс, поэтому мы не используем его декодер:
аудио извлекает ffmpeg, а faster-whisper получает numpy-массив. Небольшой
shim позволяет импортировать пакет без установленного PyAV.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import types
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from ..config import settings

log = logging.getLogger(__name__)


def install_av_shim() -> None:
    """Разрешает импорт faster_whisper, когда PyAV недоступен."""
    try:
        import av  # noqa: F401
        return
    except Exception:
        pass
    if "av" in sys.modules:
        return

    class _Unavailable:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "PyAV не установлен. Аудио декодируется через ffmpeg и передаётся в Whisper как numpy-массив."
            )

    av = types.ModuleType("av")
    audio = types.ModuleType("av.audio")
    resampler = types.ModuleType("av.audio.resampler")
    fifo = types.ModuleType("av.audio.fifo")
    error = types.ModuleType("av.error")
    resampler.AudioResampler = _Unavailable
    fifo.AudioFifo = _Unavailable
    error.InvalidDataError = RuntimeError
    audio.resampler = resampler
    audio.fifo = fifo
    av.audio = audio
    av.error = error
    av.open = _Unavailable
    av.AudioFrame = _Unavailable
    sys.modules["av"] = av
    sys.modules["av.audio"] = audio
    sys.modules["av.audio.resampler"] = resampler
    sys.modules["av.audio.fifo"] = fifo
    sys.modules["av.error"] = error


@dataclass
class ASRResult:
    cues: list[dict]
    language: str = "ru"
    language_probability: float = 0.0
    provider: str = "faster-whisper"
    duration: float = 0.0
    text: str = ""


def read_wav_16k(path: str | Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise RuntimeError("Ожидается mono PCM16 WAV, подготовленный через ffmpeg.")
        frames = handle.readframes(handle.getnframes())
        rate = handle.getframerate()
    array = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != 16000:
        raise RuntimeError(f"Ожидается 16000 Гц, получено {rate} Гц.")
    return array


def _clean_word(word: str) -> str:
    return word.replace("\n", " ").strip()


def words_to_cues(words: Iterable[dict], fallback_segments: Iterable[dict] | None = None,
                  max_duration: float = 13.0, max_chars: int = 260) -> list[dict]:
    """Склеивает слова Whisper в читаемые реплики с таймкодами."""
    cues: list[dict] = []
    current: list[dict] = []
    current_start = 0.0
    current_chars = 0
    last_end = 0.0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        pieces: list[str] = []
        for w in current:
            token = _clean_word(str(w["word"] or ""))
            if not token:
                continue
            if not pieces:
                pieces.append(token)
            elif token[0] in ",.!?;:…%)]}»”":
                # Пунктуация не должна отделяться пробелом от слова: «мир .» → «мир.»
                pieces[-1] += token
            elif token.startswith(("-", "—")):
                pieces[-1] += token
            else:
                pieces.append(" " + token)
        text = _clean_word("".join(pieces))

        if not text:
            current = []
            current_chars = 0
            return
        start = float(current[0]["start"])
        end = float(current[-1]["end"])
        if end <= start:
            end = start + 0.6
        cues.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "words": [
                    {
                        "start": round(float(w["start"]), 3),
                        "end": round(float(w["end"]), 3),
                        "word": _clean_word(w["word"]),
                        "probability": round(float(w.get("probability") or 0), 3),
                    }
                    for w in current
                ],
            }
        )
        current = []
        current_chars = 0

    for raw in words:
        word = _clean_word(str(raw.get("word") or ""))
        if not word:
            continue
        start = float(raw.get("start") or 0)
        end = float(raw.get("end") or start)
        if not current:
            current_start = start
        gap = start - last_end if last_end else 0.0
        projected = end - current_start
        if current and (
            gap > 1.15
            or projected > max_duration
            or current_chars + len(word) > max_chars
            or (word[:1].isupper() and current_chars > 0 and gap > 0.55)
        ):
            flush()
            current_start = start
        current.append({"word": word, "start": start, "end": end,
                        "probability": raw.get("probability") or 0})
        current_chars += len(word) + 1
        last_end = end
        if word.rstrip().endswith((".", "!", "?", "…", ":", ";")):
            flush()
    flush()

    if not cues and fallback_segments:
        for seg in fallback_segments:
            text = _clean_word(str(seg.get("text") or ""))
            if not text:
                continue
            cues.append(
                {
                    "start": round(float(seg.get("start") or 0), 3),
                    "end": round(float(seg.get("end") or 0), 3),
                    "text": text,
                    "words": [],
                }
            )

    # нормализуем границы и убираем пустые дубли
    cleaned: list[dict] = []
    for cue in cues:
        cue["start"] = max(0.0, cue["start"])
        cue["end"] = max(cue["start"] + 0.35, cue["end"])
        if cleaned and cue["start"] < cleaned[-1]["end"] - 0.05:
            cue["start"] = cleaned[-1]["end"]
            cue["end"] = max(cue["start"] + 0.35, cue["end"])
        if cleaned and cue["text"].strip().lower() == cleaned[-1]["text"].strip().lower():
            cleaned[-1]["end"] = max(cleaned[-1]["end"], cue["end"])
            continue
        cleaned.append(cue)
    return cleaned


class WhisperASR:
    provider = "faster-whisper"

    def __init__(self, model_name: str | None = None, model_dir: Path | None = None,
                 compute_type: str | None = None, cpu_threads: int | None = None):
        install_av_shim()
        from faster_whisper import WhisperModel  # noqa: WPS433

        self.model_name = model_name or settings.whisper_model
        self.model_dir = Path(model_dir or settings.whisper_model_dir)
        self.compute_type = compute_type or settings.whisper_compute
        self.cpu_threads = cpu_threads or settings.asr_cpu_threads
        self._model = None
        self._cls = WhisperModel

    def _load(self):
        if self._model is not None:
            return self._model
        if self.model_dir.exists() and (self.model_dir / "model.bin").exists():
            target = str(self.model_dir)
            log.info("Загружаю Whisper из %s", target)
        else:
            target = self.model_name
            log.info("Загружаю Whisper «%s» (будет скачан при необходимости)", target)
        self._model = self._cls(
            target,
            device="cpu",
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            download_root=str(settings.models_dir) if not self.model_dir.exists() else None,
        )
        return self._model

    def transcribe(self, audio_path: str | Path, duration: float = 0.0,
                   language: str | None = None,
                   on_progress: Callable[[float], None] | None = None) -> ASRResult:
        audio = read_wav_16k(audio_path)
        model = self._load()
        lang = language or settings.whisper_language
        if lang in {"", "auto", "none"}:
            lang = None
        segments, info = model.transcribe(
            audio,
            language=lang,
            task="transcribe",
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=True,
            word_timestamps=True,
            vad_filter=False,
            no_speech_threshold=0.65,
            compression_ratio_threshold=2.5,
            log_prob_threshold=-1.0,
        )
        all_words: list[dict] = []
        fallback: list[dict] = []
        for segment in segments:
            fallback.append(
                {"start": segment.start, "end": segment.end, "text": segment.text}
            )
            for word in getattr(segment, "words", None) or []:
                all_words.append(
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": getattr(word, "probability", 0.0),
                    }
                )
            if on_progress and duration > 0:
                on_progress(min(0.99, max(0.0, float(segment.end) / duration)))
        cues = words_to_cues(all_words, fallback)
        text = " ".join(cue["text"] for cue in cues).strip()
        return ASRResult(
            cues=cues,
            language=getattr(info, "language", None) or lang or "ru",
            language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            provider=self.provider,
            duration=float(duration or (cues[-1]["end"] if cues else 0)),
            text=text,
        )


class MockASR:
    """Детерминированный ASR для тестов и демонстрации без модели."""

    provider = "mock"

    def __init__(self, fixture: str | Path | dict | None = None):
        self.fixture = fixture

    def transcribe(self, audio_path: str | Path, duration: float = 0.0,
                   language: str | None = None,
                   on_progress: Callable[[float], None] | None = None) -> ASRResult:
        data: dict = {}
        if isinstance(self.fixture, dict):
            data = self.fixture
        elif self.fixture:
            data = json.loads(Path(self.fixture).read_text(encoding="utf-8"))
        cues = data.get("cues") or [
            {"start": 0.0, "end": 5.0, "text": "Сегодня мы разберём теорему Пифагора.", "words": []},
            {"start": 5.0, "end": 12.0, "text": "Квадрат гипотенузы равен сумме квадратов катетов.", "words": []},
        ]
        if on_progress:
            on_progress(1.0)
        return ASRResult(
            cues=cues,
            language=data.get("language", language or "ru"),
            language_probability=0.99,
            provider=self.provider,
            duration=duration or cues[-1]["end"],
            text=" ".join(c["text"] for c in cues),
        )


_ASR_SINGLETON: WhisperASR | None = None


def get_asr() -> WhisperASR:
    global _ASR_SINGLETON
    if _ASR_SINGLETON is None:
        _ASR_SINGLETON = WhisperASR()
    return _ASR_SINGLETON


def asr_status() -> dict:
    model_dir = settings.whisper_model_dir
    model_present = (model_dir / "model.bin").exists()
    try:
        install_av_shim()
        import faster_whisper  # noqa: F401
        package = True
    except Exception:
        package = False
    return {
        "provider": "faster-whisper",
        "package_installed": package,
        "model": settings.whisper_model,
        "model_present": model_present,
        "compute_type": settings.whisper_compute,
        "cpu_threads": settings.asr_cpu_threads,
        "ready": package,
    }
