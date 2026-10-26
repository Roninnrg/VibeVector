"""Загрузка офлайн-моделей: faster-whisper и model2vec.

Модели складываются в ``data/models`` и после этого приложение работает без
интернета. Скрипт не скачивает повторно то, что уже лежит на диске.

Запуск:
    python scripts/download_models.py
    python scripts/download_models.py --whisper base
    python scripts/download_models.py --force --skip-embeddings
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

EMBEDDING_REPO = "minishlab/potion-multilingual-128M"
EMBEDDING_FILES = [
    "config.json",
    "modules.json",
    "tokenizer.json",
    "model.safetensors",
    "README.md",
]


def _snapshot(repo_id: str, target: Path, allow_patterns: list[str] | None = None,
              force: bool = False) -> None:
    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        allow_patterns=allow_patterns,
        force_download=force,
    )


def download_whisper(model_name: str, force: bool = False) -> Path:
    target = settings.models_dir / f"whisper-{model_name}"
    if (target / "model.bin").exists() and not force:
        print(f"Whisper уже на месте: {target}")
        return target
    repo = f"Systran/faster-whisper-{model_name}"
    print(f"Загружаю Whisper «{model_name}»: {repo}")
    _snapshot(repo, target, [
        "config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.txt",
        "preprocessor_config.json",
    ], force=force)
    print(f"  + {target}")
    return target


def download_embeddings(force: bool = False) -> Path:
    target = settings.embedder_model_dir
    weights = target / "embeddings.f16.npy"
    if (target / "model.safetensors").exists() and (target / "tokenizer.json").exists() and not force:
        print(f"Эмбеддинги уже на месте: {target}")
    else:
        print(f"Загружаю эмбеддинги: {EMBEDDING_REPO}")
        _snapshot(EMBEDDING_REPO, target, EMBEDDING_FILES, force=force)
        print(f"  + {target}")

    if not weights.exists() or force:
        print("Конвертирую веса в компактный float16 для memmap…")
        from app.services.embeddings import Model2VecEmbedder

        embedder = Model2VecEmbedder()
        embedder._load()  # noqa: SLF001 - публичного метода подготовки нет
        print(f"  + {weights} ({weights.stat().st_size / (1024 * 1024):.0f} МБ)")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузка офлайн-моделей «Вектора».")
    parser.add_argument("--whisper", default=settings.whisper_model,
                        help="Размер Whisper: tiny/base/small/medium/large-v3.")
    parser.add_argument("--force", action="store_true", help="Скачать заново.")
    parser.add_argument("--skip-whisper", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    settings.ensure_dirs()
    if not args.skip_whisper:
        download_whisper(args.whisper, force=args.force)
    if not args.skip_embeddings:
        download_embeddings(force=args.force)
    print("\nМодели готовы. Дальше интернет не нужен.")


if __name__ == "__main__":
    main()
