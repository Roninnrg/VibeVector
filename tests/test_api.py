"""Интеграционные тесты HTTP API через TestClient."""
from __future__ import annotations

import io
import json
import wave
from pathlib import Path

import pytest

from app import db
from app.config import settings

from conftest import insert_lecture

CUES = [
    {"start": 0.0, "end": 8.0, "text": "Сегодня мы разберём теорему Пифагора."},
    {"start": 8.0, "end": 18.0, "text": "Квадрат гипотенузы равен сумме квадратов катетов."},
    {"start": 18.0, "end": 30.0, "text": "Теорема применима к прямоугольным треугольникам."},
]


def wav_bytes(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


@pytest.fixture
def lecture() -> dict:
    return insert_lecture("api-lecture", "API-лекция", CUES)


class TestHealthAndMeta:
    def test_health_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] in {"ok", "degraded"}
        assert payload["db"]["ok"] is True
        assert "ffmpeg" in payload
        assert "asr" in payload
        assert "embeddings" in payload
        assert isinstance(payload["warnings"], list)

    def test_meta_capabilities(self, client):
        payload = client.get("/api/meta").json()
        assert payload["app_name"] == "Вектор"
        assert payload["capabilities"]["semantic_search"] is True
        assert payload["capabilities"]["upload"] is True

    def test_security_headers(self, client):
        response = client.get("/api/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_unknown_api_route(self, client):
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.json()["detail"]


class TestLectures:
    def test_empty_list(self, client):
        payload = client.get("/api/lectures").json()
        assert payload == {"items": [], "count": 0}

    def test_list_with_counts(self, client, lecture):
        payload = client.get("/api/lectures").json()
        assert payload["count"] == 1
        item = payload["items"][0]
        assert item["id"] == "api-lecture"
        assert item["segments_count"] == 3
        assert item["status"] == "ready"
        assert item["media_url"] is None

    def test_status_filter(self, client, lecture):
        assert client.get("/api/lectures?status=ready").json()["count"] == 1
        assert client.get("/api/lectures?status=failed").json()["count"] == 0

    def test_get_lecture(self, client, lecture):
        payload = client.get("/api/lectures/api-lecture").json()
        assert payload["title"] == "API-лекция"
        assert payload["segments_count"] == 3
        assert payload["chapters_count"] == 1
        assert payload["chapters"][0]["title"]

    def test_get_lecture_increments_views(self, client, lecture):
        client.get("/api/lectures/api-lecture")
        payload = client.get("/api/lectures/api-lecture").json()
        assert payload["views"] >= 1

    def test_missing_lecture_404(self, client):
        response = client.get("/api/lectures/nope")
        assert response.status_code == 404

    def test_patch_title_and_description(self, client, lecture):
        response = client.patch(
            "/api/lectures/api-lecture",
            json={"title": "Новое название", "description": "Описание"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "Новое название"
        assert payload["description"] == "Описание"

    def test_patch_validation(self, client, lecture):
        assert client.patch("/api/lectures/api-lecture", json={"title": ""}).status_code == 422

    def test_delete_lecture(self, client, lecture):
        response = client.delete("/api/lectures/api-lecture")
        assert response.status_code == 200
        assert response.json()["deleted"] is True
        assert client.get("/api/lectures/api-lecture").status_code == 404
        assert client.get("/api/lectures").json()["count"] == 0

    def test_delete_missing_404(self, client):
        assert client.delete("/api/lectures/nope").status_code == 404


class TestTranscriptAndSubtitles:
    def test_transcript(self, client, lecture):
        payload = client.get("/api/lectures/api-lecture/transcript").json()
        assert payload["count"] == 3
        assert payload["cues"][1]["text"].startswith("Квадрат")
        assert payload["cues"][0]["start"] == 0
        assert "words" not in payload["cues"][0]

    def test_transcript_with_words(self, client, lecture):
        payload = client.get("/api/lectures/api-lecture/transcript?words=true").json()
        assert payload["cues"][0]["words"] == []

    def test_transcript_missing_404(self, client):
        assert client.get("/api/lectures/nope/transcript").status_code == 404

    def test_vtt(self, client, lecture):
        response = client.get("/api/lectures/api-lecture/subtitles.vtt")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/vtt")
        assert response.text.startswith("WEBVTT")
        assert "00:00:08.000" in response.text

    def test_srt_download(self, client, lecture):
        response = client.get("/api/lectures/api-lecture/subtitles.srt?download=true")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert "00:00:08,000 --> 00:00:18,000" in response.text

    def test_unsupported_subtitle_format(self, client, lecture):
        response = client.get("/api/lectures/api-lecture/subtitles.txt")
        assert response.status_code in {400, 422}


class TestExport:
    def test_markdown_export(self, client, lecture):
        response = client.get("/api/lectures/api-lecture/export")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        body = response.text
        assert body.startswith("# API-лекция")
        assert "## Расшифровка" in body
        assert "**[0:08]** Квадрат гипотенузы" in body

    def test_export_missing_404(self, client):
        assert client.get("/api/lectures/nope/export").status_code == 404


class TestThumbnailAndMedia:
    def test_thumbnail_missing_404(self, client, lecture):
        assert client.get("/api/lectures/api-lecture/thumbnail").status_code == 404

    def test_media_missing_404(self, client, lecture):
        assert client.get("/api/lectures/api-lecture/media").status_code == 404

    def test_media_full_and_range(self, client, lecture):
        path = Path(settings.media_dir) / "api-media.mp4"
        path.write_bytes(b"0123456789abcdef")
        with db.db() as conn:
            conn.execute(
                "UPDATE lectures SET media_path=?, media_mime=? WHERE id=?",
                (str(path), "video/mp4", "api-lecture"),
            )

        full = client.get("/api/lectures/api-lecture/media")
        assert full.status_code == 200
        assert full.content == b"0123456789abcdef"
        assert full.headers["accept-ranges"] == "bytes"

        partial = client.get(
            "/api/lectures/api-lecture/media", headers={"Range": "bytes=0-3"}
        )
        assert partial.status_code == 206
        assert partial.content == b"0123"
        assert partial.headers["content-range"] == "bytes 0-3/16"

        suffix = client.get(
            "/api/lectures/api-lecture/media", headers={"Range": "bytes=-4"}
        )
        assert suffix.status_code == 206
        assert suffix.content == b"cdef"

    def test_invalid_range(self, client, lecture):
        path = Path(settings.media_dir) / "api-media.mp4"
        path.write_bytes(b"0123456789")
        with db.db() as conn:
            conn.execute(
                "UPDATE lectures SET media_path=? WHERE id=?",
                (str(path), "api-lecture"),
            )
        response = client.get(
            "/api/lectures/api-lecture/media", headers={"Range": "bytes=abc"}
        )
        assert response.status_code == 416

    def test_head_media(self, client, lecture):
        path = Path(settings.media_dir) / "api-media.mp4"
        path.write_bytes(b"0123456789")
        with db.db() as conn:
            conn.execute(
                "UPDATE lectures SET media_path=?, media_mime=? WHERE id=?",
                (str(path), "video/mp4", "api-lecture"),
            )
        response = client.head("/api/lectures/api-lecture/media")
        assert response.status_code == 200
        assert response.headers["content-length"] == "10"


class TestSearchAPI:
    def test_search(self, client, lecture):
        payload = client.get("/api/search", params={"q": "чему равна гипотенуза"}).json()
        assert payload["count"] >= 1
        assert payload["results"][0]["lecture_id"] == "api-lecture"
        assert payload["mode"] == "hashing"

    def test_search_requires_query(self, client):
        assert client.get("/api/search").status_code == 422

    def test_search_limit_validation(self, client):
        assert client.get("/api/search", params={"q": "x", "limit": 0}).status_code == 422
        assert client.get("/api/search", params={"q": "x", "limit": 51}).status_code == 422

    def test_suggest(self, client, lecture):
        payload = client.get("/api/search/suggest", params={"q": "гипо"}).json()
        assert "гипотенуза" in payload["items"]

    def test_ask(self, client, lecture):
        response = client.post(
            "/api/lectures/api-lecture/ask",
            json={"question": "Чему равен квадрат гипотенузы?", "limit": 5},
        )
        assert response.status_code == 200
        payload = response.json()
        assert "гипотенуз" in payload["answer"].lower()
        assert payload["citations"]
        assert payload["mode"] == "local"

    def test_ask_limit_validation(self, client, lecture):
        response = client.post(
            "/api/lectures/api-lecture/ask", json={"question": "Что?", "limit": 1}
        )
        assert response.status_code == 422

    def test_ask_missing_lecture_404(self, client):
        response = client.post("/api/lectures/nope/ask", json={"question": "Что такое?"})
        assert response.status_code == 404


class TestStats:
    def test_stats(self, client, lecture):
        payload = client.get("/api/stats").json()
        assert payload["lectures"] == 1
        assert payload["ready"] == 1
        assert payload["segments"] == 3
        assert payload["chapters"] == 1
        assert payload["hours"] >= 0
        assert isinstance(payload["disk"], dict)

    def test_stats_empty(self, client):
        payload = client.get("/api/stats").json()
        assert payload["lectures"] == 0
        assert payload["segments"] == 0


class TestUploadAndImport:
    def test_upload_rejects_unsupported_extension(self, client):
        response = client.post(
            "/api/lectures/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 422

    def test_upload_rejects_empty_file(self, client):
        response = client.post(
            "/api/lectures/upload",
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        assert response.status_code == 422

    def test_upload_wav_creates_lecture(self, client, monkeypatch):
        monkeypatch.setattr("app.api.MANAGER.submit", lambda *a, **k: True)
        response = client.post(
            "/api/lectures/upload",
            files={"file": ("Лекция.wav", wav_bytes(), "audio/wav")},
            data={"title": "Загруженная лекция", "description": "Из теста"},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["title"] == "Загруженная лекция"
        assert payload["description"] == "Из теста"
        assert payload["status"] == "queued"
        assert payload["duration"] > 0
        assert payload["media_url"]

    def test_import_rejects_unknown_host(self, client):
        response = client.post(
            "/api/lectures/import", json={"url": "https://example.com/video"}
        )
        assert response.status_code == 422

    def test_import_rejects_bad_scheme(self, client):
        response = client.post(
            "/api/lectures/import", json={"url": "ftp://youtube.com/watch?v=1"}
        )
        assert response.status_code == 422

    def test_import_youtube(self, client, monkeypatch):
        monkeypatch.setattr("app.api.MANAGER.submit", lambda *a, **k: True)
        response = client.post(
            "/api/lectures/import",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["source_type"] == "url"
        assert payload["title"] == "Лекция с YouTube"
        assert payload["status"] == "queued"

    def test_import_vimeo(self, client, monkeypatch):
        monkeypatch.setattr("app.api.MANAGER.submit", lambda *a, **k: True)
        response = client.post(
            "/api/lectures/import",
            json={"url": "https://vimeo.com/123456", "title": "Своё название"},
        )
        assert response.status_code == 202
        assert response.json()["title"] == "Своё название"

    def test_reprocess_missing_404(self, client):
        assert client.post("/api/lectures/nope/reprocess").status_code == 404


class TestSPA:
    def test_index_served(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Вектор" in response.text

    def test_spa_fallback(self, client):
        response = client.get("/lecture/anything")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_favicon(self, client):
        response = client.get("/favicon.svg")
        assert response.status_code == 200
        assert "svg" in response.headers["content-type"]

    def test_lecture_json_parse(self, client, lecture):
        """Данные лекции сериализуются в валидный JSON без NaN."""
        response = client.get("/api/lectures/api-lecture")
        json.loads(response.text)
        assert response.status_code == 200
