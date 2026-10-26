"""Источники для импорта видео по ссылке и подсказки по ошибкам скачивания."""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

# Расширения, которые можно скачать напрямую, без страницы-обёртки.
DIRECT_VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}

# (ключ, название по умолчанию, хосты). Порядок важен только для документации.
SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "youtube",
        "Лекция с YouTube",
        (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
            "www.youtu.be",
        ),
    ),
    ("vimeo", "Лекция с Vimeo", ("vimeo.com", "www.vimeo.com", "player.vimeo.com")),
    (
        "vk",
        "Лекция с VK Видео",
        ("vk.com", "www.vk.com", "m.vk.com", "vkvideo.ru", "www.vkvideo.ru"),
    ),
    ("rutube", "Лекция с Rutube", ("rutube.ru", "www.rutube.ru", "m.rutube.ru")),
    (
        "dailymotion",
        "Лекция с Dailymotion",
        ("dailymotion.com", "www.dailymotion.com", "dai.ly"),
    ),
)

DIRECT_TITLE = "Видео по ссылке"

HOST_TITLES: dict[str, str] = {
    host: title for _, title, hosts in SOURCES for host in hosts
}
# Названия-заглушки: их можно заменить настоящим названием из yt-dlp.
DEFAULT_TITLES: frozenset[str] = frozenset(
    {title for _, title, _ in SOURCES} | {DIRECT_TITLE}
)

SUPPORTED_HINT = (
    "Поддерживаются YouTube, Vimeo, VK Видео, Rutube, Dailymotion "
    "и прямые ссылки на видеофайл (MP4, WebM, MOV, MKV)."
)

_LOCAL_SUFFIXES = (".local", ".localdomain", ".internal", ".home.arpa")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_YTDLP_PREFIX_RE = re.compile(r"^ERROR:\s*\[[^\]]+\]\s*[^:]*:\s*", re.IGNORECASE)

_ERROR_HINTS: tuple[tuple[str, str], ...] = (
    (
        "sign in to confirm",
        "YouTube требует подтвердить, что запрос делает человек (бот-защита). "
        "С IP дата-центра это ограничение не обойти: загрузите файл вручную "
        "или передайте cookies через YTDLP_COOKIES_FILE.",
    ),
    (
        "not a bot",
        "Сервис требует подтвердить, что запрос делает человек (бот-защита). "
        "Загрузите файл вручную или передайте cookies через YTDLP_COOKIES_FILE.",
    ),
    (
        "only works when logged-in",
        "Vimeo отдаёт это видео только авторизованным пользователям. "
        "Загрузите файл вручную или передайте cookies через YTDLP_COOKIES_FILE.",
    ),
    (
        "private video",
        "Видео приватное: автор запретил публичный доступ.",
    ),
    (
        "this video is not available",
        "Видео недоступно: возможно, удалено, приватное или ограничено по региону.",
    ),
    (
        "video unavailable",
        "Видео недоступно: возможно, удалено, приватное или ограничено по региону.",
    ),
    (
        "unsupported url",
        "Этот сайт не поддерживается для импорта по ссылке.",
    ),
    (
        "unable to download webpage",
        "Не удалось открыть страницу с видео. Проверьте ссылку и доступ в интернет.",
    ),
    (
        "timed out",
        "Сервис не ответил вовремя. Проверьте доступ в интернет и повторите попытку.",
    ),
    (
        "connection refused",
        "Сервис отклонил подключение. Проверьте прокси и доступ в интернет.",
    ),
    (
        "http error 404",
        "Видео не найдено (404). Проверьте ссылку.",
    ),
    (
        "http error 403",
        "Сервис запретил доступ (403). Возможно, нужны cookies или другой IP.",
    ),
)


def normalize_host(value: str | None) -> str:
    return (value or "").strip().lower().rstrip(".")


def default_title(url: str) -> str:
    host = normalize_host(urlparse(url).hostname)
    return HOST_TITLES.get(host, DIRECT_TITLE)


def is_private_host(host: str) -> bool:
    """Не даём серверу ходить по локальной сети и служебным адресам."""
    host = normalize_host(host)
    if not host:
        return True
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def validate_import_url(url: str) -> str:
    """Проверяет ссылку и возвращает её в нормализованном виде.

    ValueError содержит готовое для пользователя объяснение.
    """
    value = (url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Ссылка должна начинаться с http:// или https://")
    host = normalize_host(parsed.hostname)
    if not host:
        raise ValueError("В ссылке не найден адрес сайта.")
    if host in HOST_TITLES:
        return value
    if Path(parsed.path).suffix.lower() in DIRECT_VIDEO_EXT and not is_private_host(host):
        return value
    raise ValueError(SUPPORTED_HINT)


def download_error_message(raw: str, details_limit: int = 300) -> str:
    """Переводит типовые ошибки yt-dlp в понятное объяснение по-русски."""
    message = _ANSI_RE.sub("", str(raw or "")).strip()
    message = " ".join(message.split())
    details = _YTDLP_PREFIX_RE.sub("", message)[:details_limit]
    lowered = message.lower()
    for needle, hint in _ERROR_HINTS:
        if needle in lowered:
            return f"Не удалось скачать видео: {hint} Технические детали: {details}"
    return f"Не удалось скачать видео: {details or 'неизвестная ошибка'}"
