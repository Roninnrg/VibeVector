"""Конфигурация приложения «Вектор»."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    app_name: str = "Вектор"
    version: str = "1.0.0"
    base_dir: Path = BASE_DIR
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("VECTOR_DATA_DIR", BASE_DIR / "data")))
    db_path: Path | None = None
    media_dir: Path | None = None
    audio_dir: Path | None = None
    thumb_dir: Path | None = None
    models_dir: Path | None = None
    tools_dir: Path = BASE_DIR / "tools"

    max_upload_mb: int = _env_int("MAX_UPLOAD_MB", 2048)
    max_duration_sec: int = _env_int("MAX_DURATION_SEC", 4 * 60 * 60)
    allowed_media_ext: tuple[str, ...] = (
        ".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi",
        ".mp3", ".m4a", ".wav", ".ogg", ".opus",
    )

    # ASR
    asr_backend: str = os.getenv("ASR_BACKEND", "auto").strip().lower()
    whisper_model: str = os.getenv("WHISPER_MODEL", "small").strip()
    whisper_compute: str = os.getenv("WHISPER_COMPUTE", "int8").strip()
    whisper_language: str = os.getenv("WHISPER_LANGUAGE", "auto").strip()
    asr_cpu_threads: int = _env_int("ASR_CPU_THREADS", max(2, min(8, (os.cpu_count() or 4) - 2)))

    # Embeddings
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "auto").strip().lower()
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "minishlab/potion-multilingual-128M").strip()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    openai_embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()

    # LLM (optional, OpenAI-compatible: OpenAI / OpenRouter / Ollama)
    llm_enabled: bool = _env_bool("LLM_ENABLED", False)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "").strip()
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    llm_timeout: int = _env_int("LLM_TIMEOUT", 90)

    # Search
    search_min_score: float = float(os.getenv("SEARCH_MIN_SCORE", "0.16"))
    search_default_limit: int = _env_int("SEARCH_DEFAULT_LIMIT", 12)

    # Demo / UI
    seed_demo: bool = _env_bool("SEED_DEMO", False)
    admin_token: str = os.getenv("VECTOR_ADMIN_TOKEN", "").strip()
    log_level: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.db_path = Path(os.getenv("VECTOR_DB", self.data_dir / "vector.db"))
        self.media_dir = self.data_dir / "media"
        self.audio_dir = self.data_dir / "audio"
        self.thumb_dir = self.data_dir / "thumbnails"
        self.models_dir = Path(os.getenv("VECTOR_MODELS_DIR", self.data_dir / "models"))

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.media_dir, self.audio_dir, self.thumb_dir, self.models_dir):
            Path(path).mkdir(parents=True, exist_ok=True)

    @property
    def whisper_model_dir(self) -> Path:
        return self.models_dir / f"whisper-{self.whisper_model}"

    @property
    def embedder_model_dir(self) -> Path:
        return self.models_dir / "potion-multilingual-128M"

    @property
    def ffmpeg(self) -> str | None:
        return self._find_binary("ffmpeg")

    @property
    def ffprobe(self) -> str | None:
        return self._find_binary("ffprobe")

    def _find_binary(self, name: str) -> str | None:
        explicit = os.getenv(f"{name.upper()}_PATH", "").strip()
        if explicit and Path(explicit).exists():
            return explicit
        candidates = [
            self.tools_dir / "ffmpeg" / "bin" / f"{name}.exe",
            self.tools_dir / "ffmpeg" / "bin" / name,
            self.tools_dir / "ffmpeg" / f"{name}.exe",
            self.tools_dir / "ffmpeg" / name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which(name)

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_enabled and self.llm_base_url and self.llm_model)

    def public_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "version": self.version,
            "llm_ready": self.llm_ready,
            "asr_backend": self.asr_backend,
            "embedding_backend": self.embedding_backend,
            "max_upload_mb": self.max_upload_mb,
        }


settings = Settings()
settings.ensure_dirs()
