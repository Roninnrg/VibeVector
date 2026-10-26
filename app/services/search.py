"""Гибридный семантический поиск: dense + BM25 + покрытие + MMR."""
from __future__ import annotations

import math
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from .. import db
from ..config import settings
from ..text import STOPWORDS, highlight_html, query_terms, words
from .embeddings import get_embedder


@dataclass
class IndexRow:
    segment_id: int
    lecture_id: str
    idx: int
    start: float
    end: float
    text: str
    lemmas: list[str]
    vector: np.ndarray | None = None


@dataclass
class LectureMeta:
    id: str
    title: str
    duration: float
    language: str | None
    thumbnail_path: str | None


@dataclass
class SearchIndex:
    version: int = -1
    rows: list[IndexRow] = field(default_factory=list)
    vectors: np.ndarray | None = None
    token_counts: list[Counter] = field(default_factory=list)
    doc_lengths: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    avg_len: float = 1.0
    df: Counter = field(default_factory=Counter)
    idf: dict[str, float] = field(default_factory=dict)
    lectures: dict[str, LectureMeta] = field(default_factory=dict)
    embedder_name: str = ""

    @property
    def size(self) -> int:
        return len(self.rows)


class SearchService:
    def __init__(self):
        self._index = SearchIndex()
        self._lock = threading.RLock()
        self._embedder = get_embedder()

    # ------------------------------------------------------------------ index
    def refresh(self, force: bool = False) -> SearchIndex:
        version = db.index_version()
        if not force and self._index.version == version:
            return self._index
        with self._lock:
            version = db.index_version()
            if not force and self._index.version == version:
                return self._index
            rows: list[IndexRow] = []
            lectures: dict[str, LectureMeta] = {}
            with db.db() as conn:
                lecture_rows = conn.execute(
                    "SELECT id, title, duration, language, thumbnail_path, status FROM lectures WHERE status='ready'"
                ).fetchall()
                for lecture in lecture_rows:
                    lectures[lecture["id"]] = LectureMeta(
                        id=lecture["id"],
                        title=lecture["title"],
                        duration=float(lecture["duration"] or 0),
                        language=lecture["language"],
                        thumbnail_path=lecture["thumbnail_path"],
                    )
                segment_rows = conn.execute(
                    """SELECT s.id, s.lecture_id, s.idx, s.start, s.end, s.text, s.lemmas, s.vector, s.dim
                       FROM segments s JOIN lectures l ON l.id = s.lecture_id
                       WHERE l.status = 'ready'
                       ORDER BY l.created_at, s.idx"""
                ).fetchall()
            dim = 0
            for row in segment_rows:
                if row["vector"]:
                    dim = max(dim, int(row["dim"] or 0))
            matrix = np.zeros((len(segment_rows), max(1, dim)), dtype=np.float32)
            for i, row in enumerate(segment_rows):
                vector = None
                if row["vector"] and int(row["dim"] or 0) == dim:
                    vector = np.frombuffer(row["vector"], dtype=np.float32).copy()
                    if vector.shape[0] == dim:
                        matrix[i] = vector
                    else:
                        vector = None
                rows.append(
                    IndexRow(
                        segment_id=int(row["id"]),
                        lecture_id=row["lecture_id"],
                        idx=int(row["idx"]),
                        start=float(row["start"]),
                        end=float(row["end"]),
                        text=row["text"],
                        lemmas=row["lemmas"].split() if row["lemmas"] else [],
                        vector=vector,
                    )
                )
            index = SearchIndex(
                version=version,
                rows=rows,
                vectors=matrix if dim and len(rows) else None,
                token_counts=[Counter(r.lemmas) for r in rows],
                doc_lengths=np.asarray([len(r.lemmas) for r in rows], dtype=np.float32),
                df=Counter(),
                lectures=lectures,
                embedder_name=self._embedder.name,
            )
            for counts in index.token_counts:
                index.df.update(counts.keys())
            index.avg_len = float(index.doc_lengths.mean()) if len(rows) else 1.0
            n = len(rows)
            index.idf = {
                term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
                for term, freq in index.df.items()
            }
            self._index = index
            return index

    # ------------------------------------------------------------------ search
    def search(self, query: str, lecture_id: str | None = None, limit: int = 12,
               min_score: float | None = None, diversify: bool = True) -> dict:
        started = time.perf_counter()
        query = (query or "").strip()
        if not query:
            return {"query": query, "results": [], "count": 0, "took_ms": 0, "low_confidence": False}
        index = self.refresh()
        if not index.rows:
            return {"query": query, "results": [], "count": 0, "took_ms": 0, "low_confidence": False}
        limit = max(1, min(int(limit or 12), 50))
        threshold = settings.search_min_score if min_score is None else float(min_score)

        positions = list(range(len(index.rows)))
        if lecture_id:
            positions = [i for i in positions if index.rows[i].lecture_id == lecture_id]
        if not positions:
            return {"query": query, "results": [], "count": 0, "took_ms": 0, "low_confidence": False}

        q_weights = query_terms(query)
        base_terms = {t for t, w in q_weights.items() if w >= 0.9}
        if not q_weights:
            return {"query": query, "results": [], "count": 0, "took_ms": 0, "low_confidence": False}

        bm25_scores = np.zeros(len(positions), dtype=np.float32)
        density_scores = np.zeros(len(positions), dtype=np.float32)
        coverage_scores = np.zeros(len(positions), dtype=np.float32)
        phrase_scores = np.zeros(len(positions), dtype=np.float32)

        k1, b = 1.5, 0.72
        q_norm = " ".join(query.lower().replace("ё", "е").split())
        q_norm = q_norm.strip(" .,!?:;—-")
        for local, pos in enumerate(positions):
            counts = index.token_counts[pos]
            dl = index.doc_lengths[pos] or 1.0
            score = 0.0
            for term, weight in q_weights.items():
                tf = counts.get(term, 0)
                if not tf:
                    continue
                idf = index.idf.get(term, 0.0)
                score += weight * idf * (tf * (k1 + 1.0)) / (
                    tf + k1 * (1.0 - b + b * dl / max(1.0, index.avg_len))
                )
            bm25_scores[local] = score
            doc_lemmas = set(index.rows[pos].lemmas)
            covered = sum(w for t, w in q_weights.items() if t in doc_lemmas)
            total = sum(q_weights.values()) or 1.0
            coverage_scores[local] = min(1.0, covered / total)
            if q_norm and len(q_norm) >= 3:
                text_norm = " ".join(index.rows[pos].text.lower().replace("ё", "е").split())
                if q_norm in text_norm:
                    phrase_scores[local] = 1.0

        # dense cosine
        if index.vectors is not None and len(index.vectors):
            try:
                qvec = self._embedder.encode_query(query)
                if qvec.shape[0] == index.vectors.shape[1]:
                    sims = index.vectors[positions] @ qvec
                    density_scores = np.clip(sims, 0.0, 1.0).astype(np.float32)
            except Exception:
                density_scores = np.zeros(len(positions), dtype=np.float32)

        lex_norm = bm25_scores / (bm25_scores + 4.2 + 1e-9)
        has_dense = bool(np.any(density_scores > 0))
        if has_dense:
            if self._embedder.name == "hashing":
                scores = 0.50 * density_scores + 0.30 * lex_norm + 0.14 * coverage_scores + 0.06 * phrase_scores
            else:
                scores = 0.60 * density_scores + 0.22 * lex_norm + 0.12 * coverage_scores + 0.06 * phrase_scores
        else:
            scores = 0.62 * lex_norm + 0.28 * coverage_scores + 0.10 * phrase_scores

        # мягкая калибровка: убираем «серый фон» косинуса
        if has_dense and self._embedder.name != "hashing":
            scores = np.clip((scores - 0.08) / 0.92, 0.0, 1.0)

        order = np.argsort(-scores)[: max(limit * 4, 24)]
        candidate_indices: list[int] = []
        for local in order:
            if scores[local] < max(0.02, threshold * 0.55):
                continue
            candidate_indices.append(int(local))

        if diversify and len(candidate_indices) > 1:
            candidate_indices = self._mmr(candidate_indices, scores, positions, limit, index)

        results = []
        lecture_counts: Counter[str] = Counter()
        for local in candidate_indices:
            score = float(scores[local])
            if score < threshold:
                continue
            pos = positions[local]
            row = index.rows[pos]
            meta = index.lectures.get(row.lecture_id)
            if meta is None:
                continue
            # не отдаём более 4 фрагментов одной лекции в общем поиске
            if lecture_id is None and lecture_counts[row.lecture_id] >= 4:
                continue
            lecture_counts[row.lecture_id] += 1
            terms = [w for w in words(query) if len(w) >= 3 and w.lower() not in STOPWORDS]
            snippet = self._snippet(row.text, terms)
            results.append(
                {
                    "segment_id": row.segment_id,
                    "lecture_id": row.lecture_id,
                    "lecture_title": meta.title,
                    "lecture_duration": meta.duration,
                    "lecture_language": meta.language,
                    "thumbnail_url": f"/api/lectures/{meta.id}/thumbnail" if meta.thumbnail_path else None,
                    "start": round(row.start, 3),
                    "end": round(row.end, 3),
                    "text": row.text,
                    "snippet_html": highlight_html(snippet, terms, sorted(base_terms)),
                    "score": round(score, 4),
                    "score_percent": int(round(score * 100)),
                    "dense": round(float(density_scores[local]), 4),
                    "lexical": round(float(lex_norm[local]), 4),
                    "coverage": round(float(coverage_scores[local]), 4),
                }
            )
            if len(results) >= limit:
                break

        took = int((time.perf_counter() - started) * 1000)
        low_confidence = bool(not results or (results and results[0]["score"] < 0.26))
        if results:
            db.log_event(
                "search", query=query, lecture_id=lecture_id,
                result_count=len(results), took_ms=took,
            )
        return {
            "query": query,
            "results": results,
            "count": len(results),
            "took_ms": took,
            "low_confidence": low_confidence,
            "mode": self._embedder.name,
        }

    def _mmr(self, candidates: list[int], scores: np.ndarray, positions: list[int],
             limit: int, index: SearchIndex) -> list[int]:
        selected: list[int] = []
        remaining = list(candidates)
        max_vectors = index.vectors
        while remaining and len(selected) < limit * 2:
            best_local = None
            best_value = -1e9
            for local in remaining:
                pos = positions[local]
                relevance = float(scores[local])
                redundancy = 0.0
                if selected:
                    if max_vectors is not None:
                        a = max_vectors[pos]
                        for chosen in selected:
                            b = max_vectors[positions[chosen]]
                            redundancy = max(redundancy, float(a @ b))
                    else:
                        a = set(index.rows[pos].lemmas)
                        for chosen in selected:
                            b = set(index.rows[positions[chosen]].lemmas)
                            union = len(a | b) or 1
                            redundancy = max(redundancy, len(a & b) / union)
                lecture_penalty = 0.0
                if sum(1 for c in selected if index.rows[positions[c]].lecture_id == index.rows[pos].lecture_id) >= 2:
                    lecture_penalty = 0.035
                value = 0.80 * relevance - 0.20 * redundancy - lecture_penalty
                if value > best_value:
                    best_value = value
                    best_local = local
            if best_local is None:
                break
            selected.append(best_local)
            remaining.remove(best_local)
        return selected

    @staticmethod
    def _snippet(text: str, terms: Sequence[str], size: int = 340) -> str:
        text = " ".join(text.split())
        if len(text) <= size:
            return text
        lowered = text.lower()
        position = -1
        for term in terms:
            found = lowered.find(term.lower())
            if found >= 0 and (position < 0 or found < position):
                position = found
        if position < 0:
            return text[:size].rstrip() + "…"
        start = max(0, position - size // 3)
        end = min(len(text), start + size)
        if start > 0:
            space = text.find(" ", start)
            if 0 <= space < position:
                start = space + 1
        if end < len(text):
            space = text.rfind(" ", position, end)
            if space > position:
                end = space
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(text) else ""
        return prefix + text[start:end].strip() + suffix

    def suggest(self, query: str, limit: int = 8) -> list[str]:
        index = self.refresh()
        query = (query or "").strip().lower()
        if not index.rows:
            return []
        seen: dict[str, float] = {}
        for row in index.rows:
            for word in row.lemmas:
                if len(word) < 4 or word in STOPWORDS:
                    continue
                if query and not word.startswith(query):
                    continue
                seen[word] = seen.get(word, 0.0) + 1.0
        ranked = sorted(seen.items(), key=lambda item: -item[1])[:limit]
        return [word for word, _ in ranked]

    def rebuild(self) -> SearchIndex:
        return self.refresh(force=True)


_SERVICE: SearchService | None = None
_LOCK = threading.Lock()


def get_search_service() -> SearchService:
    global _SERVICE
    if _SERVICE is None:
        with _LOCK:
            if _SERVICE is None:
                _SERVICE = SearchService()
    return _SERVICE


def reset_search_service() -> None:
    global _SERVICE
    _SERVICE = None
