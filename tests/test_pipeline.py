"""Тесты конвейера обработки: ASR→эмбеддинги→конспект→индекс."""
from __future__ import annotations

import base64
import sys
import threading
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


def create_lecture(
    lecture_id: str = "pipe-lecture",
    status: str = "queued",
    title: str = "Конвейерная лекция",
) -> Path:
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
                lecture_id, title, "", "upload", media.name, str(media),
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

    def test_video_without_audio_sets_clear_error(self, patched_pipeline):
        create_lecture("silent-lecture")
        info = FakeInfo.as_probe()
        info["has_audio"] = False
        patched_pipeline.setattr(pipeline, "probe", lambda path: info)

        with pytest.raises(pipeline.MediaError):
            pipeline.process_lecture("silent-lecture")

        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT * FROM lectures WHERE id='silent-lecture'"
            ).fetchone())
        assert lecture["status"] == "failed"
        assert "аудиодорожки" in lecture["error"]

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


class TestCancelDuringProcessing:
    def test_cancelled_job_stops_and_removes_files(self, patched_pipeline):
        manager = pipeline.JobManager(max_workers=1)
        patched_pipeline.setattr(pipeline, "MANAGER", manager)
        media = create_lecture("cancel-lecture")
        started = threading.Event()
        release = threading.Event()

        def slow_probe(path):
            started.set()
            release.wait(5)
            return FakeInfo.as_probe()

        patched_pipeline.setattr(pipeline, "probe", slow_probe)
        assert manager.submit("cancel-lecture") is True
        assert started.wait(5)
        assert manager.cancel("cancel-lecture") is True

        # Так же поступает DELETE: сначала отменяет задачу, затем убирает запись.
        with db.db() as conn:
            conn.execute("DELETE FROM lectures WHERE id='cancel-lecture'")
        release.set()

        deadline = time.time() + 10
        while manager.active() and time.time() < deadline:
            time.sleep(0.02)
        manager.executor.shutdown(wait=True)

        with db.db() as conn:
            lectures = conn.execute(
                "SELECT COUNT(*) AS c FROM lectures WHERE id='cancel-lecture'"
            ).fetchone()["c"]
            segments = conn.execute(
                "SELECT COUNT(*) AS c FROM segments WHERE lecture_id='cancel-lecture'"
            ).fetchone()["c"]
        assert lectures == 0
        assert segments == 0
        assert not Path(media).exists()
        assert not (Path(settings.audio_dir) / "cancel-lecture.wav").exists()


class TestRemoteDownload:
    @staticmethod
    def _fake_yt_dlp(monkeypatch, ffmpeg: str | None, proxy: str | None = None):
        """Подменяет yt-dlp и ffmpeg, чтобы проверить параметры скачивания."""
        calls: dict = {}
        monkeypatch.setattr(pipeline, "_proxy_url", lambda: proxy)

        class FakeYoutubeDL:
            def __init__(self, options):
                calls["options"] = options

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download=True):
                outtmpl = calls["options"]["outtmpl"]
                Path(outtmpl.replace("%(ext)s", "mp4")).write_bytes(b"fake-video")
                return {"title": "Видео с YouTube"}

        fake_module = type("FakeYTDLP", (), {"YoutubeDL": FakeYoutubeDL})
        monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
        if ffmpeg:
            monkeypatch.setattr(
                type(settings), "ffmpeg", property(lambda self: ffmpeg)
            )
        else:
            monkeypatch.setattr(
                type(settings), "ffmpeg", property(lambda self: None)
            )
        return calls

    def test_uses_bundled_ffmpeg_for_merging(self, monkeypatch):
        ffmpeg = str(Path(settings.tools_dir) / "ffmpeg" / "bin" / "ffmpeg.exe")
        calls = self._fake_yt_dlp(monkeypatch, ffmpeg)
        create_lecture("remote-lecture", title="Лекция с YouTube")

        path = pipeline._download_remote(
            "remote-lecture", "https://www.youtube.com/watch?v=test", lambda *a: None
        )

        assert path.suffix == ".mp4"
        assert path.read_bytes() == b"fake-video"
        assert calls["options"]["ffmpeg_location"] == str(Path(ffmpeg).parent)
        assert "+ba" in calls["options"]["format"]
        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT title FROM lectures WHERE id='remote-lecture'"
            ).fetchone())
        assert lecture["title"] == "Видео с YouTube"

    def test_keeps_user_title_on_download(self, monkeypatch):
        ffmpeg = str(Path(settings.tools_dir) / "ffmpeg" / "bin" / "ffmpeg.exe")
        self._fake_yt_dlp(monkeypatch, ffmpeg)
        create_lecture("remote-lecture-titled", title="Моё название лекции")

        pipeline._download_remote(
            "remote-lecture-titled",
            "https://www.youtube.com/watch?v=test",
            lambda *a: None,
        )

        with db.db() as conn:
            lecture = dict(conn.execute(
                "SELECT title FROM lectures WHERE id='remote-lecture-titled'"
            ).fetchone())
        assert lecture["title"] == "Моё название лекции"

    def test_falls_back_to_single_format_without_ffmpeg(self, monkeypatch):
        calls = self._fake_yt_dlp(monkeypatch, None)
        create_lecture("remote-no-ffmpeg")

        pipeline._download_remote(
            "remote-no-ffmpeg", "https://vimeo.com/123", lambda *a: None
        )

        assert "ffmpeg_location" not in calls["options"]
        assert calls["options"]["format"] == "b[height<=720]/b"
        assert "+ba" not in calls["options"]["format"]

    def test_download_uses_detected_proxy(self, monkeypatch):
        ffmpeg = str(Path(settings.tools_dir) / "ffmpeg" / "bin" / "ffmpeg.exe")
        calls = self._fake_yt_dlp(monkeypatch, ffmpeg, proxy="http://127.0.0.1:10809")
        create_lecture("remote-proxy")

        pipeline._download_remote(
            "remote-proxy", "https://www.youtube.com/watch?v=test", lambda *a: None
        )

        assert calls["options"]["proxy"] == "http://127.0.0.1:10809"

    def test_proxy_from_environment(self, monkeypatch):
        for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                     "ALL_PROXY", "all_proxy"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:3128")
        assert pipeline._proxy_url() == "http://proxy.local:3128"

    @pytest.mark.parametrize("raw, expected", [
        ("127.0.0.1:10809", "http://127.0.0.1:10809"),
        ("http=proxy:8080;https=secure:8443", "http://secure:8443"),
        ("socks=proxy:1080", "socks5://proxy:1080"),
        ("", ""),
    ])
    def test_normalize_proxy(self, raw, expected):
        assert pipeline._normalize_proxy(raw) == expected

    def test_download_error_strips_ansi(self, monkeypatch):
        class BrokenYoutubeDL:
            def __init__(self, options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download=True):
                raise RuntimeError("\x1b[0;31mERROR:\x1b[0m video unavailable")

        fake_module = type("FakeYTDLP", (), {"YoutubeDL": BrokenYoutubeDL})
        monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
        create_lecture("remote-broken")

        with pytest.raises(pipeline.MediaError) as info:
            pipeline._download_remote(
                "remote-broken", "https://youtu.be/broken", lambda *a: None
            )

        message = str(info.value)
        assert message.startswith("Не удалось скачать видео:")
        assert "\x1b[" not in message
        assert "video unavailable" in message

    def test_download_error_explains_bot_protection(self, monkeypatch):
        class BlockedYoutubeDL:
            def __init__(self, options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download=True):
                raise RuntimeError(
                    "\x1b[0;31mERROR:\x1b[0m [youtube] abc: Sign in to confirm "
                    "you're not a bot. This helps protect our community."
                )

        fake_module = type("FakeYTDLP", (), {"YoutubeDL": BlockedYoutubeDL})
        monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
        create_lecture("remote-blocked")

        with pytest.raises(pipeline.MediaError) as info:
            pipeline._download_remote(
                "remote-blocked", "https://youtu.be/blocked", lambda *a: None
            )

        message = str(info.value)
        assert "бот-защита" in message
        assert "YTDLP_COOKIES_FILE" in message
        assert "\x1b[" not in message
        assert message.startswith("Не удалось скачать видео:")

    def test_download_uses_cookies_file(self, monkeypatch, tmp_path):
        ffmpeg = str(Path(settings.tools_dir) / "ffmpeg" / "bin" / "ffmpeg.exe")
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        monkeypatch.setenv("YTDLP_COOKIES_FILE", str(cookies))
        monkeypatch.delenv("YTDLP_COOKIES_B64", raising=False)
        calls = self._fake_yt_dlp(monkeypatch, ffmpeg)
        create_lecture("remote-cookies")

        pipeline._download_remote(
            "remote-cookies", "https://youtu.be/test", lambda *a: None
        )

        assert calls["options"]["cookiefile"] == str(cookies)

    def test_download_uses_cookies_base64(self, monkeypatch):
        ffmpeg = str(Path(settings.tools_dir) / "ffmpeg" / "bin" / "ffmpeg.exe")
        raw = b"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n"
        monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
        monkeypatch.setenv("YTDLP_COOKIES_B64", base64.b64encode(raw).decode())
        calls = self._fake_yt_dlp(monkeypatch, ffmpeg)
        create_lecture("remote-cookies-b64")

        pipeline._download_remote(
            "remote-cookies-b64", "https://youtu.be/test", lambda *a: None
        )

        path = Path(calls["options"]["cookiefile"])
        assert path.read_bytes() == raw

    def test_invalid_cookies_base64_is_ignored(self, monkeypatch):
        ffmpeg = str(Path(settings.tools_dir) / "ffmpeg" / "bin" / "ffmpeg.exe")
        monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
        monkeypatch.setenv("YTDLP_COOKIES_B64", "%%% not base64 %%%")
        calls = self._fake_yt_dlp(monkeypatch, ffmpeg)
        create_lecture("remote-cookies-bad")

        pipeline._download_remote(
            "remote-cookies-bad", "https://youtu.be/test", lambda *a: None
        )

        assert "cookiefile" not in calls["options"]


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
