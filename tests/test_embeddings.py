"""Тесты эмбеддингов: форма, нормализация, устойчивость к морфологии."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.embeddings import (
    BaseEmbedder,
    HashingEmbedder,
    build_embedder,
    embedding_status,
    get_embedder,
    set_embedder,
)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


@pytest.fixture
def hashing() -> HashingEmbedder:
    return HashingEmbedder()


class TestHashingEmbedder:
    def test_shape_and_dtype(self, hashing):
        matrix = hashing.encode_documents(["теорема", "гипотенуза"])
        assert matrix.shape == (2, hashing.dim)
        assert matrix.dtype == np.float32

    def test_vectors_are_normalized(self, hashing):
        matrix = hashing.encode_documents(["квадрат гипотенузы", "нейронная сеть"])
        norms = np.linalg.norm(matrix, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)

    def test_empty_text_is_zero_vector(self, hashing):
        matrix = hashing.encode_documents([""])
        assert np.allclose(matrix, 0.0)

    def test_deterministic(self, hashing):
        first = hashing.encode_documents(["теорема пифагора"])
        second = hashing.encode_documents(["теорема пифагора"])
        assert np.array_equal(first, second)

    def test_query_returns_one_dimension(self, hashing):
        vector = hashing.encode_query("теорема")
        assert vector.shape == (hashing.dim,)

    def test_morphology_is_close(self, hashing):
        a = hashing.encode_query("теоремы пифагора")
        b = hashing.encode_query("теорема пифагора")
        unrelated = hashing.encode_query("прогноз погоды на завтра")
        assert cosine(a, b) > cosine(a, unrelated)
        assert cosine(a, b) > 0.7

    def test_semantic_match_beats_unrelated(self, hashing):
        query = hashing.encode_query("теорема пифагора")
        relevant = hashing.encode_query("Пифагор доказал теорему о гипотенузе и катетах")
        unrelated = hashing.encode_query("нейронная сеть обучается градиентным спуском")
        assert cosine(query, relevant) > cosine(query, unrelated)

    def test_batch_matches_single(self, hashing):
        texts = ["первый текст", "второй текст"]
        batch = hashing.encode_documents(texts)
        single = hashing.encode_documents([texts[0]])[0]
        assert np.allclose(batch[0], single, atol=1e-6)

    def test_status(self, hashing):
        status = hashing.status()
        assert status["backend"] == "hashing"
        assert status["dim"] == hashing.dim
        assert status["ready"] is True


class TestFactory:
    def test_build_hashing(self):
        embedder = build_embedder("hashing")
        assert isinstance(embedder, HashingEmbedder)

    def test_get_and_set(self, hashing):
        set_embedder(hashing)
        assert get_embedder() is hashing

    def test_base_embedder_not_implemented(self):
        with pytest.raises(NotImplementedError):
            BaseEmbedder().encode_documents(["x"])

    def test_embedding_status(self, hashing):
        set_embedder(hashing)
        status = embedding_status()
        assert status["active"] == "hashing"
        assert status["dim"] == hashing.dim
        assert "model_present" in status
