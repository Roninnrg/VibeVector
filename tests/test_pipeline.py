"""Тесты конвейера обработки: ASR→эмбеддинги→конспект→индекс."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app import db
from app.config import settings
from app.services import pipeline
from app.services.asr import ASRResult, MockASR

from conftest import make_wav


class FakeInfo:
    duration = 30.0

    @staticmethod
    def as_probe() -> dict:
        return {
            "duration": 30.0,
            "width": 1280,
            "height": 720,
            "video_codec": "h264",
            "audio_codec": "aac",
            "has_video": True,
            "has_audio": True,
            "format": "mp4",
            "mime": "video/mp4",
            "size": 1024,
        }


MOCK_CUES = [
    {"start": 0.0, "end": 8.0, "text": "Сегодня мы разберём теорему Пифагора и её смысл.",
     "words": []},
    {"start": 8.0, "end": 18.0, "text": "Квадрат гипотенузы равен сумме квадратов катетов.",
     "words": []},
    {"start": 18.0, "end": 28.0, "text": "Теорема работает только для прямоугольных треугольников.",
     "words": []},
]


def create_lecture(lecture_id: str = "pipe-lecture", status: str = "queued") -> Path:
    media = Path(settings.media_dir) / f"{lecture_id}.mp4"
    media.write_bytes(b"\x00" * 64)
    now = db.now_iso()
    with db.db() as conn:
        conn.execute(
            """INSERT INTO lectures
               (id, title, description, source_type, original_filename, media_path,
                media_mime, media_size, duration, status, stage, progress,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lecture_id, "Конвейерная лекция", "", "upload", media.name, str(media),
                "video/mp4", 64, 30.0, status, "В очереди", 0, now, now,
            ),
        )
    return media


@pytest.fixture
def patched_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline, "probe", lambda path: FakeInfo.as_probe())
    monkeypatch.setattr(
        pipeline, "extract_audio",
        lambda source, destination, on_progress=None: make_wav(Path(destination), seconds=1.0),
    )
    monkeypatch.setattr(pipeline, "make_thumbnail", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "get_asr", lambda: MockASR({"cues": MOCK_CUES}))
    return monkeypatch


class TestProcessLecture:
    def test_successful_pipeline(self, patched_pipeline):
        create_lecture()
        pipeline.process_lecture("pipe-lecture")

        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT * FROM lectures WHERE id='pipe-lecture'"
            ).fetchone())
            segments = conn.execute(
                "SELECT * FROM segments WHERE lecture_id='pipe-lecture' ORDER BY idx"
            ).fetchall()
            chapters = conn.execute(
                "SELECT * FROM chapters WHERE lecture_id='pipe-lecture'"
            ).fetchall()

        assert lecture["status"] == "ready"
        assert lecture["stage"] == "Готово"
        assert lecture["progress"] == 100
        assert lecture["error"] is None
        assert lecture["duration"] == 30.0
        assert lecture["asr_provider"] == "mock"
        assert lecture["embedding_provider"] == "hashing"
        assert lecture["summary"]
        assert lecture["summary_points_json"] != "[]"
        assert lecture["keywords_json"] != "[]"
        assert len(segments) == 3
        assert segments[1]["text"].startswith("Квадрат гипотенузы")
        assert segments[0]["lemmas"]
        assert segments[0]["dim"] == 768
        assert len(chapters) >= 1
        assert chapters[0]["title"]

    def test_index_is_searchable_after_processing(self, patched_pipeline):
        create_lecture()
        pipeline.process_lecture("pipe-lecture")

        from app.services.search import get_search_service

        result = get_search_service().search("чему равна гипотенуза")
        assert result["count"] >= 1
        assert result["results"][0]["lecture_id"] == "pipe-lecture"

    def test_audio_is_removed_after_success(self, patched_pipeline):
        create_lecture()
        pipeline.process_lecture("pipe-lecture")
        assert not (Path(settings.audio_dir) / "pipe-lecture.wav").exists()

    def test_failure_sets_error(self, patched_pipeline):
        create_lecture("broken-lecture")

        class EmptyASR:
            provider = "mock"

            def transcribe(self, *args, **kwargs):
                return ASRResult(cues=[], provider="mock")

        patched_pipeline.setattr(pipeline, "get_asr", lambda: EmptyASR())
        with pytest.raises(RuntimeError):
            pipeline.process_lecture("broken-lecture")

        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT * FROM lectures WHERE id='broken-lecture'"
            ).fetchone())
        assert lecture["status"] == "failed"
        assert lecture["progress"] == 0
        assert "Речь не распознана" in lecture["error"]

    def test_missing_media_sets_error(self, patched_pipeline):
        create_lecture("missing-lecture")
        with db.db() as conn:
            conn.execute(
                "UPDATE lectures SET media_path=NULL WHERE id='missing-lecture'"
            )
        with pytest.raises(Exception):
            pipeline.process_lecture("missing-lecture")
        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT * FROM lectures WHERE id='missing-lecture'"
            ).fetchone())
        assert lecture["status"] == "failed"
        assert "не найден" in lecture["error"].lower()

    def test_processing_status_is_skipped(self, patched_pipeline):
        create_lecture("busy-lecture", status="processing")
        pipeline.process_lecture("busy-lecture")
        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT * FROM lectures WHERE id='busy-lecture'"
            ).fetchone())
        assert lecture["status"] == "processing"
        assert "уже идёт" in lecture["stage"]

    def test_force_reprocesses_processing_lecture(self, patched_pipeline):
        create_lecture("forced-lecture", status="processing")
        pipeline.process_lecture("forced-lecture", force=True)
        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT * FROM lectures WHERE id='forced-lecture'"
            ).fetchone())
        assert lecture["status"] == "ready"

    def test_missing_lecture_is_noop(self):
        pipeline.process_lecture("unknown")
        with db.db() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM lectures").fetchone()["c"]
        assert count == 0

    def test_reprocess_sets_queued(self, patched_pipeline):
        create_lecture("reprocess-lecture", status="ready")
        patched_pipeline.setattr(pipeline.MANAGER, "submit", lambda *a, **k: True)
        assert pipeline.reprocess("reprocess-lecture") is True
        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT * FROM lectures WHERE id='reprocess-lecture'"
            ).fetchone())
        assert lecture["status"] == "queued"
        assert lecture["progress"] == 0

    def test_reprocess_unknown(self):
        assert pipeline.reprocess("unknown") is False


class TestPipelineInternals:
    def test_pipeline_status(self):
        status = pipeline.pipeline_status()
        assert status["workers"] == 1
        assert "active" in status
        assert isinstance(status["ffmpeg"], bool)

    def test_progress_writer_clamps(self):
        create_lecture("progress-lecture")
        callback = pipeline._progress_writer("progress-lecture", 10, 40, "Тест")
        callback(-5.0)
        callback(5.0)
        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT progress, stage FROM lectures WHERE id='progress-lecture'"
            ).fetchone())
        assert 10 <= lecture["progress"] <= 100
        assert "Тест" in lecture["stage"]

    def test_job_manager_rejects_after_shutdown(self):
        manager = pipeline.JobManager(max_workers=1)
        manager.shutdown()
        assert manager.submit("x") is False


@pytest.mark.integration
class TestUploadEndToEnd:
    def test_upload_becomes_ready_and_searchable(self, client, monkeypatch):
        """Реальная загрузка WAV → ffmpeg → MockASR → поиск и Q&A через API."""
        monkeypatch.setattr(
            pipeline, "get_asr", lambda: MockASR({"cues": MOCK_CUES})
        )
        from conftest import make_wav as _make_wav

        audio = _make_wav(Path(settings.data_dir) / "e2e-upload.wav", seconds=30.0)
        content = audio.read_bytes()
        response = client.post(
            "/api/lectures/upload",
            files={"file": ("e2e.wav", content, "audio/wav")},
            data={"title": "E2E лекция"},
        )
        assert response.status_code == 202
        lecture_id = response.json()["id"]

        deadline = time.time() + 90
        payload = {}
        while time.time() < deadline:
            payload = client.get(f"/api/lectures/{lecture_id}").json()
            if payload["status"] in {"ready", "failed"}:
                break
            time.sleep(0.25)

        assert payload["status"] == "ready", payload.get("error")
        assert payload["segments_count"] == 3
        assert payload["chapters_count"] >= 1

        transcript = client.get(f"/api/lectures/{lecture_id}/transcript").json()
        assert transcript["count"] == 3
        assert transcript["cues"][1]["start"] == 8.0

        search = client.get(
            "/api/search", params={"q": "гипотенуза", "lecture_id": lecture_id}
        ).json()
        assert search["count"] >= 1

        ask = client.post(
            f"/api/lectures/{lecture_id}/ask",
            json={"question": "Чему равен квадрат гипотенузы?"},
        )
        assert ask.status_code == 200
        assert ask.json()["citations"]

        exported = client.get(f"/api/lectures/{lecture_id}/export")
        assert exported.status_code == 200
        assert "## Расшифровка" in exported.text

        subtitles = client.get(f"/api/lectures/{lecture_id}/subtitles.vtt")
        assert subtitles.status_code == 200
        assert subtitles.text.startswith("WEBVTT")
