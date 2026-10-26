"""Вопрос-ответ по лекции: retrieval + extractive fallback + LLM."""
from __future__ import annotations

import re
import time

from ..text import lemma_set, split_sentences
from .llm import LLMClient
from .search import SearchService


class QAService:
    def __init__(self, search: SearchService, llm: LLMClient | None = None):
        self.search = search
        self.llm = llm or LLMClient()

    def ask(self, lecture_id: str, question: str, limit: int = 5) -> dict:
        started = time.perf_counter()
        question = (question or "").strip()
        if not question:
            raise ValueError("Пустой вопрос.")
        search_result = self.search.search(
            question,
            lecture_id=lecture_id,
            limit=max(3, min(limit, 8)),
            min_score=0.07,
        )
        results = search_result["results"]
        citations = [
            {
                "segment_id": item["segment_id"],
                "start": item["start"],
                "end": item["end"],
                "text": item["text"],
                "score": item["score"],
            }
            for item in results
        ]
        if not results:
            return {
                "answer": "В этой лекции не нашлось фрагментов, по которым можно ответить. "
                          "Попробуйте переформулировать вопрос или найти момент через поиск.",
                "citations": [],
                "mode": "local",
                "took_ms": int((time.perf_counter() - started) * 1000),
            }

        llm_answer = None
        if self.llm.ready:
            llm_answer = self.llm.answer(question, results)
        if llm_answer:
            answer = self._normalize_citations(llm_answer, len(citations))
            mode = "llm"
        else:
            answer = self._extractive_answer(question, results)
            mode = "local"

        return {
            "answer": answer,
            "citations": citations,
            "mode": mode,
            "took_ms": int((time.perf_counter() - started) * 1000),
        }

    @staticmethod
    def _extractive_answer(question: str, results: list[dict]) -> str:
        q_lemmas = lemma_set(question)
        candidates: list[tuple[float, int, str]] = []
        seen: set[str] = set()
        for result_index, result in enumerate(results[:4], 1):
            for sentence in split_sentences(result["text"]):
                if len(sentence) < 18:
                    continue
                normalized = re.sub(r"\s+", " ", sentence.lower())
                if normalized in seen:
                    continue
                seen.add(normalized)
                s_lemmas = lemma_set(sentence)
                overlap = len(q_lemmas & s_lemmas) / max(1, len(q_lemmas))
                score = overlap * 1.4 + result["score"] + (0.08 if result_index == 1 else 0.0)
                candidates.append((score, result_index, sentence))
        if not candidates:
            top = results[0]
            return f"Ближайший фрагмент лекции: «{top['text']}» [{1}]"
        candidates.sort(reverse=True)
        chosen: list[tuple[int, str]] = []
        used_text: list[str] = []
        for _, index, sentence in candidates:
            if any(sentence == s for _, s in chosen):
                continue
            if len(chosen) >= 3:
                break
            chosen.append((index, sentence))
            used_text.append(sentence)
        chosen.sort(key=lambda item: item[0])
        body = " ".join(f"{sentence} [{index}]" for index, sentence in chosen)
        return f"По содержанию лекции: {body}"

    @staticmethod
    def _normalize_citations(answer: str, count: int) -> str:
        def replace(match: re.Match) -> str:
            try:
                number = int(match.group(1))
            except ValueError:
                return match.group(0)
            if 1 <= number <= count:
                return f"[{number}]"
            return ""

        return re.sub(r"\[(\d+)\]", replace, answer)


_QA_SINGLETON: QAService | None = None


def get_qa_service(search: SearchService) -> QAService:
    global _QA_SINGLETON
    if _QA_SINGLETON is None:
        _QA_SINGLETON = QAService(search)
    return _QA_SINGLETON
