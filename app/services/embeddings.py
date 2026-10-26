"""Семантические эмбеддинги: model2vec (офлайн), хэширующий резерв, OpenAI."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import struct
import threading
from pathlib import Path

import numpy as np

from ..config import settings
from ..text import lemmatize, words

log = logging.getLogger(__name__)


def _normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class BaseEmbedder:
    name = "base"
    dim = 0
    ready = False

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode_documents([text])[0]

    def status(self) -> dict:
        return {"backend": self.name, "dim": self.dim, "ready": self.ready}


class HashingEmbedder(BaseEmbedder):
    """Быстрый офлайн-резерв: леммы, символьные n-граммы и синонимы.

    Не нейросеть, но заметно устойчивее точного совпадения слов: учитывает
    морфологию, опечатки и словарь близких по смыслу терминов.
    """

    name = "hashing"
    dim = 768

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.ready = True
        from ..text import _SYNONYMS  # noqa: WPS433

        self._synonyms = _SYNONYMS

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        index = value % self.dim
        sign = 1.0 if (value >> 63) & 1 == 0 else -1.0
        return index, sign

    def _features(self, text: str) -> dict[str, float]:
        features: dict[str, float] = {}
        lemmas = lemmatize(text, keep_stop=True)
        content = [w for w in lemmas if w not in {"и", "в", "на", "с", "по", "не", "что", "это"}]
        for term in content:
            features[f"w:{term}"] = features.get(f"w:{term}", 0.0) + 1.0
            for syn in self._synonyms.get(term, ()):
                features[f"w:{syn}"] = features.get(f"w:{syn}", 0.0) + 0.22
        for i in range(len(content) - 1):
            features[f"b:{content[i]}_{content[i + 1]}"] = 1.35
        lowered = re.sub(r"\s+", " ", text.lower().replace("ё", "е"))
        for token in words(lowered):
            padded = f"#{token}#"
            for n in (3, 4, 5):
                for i in range(0, max(1, len(padded) - n + 1)):
                    gram = padded[i:i + n]
                    features[f"c:{gram}"] = features.get(f"c:{gram}", 0.0) + 0.35
        if len(lowered) > 2:
            features[f"q:{lowered}"] = 1.2
        return features

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        result = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            features = self._features(text or "")
            for feature, weight in features.items():
                index, sign = self._bucket(feature)
                result[row, index] += sign * weight
        return _normalize(result)


class Model2VecEmbedder(BaseEmbedder):
    """Статические эмбеддинги model2vec без загрузки всей матрицы в RAM.

    Штатный загрузчик model2vec копирует полугигабайтную матрицу в память и на
    машинах с 8 ГБ RAM падает с MemoryError рядом с Whisper. Здесь веса один раз
    переводятся в float16-`.npy`, а затем открываются через memmap: в память
    попадают только реально нужные строки словаря. Токенизация и mean-pooling
    повторяют поведение StaticModel.
    """

    name = "model2vec"

    def __init__(self, model_path: Path | None = None, model_id: str | None = None):
        self.model_path = Path(model_path or settings.embedder_model_dir)
        self.model_id = model_id or settings.embedding_model
        self._embeddings = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self.dim = 0
        self.ready = False

    @property
    def weights_path(self) -> Path:
        return self.model_path / "embeddings.f16.npy"

    @property
    def model_present(self) -> bool:
        return self.weights_path.exists() or (self.model_path / "model.safetensors").exists()

    def _convert_weights(self) -> Path:
        source = self.model_path / "model.safetensors"
        if not source.exists():
            raise FileNotFoundError(
                f"Модель эмбеддингов не найдена: {source}. "
                "Запустите scripts/download_models.py."
            )
        destination = self.weights_path
        temporary = destination.with_suffix(".tmp.npy")
        with open(source, "rb") as handle:
            header_size = struct.unpack("<Q", handle.read(8))[0]
            header = json.loads(handle.read(header_size))
            tensors = {key: value for key, value in header.items() if key != "__metadata__"}
            if not tensors:
                raise ValueError("В model.safetensors нет тензоров.")
            key = "embeddings" if "embeddings" in tensors else next(iter(tensors))
            tensor = tensors[key]
            if tensor.get("dtype") != "F32":
                raise ValueError(f"Ожидался F32, получен {tensor.get('dtype')}.")
            rows, cols = (int(value) for value in tensor["shape"])
            offset = int(tensor["data_offsets"][0])
            data_start = 8 + header_size + offset
            log.info("Готовлю компактные веса эмбеддингов: %s → %s", source.name, destination.name)
            array = np.lib.format.open_memmap(
                temporary, mode="w+", dtype=np.float16, shape=(rows, cols)
            )
            bytes_per_row = cols * 4
            chunk_rows = max(1, 8 * 1024 * 1024 // bytes_per_row)
            handle.seek(data_start)
            for start in range(0, rows, chunk_rows):
                count = min(chunk_rows, rows - start)
                raw = handle.read(count * bytes_per_row)
                if len(raw) != count * bytes_per_row:
                    raise ValueError("Файл модели повреждён: неожиданный конец данных.")
                chunk = np.frombuffer(raw, dtype=np.float32).reshape(count, cols)
                array[start:start + count] = chunk.astype(np.float16)
            array.flush()
            del array
        temporary.replace(destination)
        return destination

    def _load(self):
        if self._embeddings is not None:
            return self._embeddings
        with self._lock:
            if self._embeddings is not None:
                return self._embeddings
            from tokenizers import Tokenizer  # noqa: WPS433

            if not self.weights_path.exists():
                self._convert_weights()
            tokenizer_file = self.model_path / "tokenizer.json"
            if not tokenizer_file.exists():
                raise FileNotFoundError(f"Не найден токенизатор: {tokenizer_file}")
            tokenizer = Tokenizer.from_file(str(tokenizer_file))
            tokenizer.enable_truncation(max_length=512)
            embeddings = np.load(self.weights_path, mmap_mode="r")
            if embeddings.ndim != 2:
                raise ValueError("Некорректная форма матрицы эмбеддингов.")
            self._tokenizer = tokenizer
            self._embeddings = embeddings
            self.dim = int(embeddings.shape[1])
            self.ready = True
            log.info(
                "Эмбеддинги готовы: %s, %s×%s, memmap %s МБ",
                self.model_id, embeddings.shape[0], embeddings.shape[1],
                embeddings.shape[0] * embeddings.shape[1] * 2 // (1024 * 1024),
            )
            return embeddings

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim or 256), dtype=np.float32)
        embeddings = self._load()
        encodings = self._tokenizer.encode_batch(
            [text if text and text.strip() else " " for text in texts],
            add_special_tokens=False,
        )
        output = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, encoding in enumerate(encodings):
            ids = [token_id for token_id in encoding.ids if token_id not in {0, 1}]
            if not ids:
                continue
            vectors = np.asarray(embeddings[np.asarray(ids, dtype=np.int64)], dtype=np.float32)
            output[row] = vectors.mean(axis=0)
        return _normalize(output)

    def status(self) -> dict:
        return {
            "backend": self.name,
            "model": self.model_id,
            "path": str(self.model_path),
            "model_present": self.model_present,
            "weights": str(self.weights_path) if self.weights_path.exists() else None,
            "dim": self.dim,
            "ready": self.ready,
        }


class OpenAIEmbedder(BaseEmbedder):
    name = "openai"

    def __init__(self):
        self.dim = 1536
        self.ready = bool(settings.openai_api_key)
        self.model = settings.openai_embedding_model
        self._client = None

    def _load(self):
        if self._client is not None:
            return self._client
        import httpx

        self._client = httpx.Client(
            base_url=settings.openai_base_url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=60,
        )
        return self._client

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        if not self.ready:
            raise RuntimeError("OPENAI_API_KEY не задан.")
        client = self._load()
        vectors: list[list[float]] = []
        batch_size = 64
        for start in range(0, len(texts), batch_size):
            batch = [t or " " for t in texts[start:start + batch_size]]
            response = client.post(
                "/embeddings",
                json={"model": self.model, "input": batch, "encoding_format": "float"},
            )
            response.raise_for_status()
            payload = response.json()
            vectors.extend(item["embedding"] for item in payload["data"])
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.size:
            self.dim = int(matrix.shape[1])
        return _normalize(matrix)

    def status(self) -> dict:
        return {
            "backend": self.name,
            "model": self.model,
            "configured": self.ready,
            "dim": self.dim,
            "ready": self.ready,
        }


_EMBEDDER: BaseEmbedder | None = None
_EMBEDDER_LOCK = threading.Lock()


def build_embedder(backend: str | None = None) -> BaseEmbedder:
    backend = (backend or settings.embedding_backend or "auto").lower()
    if backend == "openai":
        return OpenAIEmbedder()
    if backend in {"model2vec", "static", "local"}:
        return Model2VecEmbedder()
    if backend == "hashing":
        return HashingEmbedder()
    # auto: локальная модель, если файлы уже есть; иначе лексический резерв.
    return Model2VecEmbedder()


def get_embedder() -> BaseEmbedder:
    global _EMBEDDER
    if _EMBEDDER is None:
        with _EMBEDDER_LOCK:
            if _EMBEDDER is None:
                candidate = build_embedder()
                if isinstance(candidate, Model2VecEmbedder) and not candidate.model_present:
                    # Не блокируем первый запрос скачиванием полугигабайтной модели:
                    # резерв сразу работает, а модель подхватится после setup.
                    log.info("Локальная модель эмбеддингов ещё не скачана — использую резерв.")
                    candidate = HashingEmbedder()
                _EMBEDDER = candidate
    return _EMBEDDER


def set_embedder(embedder: BaseEmbedder) -> None:
    global _EMBEDDER
    _EMBEDDER = embedder


def embedding_status() -> dict:
    backend = settings.embedding_backend
    path = settings.embedder_model_dir
    present = (path / "embeddings.f16.npy").exists() or (path / "model.safetensors").exists()
    embedder = get_embedder()
    return {
        "requested_backend": backend,
        "model": settings.embedding_model,
        "model_present": present,
        "model_path": str(path),
        "fallback": "hashing" if backend == "auto" and not present else None,
        "active": embedder.name,
        "dim": embedder.dim,
    }
