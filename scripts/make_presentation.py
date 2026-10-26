"""Сборка презентации «Вектор» из скриншотов.

Запуск:
    python scripts/make_presentation.py

Результат: docs/Вектор_презентация.pptx
Скриншоты: docs/screenshots/*.png (снимаются отдельно из работающего UI).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
OUTPUT = ROOT / "docs" / "Вектор_презентация.pptx"

BG = RGBColor(0x08, 0x0A, 0x09)
PANEL = RGBColor(0x10, 0x14, 0x0F)
PANEL_2 = RGBColor(0x15, 0x1A, 0x13)
INK = RGBColor(0xF1, 0xF4, 0xEC)
MUTED = RGBColor(0x9A, 0xA3, 0x94)
MUTED_2 = RGBColor(0x6F, 0x78, 0x6A)
LIME = RGBColor(0xC8, 0xF5, 0x60)
LINE = RGBColor(0x2B, 0x33, 0x27)
AMBER = RGBColor(0xF5, 0xC8, 0x60)

SANS = "Segoe UI"
SERIF = "Cambria"
W, H = 13.333, 7.5


def new_deck() -> Presentation:
    deck = Presentation()
    deck.slide_width = Inches(W)
    deck.slide_height = Inches(H)
    return deck


def blank(deck: Presentation):
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG
    return slide


def add_rect(slide, x, y, w, h, fill=None, line=None, radius=None, width=1.0):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    if radius:
        shape.adjustments[0] = radius
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(width)
    shape.shadow.inherit = False
    return shape


def add_text(slide, x, y, w, h, text, size=14, color=MUTED, bold=False,
             font=SANS, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
             italic=False, spacing=1.0, margin=0.0):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = Inches(margin)
    frame.margin_right = Inches(margin)
    frame.margin_top = 0
    frame.margin_bottom = 0
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = spacing
    run = paragraph.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return box


def add_rich_text(slide, x, y, w, h, parts, size=14, spacing=1.0,
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """parts: list of (text, color, bold, font, italic?)"""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = spacing
    for part in parts:
        text, color, bold, font = part[:4]
        italic = part[4] if len(part) > 4 else False
        run = paragraph.add_run()
        run.text = text
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
    return box


def add_bullets(slide, x, y, w, items, size=14, color=MUTED, gap=8, line_spacing=1.12):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.5))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(gap)
        paragraph.line_spacing = line_spacing
        paragraph.alignment = PP_ALIGN.LEFT
        if isinstance(item, tuple):
            lead, rest = item
            first = paragraph.add_run()
            first.text = lead
            first.font.name = SANS
            first.font.size = Pt(size)
            first.font.bold = True
            first.font.color.rgb = INK
            second = paragraph.add_run()
            second.text = rest
            second.font.name = SANS
            second.font.size = Pt(size)
            second.font.color.rgb = color
        else:
            run = paragraph.add_run()
            run.text = "—  " + item
            run.font.name = SANS
            run.font.size = Pt(size)
            run.font.color.rgb = color
    return box


def add_header(slide, kicker, title, subtitle=None):
    add_text(slide, 0.75, 0.50, 10.5, 0.28, kicker.upper(), size=10.5, color=LIME, bold=True)
    add_text(slide, 0.75, 0.80, 11.6, 0.62, title, size=31, color=INK, bold=True, spacing=0.95)
    if subtitle:
        add_text(slide, 0.75, 1.38, 11.4, 0.44, subtitle, size=13.5, color=MUTED, spacing=1.05)


def add_footer(slide, number: int, total: int):
    add_rect(slide, 0.75, 7.05, 11.83, 0.01, fill=LINE)
    add_text(slide, 0.75, 7.12, 8.5, 0.22,
             "Вектор · семантический поиск по видеолекциям", size=9, color=MUTED_2)
    add_text(slide, 11.2, 7.12, 1.38, 0.22, f"{number:02d} / {total:02d}",
             size=9, color=MUTED_2, align=PP_ALIGN.RIGHT, font=SANS)


def add_picture(slide, name: str, x: float, y: float, w: float,
                border=True, max_h: float | None = None):
    path = SHOTS / name
    if not path.exists():
        raise SystemExit(f"Нет скриншота {path}. Сначала снимите UI.")
    with Image.open(path) as image:
        ratio = image.width / image.height
    height = w / ratio
    if max_h and height > max_h:
        height = max_h
        w = height * ratio
    picture = slide.shapes.add_picture(
        str(path), Inches(x), Inches(y), width=Inches(w), height=Inches(height)
    )
    if border:
        add_rect(slide, x, y, w, height, fill=None, line=LINE, width=0.75)
    return w, height


def add_caption(slide, x, y, w, text):
    add_text(slide, x, y, w, 0.24, text, size=9.5, color=MUTED_2, italic=True)


def add_pill(slide, x, y, w, text, color=LIME, fill=PANEL):
    add_rect(slide, x, y, w, 0.34, fill=fill, line=LINE, radius=0.5)
    add_text(slide, x + 0.16, y + 0.06, w - 0.3, 0.22, text, size=9.5, color=color, bold=True)


def add_card(slide, x, y, w, h, number, title, body, accent=False):
    add_rect(slide, x, y, w, h, fill=PANEL, line=LINE, radius=0.06)
    add_text(slide, x + 0.28, y + 0.24, 0.8, 0.5, number, size=28, color=LIME if accent else MUTED_2,
             bold=True, font=SERIF, italic=True)
    add_text(slide, x + 0.28, y + 0.86, w - 0.56, 0.32, title, size=15.5, color=INK, bold=True)
    add_text(slide, x + 0.28, y + 1.26, w - 0.56, h - 1.45, body, size=11.5, color=MUTED, spacing=1.18)


def add_notes(slide, text: str):
    slide.notes_slide.notes_text_frame.text = text


def build() -> None:
    deck = new_deck()
    total = 14

    # 1 ---------------------------------------------------------------- title
    slide = blank(deck)
    add_rect(slide, 0, 0, 0.18, H, fill=LIME)
    add_text(slide, 0.95, 0.85, 6.0, 0.3, "КИБЕРРЫВОК · ОСЕНЬ 2026", size=11, color=LIME, bold=True)
    add_rich_text(slide, 0.9, 1.18, 9.0, 1.4, [
        ("Вектор", INK, True, SANS),
        (".", LIME, True, SANS),
    ], size=78, spacing=0.9)
    add_text(slide, 0.95, 2.72, 9.6, 0.9, "Найдите момент, а не таймкод.", size=31,
             color=INK, font=SERIF, italic=True)
    add_text(slide, 0.95, 3.62, 8.0, 1.0,
             "Семантический поиск по видеолекциям: загрузка, расшифровка, конспект, "
             "структура и переход к нужной секунде по смыслу запроса.",
             size=16, color=MUTED, spacing=1.25)
    add_pill(slide, 0.95, 4.95, 1.55, "FastAPI")
    add_pill(slide, 2.62, 4.95, 2.15, "faster-whisper")
    add_pill(slide, 4.90, 4.95, 2.45, "potion-multilingual")
    add_pill(slide, 7.48, 4.95, 1.25, "SQLite")
    add_text(slide, 0.95, 6.62, 11.4, 0.32,
             "Полностью локальный прототип · без обязательных API-ключей · запуск одной командой",
             size=11.5, color=MUTED_2)
    add_text(slide, 10.55, 6.55, 2.0, 0.4, "01", size=8, color=LINE, bold=True, align=PP_ALIGN.RIGHT)
    add_notes(slide, "«Вектор» — прототип семантического поиска по видеолекциям. "
                     "Главная идея: пользователь ищет смысл, а не точные слова, и сразу попадает на нужную секунду.")

    # 2 -------------------------------------------------------------- problem
    slide = blank(deck)
    add_header(slide, "Проблема", "Лекция длится час. Нужная мысль — 40 секунд.",
               "Искать по таймкоду, субтитрам и названиям глав — долго. Конспект приходится писать вручную.")
    stats = [
        ("90+", "минут", "средняя видеолекция"),
        ("~15", "минут", "на ручной поиск фрагмента"),
        ("0", "систем", "ищут по смыслу, а не по словам"),
    ]
    for index, (value, unit, label) in enumerate(stats):
        x = 0.75 + index * 4.12
        add_rect(slide, x, 2.25, 3.82, 1.62, fill=PANEL, line=LINE, radius=0.06)
        add_text(slide, x + 0.3, 2.45, 1.5, 0.7, value, size=40, color=LIME, bold=True)
        add_text(slide, x + 1.7, 2.62, 1.9, 0.3, unit, size=12, color=INK, bold=True)
        add_text(slide, x + 0.3, 3.25, 3.2, 0.4, label, size=11, color=MUTED)
    add_text(slide, 0.75, 4.30, 11.7, 0.4, "Что не работает сегодня", size=12, color=INK, bold=True)
    add_bullets(slide, 0.75, 4.78, 11.7, [
        ("Поиск по словам. ", "«как учится нейросеть» не находит «сеть учится на данных»."),
        ("Ручная навигация. ", "студент перематывает видео, чтобы проверить одну цитату."),
        ("Нет структуры. ", "конспект, главы и термины приходится собирать вручную."),
    ], size=14, gap=9)
    add_footer(slide, 2, total)
    add_notes(slide, "Боль: видеолекции длинные, а поиск обычно лексический. "
                     "Нужен инструмент, который понимает смысл и сразу ведёт к моменту.")

    # 3 ------------------------------------------------------------- solution
    slide = blank(deck)
    add_header(slide, "Решение", "Один путь: от файла до нужной секунды",
               "Четыре шага, без ручной разметки, субтитров и облачных сервисов.")
    steps = [
        ("01", "Загрузка", "MP4, WebM, MOV или ссылка YouTube / Vimeo. Файл остаётся на вашем сервере."),
        ("02", "Расшифровка", "Whisper распознаёт речь, расставляет таймкоды и слова. Язык — автоматически."),
        ("03", "Индексация", "model2vec считает векторы реплик. TextRank собирает конспект, главы и термины."),
        ("04", "Поиск", "Запрос на естественном языке → фрагмент, таймкод и переход в плеере."),
    ]
    for index, (number, title, body) in enumerate(steps):
        x = 0.75 + index * 3.05
        add_card(slide, x, 2.15, 2.72, 3.2, number, title, body, accent=index == 3)
        if index < 3:
            add_text(slide, x + 2.76, 3.45, 0.3, 0.4, "→", size=18, color=LIME, bold=True)
    add_rect(slide, 0.75, 5.78, 11.83, 0.78, fill=PANEL_2, line=LINE, radius=0.08)
    add_rich_text(slide, 1.0, 5.98, 11.35, 0.4, [
        ("Результат: ", LIME, True, SANS),
        ("студент задаёт вопрос по-человечески и оказывается на нужной секунде за один клик.", INK, False, SANS),
    ], size=14)
    add_footer(slide, 3, total)
    add_notes(slide, "Вся цепочка автоматическая: загрузка, ASR, эмбеддинги, структура, поиск. "
                     "Ключевой результат — переход к моменту, а не список файлов.")

    # 4 ----------------------------------------------------------- home shot
    slide = blank(deck)
    add_header(slide, "Интерфейс", "Библиотека и живой поиск",
               "Сразу видно, что уже готово к поиску: лекции, часы, фрагменты и главы.")
    width, height = add_picture(slide, "01-home.png", 4.55, 1.85, 8.0, max_h=5.0)
    add_caption(slide, 4.55, 1.85 + height + 0.08, 8.0, "Главная страница: герой, живой семантический пример и библиотека")
    add_text(slide, 0.75, 1.95, 3.5, 0.4, "Что на экране", size=12, color=INK, bold=True)
    add_bullets(slide, 0.75, 2.45, 3.55, [
        "2 демо-лекции, 131 фрагмент, 12 глав",
        "поиск по всему курсу из шапки",
        "загрузка и импорт по ссылке",
        "редакторский тёмный интерфейс без сборки",
    ], size=12.5, gap=7)
    add_rect(slide, 0.75, 4.55, 3.55, 1.05, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 0.95, 4.72, 3.15, 0.7, "«Откройте момент» — каждая карточка результата ведёт на таймкод.",
             size=11, color=MUTED, spacing=1.15)
    add_footer(slide, 4, total)
    add_notes(slide, "Главная страница показывает ценность сразу: живой семантический пример, статистику и библиотеку.")

    # 5 --------------------------------------------------------- upload shot
    slide = blank(deck)
    add_header(slide, "Загрузка", "Файл или ссылка — дальше без ручной работы",
               "Очередь, прогресс и статусы: «В очереди → Обработка → Готово».")
    width, height = add_picture(slide, "07-upload.png", 4.55, 1.85, 8.0, max_h=5.0)
    add_caption(slide, 4.55, 1.85 + height + 0.08, 8.0, "Модальное окно загрузки: файл или ссылка, название и язык")
    add_text(slide, 0.75, 1.95, 3.55, 0.4, "Поддерживается", size=12, color=INK, bold=True)
    add_bullets(slide, 0.75, 2.45, 3.55, [
        ("Видео: ", "MP4, WebM, MOV, MKV, M4V, AVI"),
        ("Аудио: ", "MP3, M4A, WAV, OGG, OPUS"),
        ("Ссылки: ", "YouTube и Vimeo через yt-dlp"),
        ("Проверка: ", "ffprobe, длительность, кодек, превью"),
        ("Хранение: ", "файлы вне БД, отдача с HTTP Range"),
    ], size=12.5, gap=7)
    add_footer(slide, 5, total)
    add_notes(slide, "Загрузка поддерживает видео, аудио и ссылки. Валидация и превью — на стороне сервера. "
                     "Файлы лежат вне SQLite, видео отдаётся с поддержкой Range.")

    # 6 --------------------------------------------------------- lecture shot
    slide = blank(deck)
    add_header(slide, "Просмотр", "Плеер, который понимает текст",
               "Расшифровка, субтитры и главы синхронизированы с видео.")
    width, height = add_picture(slide, "03-lecture.png", 4.55, 1.85, 8.0, max_h=5.0)
    add_caption(slide, 4.55, 1.85 + height + 0.08, 8.0, "Лекция открыта на 05:02: плеер, главы, термины и действия")
    add_text(slide, 0.75, 1.95, 3.55, 0.4, "Навигация", size=12, color=INK, bold=True)
    add_bullets(slide, 0.75, 2.45, 3.55, [
        "клик по реплике перематывает видео",
        "активная реплика подсвечивается",
        "субтитры VTT поверх видео",
        "маркеры глав и результатов на таймлайне",
        "deep link ?t=302 и «поделиться моментом»",
    ], size=12.5, gap=7)
    add_rect(slide, 0.75, 5.22, 3.55, 0.72, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 0.95, 5.36, 3.15, 0.5, "Скорость, звук, ±10 секунд, fullscreen — без внешнего плеера.",
             size=10.5, color=MUTED, spacing=1.1)
    add_footer(slide, 6, total)
    add_notes(slide, "Собственный плеер: клик по тексту перематывает, активная реплика подсвечивается. "
                     "Ссылка ?t=302 открывает лекцию ровно на нужном моменте.")

    # 7 ------------------------------------------------- summary + chapters
    slide = blank(deck)
    add_header(slide, "Конспект и структура", "Лекция сама становится оглавлением",
               "Экстрактивный конспект, ключевые тезисы с таймкодами и автоматические главы.")
    w1, h1 = add_picture(slide, "04a-summary.png", 0.75, 1.82, 5.72, max_h=3.45)
    w2, h2 = add_picture(slide, "04b-chapters.png", 6.86, 1.82, 5.72, max_h=3.45)
    add_caption(slide, 0.75, 1.82 + h1 + 0.08, 5.72, "Конспект: главная мысль и ключевые тезисы с таймкодами")
    add_caption(slide, 6.86, 1.82 + h2 + 0.08, 5.72, "Структура: главы, названия и переходы к началу")
    add_text(slide, 0.75, 5.72, 11.83, 0.75,
             "TextRank + семантические сдвиги: без ручной разметки и без обязательного LLM. "
             "Экспорт конспекта — в Markdown, субтитры — в VTT/SRT.",
             size=13, color=MUTED, spacing=1.2)
    add_footer(slide, 7, total)
    add_notes(slide, "Конспект и главы строятся локально. На слайде — один и тот же экран в двух вкладках. "
                     "Всё можно скачать: Markdown, VTT, SRT.")

    # 8 ---------------------------------------------------------- search shot
    slide = blank(deck)
    add_header(slide, "Семантический поиск", "Находит смысл, даже когда слов нет",
               "Гибрид dense + BM25 + покрытие запроса + MMR-диверсификация.")
    width, height = add_picture(slide, "05-search.png", 3.95, 1.85, 8.65, max_h=5.0)
    add_caption(slide, 3.95, 1.85 + height + 0.08, 8.65, "Запрос «как учится нейросеть» → 06:20, 5 фрагментов, 79 мс")
    add_rect(slide, 0.75, 1.95, 2.95, 1.42, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 0.94, 2.10, 2.6, 0.26, "ЗАПРОС", size=9, color=LIME, bold=True)
    add_text(slide, 0.94, 2.42, 2.6, 0.8, "«как учится нейросеть»", size=14, color=INK, bold=True, spacing=1.1)
    add_rect(slide, 0.75, 3.55, 2.95, 1.42, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 0.94, 3.70, 2.6, 0.26, "НАЙДЕНО НА 06:20", size=9, color=LIME, bold=True)
    add_text(slide, 0.94, 4.02, 2.6, 0.8, "«Так сеть постепенно уменьшает ошибку и учится на данных»",
             size=11.5, color=INK, spacing=1.12)
    add_bullets(slide, 0.75, 5.22, 2.95, [
        "слова «нейросеть» в тексте нет",
        "каждый результат — таймкод и сниппет",
        "фильтр по лекции или весь курс",
    ], size=10.5, gap=5)
    add_footer(slide, 8, total)
    add_notes(slide, "Главный вау-момент: запрос «как учится нейросеть» находит фразу «сеть учится на данных». "
                     "Слова «нейросеть» в тексте нет — работает смысловой индекс.")

    # 9 -------------------------------------------------------------- qa shot
    slide = blank(deck)
    add_header(slide, "Вопрос-ответ", "Ответ с цитатами, а не пересказ без источника",
               "RAG по расшифровке: офлайн-экстрактивный режим или любой OpenAI-совместимый LLM.")
    width, height = add_picture(slide, "06-qa.png", 4.35, 1.85, 8.25, max_h=5.0)
    add_caption(slide, 4.35, 1.85 + height + 0.08, 8.25, "Вопрос по лекции → ответ и цитаты с таймкодами")
    add_text(slide, 0.75, 1.95, 3.35, 0.4, "Как это работает", size=12, color=INK, bold=True)
    add_bullets(slide, 0.75, 2.45, 3.35, [
        "вопрос → поиск релевантных реплик",
        "ответ только по расшифровке лекции",
        "у каждой мысли — номер и таймкод",
        "без LLM — экстрактивный режим",
        "с LLM — формулировки, но те же цитаты",
    ], size=12, gap=6)
    add_rect(slide, 0.75, 4.95, 3.35, 1.02, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 0.94, 5.08, 3.0, 0.76, "Ответ не выходит за пределы лекции: меньше галлюцинаций и понятная проверка.",
             size=10.5, color=MUTED, spacing=1.12)
    add_footer(slide, 9, total)
    add_notes(slide, "Q&A отвечает по расшифровке и даёт цитаты. Без LLM это экстрактивный ответ, с LLM — более гладкий текст, "
                     "но опора всё равно на найденные фрагменты.")

    # 10 --------------------------------------------------------- architecture
    slide = blank(deck)
    add_header(slide, "Архитектура", "Всё локально, без облака",
               "SPA без сборки, FastAPI, SQLite WAL, файловое хранилище и одна очередь обработки.")
    add_rect(slide, 0.75, 1.95, 11.83, 0.68, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 1.0, 2.12, 11.3, 0.34, "Браузер · SPA на ES-модулях · History API · Range и VTT",
             size=13, color=INK, bold=True)
    add_text(slide, 6.3, 2.77, 0.7, 0.3, "↓", size=17, color=LIME, bold=True, align=PP_ALIGN.CENTER)
    add_rect(slide, 0.75, 3.10, 11.83, 0.68, fill=PANEL_2, line=LINE, radius=0.08)
    add_text(slide, 1.0, 3.27, 11.3, 0.34, "FastAPI · API, безопасные заголовки, gzip, стриминг, SPA fallback",
             size=13, color=INK, bold=True)
    columns = [
        ("Хранилище", ["SQLite WAL", "медиа и аудио", "float32-векторы", "кэш индекса"]),
        ("Обработка", ["ffmpeg / ffprobe", "faster-whisper", "model2vec", "TextRank / главы"]),
        ("Поиск и ответы", ["dense + BM25", "MMR-диверсификация", "RAG с цитатами", "VTT / SRT / Markdown"]),
    ]
    for index, (title, items) in enumerate(columns):
        x = 0.75 + index * 4.05
        add_rect(slide, x, 4.15, 3.75, 1.72, fill=PANEL, line=LINE, radius=0.06)
        add_text(slide, x + 0.24, 4.32, 3.2, 0.3, title, size=12, color=LIME, bold=True)
        for row, item in enumerate(items):
            add_text(slide, x + 0.24, 4.70 + row * 0.26, 3.25, 0.24, "·  " + item, size=10.5, color=MUTED)
    add_text(slide, 0.75, 6.20, 11.83, 0.5,
             "Модели: faster-whisper-small + potion-multilingual-128M. После первой загрузки интернет не нужен.",
             size=11.5, color=MUTED_2)
    add_footer(slide, 10, total)
    add_notes(slide, "Архитектура намеренно простая: один процесс FastAPI, SQLite и файловое хранилище. "
                     "Очередь обработки — ThreadPool с прогрессом в БД. Всё работает офлайн.")

    # 11 ------------------------------------------------------------ quality
    slide = blank(deck)
    add_header(slide, "Инженерия", "Качество подтверждено тестами",
               "157 тестов: unit, API, пайплайн и реальная загрузка до статуса ready.")
    metrics = [
        ("156", "passed", "зелёный прогон pytest"),
        ("1", "skipped", "только реальный Whisper smoke"),
        ("9,9", "секунды", "полный быстрый прогон"),
        ("0", "ошибок JS", "в консоли UI"),
    ]
    for index, (value, unit, label) in enumerate(metrics):
        x = 0.75 + index * 3.0
        add_rect(slide, x, 1.95, 2.74, 1.38, fill=PANEL, line=LINE, radius=0.06)
        add_text(slide, x + 0.22, 2.10, 1.5, 0.55, value, size=30, color=LIME, bold=True)
        add_text(slide, x + 1.42, 2.20, 1.15, 0.3, unit, size=10.5, color=INK, bold=True)
        add_text(slide, x + 0.22, 2.72, 2.3, 0.42, label, size=10, color=MUTED)
    add_text(slide, 0.75, 3.65, 5.8, 0.4, "Что покрыто", size=12, color=INK, bold=True)
    add_bullets(slide, 0.75, 4.08, 5.7, [
        "текст, леммы, TextRank, главы, VTT/SRT",
        "все HTTP-методы и коды ошибок",
        "гибридный поиск, MMR, сниппеты",
        "пайплайн с моками и E2E загрузка",
        "ASR-обёртка, эмбеддинги, Q&A",
    ], size=11.5, gap=5)
    add_text(slide, 6.95, 3.65, 5.5, 0.4, "Найденные и исправленные баги", size=12, color=INK, bold=True)
    add_bullets(slide, 6.95, 4.08, 5.5, [
        "кириллица в Content-Disposition экспорта",
        "ложные «висячие союзы» на «и»",
        "пробелы перед пунктуацией в ASR",
        "подсветка словоформ в сниппетах",
        "горизонтальный скролл на мобильном поиске",
    ], size=11.5, gap=5)
    add_rect(slide, 0.75, 6.08, 11.83, 0.55, fill=PANEL_2, line=LINE, radius=0.1)
    add_text(slide, 0.95, 6.20, 11.45, 0.3,
             "python -m pytest -q  →  156 passed, 1 skipped in 9.94s",
             size=11.5, color=LIME, font="Consolas", bold=True)
    add_footer(slide, 11, total)
    add_notes(slide, "Тесты нашли четыре реальных дефекта — все исправлены. Пятый, горизонтальный скролл на мобильном поиске, "
                     "обнаружился при ручной проверке вёрстки. Один skipped — дымовой тест настоящего Whisper, "
                     "включается переменной VECTOR_SLOW_TESTS=1.")

    # 12 -------------------------------------------------------- diagnostics
    slide = blank(deck)
    add_header(slide, "Диагностика", "Видно, что работает, а что требует внимания",
               "Health-check БД, ffmpeg, ASR, эмбеддингов, LLM и очереди — на одном экране.")
    width, height = add_picture(slide, "08-diagnostics.png", 4.55, 1.85, 8.0, max_h=5.0)
    add_caption(slide, 4.55, 1.85 + height + 0.08, 8.0, "Диагностика: статус систем, модели, диск, предупреждения")
    add_text(slide, 0.75, 1.95, 3.55, 0.4, "Почему это важно", size=12, color=INK, bold=True)
    add_bullets(slide, 0.75, 2.45, 3.55, [
        "видно, скачаны ли модели",
        "видно, найден ли ffmpeg",
        "прогресс очереди и активные задачи",
        "предупреждения с человеческим текстом",
        "статистика: часы, фрагменты, запросы",
    ], size=12, gap=7)
    add_rect(slide, 0.75, 4.95, 3.55, 0.9, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 0.95, 5.10, 3.15, 0.62, "Офлайн-режим: после первой загрузки моделей сеть не требуется.",
             size=10.5, color=MUTED, spacing=1.12)
    add_footer(slide, 12, total)
    add_notes(slide, "Диагностика снимает страх «а оно точно работает?». Видно состояние моделей, ffmpeg и очереди.")

    # 13 ------------------------------------------------------------- mobile
    slide = blank(deck)
    add_header(slide, "Мобильная вёрстка", "Тот же поиск — в кармане",
               "Отдельные раскладки для 390 px: библиотека, лекция и результаты без горизонтального скролла.")
    phones = [("09-mobile-home.png", "Библиотека"), ("10-mobile-lecture.png", "Лекция"), ("11-mobile-search.png", "Поиск")]
    for index, (name, label) in enumerate(phones):
        x = 0.75 + index * 2.55
        add_rect(slide, x - 0.08, 1.86, 2.28, 4.66, fill=PANEL_2, line=LINE, radius=0.10)
        add_picture(slide, name, x, 1.94, 2.12, max_h=4.5, border=False)
        add_text(slide, x, 6.62, 2.12, 0.25, label, size=10, color=MUTED, align=PP_ALIGN.CENTER)
    add_text(slide, 8.75, 1.98, 3.7, 0.4, "Проверено", size=12, color=INK, bold=True)
    add_bullets(slide, 8.75, 2.45, 3.7, [
        "390 × 844, без горизонтального скролла",
        "плеер и расшифровка перестраиваются",
        "фильтры и результаты читаемы",
        "меню и поиск доступны с телефона",
    ], size=12, gap=7)
    add_rect(slide, 8.75, 4.55, 3.7, 1.35, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 8.95, 4.72, 3.3, 1.0,
             "Мобильный поиск был с горизонтальным скроллом. Исправлено: minmax(0, 1fr) и min-width: 0 в гридах.",
             size=10.5, color=MUTED, spacing=1.14)
    add_footer(slide, 13, total)
    add_notes(slide, "Мобильная проверка выявила горизонтальный скролл на странице поиска. Исправлено в CSS. "
                     "Сейчас 390 px: библиотека, лекция и поиск без переполнения.")

    # 14 ------------------------------------------------------------ results
    slide = blank(deck)
    add_rect(slide, 0, 0, 0.18, H, fill=LIME)
    add_text(slide, 0.95, 0.62, 8.0, 0.3, "ИТОГИ", size=11, color=LIME, bold=True)
    add_text(slide, 0.95, 0.92, 10.5, 0.6, "Что уже работает", size=32, color=INK, bold=True)
    checks = [
        "Загрузка MP4 / WebM и ссылок → ready без ручных действий",
        "Транскрипт с таймкодами, клик по реплике перематывает",
        "Семантический поиск находит фрагмент без точных слов",
        "Конспект, главы и термины появляются автоматически",
        "Поиск по двум лекциям, Q&A с цитатами, экспорт",
    ]
    for index, item in enumerate(checks):
        y = 1.95 + index * 0.56
        add_text(slide, 0.95, y, 0.3, 0.3, "✓", size=14, color=LIME, bold=True)
        add_text(slide, 1.30, y, 7.8, 0.4, item, size=13.5, color=INK)
    add_rect(slide, 8.85, 1.85, 3.7, 2.42, fill=PANEL, line=LINE, radius=0.08)
    add_text(slide, 9.05, 2.02, 3.3, 0.3, "ЗАПУСК ОДНОЙ КОМАНДОЙ", size=9.5, color=LIME, bold=True)
    add_text(slide, 9.05, 2.40, 3.3, 0.3, ".\\run.ps1", size=18, color=INK, bold=True, font="Consolas")
    add_text(slide, 9.05, 2.78, 3.3, 0.28, "./run.sh", size=18, color=INK, bold=True, font="Consolas")
    add_text(slide, 9.05, 3.18, 3.28, 0.9, "venv → зависимости → ffmpeg → модели → демо → сервер",
             size=10, color=MUTED, spacing=1.18)
    add_text(slide, 8.85, 4.55, 3.7, 0.4, "Дальше", size=12, color=INK, bold=True)
    add_bullets(slide, 8.85, 4.95, 3.7, [
        "GPU-ASR и несколько воркеров",
        "авторизация и курсы",
        "аналитика по вопросам студентов",
        "экспорт в LMS",
    ], size=10.5, gap=5)
    add_text(slide, 0.95, 5.55, 7.5, 1.1,
             "Вектор — не ещё один видеоплеер. Это слой понимания, который превращает часовую запись "
             "в управляемый конспект и точку входа в нужный момент.",
             size=13, color=MUTED, font=SERIF, italic=True, spacing=1.25)
    add_text(slide, 0.95, 6.72, 11.0, 0.3,
             "Киберрывок · Осень 2026 · Python, FastAPI, SQLite, faster-whisper, model2vec",
             size=9.5, color=MUTED_2)
    add_notes(slide, "Итог: все пункты приёмки закрыты. Запуск одной командой, полностью локально. "
                     "Дальше — GPU, многопользовательский режим и интеграция с LMS.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    deck.save(OUTPUT)
    print(f"Готово: {OUTPUT} ({OUTPUT.stat().st_size / 1024:.0f} КБ)")


if __name__ == "__main__":
    build()
