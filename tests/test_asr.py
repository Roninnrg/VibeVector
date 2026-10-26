"""Тесты ASR-утилит: склейка слов в реплики, WAV, MockASR."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from app.services.asr import (
    ASRResult,
    MockASR,
    install_av_shim,
    read_wav_16k,
    words_to_cues,
)

from conftest import make_wav


def word(text: str, start: float, end: float) -> dict:
    return {"word": text, "start": start, "end": end, "probability": 0.9}


class TestWordsToCues:
    def test_punctuation_flushes_cue(self):
        cues = words_to_cues([
            word("Привет", 0.0, 0.4),
            word(",", 0.4, 0.5),
            word("мир", 0.5, 0.9),
            word(".", 0.9, 1.0),
            word("Далее", 1.0, 1.4),
            word(".", 1.4, 1.5),
        ])
        assert len(cues) == 2
        assert cues[0]["text"] == "Привет, мир."
        assert cues[1]["text"] == "Далее."
        assert cues[0]["start"] == 0.0
        assert cues[0]["end"] == 1.0

    def test_long_gap_splits(self):
        cues = words_to_cues([
            word("Первая", 0.0, 0.5),
            word("фраза", 0.5, 1.0),
            word("Вторая", 3.0, 3.5),
            word("фраза", 3.5, 4.0),
        ])
        assert len(cues) == 2

    def test_max_chars_splits(self):
        words = [word(f"слово{i}", i * 0.4, i * 0.4 + 0.35) for i in range(40)]
        cues = words_to_cues(words, max_chars=60)
        assert len(cues) > 1
        assert all(len(cue["text"]) <= 120 for cue in cues)

    def test_fallback_segments_used_when_no_words(self):
        cues = words_to_cues([], fallback_segments=[
            {"start": 1.0, "end": 2.0, "text": "Готовая реплика"},
        ])
        assert len(cues) == 1
        assert cues[0]["text"] == "Готовая реплика"
        assert cues[0]["words"] == []

    def test_times_are_monotonic_and_nonzero_length(self):
        cues = words_to_cues([
            word("А", 0.0, 0.0),
            word("Б", 0.0, 0.0),
            word("В", 0.0, 0.0),
            word(".", 0.0, 0.0),
        ])
        assert cues
        for cue in cues:
            assert cue["end"] >= cue["start"] + 0.35

    def test_duplicate_cues_are_merged(self):
        cues = words_to_cues([
            word("Одинаково", 0.0, 0.5),
            word(".", 0.5, 0.6),
            word("Одинаково", 2.0, 2.5),
            word(".", 2.5, 2.6),
        ])
        assert len(cues) == 1
        assert cues[0]["end"] >= 2.5

    def test_word_probabilities_are_saved(self):
        cues = words_to_cues([word("Тест", 0.0, 0.3), word(".", 0.3, 0.4)])
        assert cues[0]["words"][0]["probability"] == 0.9

    def test_empty_input(self):
        assert words_to_cues([]) == []


class TestReadWav:
    def test_reads_mono_16k(self):
        path = make_wav(Path(os.environ["VECTOR_DATA_DIR"]) / "asr-test.wav", seconds=0.5)
        audio = read_wav_16k(path)
        assert audio.dtype == np.float32
        assert audio.shape == (8000,)
        assert np.max(np.abs(audio)) <= 1.0

    def test_rejects_stereo(self):
        path = make_wav(
            Path(os.environ["VECTOR_DATA_DIR"]) / "stereo.wav", seconds=0.2, channels=2
        )
        with pytest.raises(RuntimeError):
            read_wav_16k(path)

    def test_rejects_wrong_rate(self):
        path = make_wav(
            Path(os.environ["VECTOR_DATA_DIR"]) / "8k.wav", seconds=0.2, rate=8000
        )
        with pytest.raises(RuntimeError):
            read_wav_16k(path)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_wav_16k(Path(os.environ["VECTOR_DATA_DIR"]) / "nope.wav")


class TestMockASR:
    def test_default_fixture(self):
        result = MockASR().transcribe("unused.wav", duration=12.0)
        assert isinstance(result, ASRResult)
        assert result.provider == "mock"
        assert result.language == "ru"
        assert len(result.cues) == 2
        assert result.duration == 12.0
        assert "Пифагора" in result.text

    def test_dict_fixture_and_progress(self):
        seen: list[float] = []
        result = MockASR({"cues": [
            {"start": 0.0, "end": 3.0, "text": "Тест."},
        ], "language": "en"}).transcribe("unused.wav", on_progress=seen.append)
        assert result.language == "en"
        assert result.duration == 3.0
        assert seen == [1.0]

    def test_json_fixture(self, tmp_path):
        fixture = tmp_path / "fixture.json"
        fixture.write_text(
            json.dumps({"cues": [{"start": 0, "end": 2, "text": "Из файла."}]},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        result = MockASR(fixture).transcribe("unused.wav")
        assert result.cues[0]["text"] == "Из файла."


def test_install_av_shim_is_idempotent():
    install_av_shim()
    install_av_shim()
    assert "av" in __import__("sys").modules


@pytest.mark.skipif(
    not os.getenv("VECTOR_SLOW_TESTS"),
    reason="Реальный Whisper: запускайте с VECTOR_SLOW_TESTS=1",
)
def test_real_whisper_smoke():
    from app.services.asr import WhisperASR

    path = make_wav(Path(os.environ["VECTOR_DATA_DIR"]) / "silence.wav", seconds=1.0)
    result = WhisperASR().transcribe(path, duration=1.0)
    assert result.provider == "faster-whisper"
    assert result.cues == [] or isinstance(result.cues, list)
