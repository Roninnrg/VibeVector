"""Тесты вопрос-ответ: извлекательный ответ, ссылки на фрагменты, LLM-режим."""
from __future__ import annotations

import pytest

from app.services.qa import QAService
from app.services.search import get_search_service

from conftest import insert_lecture

CUES = [
    {"start": 0.0, "end": 8.0, "text": "Сегодня мы разберём теорему Пифагора."},
    {"start": 8.0, "end": 18.0, "text": "Квадрат гипотенузы равен сумме квадратов катетов."},
    {"start": 18.0, "end": 30.0, "text": "Теорема работает только для прямоугольных треугольников."},
    {"start": 30.0, "end": 42.0, "text": "Например, при катетах три и четыре гипотенуза равна пяти."},
]


class FakeLLM:
    ready = True

    def __init__(self, answer: str = "Ответ на основе лекции [1]."):
        self.answer_text = answer

    def answer(self, question, results):
        return self.answer_text


class DisabledLLM:
    ready = False

    def answer(self, question, results):  # pragma: no cover - не вызывается
        raise AssertionError("LLM не должен вызываться")


@pytest.fixture
def service():
    insert_lecture("lecture", "Теорема Пифагора", CUES)
    return QAService(get_search_service(), llm=DisabledLLM())


class TestExtractiveQA:
    def test_answer_contains_relevant_sentence(self, service):
        result = service.ask("lecture", "Чему равен квадрат гипотенузы?")
        assert result["mode"] == "local"
        assert "гипотенуз" in result["answer"].lower()
        assert result["citations"]

    def test_citations_have_timestamps(self, service):
        result = service.ask("lecture", "Как найти гипотенузу, если катеты три и четыре?")
        for citation in result["citations"]:
            assert citation["start"] < citation["end"] <= 42
            assert citation["text"]
            assert "segment_id" in citation
            assert 0 <= citation["score"] <= 1

    def test_answer_has_numbered_links(self, service):
        result = service.ask("lecture", "Для каких треугольников работает теорема?")
        assert "[1]" in result["answer"]

    def test_empty_question_raises(self, service):
        with pytest.raises(ValueError):
            service.ask("lecture", "   ")

    def test_unknown_lecture_returns_no_citations(self, service):
        result = service.ask("missing", "Что такое теорема?")
        assert result["citations"] == []
        assert result["mode"] == "local"
        assert "не нашлось" in result["answer"].lower()

    def test_took_ms_is_reported(self, service):
        result = service.ask("lecture", "Что такое гипотенуза?")
        assert isinstance(result["took_ms"], int)
        assert result["took_ms"] >= 0


class TestLLMQA:
    def test_llm_answer_is_used(self):
        insert_lecture("lecture", "Теорема Пифагора", CUES)
        service = QAService(get_search_service(), llm=FakeLLM())
        result = service.ask("lecture", "Что такое теорема Пифагора?")
        assert result["mode"] == "llm"
        assert result["answer"] == "Ответ на основе лекции [1]."

    def test_out_of_range_citation_removed(self):
        insert_lecture("lecture", "Теорема Пифагора", CUES)
        service = QAService(get_search_service(), llm=FakeLLM("Факт [1], выдумка [7]."))
        result = service.ask("lecture", "Что такое теорема?")
        assert "[1]" in result["answer"]
        assert "[7]" not in result["answer"]

    def test_llm_failure_falls_back_to_extractive(self):
        class BrokenLLM:
            ready = True

            def answer(self, question, results):
                return None

        insert_lecture("lecture", "Теорема Пифагора", CUES)
        service = QAService(get_search_service(), llm=BrokenLLM())
        result = service.ask("lecture", "Что такое гипотенуза?")
        assert result["mode"] == "local"
        assert "По содержанию лекции" in result["answer"]
