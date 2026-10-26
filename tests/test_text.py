"""Юнит-тесты лингвистики: леммы, предложения, конспект, главы, субтитры."""
from __future__ import annotations

from app import text
from app.text import (
    build_chapters,
    cues_to_srt,
    cues_to_vtt,
    format_timestamp,
    highlight_html,
    keyword_weights,
    lemmatize,
    normalize_text,
    query_terms,
    split_sentences,
    srt_timestamp,
    summarize,
    textrank_sentences,
    vtt_timestamp,
)


class TestNormalize:
    def test_strips_bom_and_collapses_spaces(self):
        assert normalize_text("\ufeffПривет   мир\t\t!" ) == "Привет мир !"

    def test_collapses_blank_lines(self):
        assert normalize_text("a\n\n\n\nb") == "a\n\nb"

    def test_empty(self):
        assert normalize_text("   ") == ""


class TestLemmatize:
    def test_russian_morphology(self):
        lemmas = lemmatize("Теоремы Пифагора доказываются для треугольников")
        assert "теорема" in lemmas
        assert "пифагор" in lemmas
        assert "треугольник" in lemmas

    def test_stopwords_removed(self):
        assert "и" not in lemmatize("теорема и доказательство")
        assert "the" not in lemmatize("the theorem")

    def test_stopwords_can_be_kept(self):
        assert "the" in lemmatize("the theorem", keep_stop=True)
        assert "the" not in lemmatize("the theorem")

    def test_single_letters_dropped(self):
        assert "я" not in lemmatize("я знаю теорему")

    def test_empty_text(self):
        assert lemmatize("") == []


class TestSentences:
    def test_splits_three(self):
        assert split_sentences("Привет! Как дела? Всё хорошо.") == [
            "Привет!", "Как дела?", "Всё хорошо."
        ]

    def test_decimal_point_is_not_boundary(self):
        assert split_sentences("Число пи равно 3.14 и это важно.") == [
            "Число пи равно 3.14 и это важно."
        ]

    def test_lowercase_after_dot_is_not_boundary(self):
        assert split_sentences("Это конец. далее продолжение мысли.") == [
            "Это конец. далее продолжение мысли."
        ]

    def test_newline_boundary(self):
        parts = split_sentences("Первая мысль без точки\nВторая мысль без точки")
        assert len(parts) == 2

    def test_empty(self):
        assert split_sentences("   ") == []


class TestQueryTerms:
    def test_base_weight_is_one(self):
        weights = query_terms("теорема пифагора")
        assert weights["теорема"] == 1.0
        assert weights["пифагор"] == 1.0

    def test_synonym_weight_is_lower(self):
        weights = query_terms("нейросеть")
        assert weights["нейросеть"] == 1.0
        assert 0 < weights.get("модель", 0) < 1.0

    def test_phrase_expansion(self):
        weights = query_terms("теорема пифагора")
        assert "гипотенуза" in weights
        assert weights["гипотенуза"] < 1.0

    def test_empty(self):
        assert query_terms("") == {}


class TestKeywords:
    def test_returns_ranked_terms(self):
        texts = [
            "Гипотенуза — это сторона прямоугольного треугольника.",
            "Квадрат гипотенузы равен сумме квадратов катетов.",
            "Теорема Пифагора связывает гипотенузу и катеты.",
        ]
        keywords = keyword_weights(texts, top_n=5)
        assert 1 <= len(keywords) <= 5
        lemmas = [item["lemma"] for item in keywords]
        assert "гипотенуза" in lemmas
        scores = [item["score"] for item in keywords]
        assert scores == sorted(scores, reverse=True)
        assert all(item["count"] >= 1 for item in keywords)

    def test_english_terms(self):
        keywords = keyword_weights(["Neural network learns weights", "Network has layers"])
        assert any(item["lemma"] in {"network", "learn", "weight", "layer"} for item in keywords)

    def test_empty_list(self):
        assert keyword_weights([]) == []


class TestSummarize:
    def test_extractive_summary_has_points_and_timecodes(self):
        texts = [
            "Сегодня мы разберём теорему Пифагора и её применение.",
            "Квадрат гипотенузы равен сумме квадратов катетов.",
            "Теорема работает только для прямоугольных треугольников.",
            "В конце разберём практические задачи на вычисление сторон.",
        ]
        starts = [0.0, 8.0, 16.0, 24.0]
        ends = [8.0, 16.0, 24.0, 32.0]
        result = summarize(texts, starts, ends)
        assert result.text
        assert result.points
        assert result.keywords
        for point in result.points:
            assert 0 <= point["start"] <= 32
            assert point["end"] >= point["start"]
            assert point["text"] in result.text

    def test_short_texts_still_summarized(self):
        result = summarize(["Короткая фраза."])
        assert result.text == "Короткая фраза."

    def test_textrank_returns_sorted_indices(self):
        sentences = [
            "Первое предложение про теорему Пифагора и катеты.",
            "Второе предложение о погоде и природе весной.",
            "Третье предложение про гипотенузу и прямоугольный треугольник.",
            "Четвёртое предложение о музыке и искусстве.",
            "Пятое предложение про доказательство теоремы Пифагора.",
        ]
        chosen = textrank_sentences(sentences, top_k=2)
        assert len(chosen) == 2
        assert chosen == sorted(chosen)

    def test_textrank_with_few_sentences(self):
        assert textrank_sentences(["Одно предложение."], 3) == [0]
        assert textrank_sentences([], 3) == []


class TestChapters:
    def test_section_marker_creates_boundary(self):
        cues = []
        for i in range(20):
            cues.append(
                {
                    "start": float(i * 10),
                    "end": float(i * 10 + 9),
                    "text": "Перейдём к новой теме и разберём пример." if i == 8
                            else f"Реплика номер {i} про теорему и треугольники.",
                }
            )
        chapters = build_chapters(cues, duration=200.0)
        assert len(chapters) >= 2
        assert chapters[0]["start"] == 0
        assert chapters[-1]["end"] <= 200
        assert all(chapter["title"] for chapter in chapters)
        assert [chapter["idx"] for chapter in chapters] == list(range(len(chapters)))

    def test_short_chapters_are_merged(self):
        cues = [
            {"start": 0.0, "end": 29.0, "text": "Первая часть."},
            {"start": 29.0, "end": 60.0, "text": "Вторая часть."},
        ]
        chapters = build_chapters(cues, duration=60.0)
        assert len(chapters) == 1

    def test_empty_cues(self):
        assert build_chapters([]) == []


class TestTimestamps:
    def test_format_short(self):
        assert format_timestamp(0) == "0:00"
        assert format_timestamp(65.4) == "1:05"
        assert format_timestamp(599) == "9:59"

    def test_format_hours(self):
        assert format_timestamp(3661) == "1:01:01"

    def test_format_negative_is_zero(self):
        assert format_timestamp(-5) == "0:00"

    def test_srt_and_vtt_milliseconds(self):
        assert srt_timestamp(1.5) == "00:00:01,500"
        assert vtt_timestamp(1.5) == "00:00:01.500"

    def test_cues_to_srt(self):
        content = cues_to_srt([{"start": 0, "end": 1.5, "text": "Привет"}])
        assert "1\n00:00:00,000 --> 00:00:01,500\nПривет" in content

    def test_cues_to_vtt_header(self):
        content = cues_to_vtt([{"start": 0, "end": 1.0, "text": "Текст"}])
        assert content.startswith("WEBVTT")
        assert "00:00:00.000 --> 00:00:01.000" in content


class TestHighlight:
    def test_marks_terms(self):
        html = highlight_html("Гипотенуза равна сумме", ["гипотенуза"])
        assert "<mark>Гипотенуза</mark>" in html

    def test_escapes_html(self):
        html = highlight_html("<script>alert(1)</script>", ["script"])
        assert "<script>" not in html
        assert "&lt;" in html
        assert "<mark>script</mark>" in html

    def test_no_terms_returns_escaped(self):
        assert highlight_html("a < b", []) == "a &lt; b"

    def test_longer_term_wins(self):
        html = highlight_html("нейронная сеть", ["сеть", "нейронная сеть"])
        assert "<mark>нейронная сеть</mark>" in html

    def test_lemma_highlight_marks_inflections(self):
        html = highlight_html(
            "Квадрат гипотенузы равен сумме квадратов.", [], ["гипотенуза"]
        )
        assert "<mark>гипотенузы</mark>" in html
        assert "<mark>Квадрат</mark>" not in html


def test_format_timestamp_used_in_summary_points():
    result = summarize(["Мы начинаем лекцию о теореме Пифагора сегодня."])
    assert text.format_timestamp(result.points[0]["start"]) == "0:00"
