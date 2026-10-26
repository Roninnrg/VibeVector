"""Опциональный LLM (OpenAI-совместимый API) для конспектов и Q&A."""
from __future__ import annotations

import logging
from typing import Sequence

import httpx

from ..config import settings
from ..text import split_sentences

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self):
        self.ready = settings.llm_ready
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if settings.llm_api_key:
                headers["Authorization"] = f"Bearer {settings.llm_api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=settings.llm_timeout,
            )
        return self._client

    def chat(self, messages: list[dict], temperature: float = 0.2,
             max_tokens: int = 900) -> str:
        if not self.ready:
            raise LLMError("LLM не настроен.")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = self._get_client().post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:
            log.warning("LLM request failed: %s", exc)
            raise LLMError(str(exc)) from exc

    def improve_summary(self, transcript: str, local_summary: str) -> str | None:
        if not self.ready:
            return None
        transcript = transcript[:24000]
        prompt = (
            "Ты — методист, который делает конспекты учебных лекций на русском языке.\n"
            "На основе расшифровки напиши краткий связный конспект: 5–8 предложений, "
            "только факты из текста, без выдумок и без вводных фраз вроде «в данной лекции».\n"
            "Сохрани важные термины, формулы и имена. Верни только текст конспекта.\n\n"
            f"Расшифровка:\n{transcript}\n\n"
            f"Черновой экстрактивный конспект:\n{local_summary}"
        )
        try:
            return self.chat([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=700)
        except LLMError:
            return None

    def answer(self, question: str, context: Sequence[dict]) -> str | None:
        if not self.ready:
            return None
        lines = []
        for i, item in enumerate(context, 1):
            lines.append(f"[{i}] {item['text']}")
        prompt = (
            "Ты — ассистент по видеолекциям. Ответь на вопрос студента, опираясь ТОЛЬКО "
            "на приведённые фрагменты. Пиши по-русски, кратко (2–5 предложений). "
            "После каждого утверждения ставь ссылку на фрагмент в формате [1], [2]. "
            "Если ответа нет во фрагментах, честно скажи об этом.\n\n"
            f"Вопрос: {question}\n\nФрагменты:\n" + "\n".join(lines)
        )
        try:
            return self.chat([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=600)
        except LLMError:
            return None


def llm_status() -> dict:
    return {
        "enabled": settings.llm_enabled,
        "configured": settings.llm_ready,
        "model": settings.llm_model if settings.llm_enabled else None,
        "base_url": settings.llm_base_url if settings.llm_enabled else None,
    }


def safe_sentences(text: str) -> list[str]:
    return [s for s in split_sentences(text) if len(s) > 12]
