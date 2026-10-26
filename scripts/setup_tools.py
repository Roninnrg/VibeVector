"""Загрузка ffmpeg/ffprobe в ``tools/ffmpeg/bin``.

Windows: официальная сборка gyan.dev. Linux: статическая сборка johnvansickle.
macOS: подскажет установить через Homebrew. Если ffmpeg уже есть в PATH,
ничего скачивать не нужно.

Запуск:
    python scripts/setup_tools.py
    python scripts/setup_tools.py --force
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

WINDOWS_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
LINUX_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"


def _download(url: str, destination: Path) -> None:
    print(f"Скачиваю {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "vector-setup/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, open(destination, "wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if total:
                print(f"\r  {downloaded * 100 // total:3d}%", end="", flush=True)
    print()


def _install_windows(target: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "ffmpeg.zip"
        _download(WINDOWS_URL, archive)
        with zipfile.ZipFile(archive) as package:
            for member in package.namelist():
                name = Path(member).name
                if name not in {"ffmpeg.exe", "ffprobe.exe"}:
                    continue
                target.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, open(target / name, "wb") as handle:
                    shutil.copyfileobj(source, handle, length=1024 * 1024)
                print(f"  + {name}")


def _install_linux(target: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "ffmpeg.tar.xz"
        _download(LINUX_URL, archive)
        with tarfile.open(archive, "r:xz") as package:
            for member in package.getmembers():
                name = Path(member.name).name
                if name not in {"ffmpeg", "ffprobe"} or not member.isfile():
                    continue
                target.mkdir(parents=True, exist_ok=True)
                extracted = package.extractfile(member)
                if extracted is None:
                    continue
                with extracted, open(target / name, "wb") as handle:
                    shutil.copyfileobj(extracted, handle, length=1024 * 1024)
                (target / name).chmod(0o755)
                print(f"  + {name}")


def _verify() -> bool:
    ffmpeg = settings.ffmpeg
    ffprobe = settings.ffprobe
    if not ffmpeg or not ffprobe:
        return False
    try:
        result = subprocess.run(
            [ffmpeg, "-version"], capture_output=True, timeout=20, check=False
        )
    except Exception:
        return False
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Установка ffmpeg/ffprobe.")
    parser.add_argument("--force", action="store_true", help="Скачать заново.")
    args = parser.parse_args()

    if _verify() and not args.force:
        print(f"ffmpeg уже готов: {settings.ffmpeg}")
        return

    system = platform.system()
    target = Path(settings.tools_dir) / "ffmpeg" / "bin"
    if system == "Windows":
        _install_windows(target)
    elif system == "Linux":
        _install_linux(target)
    else:
        raise SystemExit(
            "macOS: установите ffmpeg командой `brew install ffmpeg`. "
            "Приложение найдёт его в PATH."
        )

    if not _verify():
        raise SystemExit(
            "Не удалось установить ffmpeg. Скачайте вручную и положите "
            "ffmpeg/ffprobe в tools/ffmpeg/bin или задайте FFMPEG_PATH/FFPROBE_PATH."
        )
    print(f"Готово: {settings.ffmpeg}")


if __name__ == "__main__":
    main()
