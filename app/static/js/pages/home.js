import { api } from "../api.js";
import {
  escapeHtml,
  formatClockText,
  formatDate,
  formatDuration,
  formatNumber,
  formatTime,
  icon,
  plural,
  statusInfo,
  toast,
} from "../utils.js";

const FILTERS = [
  ["all", "Все"],
  ["ready", "Готовые"],
  ["processing", "В обработке"],
  ["failed", "Ошибки"],
];

const QUICK_QUERIES = [
  "теорема Пифагора",
  "как сеть учится",
  "что такое градиент",
  "примеры применения",
];

function skeletonCards(count = 3) {
  return Array.from({ length: count }, () => '<div class="skeleton skeleton-card"></div>').join("");
}

function statValue(value) {
  return `<strong data-stat="${value}">${value}</strong>`;
}

function heroVisual() {
  return `
  <div class="hero-visual" aria-hidden="true">
    <div class="orbit"></div>
    <div class="orbit two"></div>
    <div class="semantic-card" id="hero-result-card">
      <div class="sc-head">
        <div class="sc-title">${icon("sparkles")} Семантический поиск</div>
        <span class="badge lime">живой пример</span>
      </div>
      <div class="sc-query">«<em>как сеть учится</em>»</div>
      <div id="hero-result">
        <div class="sc-result">
          <div class="sc-result-top">
            <span class="time">01:24</span><span>·</span><span>Нейронные сети</span>
          </div>
          <div class="skeleton" style="height:12px"></div>
          <div class="skeleton" style="height:12px;width:86%"></div>
        </div>
      </div>
    </div>
    <div class="semantic-card">
      <div class="sc-head">
        <div class="sc-title">${icon("layers")} Структура лекции</div>
      </div>
      <div class="sc-query" style="margin-bottom:12px">Автоматические главы<br>с таймкодами</div>
      <div class="sc-result">
        <div class="sc-result-top"><span class="time">00:00</span><span>Введение</span></div>
        <div class="sc-result-top"><span class="time">02:10</span><span>Основная идея</span></div>
        <div class="sc-result-top"><span class="time">05:40</span><span>Примеры</span></div>
      </div>
    </div>
  </div>`;
}

export function mount(root, ctx) {
  let cancelled = false;
  let pollTimer = null;
  let filter = "all";
  let lectures = [];
  let stats = null;
  let loading = false;

  root.innerHTML = `
  <section class="hero">
    <div class="container hero-grid">
      <div>
        <div class="eyebrow">Семантический поиск по видеолекциям</div>
        <h1>Найдите <span class="accent">момент</span>,<br>а не таймкод.</h1>
        <p class="hero-lead">
          Загрузите лекцию — «Вектор» расшифрует речь, соберёт конспект и структуру,
          а затем найдёт нужный фрагмент по смыслу. С точностью до секунды.
        </p>
        <form class="hero-search" id="hero-search" role="search" autocomplete="off">
          <div class="field">
            <label class="sr-only" for="hero-q">Что найти в лекциях?</label>
            ${icon("search")}
            <input id="hero-q" name="q" type="search" placeholder="Например: почему производная — это скорость?" maxlength="500">
          </div>
          <button class="btn btn-primary" type="submit">Найти момент ${icon("chevron-right")}</button>
        </form>
        <div class="hero-queries">
          <span class="label">Попробуйте:</span>
          ${QUICK_QUERIES.map((query) => `<button class="chip" type="button" data-query="${escapeHtml(query)}">${escapeHtml(query)}</button>`).join("")}
        </div>
        <div class="hero-stats" id="hero-stats">
          <div class="hero-stat">${statValue("—")}<span>${plural(0, ["лекция", "лекции", "лекций"])}</span></div>
          <div class="hero-stat">${statValue("—")}<span>часов видео</span></div>
          <div class="hero-stat">${statValue("—")}<span>фрагментов</span></div>
          <div class="hero-stat">${statValue("—")}<span>глав</span></div>
        </div>
      </div>
      ${heroVisual()}
    </div>
  </section>

  <section class="section" id="library-section">
    <div class="container">
      <div class="section-head">
        <div>
          <div class="eyebrow">Библиотека</div>
          <h2>Ваши лекции</h2>
          <p>Расшифровки, конспекты и структура — всё готово к поиску.</p>
        </div>
        <button class="btn" type="button" data-open-upload>
          ${icon("upload")} Добавить лекцию
        </button>
      </div>
      <div class="library-toolbar" id="library-toolbar">
        ${FILTERS.map(([value, label]) => `<button class="filter-tab${value === "all" ? " active" : ""}" type="button" data-filter="${value}">${label}</button>`).join("")}
        <span class="count" id="library-count">Загружаем…</span>
      </div>
      <div class="library-grid" id="library-grid">${skeletonCards()}</div>
    </div>
  </section>

  <section class="section" style="padding-top:8px">
    <div class="container">
      <div class="section-head">
        <div>
          <div class="eyebrow">Как это работает</div>
          <h2>От файла до ответа</h2>
        </div>
        <p>Три шага, без ручной разметки и субтитров.</p>
      </div>
      <div class="how-grid">
        <div class="how-step">
          ${icon("upload")}
          <div class="num">01 / ЗАГРУЗКА</div>
          <h3>Добавьте лекцию</h3>
          <p>MP4, WebM, MOV или ссылка на YouTube, VK Видео, Rutube. Файл остаётся на вашем сервере.</p>
        </div>
        <div class="how-step">
          ${icon("mic")}
          <div class="num">02 / ОБРАБОТКА</div>
          <h3>Речь становится текстом</h3>
          <p>Whisper распознаёт речь, расставляет таймкоды и собирает смысловой индекс.</p>
        </div>
        <div class="how-step">
          ${icon("sparkles")}
          <div class="num">03 / ПОИСК</div>
          <h3>Спросите по-человечески</h3>
          <p>«Где про теорему Пифагора?» — и плеер откроется ровно на нужной секунде.</p>
        </div>
      </div>
    </div>
  </section>`;

  const grid = root.querySelector("#library-grid");
  const countLabel = root.querySelector("#library-count");
  const heroStats = root.querySelector("#hero-stats");
  const heroResult = root.querySelector("#hero-result");

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (cancelled) return;
    const pending = lectures.some((lecture) => ["queued", "processing"].includes(lecture.status));
    if (pending) {
      pollTimer = setTimeout(() => load(false), 2800);
    }
  }

  function renderStats(data) {
    const hours = Number(data.hours || 0);
    const values = [
      [formatNumber(data.lectures), plural(data.lectures, ["лекция", "лекции", "лекций"])],
      [hours >= 10 ? Math.round(hours) : hours.toFixed(1).replace(".", ","), "часов видео"],
      [formatNumber(data.segments), "фрагментов"],
      [formatNumber(data.chapters), "глав"],
    ];
    heroStats.innerHTML = values
      .map(([value, label]) => `<div class="hero-stat"><strong>${value}</strong><span>${label}</span></div>`)
      .join("");
  }

  function lectureCard(lecture) {
    const status = statusInfo(lecture.status);
    const summary = (lecture.summary || lecture.description || "").replace(/\s+/g, " ").trim();
    const preview = summary
      ? escapeHtml(summary.length > 180 ? `${summary.slice(0, 180)}…` : summary)
      : lecture.status === "failed"
        ? "Обработка не удалась — откройте лекцию, чтобы увидеть детали."
        : lecture.status === "processing"
          ? escapeHtml(lecture.stage || "Идёт обработка…")
          : "Расшифровка и конспект появятся после обработки.";
    const duration = lecture.duration ? formatTime(lecture.duration) : "";
    const segments = lecture.segments_count || 0;
    const chapters = lecture.chapters_count || 0;
    return `
    <a class="lecture-card" href="/lecture/${encodeURIComponent(lecture.id)}" data-link>
      <div class="lecture-thumb">
        ${lecture.thumbnail_url
          ? `<img src="${lecture.thumbnail_url}" alt="" loading="lazy">`
          : `<div class="thumb-placeholder">${icon("file-video")}</div>`}
        ${lecture.status === "ready" ? `<span class="thumb-play">${icon("play")}</span>` : ""}
        ${duration ? `<span class="thumb-duration">${duration}</span>` : ""}
      </div>
      <div class="lecture-card-body">
        <div class="chip-row">
          <span class="badge ${status.tone}"><span class="dot"></span>${status.label}</span>
          ${lecture.language ? `<span class="badge">${escapeHtml(lecture.language.toUpperCase())}</span>` : ""}
          ${lecture.llm_used ? `<span class="badge blue">LLM</span>` : ""}
        </div>
        <h3>${escapeHtml(lecture.title || "Без названия")}</h3>
        <p>${preview}</p>
        <div class="lecture-card-meta">
          ${segments ? `<span class="meta-item">${icon("list")}${segments} ${plural(segments, ["фрагмент", "фрагмента", "фрагментов"])}</span>` : ""}
          ${chapters ? `<span class="meta-item">${icon("layers")}${chapters} ${plural(chapters, ["глава", "главы", "глав"])}</span>` : ""}
          <span class="meta-item">${icon("clock")}${formatDate(lecture.created_at)}</span>
        </div>
        ${["queued", "processing"].includes(lecture.status) ? `
        <div class="status-line">
          <div class="progress-track"><div class="progress-fill amber" style="width:${Math.max(2, lecture.progress || 0)}%"></div></div>
          <span class="pct">${lecture.progress || 0}%</span>
        </div>` : ""}
      </div>
    </a>`;
  }

  function renderLibrary() {
    const filtered = filter === "all" ? lectures : lectures.filter((lecture) => lecture.status === filter);
    const ready = lectures.filter((lecture) => lecture.status === "ready").length;
    countLabel.textContent = `${filtered.length} из ${lectures.length} · ${ready} ${plural(ready, ["готова", "готовы", "готово"])}`;
    if (!lectures.length) {
      grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <span class="empty-icon">${icon("upload")}</span>
        <h3>Библиотека пока пуста</h3>
        <p>Добавьте первую лекцию — файл или ссылку. «Вектор» расшифрует её и подготовит поиск.</p>
        <button class="btn btn-primary" type="button" data-open-upload>${icon("upload")} Загрузить лекцию</button>
      </div>`;
      return;
    }
    if (!filtered.length) {
      grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <span class="empty-icon">${icon("folder")}</span>
        <h3>Здесь пока ничего нет</h3>
        <p>В этой категории нет лекций. Выберите другой фильтр или добавьте новую лекцию.</p>
      </div>`;
      return;
    }
    grid.innerHTML = filtered.map(lectureCard).join("");
  }

  async function loadHeroExample() {
    try {
      const result = await api.search("как сеть учится", { limit: 1, min_score: 0.05 });
      if (cancelled) return;
      const item = result.results?.[0];
      if (!item) throw new Error("empty");
      heroResult.innerHTML = `
        <div class="sc-result">
          <div class="sc-result-top">
            <span class="time">${formatTime(item.start)}</span><span>·</span>
            <span>${escapeHtml(item.lecture_title)}</span>
            <span style="margin-left:auto" class="badge lime">${item.score_percent}%</span>
          </div>
          <p>${item.snippet_html}</p>
          <div class="sc-bar"><span>смысловое совпадение</span><span class="track"><span class="fill" style="width:${item.score_percent}%"></span></span><span>${item.dense ? Math.round(item.dense * 100) : "—"}%</span></div>
        </div>`;
      const link = document.createElement("a");
      link.className = "result-link";
      link.href = `/lecture/${encodeURIComponent(item.lecture_id)}?t=${Math.floor(item.start)}`;
      link.dataset.link = "";
      link.style.marginTop = "10px";
      link.innerHTML = `Открыть момент ${icon("chevron-right")}`;
      heroResult.querySelector(".sc-result").append(link);
      const scQuery = root.querySelector("#hero-result-card .sc-query");
      if (scQuery) scQuery.innerHTML = "«<em>как сеть учится</em>»";
    } catch {
      if (cancelled) return;
      heroResult.innerHTML = `
        <div class="sc-result">
          <div class="sc-result-top"><span class="time">02:18</span><span>·</span><span>Нейронные сети</span></div>
          <p>Сеть учится, постепенно уменьшая ошибку: <mark>градиентный спуск</mark> подсказывает, в какую сторону менять веса.</p>
          <div class="sc-bar"><span>смысловое совпадение</span><span class="track"><span class="fill" style="width:92%"></span></span><span>92%</span></div>
        </div>`;
    }
  }

  async function load(showSkeleton = true) {
    if (loading || cancelled) return;
    loading = true;
    if (showSkeleton && !lectures.length) grid.innerHTML = skeletonCards();
    try {
      const [statsData, listData] = await Promise.all([api.stats(), api.lectures({ limit: 200 })]);
      if (cancelled) return;
      stats = statsData;
      lectures = listData.items || [];
      renderStats(stats);
      renderLibrary();
      schedulePoll();
    } catch (error) {
      if (cancelled) return;
      countLabel.textContent = "Не удалось загрузить";
      if (!lectures.length) {
        grid.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1">
          <span class="empty-icon">${icon("alert")}</span>
          <h3>Сервер не отвечает</h3>
          <p>${escapeHtml(error.message || "Проверьте, что приложение запущено, и обновите страницу.")}</p>
          <button class="btn" type="button" data-retry>${icon("refresh")} Повторить</button>
        </div>`;
      } else {
        toast(error.message || "Не удалось обновить библиотеку", "error");
      }
    } finally {
      loading = false;
    }
  }

  function onClick(event) {
    const queryButton = event.target.closest("[data-query]");
    if (queryButton) {
      ctx.navigate(`/search?q=${encodeURIComponent(queryButton.dataset.query)}`);
      return;
    }
    const filterButton = event.target.closest("[data-filter]");
    if (filterButton) {
      filter = filterButton.dataset.filter;
      root.querySelectorAll("[data-filter]").forEach((button) => {
        button.classList.toggle("active", button.dataset.filter === filter);
      });
      renderLibrary();
      return;
    }
    if (event.target.closest("[data-open-upload]")) {
      ctx.openUpload();
      return;
    }
    if (event.target.closest("[data-retry]")) {
      load();
    }
  }

  root.addEventListener("click", onClick);
  const heroForm = root.querySelector("#hero-search");
  const onHeroSubmit = (event) => {
    event.preventDefault();
    const input = root.querySelector("#hero-q");
    const query = input.value.trim();
    if (!query) {
      input.focus();
      return;
    }
    ctx.navigate(`/search?q=${encodeURIComponent(query)}`);
  };
  heroForm.addEventListener("submit", onHeroSubmit);

  load();
  loadHeroExample();

  return () => {
    cancelled = true;
    clearTimeout(pollTimer);
    root.removeEventListener("click", onClick);
    heroForm.removeEventListener("submit", onHeroSubmit);
  };
}
