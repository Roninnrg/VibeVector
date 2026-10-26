"""Генерация демонстрационных лекций: русская TTS-озвучка + слайды + MP4.

Запуск:
    python scripts/make_demo.py
    python scripts/make_demo.py --only pythagoras --no-process
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.services.media import probe, safe_unlink, safe_rmtree  # noqa: E402
from app.services.pipeline import process_lecture  # noqa: E402

FONT_DIR = Path("C:/Windows/Fonts")
FONT_REGULAR = FONT_DIR / "segoeui.ttf"
FONT_SEMIBOLD = FONT_DIR / "seguisb.ttf"
FONT_BOLD = FONT_DIR / "segoeuib.ttf"
FONT_MONO = FONT_DIR / "consola.ttf"

W, H = 1280, 720
BG = (10, 13, 11)
PANEL = (17, 22, 18)
INK = (238, 242, 232)
MUTED = (150, 162, 148)
LIME = (200, 245, 96)
LIME_DIM = (94, 122, 48)
GRID = (24, 31, 25)


DEMOS = {
    "pythagoras": {
        "title": "Теорема Пифагора: от доказательства до практики",
        "description": "Геометрия · 9 класс. История, формулировка, доказательство, пифагоровы тройки и применение в реальных задачах.",
        "course": "Геометрия · лекция 1",
        "slides": [
            {
                "title": "Теорема Пифагора",
                "kicker": "ГЕОМЕТРИЯ · ЛЕКЦИЯ 1",
                "bullets": ["История и формулировка", "Доказательство через площади", "Пифагоровы тройки и практика"],
                "narration": (
                    "Здравствуйте! Сегодня мы разберём одну из самых известных теорем школьной геометрии — теорему Пифагора. "
                    "Мы поговорим о том, откуда она взялась, как формулируется, почему она верна и где пригодится в реальной жизни. "
                    "В конце лекции вы сможете самостоятельно находить неизвестную сторону прямоугольного треугольника и проверять, "
                    "является ли треугольник прямоугольным."
                ),
            },
            {
                "title": "Часть первая. История и смысл",
                "kicker": "01 · КОНТЕКСТ",
                "bullets": ["Пифагор Самосский, VI век до н. э.", "Вавилонские таблички за 1000 лет до Пифагора", "Теорема как связь между сторонами"],
                "narration": (
                    "Часть первая. История и смысл. Теорему традиционно связывают с древнегреческим математиком Пифагором Самосским, "
                    "который жил в шестом веке до нашей эры. Однако соотношение между сторонами прямоугольного треугольника знали "
                    "задолго до него: вавилонские глиняные таблички с пифагоровыми числами старше Пифагора примерно на тысячу лет. "
                    "Почему же теорему называют его именем? Пифагорейцы видели в числах гармонию мира и, вероятно, первыми "
                    "сформулировали и доказали утверждение как общий закон, а не как набор частных примеров. "
                    "Смысл теоремы прост: она связывает длины трёх сторон прямоугольного треугольника одним равенством. "
                    "Зная две стороны, мы всегда можем найти третью."
                ),
            },
            {
                "title": "Часть вторая. Формулировка",
                "kicker": "02 · ТЕОРЕМА",
                "bullets": ["c² = a² + b²", "c — гипотенуза, сторона напротив прямого угла", "a и b — катеты"],
                "narration": (
                    "Часть вторая. Формулировка. В прямоугольном треугольнике есть две стороны, образующие прямой угол. "
                    "Они называются катетами, обозначим их а и бэ. Третья сторона, лежащая напротив прямого угла, называется гипотенузой, "
                    "обозначим её цэ. Теорема Пифагора утверждает: квадрат гипотенузы равен сумме квадратов катетов. "
                    "Запишем формулу: цэ в квадрате равно а в квадрате плюс бэ в квадрате. "
                    "Обратите внимание: речь идёт именно о квадратах длин, а не о самих длинах. "
                    "Поэтому нельзя написать, что гипотенуза равна сумме катетов — это типичная ошибка. "
                    "Гипотенуза всегда длиннее каждого катета, но короче их суммы. "
                    "Если известны катеты, гипотенуза находится как квадратный корень из суммы их квадратов. "
                    "Если известны гипотенуза и один катет, второй катет равен корню из разности квадратов."
                ),
            },
            {
                "title": "Часть третья. Доказательство",
                "kicker": "03 · ПОЧЕМУ ЭТО ВЕРНО",
                "bullets": ["Достроим до квадрата со стороной a + b", "Площадь большого квадрата", "Четыре треугольника и внутренний квадрат"],
                "narration": (
                    "Часть третья. Доказательство. Самое наглядное доказательство использует площади. "
                    "Возьмём прямоугольный треугольник с катетами а и бэ и гипотенузой цэ. "
                    "Построим квадрат со стороной а плюс бэ. По углам этого большого квадрата расположим четыре копии нашего треугольника. "
                    "Тогда внутри останется свободный квадрат, сторона которого равна гипотенузе цэ. "
                    "Площадь большого квадрата равна а плюс бэ в квадрате. С другой стороны, она складывается из четырёх площадей "
                    "прямоугольных треугольников и площади внутреннего квадрата. Площадь одного треугольника равна половине произведения катетов, "
                    "четыре таких треугольника дают два произведения а на бэ. Площадь внутреннего квадрата равна цэ в квадрате. "
                    "Приравняем два выражения и раскроем скобки. Слева получаем а в квадрате плюс два а бэ плюс бэ в квадрате. "
                    "Справа получаем два а бэ плюс цэ в квадрате. Слагаемое два а бэ сокращается, и остаётся а в квадрате плюс бэ в квадрате "
                    "равно цэ в квадрате. Что и требовалось доказать."
                ),
            },
            {
                "title": "Часть четвёртая. Примеры",
                "kicker": "04 · ПРАКТИКА",
                "bullets": ["Египетский треугольник 3–4–5", "Диагональ экрана и фундамента", "Проверка прямого угла на стройке"],
                "narration": (
                    "Часть четвёртая. Примеры и применение. Самый известный пример — египетский треугольник со сторонами три, четыре и пять. "
                    "Проверим: три в квадрате равно девяти, четыре в квадрате равно шестнадцати, вместе двадцать пять. "
                    "Пять в квадрате тоже двадцать пять. Значит, треугольник со сторонами три, четыре и пять прямоугольный. "
                    "Такие наборы целых чисел называют пифагоровыми тройками. Ещё примеры: пять, двенадцать, тринадцать; "
                    "шесть, восемь, десять; восемь, пятнадцать, семнадцать. "
                    "В строительстве теорему используют для разметки прямого угла: отмеряют три метра по одной стене, "
                    "четыре метра по другой и проверяют, что расстояние между концами равно пяти метрам. "
                    "Если да, угол прямой. Ещё теорема помогает найти диагональ прямоугольного участка, длину лестницы, "
                    "высоту стропила или расстояние между противоположными углами комнаты. "
                    "В навигации она позволяет вычислить кратчайшее расстояние между двумя точками на плоскости."
                ),
            },
            {
                "title": "Часть пятая. Итоги",
                "kicker": "05 · ГЛАВНОЕ",
                "bullets": ["Квадрат гипотенузы = сумма квадратов катетов", "Работает только в прямоугольном треугольнике", "Обратная теорема проверяет угол"],
                "narration": (
                    "Часть пятая. Подведём итог. Главная формула лекции: квадрат гипотенузы равен сумме квадратов катетов. "
                    "Теорема работает только для прямоугольных треугольников. Обратное утверждение тоже верно: "
                    "если квадрат большей стороны равен сумме квадратов двух других сторон, то треугольник прямоугольный. "
                    "Именно так теорему применяют для проверки угла. "
                    "Запомните три практических вывода. Первый: чтобы найти гипотенузу, сложите квадраты катетов и извлеките корень. "
                    "Второй: чтобы найти катет, вычтите из квадрата гипотенузы квадрат известного катета и извлеките корень. "
                    "Третий: пифагоровы тройки помогают быстро строить прямые углы без транспортира. "
                    "На следующем занятии мы выведем формулу расстояния между точками на координатной плоскости — "
                    "и увидим, что это та же теорема Пифагора. Спасибо за внимание!"
                ),
            },
        ],
    },
    "neural": {
        "title": "Как работают нейронные сети: от нейрона до обучения",
        "description": "Введение в машинное обучение. Нейрон, веса, функции активации, прямой проход, функция потерь, градиентный спуск и обратное распространение.",
        "course": "Искусственный интеллект · лекция 1",
        "slides": [
            {
                "title": "Как работают нейронные сети",
                "kicker": "ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ · ЛЕКЦИЯ 1",
                "bullets": ["От биологического нейрона к модели", "Прямой проход и функция потерь", "Обучение через градиентный спуск"],
                "narration": (
                    "Здравствуйте! Сегодня мы разберёмся, как устроены нейронные сети и почему они способны решать задачи, "
                    "которые плохо поддаются обычным алгоритмам. Мы начнём с простого нейрона, соберём из них сеть, "
                    "посмотрим, как она делает предсказание, как измеряется ошибка и как веса настраиваются во время обучения. "
                    "В конце вы поймёте, что стоит за словами «искусственный интеллект» и «машинное обучение»."
                ),
            },
            {
                "title": "Часть первая. Нейрон и веса",
                "kicker": "01 · КИРПИЧИ МОДЕЛИ",
                "bullets": ["Входы, веса, смещение", "Взвешенная сумма", "Функция активации"],
                "narration": (
                    "Часть первая. Нейрон и веса. Искусственный нейрон — это математическая функция. "
                    "Он получает несколько входных чисел, например признаки объекта. Каждый вход умножается на свой вес. "
                    "Затем все произведения складываются, и к сумме прибавляется смещение. "
                    "Полученное число пропускается через функцию активации. "
                    "Веса показывают важность входа: чем больше вес, тем сильнее признак влияет на решение. "
                    "Смещение позволяет сдвинуть порог срабатывания. "
                    "Функция активации добавляет нелинейность. Без неё несколько слоёв превратились бы в одно линейное преобразование "
                    "и не смогли бы выучить сложные зависимости. "
                    "Чаще всего используют релу, сигмоиду или гиперболический тангенс. "
                    "Релу пропускает положительные значения без изменений, а отрицательные обнуляет."
                ),
            },
            {
                "title": "Часть вторая. Слои и прямой проход",
                "kicker": "02 · АРХИТЕКТУРА",
                "bullets": ["Входной, скрытые и выходной слои", "Матрицы весов", "Предсказание сети"],
                "narration": (
                    "Часть вторая. Слои и прямой проход. Нейроны объединяются в слои. "
                    "Входной слой принимает признаки, скрытые слои последовательно преобразуют представление, "
                    "выходной слой выдаёт ответ. Если мы распознаём изображение, входом могут быть пиксели, "
                    "а выходом — вероятности классов. "
                    "Вычисления удобно записывать матрицами: входной вектор умножается на матрицу весов, "
                    "прибавляется вектор смещений, применяется активация. Результат передаётся в следующий слой. "
                    "Эта последовательность называется прямым проходом. "
                    "Глубокой называют сеть с несколькими скрытыми слоями. "
                    "Каждый слой строит всё более абстрактные признаки: первые слои распознают края и цвета, "
                    "следующие — формы и части объектов, последние — целые объекты."
                ),
            },
            {
                "title": "Часть третья. Ошибка и обучение",
                "kicker": "03 · КАК СЕТЬ УЧИТСЯ",
                "bullets": ["Функция потерь", "Градиентный спуск", "Скорость обучения"],
                "narration": (
                    "Часть третья. Ошибка и обучение. Чтобы сеть училась, нужен критерий качества. "
                    "Функция потерь сравнивает предсказание с правильным ответом и возвращает число: чем больше ошибка, тем больше значение. "
                    "Для задачи классификации часто используют кросс-энтропию, для регрессии — среднюю квадратичную ошибку. "
                    "Обучение — это поиск весов, при которых потеря минимальна. "
                    "Представьте поверхность, где каждая точка — набор весов, а высота — ошибка. "
                    "Градиент показывает направление самого быстрого роста. Значит, двигаться нужно в противоположную сторону. "
                    "Это и есть градиентный спуск. "
                    "Скорость обучения задаёт размер шага. Слишком большой шаг приводит к прыжкам и расходимости, "
                    "слишком маленький делает обучение очень медленным. "
                    "На практике используют мини-батчи: считают градиент по небольшой порции примеров и обновляют веса много раз за эпоху."
                ),
            },
            {
                "title": "Часть четвёртая. Обратное распространение",
                "kicker": "04 · ГРАДИЕНТЫ",
                "bullets": ["Правило цепочки", "Ошибка идёт назад по слоям", "Обновление весов"],
                "narration": (
                    "Часть четвёртая. Обратное распространение. Как узнать, как каждый вес влияет на итоговую ошибку? "
                    "Для этого используют правило цепочки из математического анализа. "
                    "Сначала выполняется прямой проход и вычисляется потеря. "
                    "Затем ошибка распространяется назад от выходного слоя к входному. "
                    "На каждом шаге мы считаем производную потери по весам и смещениям. "
                    "Это называется обратным распространением ошибки. "
                    "После этого веса обновляются по формуле: новый вес равен старому минус скорость обучения, умноженная на градиент. "
                    "Процедура повторяется для многих батчей и эпох. "
                    "Важно, что обратное распространение — не отдельный алгоритм обучения, а эффективный способ вычисления градиентов "
                    "для градиентного спуска."
                ),
            },
            {
                "title": "Часть пятая. Итоги",
                "kicker": "05 · ГЛАВНОЕ",
                "bullets": ["Нейрон = взвешенная сумма + активация", "Обучение = минимизация потерь", "Градиентный спуск + backprop"],
                "narration": (
                    "Часть пятая. Подведём итог. Нейрон складывает входы с весами, добавляет смещение и применяет активацию. "
                    "Слои нейронов образуют сеть, которая выполняет прямой проход и выдаёт предсказание. "
                    "Функция потерь измеряет ошибку. Обратное распространение вычисляет градиенты, а градиентный спуск обновляет веса. "
                    "Так сеть постепенно уменьшает ошибку и учится на данных. "
                    "Но есть важные ограничения: качество зависит от данных, модель может переобучиться, "
                    "а вычислительные затраты растут вместе с размером сети. "
                    "На следующей лекции мы поговорим о переобучении, регуляризации и о том, как правильно делить данные "
                    "на обучающую, валидационную и тестовую выборки. Спасибо за внимание!"
                ),
            },
        ],
    },
}


def _font(path: Path, size: int):
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.truetype(str(FONT_REGULAR), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def make_slide(demo: dict, slide: dict, index: int, total: int, out: Path) -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill=GRID, width=1)
    # акцентная полоса и бренд
    draw.rectangle([(0, 0), (10, H)], fill=LIME)
    draw.text((58, 46), "вектор", font=_font(FONT_BOLD, 28), fill=INK)
    draw.text((58, 84), "семантический поиск по лекциям", font=_font(FONT_REGULAR, 15), fill=MUTED)
    draw.text((W - 58, 52), f"{index + 1:02d} / {total:02d}", font=_font(FONT_MONO, 18), fill=MUTED, anchor="ra")

    kicker_font = _font(FONT_SEMIBOLD, 17)
    draw.text((58, 160), slide["kicker"], font=kicker_font, fill=LIME)
    draw.line([(58, 192), (178, 192)], fill=LIME_DIM, width=2)

    title_font = _font(FONT_BOLD, 64 if len(slide["title"]) < 30 else 54)
    title_lines = wrap(draw, slide["title"], title_font, W - 130)
    y = 225
    for line in title_lines[:2]:
        draw.text((58, y), line, font=title_font, fill=INK)
        y += 72

    # нижний блок тезисов
    box_top = 475
    draw.rounded_rectangle([(58, box_top), (W - 58, H - 64)], radius=18, fill=PANEL, outline=(35, 45, 36), width=1)
    bullet_font = _font(FONT_REGULAR, 25)
    by = box_top + 30
    for bullet in slide["bullets"][:3]:
        draw.ellipse([(86, by + 10), (96, by + 20)], fill=LIME)
        lines = wrap(draw, bullet, bullet_font, W - 230)
        for line in lines[:2]:
            draw.text((118, by), line, font=bullet_font, fill=INK)
            by += 34
        by += 12
    draw.text((58, H - 42), demo["course"], font=_font(FONT_REGULAR, 15), fill=MUTED)

    # прогресс-бар
    progress = (index + 1) / total
    draw.rectangle([(0, H - 6), (W, H)], fill=(25, 31, 26))
    draw.rectangle([(0, H - 6), (int(W * progress), H)], fill=LIME)
    img.save(out, quality=92)


def tts(text: str, out: Path, voice: str = "Microsoft Irina Desktop") -> None:
    text_file = out.with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")
    safe = str(out).replace("'", "''")
    source = str(text_file).replace("'", "''")
    ps = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{ $s.SelectVoice('{voice}') }} catch {{ }}
$s.Rate = -1
$s.Volume = 100
$text = Get-Content -Raw -Encoding UTF8 '{source}'
$s.SetOutputToWaveFile('{safe}')
$s.Speak($text)
$s.Dispose()
"""
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
        check=False,
    )
    if result.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(
            f"TTS не сработал: {result.stderr.decode('cp1251', 'replace')[:500]}"
        )
    safe_unlink(text_file)


def ffmpeg(*args: str, timeout: int = 300) -> None:
    if not settings.ffmpeg:
        raise RuntimeError("ffmpeg не найден.")
    result = subprocess.run(
        [settings.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[:800])


def build_demo(key: str, demo: dict, work: Path, process: bool = True) -> str:
    lecture_id = f"demo-{key}"
    work.mkdir(parents=True, exist_ok=True)
    slides_dir = work / "slides"
    audio_dir = work / "audio"
    slides_dir.mkdir(exist_ok=True)
    audio_dir.mkdir(exist_ok=True)

    total = len(demo["slides"])
    durations: list[float] = []
    audio_files: list[Path] = []
    for i, slide in enumerate(demo["slides"]):
        print(f"[{key}] слайд {i + 1}/{total}: {slide['title']}", flush=True)
        make_slide(demo, slide, i, total, slides_dir / f"slide{i}.png")
        wav = audio_dir / f"part{i}.wav"
        if not wav.exists() or wav.stat().st_size < 1000:
            tts(slide["narration"], wav)
        durations.append(float(probe(wav)["duration"]))
        audio_files.append(wav)

    silence = audio_dir / "silence.wav"
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.65", "-c:a", "pcm_s16le", str(silence))

    concat_audio = audio_dir / "audio.txt"
    lines = []
    for i, wav in enumerate(audio_files):
        lines.append(f"file '{wav.as_posix()}'")
        if i < len(audio_files) - 1:
            lines.append(f"file '{silence.as_posix()}'")
    concat_audio.write_text("\n".join(lines), encoding="utf-8")
    full_audio = audio_dir / "full.wav"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat_audio), "-c", "copy", str(full_audio))

    slide_durations = []
    for i, duration in enumerate(durations):
        extra = 0.65 if i < len(durations) - 1 else 0.3
        slide_durations.append(duration + extra)
    slides_txt = audio_dir / "slides.txt"
    lines = []
    for i in range(total):
        lines.append(f"file '{ (slides_dir / f'slide{i}.png').as_posix()}'")
        lines.append(f"duration {slide_durations[i]:.3f}")
    lines.append(f"file '{(slides_dir / f'slide{total - 1}.png').as_posix()}'")
    slides_txt.write_text("\n".join(lines), encoding="utf-8")

    media_path = Path(settings.media_dir) / f"{lecture_id}.mp4"
    ffmpeg(
        "-f", "concat", "-safe", "0", "-i", str(slides_txt),
        "-i", str(full_audio),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", "25", "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart", str(media_path),
    )
    info = probe(media_path)
    print(f"[{key}] видео: {media_path} ({info['duration']:.0f} c)", flush=True)

    now = db.now_iso()
    with db.db() as conn:
        existing = conn.execute("SELECT id FROM lectures WHERE id=?", (lecture_id,)).fetchone()
        if existing:
            old = conn.execute("SELECT media_path, thumbnail_path FROM lectures WHERE id=?", (lecture_id,)).fetchone()
            safe_unlink(old["media_path"])
            safe_unlink(old["thumbnail_path"])
            conn.execute("DELETE FROM lectures WHERE id=?", (lecture_id,))
        conn.execute(
            """INSERT INTO lectures
               (id, title, description, source_type, original_filename, media_path, media_mime,
                media_size, duration, status, stage, progress, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lecture_id, demo["title"], demo["description"], "demo",
                media_path.name, str(media_path), info["mime"],
                media_path.stat().st_size, info["duration"],
                "queued", "В очереди", 0, now, now,
            ),
        )
    db.bump_index_version()

    if process:
        print(f"[{key}] запускаю транскрибацию и индексацию…", flush=True)
        process_lecture(lecture_id)
        print(f"[{key}] готово", flush=True)
    return lecture_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=sorted(DEMOS), default=None)
    parser.add_argument("--no-process", action="store_true")
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    db.init_db()
    work_root = settings.data_dir / "demo-build"
    keys = [args.only] if args.only else list(DEMOS)
    for key in keys:
        build_demo(key, DEMOS[key], work_root / key, process=not args.no_process)
    if not args.keep_work:
        safe_rmtree(work_root)
    print(json.dumps({"generated": keys}, ensure_ascii=False))


if __name__ == "__main__":
    main()
