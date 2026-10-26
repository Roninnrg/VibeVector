"""Тесты гибридного поиска: фильтры, таймкоды, сниппеты, подсказки."""
from __future__ import annotations

from app.services.search import get_search_service, reset_search_service

from conftest import insert_lecture

PYTHAGORAS_CUES = [
    {"start": 0.0, "end": 8.0, "text": "Сегодня мы разберём теорему Пифагора и её доказательство."},
    {"start": 8.0, "end": 18.0, "text": "Квадрат гипотенузы равен сумме квадратов катетов."},
    {"start": 18.0, "end": 30.0, "text": "Теорема применима только к прямоугольным треугольникам."},
    {"start": 30.0, "end": 42.0, "text": "Найдём гипотенузу, если катеты равны трём и четырём."},
]

NEURAL_CUES = [
    {"start": 0.0, "end": 9.0, "text": "Нейронная сеть состоит из слоёв и весов."},
    {"start": 9.0, "end": 20.0, "text": "Обучение нейросети использует градиентный спуск."},
    {"start": 20.0, "end": 32.0, "text": "Обратное распространение ошибки обновляет веса модели."},
]


def _two_lectures() -> None:
    insert_lecture("pyth", "Теорема Пифагора", PYTHAGORAS_CUES)
    insert_lecture("neural", "Нейронные сети", NEURAL_CUES)


class TestSearch:
    def test_finds_lecture_by_meaning(self):
        _two_lectures()
        result = get_search_service().search("чему равна гипотенуза")
        assert result["count"] >= 1
        assert result["results"][0]["lecture_id"] == "pyth"
        assert "гипотенуз" in result["results"][0]["text"].lower()

    def test_results_have_timestamps(self):
        _two_lectures()
        result = get_search_service().search("градиентный спуск")
        assert result["results"]
        top = result["results"][0]
        assert top["lecture_id"] == "neural"
        assert top["start"] < top["end"] <= 32
        assert top["start"] >= 0

    def test_lecture_filter(self):
        _two_lectures()
        result = get_search_service().search("обучение", lecture_id="pyth")
        assert result["count"] >= 0
        assert all(item["lecture_id"] == "pyth" for item in result["results"])

    def test_unknown_lecture_filter_returns_empty(self):
        _two_lectures()
        result = get_search_service().search("теорема", lecture_id="missing")
        assert result["count"] == 0
        assert result["results"] == []

    def test_empty_query(self):
        _two_lectures()
        result = get_search_service().search("   ")
        assert result["count"] == 0
        assert result["took_ms"] == 0

    def test_limit_is_respected(self):
        _two_lectures()
        result = get_search_service().search("теорема треугольник", limit=1)
        assert result["count"] <= 1

    def test_snippet_highlights_query(self):
        _two_lectures()
        result = get_search_service().search("гипотенуза")
        html = result["results"][0]["snippet_html"]
        assert "<mark>" in html
        assert "гипотенуз" in html.lower()

    def test_score_fields_are_consistent(self):
        _two_lectures()
        result = get_search_service().search("теорема пифагора")
        top = result["results"][0]
        assert 0 <= top["score"] <= 1
        assert 0 <= top["dense"] <= 1
        assert 0 <= top["lexical"] <= 1
        assert 0 <= top["coverage"] <= 1
        assert top["score_percent"] == round(top["score"] * 100)

    def test_mode_reported(self):
        _two_lectures()
        result = get_search_service().search("теорема")
        assert result["mode"] == "hashing"

    def test_lecture_title_in_results(self):
        _two_lectures()
        result = get_search_service().search("нейросеть")
        assert result["results"][0]["lecture_title"] == "Нейронные сети"

    def test_diversification_limits_one_lecture(self):
        cues = [
            {"start": float(i * 5), "end": float(i * 5 + 4),
             "text": f"Теорема Пифагора обсуждается в примере номер {i}."}
            for i in range(10)
        ]
        insert_lecture("many", "Много примеров", cues)
        result = get_search_service().search("теорема пифагора", limit=10)
        assert sum(1 for item in result["results"] if item["lecture_id"] == "many") <= 4

    def test_irrelevant_query_is_low_confidence(self):
        _two_lectures()
        result = get_search_service().search("квантовая хромодинамика кварки глюоны")
        assert result["count"] == 0 or result["low_confidence"] is True

    def test_refresh_on_index_change(self):
        _two_lectures()
        service = get_search_service()
        assert service.search("теорема")["count"] >= 1
        insert_lecture("extra", "Ещё лекция", [
            {"start": 0.0, "end": 5.0, "text": "Дополнительная лекция про теорему Пифагора."},
        ])
        result = service.search("теорема пифагора")
        assert any(item["lecture_id"] == "extra" for item in result["results"])

    def test_reset_service(self):
        _two_lectures()
        service = get_search_service()
        service.search("теорема")
        reset_search_service()
        assert get_search_service() is not service


class TestSuggest:
    def test_returns_lemmas_with_prefix(self):
        _two_lectures()
        items = get_search_service().suggest("гипо")
        assert items
        assert all(item.startswith("гипо") for item in items)

    def test_empty_index_returns_empty(self):
        assert get_search_service().suggest("") == []

    def test_respects_limit(self):
        _two_lectures()
        assert len(get_search_service().suggest("", limit=3)) <= 3
