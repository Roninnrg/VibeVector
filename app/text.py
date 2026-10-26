"""Лингвистика без тяжёлых зависимостей: предложения, леммы, ключевые слова,
экстрактивный конспект и автоматическая структура лекции.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

import numpy as np

try:  # pymorphy3 — чистый Python, работает на любом интерпретаторе
    import pymorphy3

    _MORPH = pymorphy3.MorphAnalyzer()
except Exception:  # pragma: no cover - резервный режим
    _MORPH = None

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'’][A-Za-zА-Яа-яЁё0-9]+)*")
SENT_END = ".!?…"
ABBREVIATIONS = {
    "т", "е", "д", "п", "др", "пр", "см", "ср", "напр", "рис", "табл", "гл",
    "стр", "г", "гг", "в", "вв", "н", "э", "ул", "им", "проф", "доц", "акад",
    "тыс", "млн", "млрд", "руб", "мин", "макс", "сек", "ч", "англ", "рус",
    "mr", "mrs", "dr", "prof", "vs", "etc", "e.g", "i.e", "fig", "no",
}
STOPWORDS = set(
    """
    а без более бы был была были было быть в вам вас весь во вот все всего всех вы
    где да даже для до его ее её ей ему если есть еще ещё же за здесь и из или им
    их к как какая какие какой когда кто куда ли либо мне может можно мы на над надо
    нам нас не него нее неё нет ни них но ну о об однако он она они оно от очень по
    под при про с со так также такой там те тем то того тоже той только том ты у уже
    хотя чего чей чем что чтобы чье чья эта эти это этого этой этом этот я
    the a an and or of to in on for with is are was were be been being it its this
    that these those as at by from not no yes we you they he she i do does did can
    could should would will just about into over under more most very much many
    """.split()
)

# Смысловые группы для расширения запроса. Вес расширения ниже исходных слов.
SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("теорема", "утверждение", "лемма", "свойство"),
    ("объяснение", "пояснение", "разбор", "объяснить", "рассказ"),
    ("пример", "иллюстрация", "демонстрация", "показать"),
    ("формула", "выражение", "уравнение", "равенство"),
    ("скорость", "быстрота", "темп", "быстро"),
    ("нейросеть", "нейронная сеть", "нейронка", "ии", "искусственный интеллект", "модель"),
    ("обучение", "тренировка", "учеба", "учиться", "обучать"),
    ("градиент", "производная", "наклон", "склон"),
    ("функция", "отображение", "зависимость", "преобразование"),
    ("данные", "информация", "сведения", "выборка"),
    ("алгоритм", "метод", "способ", "подход", "процедура"),
    ("память", "запоминание", "хранить", "запомнить"),
    ("ошибка", "погрешность", "неточность", "промах"),
    ("начало", "введение", "старт", "вступление"),
    ("итог", "вывод", "заключение", "резюме", "завершение"),
    ("задача", "упражнение", "вопрос", "задание"),
    ("лекция", "занятие", "урок", "выступление"),
    ("студент", "учащийся", "обучающийся", "ученик"),
    ("преподаватель", "учитель", "лектор", "педагог"),
    ("поиск", "нахождение", "отыскание", "искать", "находить"),
    ("смысл", "значение", "суть", "содержание"),
    ("конспект", "краткое содержание", "изложение", "пересказ"),
    ("гипотенуза", "сторона треугольника", "длинная сторона"),
    ("катет", "сторона", "прямой угол"),
    ("треугольник", "фигура", "геометрия"),
    ("пифагор", "древнегреческий математик"),
    ("площадь", "квадрат", "размер поверхности"),
    ("вектор", "направление", "стрелка"),
    ("матрица", "таблица чисел", "массив"),
    ("вероятность", "шанс", "случайность"),
    ("язык", "речь", "текст", "слово"),
    ("изображение", "картинка", "фото", "видео"),
    ("компьютер", "машина", "вычислитель"),
)
PHRASE_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "теорема пифагора": ("гипотенуза", "катет", "прямоугольный треугольник", "квадрат"),
    "нейронная сеть": ("нейросеть", "слой", "обучение", "вес"),
    "искусственный интеллект": ("нейросеть", "модель", "обучение"),
    "машинное обучение": ("модель", "данные", "обучение", "признак"),
    "обратное распространение": ("градиент", "ошибка", "вес", "обучение"),
}

_SYNONYMS: dict[str, set[str]] = {}
for _group in SYNONYM_GROUPS:
    for _word in _group:
        _SYNONYMS.setdefault(_word, set()).update(w for w in _group if w != _word)


def normalize_text(text: str) -> str:
    text = text.replace("\ufeff", " ").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@lru_cache(maxsize=50000)
def analyze_word(word: str) -> tuple[str, str]:
    """(лемма, часть речи) для слова."""
    lower = word.lower().replace("ё", "е")
    if not lower:
        return "", ""
    if _MORPH is None:
        return lower, ""
    try:
        parsed = _MORPH.parse(lower)[0]
        return parsed.normal_form.replace("ё", "е"), str(parsed.tag.POS or "")
    except Exception:
        return lower, ""


def lemma(word: str) -> str:
    return analyze_word(word)[0]


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def lemmatize(text: str, keep_stop: bool = False) -> list[str]:
    result: list[str] = []
    for raw in words(text):
        low = raw.lower().replace("ё", "е")
        if not keep_stop and low in STOPWORDS:
            continue
        if len(low) <= 1 and not low.isdigit():
            continue
        result.append(lemma(raw))
    return [w for w in result if w]


def lemma_string(text: str) -> str:
    return " ".join(lemmatize(text))


def lemma_set(text: str) -> set[str]:
    return set(lemmatize(text))


def is_probably_abbreviation(token: str) -> bool:
    token = token.strip("()[]«»\"'").lower().replace(".", "")
    if not token:
        return False
    if token in ABBREVIATIONS:
        return True
    # одиночная заглавная буква (инициалы): «А. С. Пушкин»
    if len(token) == 1 and token.isalpha():
        return True
    return False


def split_sentences(text: str) -> list[str]:
    """Аккуратная нарезка на предложения без внешних моделей."""
    text = normalize_text(text)
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in SENT_END:
            # многоточие/восклицательный/вопросительный — граница почти всегда
            if ch == ".":
                # десятичная дробь 3.14
                if i > 0 and i + 1 < length and text[i - 1].isdigit() and text[i + 1].isdigit():
                    i += 1
                    continue
                prev = text[start:i].split()[-1] if text[start:i].split() else ""
                if is_probably_abbreviation(prev):
                    i += 1
                    continue
            j = i + 1
            while j < length and text[j] in ".!?…":
                j += 1
            k = j
            while k < length and text[k] in " \t\n\"»”')]":
                k += 1
            if k >= length:
                chunk = text[start:j].strip()
                if chunk:
                    sentences.append(chunk)
                start = length
                break
            nxt = text[k]
            # строчная буква после точки — скорее всего не граница
            if ch == "." and nxt.islower() and not text[start:j].rstrip().endswith(("т.е.", "т. д.")):
                i = j
                continue
            chunk = text[start:j].strip()
            if chunk:
                sentences.append(chunk)
            start = k
            i = k
            continue
        if ch == "\n":
            k = i + 1
            while k < length and text[k] in " \t\n":
                k += 1
            chunk = text[start:i].strip()
            tail_words = chunk.split()
            last_word = tail_words[-1].lower() if tail_words else ""
            if chunk and (
                k >= length
                or (
                    not chunk.endswith((",", ":", "—", "-"))
                    and last_word not in {"и", "или"}
                )
            ):
                sentences.append(chunk)
                start = k
                i = k
                continue
        i += 1
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    # склеиваем совсем короткие обрывки с предыдущим предложением
    merged: list[str] = []
    for sentence in sentences:
        if merged and len(sentence) < 12 and not merged[-1].endswith((".", "!", "?", "…")):
            merged[-1] = f"{merged[-1]} {sentence}".strip()
        else:
            merged.append(sentence)
    return [s for s in merged if s]


def query_terms(query: str) -> dict[str, float]:
    """Леммы запроса с весами: исходные 1.0, синонимы 0.45."""
    base = lemmatize(query)
    weights: dict[str, float] = {}
    for term in base:
        weights[term] = max(weights.get(term, 0.0), 1.0)
    for term in list(base):
        for syn in _SYNONYMS.get(term, ()):  # type: ignore[arg-type]
            for piece in (syn.split() if " " in syn else [syn]):
                syn_lemma = lemma(piece)
                if syn_lemma and syn_lemma not in weights:
                    weights[syn_lemma] = 0.45
    q_norm = " ".join(query.lower().replace("ё", "е").split())
    for phrase, expansions in PHRASE_EXPANSIONS.items():
        if phrase in q_norm:
            for exp in expansions:
                for piece in exp.split():
                    exp_lemma = lemma(piece)
                    if exp_lemma:
                        weights.setdefault(exp_lemma, 0.5)
    return weights


def keyword_weights(texts: Sequence[str], top_n: int = 12) -> list[dict]:
    """Ключевые термины: TF-IDF по предложениям + бонус за существительные."""
    n = max(1, len(texts))
    tf: Counter[str] = Counter()
    df: Counter[str] = Counter()
    surfaces: dict[str, Counter[str]] = {}
    positions: dict[str, int] = {}
    first_char = 0
    for idx, text in enumerate(texts):
        found: set[str] = set()
        for raw in words(text):
            low = raw.lower().replace("ё", "е")
            if low in STOPWORDS or len(low) < 3:
                continue
            lem, pos = analyze_word(raw)
            if not lem or len(lem) < 3 or lem in STOPWORDS:
                continue
            tf[lem] += 1
            found.add(lem)
            surfaces.setdefault(lem, Counter())[low] += 1
            positions.setdefault(lem, first_char)
        for lem in found:
            df[lem] += 1
        first_char += len(text) + 1
    total_words = max(1, sum(tf.values()))
    scored: list[tuple[float, str]] = []
    for lem, count in tf.items():
        if count < 2 and n > 4:
            continue
        idf = math.log((n + 1) / (df[lem] + 0.5)) + 0.35
        pos = analyze_word(lem)[1]
        pos_bonus = 1.25 if pos.startswith(("NOUN", "ADJ")) else 1.0
        score = (count / total_words) * idf * pos_bonus * (1 + min(count, 8) * 0.04)
        scored.append((score, lem))
    scored.sort(reverse=True)
    result: list[dict] = []
    seen: set[str] = set()
    for score, lem in scored:
        if lem in seen:
            continue
        seen.add(lem)
        surface = surfaces[lem].most_common(1)[0][0] if surfaces.get(lem) else lem
        result.append(
            {
                "term": surface,
                "lemma": lem,
                "count": int(tf[lem]),
                "score": round(float(score) * 1000, 2),
            }
        )
        if len(result) >= top_n:
            break
    return result


def _sentence_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / (math.sqrt(len(a)) * math.sqrt(len(b)))


def textrank_sentences(sentences: Sequence[str], top_k: int) -> list[int]:
    """TextRank по леммам; возвращает индексы выбранных предложений."""
    if not sentences:
        return []
    if len(sentences) <= top_k:
        return list(range(len(sentences)))
    sets = [lemma_set(s) for s in sentences]
    n = len(sentences)
    sim = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            value = _sentence_similarity(sets[i], sets[j])
            sim[i, j] = sim[j, i] = value
    row_sum = sim.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0] = 1.0
    trans = sim / row_sum
    rank = np.full(n, 1.0 / n, dtype=np.float32)
    for _ in range(35):
        new_rank = 0.15 / n + 0.85 * (trans.T @ rank)
        if np.abs(new_rank - rank).sum() < 1e-5:
            rank = new_rank
            break
        rank = new_rank
    # лёгкий бонус за длину и раннее положение
    adjusted = []
    for i, sentence in enumerate(sentences):
        length_bonus = 1.0 if 50 <= len(sentence) <= 260 else 0.85
        position_bonus = 1.08 if i < n * 0.25 else 1.0
        adjusted.append((float(rank[i]) * length_bonus * position_bonus, i))
    adjusted.sort(reverse=True)
    chosen: list[int] = []
    chosen_sets: list[set[str]] = []
    for _, idx in adjusted:
        # MMR, чтобы тезисы не дублировали друг друга
        if chosen_sets:
            duplicate = max(_sentence_similarity(sets[idx], s) for s in chosen_sets)
            if duplicate > 0.62:
                continue
        chosen.append(idx)
        chosen_sets.append(sets[idx])
        if len(chosen) >= top_k:
            break
    return sorted(chosen)


@dataclass
class SummaryResult:
    text: str
    points: list[dict]
    keywords: list[dict]


def summarize(texts: Sequence[str], starts: Sequence[float] | None = None,
              ends: Sequence[float] | None = None, target_ratio: float = 0.16) -> SummaryResult:
    """Экстрактивный конспект с таймкодами и ключевыми терминами."""
    sentences: list[str] = []
    sent_start: list[float] = []
    sent_end: list[float] = []
    # Whisper sometimes режет предложение на две реплики. Держим «хвост»
    # без точки и склеиваем его со следующей репликой, иначе в конспект
    # попадают обрывки вроде «...настраивается во».
    pending = ""
    pending_start = 0.0
    for i, text in enumerate(texts):
        cue_start = float(starts[i]) if starts else 0.0
        cue_end = float(ends[i]) if ends else 0.0
        piece = (pending + " " + text).strip() if pending else text
        piece_start = pending_start if pending else cue_start
        pending = ""
        parts = split_sentences(piece)
        for part_index, sentence in enumerate(parts):
            is_last = part_index == len(parts) - 1
            if is_last and not sentence.rstrip().endswith((".", "!", "?", "…", ":")):
                pending = sentence
                pending_start = piece_start if part_index == 0 else cue_start
                continue
            if len(sentence) < 26:
                continue
            sentences.append(sentence)
            sent_start.append(piece_start if part_index == 0 else cue_start)
            sent_end.append(cue_end)
    if pending and len(pending) >= 26:
        sentences.append(pending)
        sent_start.append(pending_start)
        sent_end.append(float(ends[-1]) if ends else 0.0)
    if not sentences:
        joined = " ".join(texts).strip()
        return SummaryResult(text=joined, points=[], keywords=keyword_weights(texts))

    k = max(3, min(8, round(len(sentences) * target_ratio)))
    k = min(k, max(1, len(sentences)))
    chosen = textrank_sentences(sentences, k)
    points = [
        {
            "text": sentences[i],
            "start": sent_start[i],
            "end": sent_end[i],
        }
        for i in chosen
    ]
    summary_text = " ".join(p["text"] for p in points)
    return SummaryResult(
        text=summary_text,
        points=points,
        keywords=keyword_weights(texts, top_n=14),
    )


SECTION_RE = re.compile(
    r"^\s*(?:(часть|раздел|глава|тема|урок|лекция)\s+([а-яёa-z0-9]+)|"
    r"(первая|вторая|третья|четвёртая|четвертая|пятая|шестая)\s+часть|"
    r"(перейд[её]м|переходим|теперь|далее|итак|в\s+заключени[еи]|"
    r"подвед[её]м\s+итог|начн[её]м|рассмотрим))\b",
    re.IGNORECASE,
)


PART_LABEL_RE = re.compile(
    r"^(?:часть|раздел|глава|тема|урок|лекция)\s+[а-яёa-z0-9]+$",
    re.IGNORECASE,
)
GREETING_RE = re.compile(
    r"^(здравствуйте|добрый\s+(?:день|вечер)|доброе\s+утро|привет|коллеги|друзья)\b",
    re.IGNORECASE,
)


def _clean_title(sentence: str) -> str:
    title = re.sub(r"^(итак|ну|хорошо|ладно|друзья|коллеги|студенты)[,:\s]+", "", sentence.strip(),
                   flags=re.IGNORECASE)
    title = re.sub(r"^(сегодня|сейчас|теперь)\s+(мы\s+)?", "", title, flags=re.IGNORECASE)
    title = title.strip(" .,:;—–-")
    if len(title) > 72:
        cut = title[:72]
        if " " in cut:
            cut = cut[: cut.rfind(" ")]
        title = cut.rstrip(" ,:;—–-") + "…"
    if title:
        title = title[0].upper() + title[1:]
    return title


def _chapter_title(chapter_cues: Sequence[dict], chapter_text: str, chapter_idx: int) -> str:
    """Осмысленное название главы: маркер раздела + следующая фраза."""
    texts = [str(cue.get("text") or "").strip() for cue in chapter_cues[:4]]
    for index, text in enumerate(texts[:3]):
        if not SECTION_RE.match(text):
            continue
        title = _clean_title(text)
        if PART_LABEL_RE.fullmatch(title):
            # «Часть первая.» почти всегда сопровождается названием темы
            # следующей репликой — используем его вместо технического маркера.
            for candidate_text in texts[index + 1:index + 3]:
                candidate = _clean_title(candidate_text)
                if len(candidate) >= 4 and not PART_LABEL_RE.fullmatch(candidate):
                    return candidate
            return title
        return title or ""

    if chapter_idx == 0 and texts and GREETING_RE.match(texts[0]):
        return "Введение"

    for sentence in split_sentences(chapter_text):
        if len(sentence) < 18 or GREETING_RE.match(sentence):
            continue
        candidate = _clean_title(sentence)
        if len(candidate) >= 4:
            return candidate

    keywords = keyword_weights([chapter_text], top_n=2)
    if keywords:
        return str(keywords[0]["term"]).capitalize()
    return f"Часть {chapter_idx + 1}"


def build_chapters(cues: Sequence[dict], vectors: np.ndarray | None = None,
                   duration: float | None = None) -> list[dict]:
    """Автоматическая структура лекции по семантическим сдвигам и маркерам."""
    if not cues:
        return []
    duration = float(duration or cues[-1]["end"])
    n = len(cues)

    # 1. Явные маркеры начала раздела
    forced: list[int] = [0]
    for i, cue in enumerate(cues):
        text = cue.get("text", "").strip()
        if not text:
            continue
        m = SECTION_RE.match(text)
        if not m:
            continue
        if i == 0:
            continue
        if cue["start"] - cues[forced[-1]]["start"] < 25:
            continue
        if duration - cue["start"] < 25:
            continue
        forced.append(i)

    # 2. Семантические границы по окнам
    windows: list[list[int]] = []
    current: list[int] = []
    win_start = cues[0]["start"]
    for i, cue in enumerate(cues):
        current.append(i)
        if cue["end"] - win_start >= 70 or len(current) >= 9:
            windows.append(current)
            current = []
            win_start = cues[i + 1]["start"] if i + 1 < n else cue["end"]
    if current:
        windows.append(current)

    boundary_candidates: list[tuple[float, int]] = []
    if vectors is not None and len(windows) >= 2:
        win_vecs = []
        for win in windows:
            idxs = [i for i in win if i < len(vectors)]
            if idxs:
                vec = vectors[idxs].mean(axis=0)
                norm = float(np.linalg.norm(vec)) or 1.0
                win_vecs.append(vec / norm)
            else:
                win_vecs.append(np.zeros(vectors.shape[1], dtype=np.float32))
        for w in range(1, len(windows)):
            sim = float(np.dot(win_vecs[w - 1], win_vecs[w]))
            shift = max(0.0, 1.0 - sim)
            first = windows[w][0]
            lexical = 0.0
            prev_lemmas = lemma_set(" ".join(cues[i]["text"] for i in windows[w - 1]))
            next_lemmas = lemma_set(" ".join(cues[i]["text"] for i in windows[w]))
            if prev_lemmas or next_lemmas:
                lexical = 1.0 - len(prev_lemmas & next_lemmas) / max(1, len(prev_lemmas | next_lemmas))
            score = shift * 0.8 + lexical * 0.2
            if cues[first]["start"] - cues[windows[w - 1][0]]["start"] >= 45:
                boundary_candidates.append((score, first))

    min_chapter = max(50.0, min(120.0, duration / 8))
    boundaries = set(forced)
    target_max = 9
    for score, idx in sorted(boundary_candidates, reverse=True):
        if len(boundaries) >= target_max:
            break
        start = cues[idx]["start"]
        if duration - start < min_chapter * 0.7:
            continue
        if any(abs(start - cues[b]["start"]) < min_chapter for b in boundaries):
            continue
        if score < 0.12:
            continue
        boundaries.add(idx)
    boundaries = sorted(boundaries)

    chapters: list[dict] = []
    for chapter_idx, start_idx in enumerate(boundaries):
        end_idx = boundaries[chapter_idx + 1] if chapter_idx + 1 < len(boundaries) else n
        chapter_cues = cues[start_idx:end_idx]
        if not chapter_cues:
            continue
        chapter_start = float(chapter_cues[0]["start"])
        chapter_end = float(chapter_cues[-1]["end"])
        chapter_texts = [c["text"] for c in chapter_cues]
        chapter_text = " ".join(chapter_texts).strip()

        title = _chapter_title(chapter_cues, chapter_text, chapter_idx)
        if not title:
            title = f"Часть {chapter_idx + 1}"

        chapter_summary = summarize(chapter_texts, target_ratio=0.12).text
        if len(chapter_summary) > 360:
            cut = chapter_summary[:360]
            cut = cut[: cut.rfind(" ")] if " " in cut else cut
            chapter_summary = cut.rstrip(" ,:;—") + "…"
        keywords = keyword_weights(chapter_texts, top_n=6)
        chapters.append(
            {
                "idx": chapter_idx,
                "start": round(chapter_start, 3),
                "end": round(chapter_end, 3),
                "title": title,
                "summary": chapter_summary,
                "keywords": keywords,
            }
        )

    # склеиваем слишком короткие главы с предыдущей
    cleaned: list[dict] = []
    for chapter in chapters:
        if cleaned and chapter["end"] - chapter["start"] < 35:
            cleaned[-1]["end"] = chapter["end"]
            cleaned[-1]["summary"] = (cleaned[-1]["summary"] + " " + chapter["summary"]).strip()
            continue
        cleaned.append(chapter)
    for i, chapter in enumerate(cleaned):
        chapter["idx"] = i
    return cleaned


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(round(float(seconds))))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def srt_timestamp(seconds: float) -> str:
    ms = int(round(max(0.0, float(seconds)) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def vtt_timestamp(seconds: float) -> str:
    return srt_timestamp(seconds).replace(",", ".")


def cues_to_srt(cues: Iterable[dict]) -> str:
    blocks = []
    for i, cue in enumerate(cues, 1):
        blocks.append(
            f"{i}\n{srt_timestamp(cue['start'])} --> {srt_timestamp(cue['end'])}\n{cue['text']}\n"
        )
    return "\n".join(blocks)


def cues_to_vtt(cues: Iterable[dict]) -> str:
    blocks = ["WEBVTT\n"]
    for cue in cues:
        blocks.append(
            f"{vtt_timestamp(cue['start'])} --> {vtt_timestamp(cue['end'])}\n{cue['text']}\n"
        )
    return "\n".join(blocks)


def highlight_html(text: str, terms: Sequence[str],
                   lemmas: Sequence[str] | None = None) -> str:
    """Экранированный HTML с <mark> вокруг вхождений терминов.

    ``terms`` — точные подстроки (регистр не важен), ``lemmas`` — леммы для
    морфологически устойчивой подсветки: «гипотенуза» пометит «гипотенузы».
    """
    import html as html_module

    escaped = html_module.escape(text)
    candidates = {t for t in terms if t and len(t) > 1}
    targets = {lemma_value for lemma_value in (lemmas or ()) if lemma_value}
    if targets:
        for word in words(text):
            if lemma(word) in targets:
                candidates.add(word)
    clean_terms = sorted(candidates, key=len, reverse=True)
    if not clean_terms:
        return escaped
    pattern = re.compile("|".join(re.escape(t) for t in clean_terms), re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)
