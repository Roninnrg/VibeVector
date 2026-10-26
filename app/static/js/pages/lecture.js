import { api } from "../api.js";
import { playerMarkup, VectorPlayer } from "../player.js";
import {
  copyText,
  escapeHtml,
  formatDate,
  formatDuration,
  formatTime,
  icon,
  localGet,
  localSet,
  markText,
  plural,
  statusInfo,
  toast,
} from "../utils.js";

const STEPS = [
  { key: "audio", title: "Аудио", caption: "Извлекаем дорожку" },
  { key: "speech", title: "Речь", caption: "Распознаём Whisper" },
  { key: "index", title: "Индекс", caption: "Считаем эмбеддинги" },
  { key: "summary", title: "Конспект", caption: "Главы и тезисы" },
];

const TAB_IDS = ["summary", "chapters", "transcript", "qa"];

function paragraphs(text, perGroup = 3) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return [];
  const sentences = clean.match(/[^.!?…]+[.!?…]+|[^.!?…]+$/g) || [clean];
  const groups = [];
  for (let index = 0; index < sentences.length; index += perGroup) {
    groups.push(sentences.slice(index, index + perGroup).join(" ").trim());
  }
  return groups.filter(Boolean);
}

function stageIndex(stage, progress) {
  const value = String(stage || "").toLowerCase();
  if (value.includes("аудио")) return 0;
  if (value.includes("речь") || value.includes("распозн")) return 1;
  if (value.includes("индекс") || value.includes("эмбед")) return 2;
  if (value.includes("конспект") || value.includes("структур") || value.includes("глав") || value.includes("ключев")) return 3;
  if (value >= 86) return 3;
  if (value >= 70) return 2;
  if (value >= 12) return 1;
  return 0;
}

function normalizeKeywords(keywords) {
  if (!Array.isArray(keywords)) return [];
  return keywords
    .map((item) => (typeof item === "string" ? { term: item, count: 0 } : item))
    .filter((item) => item && item.term)
    .slice(0, 14);
}

function metaItems(lecture) {
  const items = [];
  if (lecture.duration) items.push([icon("clock"), formatDuration(lecture.duration)]);
  if (lecture.language) items.push([icon("mic"), lecture.language.toUpperCase()]);
  if (lecture.segments_count) items.push([icon("list"), `${lecture.segments_count} ${plural(lecture.segments_count, ["фрагмент", "фрагмента", "фрагментов"])}`]);
  if (lecture.chapters_count) items.push([icon("layers"), `${lecture.chapters_count} ${plural(lecture.chapters_count, ["глава", "главы", "глав"])}`]);
  if (lecture.views) items.push([icon("gauge"), `${lecture.views} ${plural(lecture.views, ["просмотр", "просмотра", "просмотров"])}`]);
  items.push([icon("calendar"), formatDate(lecture.created_at)]);
  return items.map(([markup, label]) => `<span class="meta-item">${markup}${escapeHtml(label)}</span>`).join("");
}

function headMarkup(lecture) {
  return `
  <h1>${escapeHtml(lecture.title)}</h1>
  ${lecture.description ? `<p class="sub">${escapeHtml(lecture.description)}</p>` : ""}
  <div class="lecture-meta">${metaItems(lecture)}</div>`;
}

function detailsMarkup(lecture) {
  const rows = [
    ["Источник", lecture.source_type === "url" ? "Ссылка" : "Файл"],
    ["Язык", lecture.language ? lecture.language.toUpperCase() : "—"],
    ["Длительность", formatDuration(lecture.duration)],
    ["Фрагментов", lecture.segments_count || 0],
    ["Глав", lecture.chapters_count || 0],
    ["Распознавание", lecture.asr_provider || "—"],
    ["Индекс", lecture.embedding_provider || "—"],
    ["Добавлена", formatDate(lecture.created_at, true)],
  ];
  return rows.map(([label, value]) => `<div class="detail-row"><span>${label}</span><span>${escapeHtml(value)}</span></div>`).join("");
}

function processingMarkup(lecture) {
  const active = stageIndex(lecture.stage, lecture.progress || 0);
  return `
  <div class="lecture-page">
    <div class="container">
      <nav class="breadcrumb" aria-label="Хлебные крошки">
        <a href="/" data-link>Библиотека</a>
        <span class="sep">/</span>
        <span class="current">${escapeHtml(lecture.title)}</span>
      </nav>
      <header class="lecture-head">
        <div>
          <div class="chip-row">
            <span class="badge amber"><span class="dot"></span>Обработка</span>
            ${lecture.language ? `<span class="badge">${escapeHtml(lecture.language.toUpperCase())}</span>` : ""}
          </div>
          <div style="margin-top:12px">${headMarkup(lecture)}</div>
        </div>
      </header>
      <div class="lecture-layout">
        <div class="lecture-main">
          <div class="processing-shell">
            <span class="spinner"></span>
            <div class="eyebrow">Идёт обработка</div>
            <h2>Готовим лекцию к поиску</h2>
            <p>Расшифровываем речь, собираем смысловой индекс и конспект. Обычно это занимает несколько минут — страницу можно оставить открытой.</p>
            <div class="progress-track"><div class="progress-fill amber" data-progress-fill style="width:${Math.max(2, lecture.progress || 0)}%"></div></div>
            <span class="stage" data-stage>${escapeHtml(lecture.stage || "В очереди")}</span>
            <div class="processing-live" data-steps>
              ${STEPS.map((step, index) => `
                <div class="${index < active ? "done" : index === active ? "on" : ""}" data-step="${index}">
                  <strong>${icon(index < active ? "check" : "clock")} ${step.title}</strong>
                  <span>${index < active ? "Готово" : index === active ? "Сейчас" : "Ожидает"}</span>
                </div>`).join("")}
            </div>
          </div>
          <div class="card card-pad">
            <div class="eyebrow" style="margin-bottom:9px">Что происходит</div>
            <p class="muted" style="font-size:13px;line-height:1.7">
              Сначала «Вектор» извлекает аудиодорожку и распознаёт речь с точностью до слова.
              Затем каждая реплика превращается в смысловой вектор, а по тексту собираются главы,
              ключевые термины и краткий конспект. Как только индекс готов, поиск и плеер включатся автоматически.
            </p>
          </div>
        </div>
        <aside class="lecture-aside">
          <div class="aside-section">
            <div class="aside-section-head"><h4>Параметры</h4></div>
            <div class="detail-list">${detailsMarkup(lecture)}</div>
          </div>
          <div class="aside-section">
            <div class="aside-section-head"><h4>Статус</h4></div>
            <div class="aside-tip">Страница обновляется автоматически каждые 2,5 секунды. Можно закрыть её и вернуться позже — обработка продолжится на сервере.</div>
            <div style="margin-top:12px"><button class="btn btn-sm btn-danger" type="button" data-delete>${icon("trash")} Удалить лекцию</button></div>
          </div>
        </aside>
      </div>
    </div>
  </div>`;
}

function failureMarkup(lecture) {
  return `
  <div class="lecture-page">
    <div class="container">
      <nav class="breadcrumb" aria-label="Хлебные крошки">
        <a href="/" data-link>Библиотека</a>
        <span class="sep">/</span>
        <span class="current">${escapeHtml(lecture.title)}</span>
      </nav>
      <header class="lecture-head">
        <div>${headMarkup(lecture)}</div>
      </header>
      <div class="lecture-layout">
        <div class="lecture-main">
          <div class="failure-shell">
            <h2>${icon("alert")} Не удалось обработать лекцию</h2>
            <p>Обработка прервалась. Чаще всего причина — нехватка памяти или недоступный медиафайл. Можно запустить обработку заново: уже загруженный файл сохранился на сервере.</p>
            <pre>${escapeHtml(lecture.error || "Причина не указана.")}</pre>
            <div class="failure-actions">
              <button class="btn btn-primary" type="button" data-retry>${icon("refresh")} Повторить обработку</button>
              <a class="btn" href="/" data-link>${icon("chevron-left")} В библиотеку</a>
              <button class="btn btn-danger" type="button" data-delete>${icon("trash")} Удалить</button>
            </div>
          </div>
        </div>
        <aside class="lecture-aside">
          <div class="aside-section">
            <div class="aside-section-head"><h4>Параметры</h4></div>
            <div class="detail-list">${detailsMarkup(lecture)}</div>
          </div>
        </aside>
      </div>
    </div>
  </div>`;
}

export function mount(root, ctx) {
  const lectureId = ctx.params[0];
  const startAt = Number(ctx.query.get("t"));
  const searchQuery = (ctx.query.get("q") || "").trim();
  let lecture = null;
  let cues = [];
  let player = null;
  let cancelled = false;
  let pollTimer = null;
  let readyBuilt = false;
  let failureBuilt = false;
  let activeTab = TAB_IDS.includes((ctx.url.hash || "").replace("#", ""))
    ? ctx.url.hash.replace("#", "")
    : searchQuery
      ? "transcript"
      : "summary";
  let activeCue = -1;
  let activeChapter = -1;
  let qaBusy = false;
  let lastChapter = -1;

  ctx.setTitle("Лекция — Вектор");

  root.innerHTML = `
  <div class="lecture-page">
    <div class="container">
      <div class="skeleton" style="height:18px;width:180px;margin-bottom:22px"></div>
      <div class="skeleton" style="height:38px;width:62%;margin-bottom:16px"></div>
      <div class="skeleton" style="height:14px;width:44%;margin-bottom:26px"></div>
      <div class="skeleton" style="height:520px;border-radius:16px"></div>
    </div>
  </div>`;

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (cancelled) return;
    pollTimer = setTimeout(load, 2500);
  }

  function updateUrlHash(tab) {
    const url = new URL(window.location.href);
    url.hash = tab;
    window.history.replaceState({ vector: true }, "", url.href);
  }

  function setTab(tab, { updateHash = true, reveal = true } = {}) {
    if (!TAB_IDS.includes(tab)) return;
    activeTab = tab;
    root.querySelectorAll("[data-tab]").forEach((button) => {
      const active = button.dataset.tab === tab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    root.querySelectorAll("[data-panel]").forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.panel !== tab);
    });
    if (updateHash) updateUrlHash(tab);
    if (reveal && tab === "transcript") {
      requestAnimationFrame(() => {
        if (activeCue >= 0) scrollCue(activeCue, true);
      });
    }
  }

  // ------------------------------------------------------------- ready page
  function cueMarkup(cue, index, highlight) {
    return `
    <div class="cue${index === activeCue ? " active" : ""}" role="button" tabindex="0"
         data-cue="${index}" data-start="${cue.start}" aria-label="Перейти к ${formatTime(cue.start)}">
      <span class="t">${formatTime(cue.start)}</span>
      <p>${markText(cue.text, highlight)}</p>
      <button class="copy-btn" type="button" data-copy-cue="${index}" aria-label="Скопировать реплику" title="Скопировать реплику">
        ${icon("copy")}
      </button>
    </div>`;
  }

  function transcriptHighlight() {
    const filter = root.querySelector("[data-transcript-filter]")?.value.trim();
    return filter || searchQuery;
  }

  function renderTranscriptList() {
    const list = root.querySelector("[data-transcript-list]");
    if (!list) return;
    const filter = (root.querySelector("[data-transcript-filter]")?.value || "").trim().toLowerCase();
    const visible = cues
      .map((cue, index) => ({ cue, index }))
      .filter(({ cue }) => !filter || cue.text.toLowerCase().includes(filter));
    const highlight = transcriptHighlight();
    list.innerHTML = visible.length
      ? visible.map(({ cue, index }) => cueMarkup(cue, index, highlight)).join("")
      : `<div class="no-transcript">Реплик по фильтру не найдено. Попробуйте другое слово.</div>`;
    const counter = root.querySelector("[data-transcript-count]");
    if (counter) {
      counter.textContent = filter ? `${visible.length} из ${cues.length}` : `${cues.length} ${plural(cues.length, ["реплика", "реплики", "реплик"])}`;
    }
    if (activeCue >= 0 && !filter) scrollCue(activeCue, true);
  }

  function scrollCue(index, smooth = false) {
    if (!autoScrollEnabled()) return;
    const list = root.querySelector("[data-transcript-list]");
    const element = list?.querySelector(`[data-cue="${index}"]`);
    if (!list || !element) return;
    const listRect = list.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    if (elementRect.top >= listRect.top + 6 && elementRect.bottom <= listRect.bottom - 6) return;
    const top = list.scrollTop + (elementRect.top - listRect.top) - list.clientHeight * 0.32;
    list.scrollTo({ top: Math.max(0, top), behavior: smooth ? "smooth" : "auto" });
  }

  function autoScrollEnabled() {
    return localGet("vector:autoscroll", "on") !== "off";
  }

  function setActiveCue(index) {
    if (index === activeCue) return;
    activeCue = index;
    root.querySelectorAll("[data-cue]").forEach((element) => {
      element.classList.toggle("active", Number(element.dataset.cue) === index);
    });
    if (index >= 0) scrollCue(index);
  }

  function setChapter(index) {
    if (!lecture?.chapters?.length) return;
    activeChapter = index;
    lastChapter = index;
    root.querySelectorAll("[data-outline-index]").forEach((element) => {
      element.classList.toggle("active", Number(element.dataset.outlineIndex) === index);
    });
    root.querySelectorAll("[data-chapter-index]").forEach((element) => {
      element.classList.toggle("active", Number(element.dataset.chapterIndex) === index);
    });
  }

  function updatePlayback(time, duration) {
    const fill = root.querySelector("[data-outline-fill]");
    if (fill) fill.style.width = `${duration ? Math.min(100, (time / duration) * 100) : 0}%`;
    if (activeTab === "transcript") scrollCue(activeCue);
  }

  function seek(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    if (!player) return;
    player.seekTo(value, true);
    root.querySelector("[data-player]")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function cueAt(seconds) {
    if (!cues.length) return -1;
    let found = 0;
    for (let index = 0; index < cues.length; index += 1) {
      if (seconds >= cues[index].start) found = index;
      else break;
    }
    return found;
  }

  function summaryPanel() {
    const blocks = paragraphs(lecture.summary || lecture.description || "");
    const points = Array.isArray(lecture.summary_points) ? lecture.summary_points : [];
    if (!blocks.length && !points.length) {
      return `<div class="tab-panel summary-block"><p class="muted">Конспект для этой лекции пока не сформирован.</p></div>`;
    }
    return `
    <div class="tab-panel summary-block" data-panel="summary">
      <div class="summary-text">${blocks.map((block) => `<p>${escapeHtml(block)}</p>`).join("")}</div>
      ${points.length ? `
      <div>
        <div class="eyebrow" style="margin-bottom:6px">Ключевые тезисы</div>
        <div class="summary-points">
          ${points.map((point) => `
            <button class="summary-point" type="button" data-seek="${Number(point.start) || 0}">
              <span class="t">${formatTime(point.start)}</span>
              <p>${escapeHtml(point.text)}</p>
              ${icon("play")}
            </button>`).join("")}
        </div>
      </div>` : ""}
      <div class="summary-source-note">
        ${icon(lecture.llm_used ? "sparkles" : "cpu")}
        ${lecture.llm_used
          ? "Конспект уточнён языковой моделью на основе расшифровки."
          : "Конспект собран локально: TextRank и взвешенные ключевые предложения."}
      </div>
    </div>`;
  }

  function chaptersPanel() {
    const chapters = Array.isArray(lecture.chapters) ? lecture.chapters : [];
    if (!chapters.length) {
      return `<div class="tab-panel" data-panel="chapters"><div class="no-transcript">Структура появится после обработки расшифровки.</div></div>`;
    }
    return `
    <div class="tab-panel" data-panel="chapters">
      <div class="chapter-list">
        ${chapters.map((chapter, index) => `
          <button class="chapter-card${index === activeChapter ? " active" : ""}" type="button"
                  data-chapter-index="${index}" data-seek="${Number(chapter.start) || 0}">
            <span class="t">${formatTime(chapter.start)}</span>
            <div>
              <h4>${escapeHtml(chapter.title || `Глава ${index + 1}`)}</h4>
              ${chapter.summary ? `<p>${escapeHtml(chapter.summary)}</p>` : ""}
              <div class="chapter-foot">
                <span>${formatDuration((chapter.end || 0) - (chapter.start || 0))}</span>
                ${Array.isArray(chapter.keywords) && chapter.keywords.length
                  ? `<span>${chapter.keywords.slice(0, 3).map((item) => escapeHtml(item.term || item)).join(" · ")}</span>`
                  : ""}
              </div>
            </div>
          </button>`).join("")}
      </div>
    </div>`;
  }

  function transcriptPanel() {
    return `
    <div class="tab-panel" data-panel="transcript">
      <div class="transcript-toolbar">
        <div class="transcript-search">
          ${icon("search")}
          <label class="sr-only" for="transcript-filter">Фильтр по расшифровке</label>
          <input id="transcript-filter" data-transcript-filter type="search" placeholder="Найти слово в расшифровке…">
        </div>
        <label class="toggle-label">
          <input type="checkbox" data-autoscroll ${autoScrollEnabled() ? "checked" : ""}> Автопрокрутка
        </label>
        <button class="btn btn-sm" type="button" data-copy-transcript>${icon("copy")} Копировать</button>
        <span class="muted" style="font-size:10.5px" data-transcript-count>${cues.length} ${plural(cues.length, ["реплика", "реплики", "реплик"])}</span>
      </div>
      <div class="transcript-list" data-transcript-list>
        ${cues.length ? cues.map((cue, index) => cueMarkup(cue, index, searchQuery)).join("") : '<div class="no-transcript">Расшифровка пуста.</div>'}
      </div>
    </div>`;
  }

  function qaSuggestions() {
    const terms = normalizeKeywords(lecture.keywords).slice(0, 3).map((item) => item.term);
    const base = ["О чём эта лекция?", "Объясни главную идею простыми словами", "Приведи пример из лекции"];
    if (terms[0]) base.push(`Что такое «${terms[0]}»?`);
    return base.slice(0, 5);
  }

  function qaPanel() {
    return `
    <div class="tab-panel" data-panel="qa">
      <div class="qa-wrap">
        <div class="qa-suggestions">
          ${qaSuggestions().map((question) => `<button class="chip" type="button" data-ask="${escapeHtml(question)}">${icon("sparkles")}${escapeHtml(question)}</button>`).join("")}
        </div>
        <div class="qa-messages" data-qa-messages>
          <div class="qa-msg assistant">
            <div class="avatar">В</div>
            <div>
              <div class="qa-bubble">
                <p>Спросите о содержании лекции — я найду подходящие фрагменты и отвечу, опираясь только на расшифровку. У каждого ответа будут таймкоды.</p>
              </div>
              <div class="qa-mode">${icon(lecture.llm_used ? "sparkles" : "cpu")} ${lecture.llm_used ? "LLM + поиск по расшифровке" : "локальный ответ по расшифровке"}</div>
            </div>
          </div>
        </div>
        <form class="qa-form" data-qa-form autocomplete="off">
          <div class="field">
            <label class="sr-only" for="qa-input">Вопрос по лекции</label>
            <input id="qa-input" type="text" maxlength="800" placeholder="Например: зачем нужна функция потерь?">
          </div>
          <button class="btn btn-primary" type="submit" data-qa-send>${icon("send")} Спросить</button>
        </form>
        <div class="qa-mode" style="margin-top:0">Ответы не выходят за пределы этой лекции${lecture.llm_used ? "; формулировки уточняет подключённая LLM" : ""}.</div>
      </div>
    </div>`;
  }

  function asideMarkup() {
    const chapters = Array.isArray(lecture.chapters) ? lecture.chapters : [];
    const keywords = normalizeKeywords(lecture.keywords);
    return `
    <aside class="lecture-aside">
      <div class="aside-section">
        <div class="aside-section-head">
          <h4>Структура лекции</h4>
          <span class="count">${chapters.length} ${plural(chapters.length, ["глава", "главы", "глав"])}</span>
        </div>
        <div class="outline-progress"><div class="fill" data-outline-fill style="width:0%"></div></div>
        <div class="outline-list">
          ${chapters.length
            ? chapters.map((chapter, index) => `
              <button class="outline-item${index === 0 ? " active" : ""}" type="button"
                      data-outline-index="${index}" data-seek="${Number(chapter.start) || 0}">
                <span class="t">${formatTime(chapter.start)}</span>
                <span class="name">${escapeHtml(chapter.title || `Глава ${index + 1}`)}</span>
              </button>`).join("")
            : '<div class="aside-tip">Главы появятся после обработки.</div>'}
        </div>
      </div>

      ${keywords.length ? `
      <div class="aside-section">
        <div class="aside-section-head"><h4>Ключевые термины</h4><span class="count">${keywords.length}</span></div>
        <div class="term-list">
          ${keywords.map((item) => `
            <button class="term-pill" type="button" data-term="${escapeHtml(item.term)}"
                    title="Найти «${escapeHtml(item.term)}» во всех лекциях">
              ${escapeHtml(item.term)}${item.count ? `<span class="term-count">${item.count}</span>` : ""}
            </button>`).join("")}
        </div>
      </div>` : ""}

      <div class="aside-section">
        <div class="aside-section-head"><h4>Детали</h4></div>
        <div class="detail-list">${detailsMarkup(lecture)}</div>
      </div>

      <div class="aside-section">
        <div class="aside-section-head"><h4>Действия</h4></div>
        <div class="aside-actions">
          <a class="btn btn-sm" href="${api.exportUrl(lecture.id)}" download>${icon("download")} Скачать конспект</a>
          <a class="btn btn-sm" href="${api.subtitlesUrl(lecture.id, "vtt", true)}" download>${icon("subtitles")} Субтитры VTT</a>
          <button class="btn btn-sm" type="button" data-reprocess>${icon("refresh")} Обработать заново</button>
          <button class="btn btn-sm btn-danger" type="button" data-delete>${icon("trash")} Удалить лекцию</button>
        </div>
      </div>
    </aside>`;
  }

  function readyMarkup() {
    const status = statusInfo(lecture.status);
    return `
    <div class="lecture-page">
      <div class="container">
        <nav class="breadcrumb" aria-label="Хлебные крошки">
          <a href="/" data-link>Библиотека</a>
          <span class="sep">/</span>
          <span class="current">${escapeHtml(lecture.title)}</span>
        </nav>
        <header class="lecture-head">
          <div>
            <div class="chip-row">
              <span class="badge ${status.tone}"><span class="dot"></span>${status.label}</span>
              ${lecture.language ? `<span class="badge">${escapeHtml(lecture.language.toUpperCase())}</span>` : ""}
              ${lecture.llm_used ? `<span class="badge blue">LLM</span>` : `<span class="badge">${icon("cpu")} локально</span>`}
            </div>
            <div style="margin-top:12px">${headMarkup(lecture)}</div>
          </div>
          <div class="head-actions">
            <a class="btn btn-sm" href="${api.exportUrl(lecture.id)}" download title="Скачать конспект в Markdown">
              ${icon("download")} Конспект
            </a>
            <a class="btn btn-sm btn-icon" href="${api.subtitlesUrl(lecture.id, "vtt", true)}" download title="Скачать субтитры VTT" aria-label="Скачать субтитры VTT">
              ${icon("subtitles")}
            </a>
          </div>
        </header>

        <div class="lecture-layout">
          <div class="lecture-main">
            ${playerMarkup({ poster: lecture.thumbnail_url || "", chapters: lecture.chapters || [], duration: lecture.duration })}
            <div class="card">
              <div style="padding:0 14px">
                <div class="tabs-bar" role="tablist" aria-label="Материалы лекции">
                  <button class="tab-btn${activeTab === "summary" ? " active" : ""}" type="button" role="tab"
                          aria-selected="${activeTab === "summary"}" data-tab="summary">${icon("book")} Конспект</button>
                  <button class="tab-btn${activeTab === "chapters" ? " active" : ""}" type="button" role="tab"
                          aria-selected="${activeTab === "chapters"}" data-tab="chapters">${icon("layers")} Структура</button>
                  <button class="tab-btn${activeTab === "transcript" ? " active" : ""}" type="button" role="tab"
                          aria-selected="${activeTab === "transcript"}" data-tab="transcript">${icon("list")} Расшифровка</button>
                  <button class="tab-btn${activeTab === "qa" ? " active" : ""}" type="button" role="tab"
                          aria-selected="${activeTab === "qa"}" data-tab="qa">${icon("message")} Вопросы</button>
                </div>
              </div>
              <div style="padding:18px 20px 22px" data-tab-panels>
                ${summaryPanel()}
                ${chaptersPanel()}
                ${transcriptPanel()}
                ${qaPanel()}
              </div>
            </div>
          </div>
          ${asideMarkup()}
        </div>
      </div>
    </div>`;
  }

  function bindPlayer() {
    player = new VectorPlayer(root.querySelector("[data-player]"), {
      src: lecture.media_url,
      title: lecture.title,
      cues,
      chapters: lecture.chapters || [],
      duration: lecture.duration,
      lectureId: lecture.id,
      poster: lecture.thumbnail_url || "",
      hitStart: Number.isFinite(startAt) && startAt > 0 ? startAt : null,
      startAt: Number.isFinite(startAt) && startAt > 0 ? startAt : null,
      autoplayStart: Boolean(Number.isFinite(startAt) && startAt > 0),
      onCue: (index) => setActiveCue(index),
      onChapter: (index) => setChapter(index),
      onTime: (time, duration) => updatePlayback(time, duration),
      onError: (message) => toast(message, "error"),
    });
    const initialChapter = (lecture.chapters || []).findIndex((chapter, index, list) => {
      const next = list[index + 1];
      return startAt >= chapter.start && (!next || startAt < next.start);
    });
    if (initialChapter >= 0) setChapter(initialChapter);
    if (startAt > 0) setActiveCue(cueAt(startAt));
  }

  function bindSeeking() {
    root.addEventListener("click", (event) => {
      const copyButton = event.target.closest("[data-copy-cue]");
      if (copyButton) {
        event.preventDefault();
        event.stopPropagation();
        const cue = cues[Number(copyButton.dataset.copyCue)];
        if (cue) copyText(`[${formatTime(cue.start)}] ${cue.text}`, "Реплика скопирована");
        return;
      }
      const cueElement = event.target.closest("[data-cue]");
      if (cueElement) {
        const seconds = Number(cueElement.dataset.start) || 0;
        setActiveCue(Number(cueElement.dataset.cue));
        player?.seekTo(seconds, true);
        root.querySelector("[data-player]")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        return;
      }
      const seekElement = event.target.closest("[data-seek]");
      if (seekElement) seek(seekElement.dataset.seek);
    });
    root.addEventListener("keydown", (event) => {
      const cueElement = event.target.closest?.("[data-cue]");
      if (!cueElement || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault();
      event.stopPropagation();
      const seconds = Number(cueElement.dataset.start) || 0;
      setActiveCue(Number(cueElement.dataset.cue));
      player?.seekTo(seconds, true);
    });
  }

  function bindReady() {
    root.querySelectorAll("[data-tab]").forEach((button) => {
      button.tabIndex = button.dataset.tab === activeTab ? 0 : -1;
    });
    setTab(activeTab, { updateHash: false, reveal: false });
    setupTabs();
    setupTranscript();
    setupQa();
    setupAside();
    bindSeeking();
    bindPlayer();
    if (startAt > 0) requestAnimationFrame(() => scrollCue(activeCue, true));
  }

  function setupTabs() {
    const bar = root.querySelector(".tabs-bar");
    if (!bar) return;
    bar.addEventListener("click", (event) => {
      const button = event.target.closest("[data-tab]");
      if (button) setTab(button.dataset.tab);
    });
    bar.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const buttons = Array.from(bar.querySelectorAll("[data-tab]"));
      const current = buttons.findIndex((button) => button.classList.contains("active"));
      const next = (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      event.preventDefault();
      buttons[next].focus();
      setTab(buttons[next].dataset.tab);
    });
  }

  function setupTranscript() {
    const filter = root.querySelector("[data-transcript-filter]");
    filter?.addEventListener("input", renderTranscriptList);
    root.querySelector("[data-autoscroll]")?.addEventListener("change", (event) => {
      localSet("vector:autoscroll", event.target.checked ? "on" : "off");
      if (event.target.checked) scrollCue(activeCue, true);
    });
    root.querySelector("[data-copy-transcript]")?.addEventListener("click", () => {
      const text = cues.map((cue) => `[${formatTime(cue.start)}] ${cue.text}`).join("\n");
      copyText(text, "Расшифровка скопирована");
    });
  }

  function setupQa() {
    const form = root.querySelector("[data-qa-form]");
    if (!form) return;
    const input = root.querySelector("#qa-input");
    const messages = root.querySelector("[data-qa-messages]");

    function scrollMessages() {
      messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
    }

    function answerMarkup(text) {
      const safe = escapeHtml(text).trim();
      const html = safe
        .split(/\n{2,}/)
        .map((block) => `<p>${block.replace(/\n/g, " ").replace(/\[(\d+)\]/g, '<span class="cite-ref">[$1]</span>')}</p>`)
        .join("");
      return html || "<p>Ответ пуст.</p>";
    }

    function citationsMarkup(citations) {
      if (!citations?.length) return "";
      return `<div class="qa-cites">
        ${citations.map((citation, index) => `
          <button class="qa-cite" type="button" data-seek="${Number(citation.start) || 0}">
            <span class="n">[${index + 1}]</span>
            <span class="txt"><span class="cite-time">${formatTime(citation.start)}</span> ${escapeHtml(citation.text)}</span>
          </button>`).join("")}
      </div>`;
    }

    async function ask(question) {
      const clean = String(question || "").trim();
      if (!clean || qaBusy) return;
      qaBusy = true;
      input.value = "";
      const send = form.querySelector("[data-qa-send]");
      send.disabled = true;
      messages.insertAdjacentHTML("beforeend", `
        <div class="qa-msg user">
          <div class="avatar">Вы</div>
          <div><div class="qa-bubble"><p>${escapeHtml(clean)}</p></div></div>
        </div>`);
      const typing = document.createElement("div");
      typing.className = "qa-msg assistant";
      typing.innerHTML = `
        <div class="avatar">В</div>
        <div><div class="qa-bubble"><div class="qa-typing"><span></span><span></span><span></span></div></div></div>`;
      messages.append(typing);
      scrollMessages();
      try {
        const result = await api.ask(lecture.id, clean, 5);
        if (cancelled) return;
        typing.remove();
        const mode = result.mode === "llm" ? "LLM + поиск по фрагментам" : "локальный ответ по расшифровке";
        messages.insertAdjacentHTML("beforeend", `
          <div class="qa-msg assistant">
            <div class="avatar">В</div>
            <div>
              <div class="qa-bubble">${answerMarkup(result.answer)}${citationsMarkup(result.citations)}</div>
              <div class="qa-mode">${icon(result.mode === "llm" ? "sparkles" : "cpu")} ${mode} · ${result.took_ms} мс</div>
            </div>
          </div>`);
        scrollMessages();
      } catch (error) {
        if (cancelled) return;
        typing.remove();
        messages.insertAdjacentHTML("beforeend", `
          <div class="qa-msg assistant">
            <div class="avatar">В</div>
            <div><div class="qa-bubble"><p>Не удалось получить ответ: ${escapeHtml(error.message || "ошибка запроса")}. Попробуйте ещё раз.</p></div></div>
          </div>`);
        scrollMessages();
      } finally {
        qaBusy = false;
        send.disabled = false;
        input.focus();
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      ask(input.value);
    });

    root.querySelectorAll("[data-ask]").forEach((button) => {
      button.addEventListener("click", () => ask(button.dataset.ask));
    });
  }

  function setupAside() {
    root.querySelectorAll("[data-term]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.navigate(`/search?q=${encodeURIComponent(button.dataset.term)}&lecture=${encodeURIComponent(lecture.id)}`);
      });
    });
    root.querySelectorAll("[data-reprocess]").forEach((button) => {
      button.addEventListener("click", () => reprocess());
    });
    root.querySelectorAll("[data-delete]").forEach((button) => {
      button.addEventListener("click", () => remove());
    });
  }

  // ---------------------------------------------------------------- actions
  async function reprocess() {
    if (!window.confirm("Запустить обработку заново? Расшифровка, конспект и индекс будут пересобраны.")) return;
    try {
      await api.reprocess(lecture.id);
      readyBuilt = false;
      failureBuilt = false;
      player?.destroy();
      player = null;
      clearTimeout(pollTimer);
      toast("Обработка запущена заново.", "success");
      await load();
    } catch (error) {
      toast(error.message || "Не удалось запустить обработку.", "error");
    }
  }

  async function remove() {
    if (!window.confirm(`Удалить лекцию «${lecture.title}»? Расшифровка, индекс и медиафайл будут удалены безвозвратно.`)) return;
    try {
      await api.deleteLecture(lecture.id);
      toast("Лекция удалена.", "success");
      ctx.navigate("/");
    } catch (error) {
      toast(error.message || "Не удалось удалить лекцию.", "error");
    }
  }

  // ------------------------------------------------------------------- load
  async function loadReady() {
    if (readyBuilt) return;
    try {
      const transcript = await api.transcript(lecture.id);
      cues = transcript.cues || [];
    } catch (error) {
      cues = [];
      toast("Расшифровка недоступна, но плеер и конспект работают.", "error");
    }
    if (cancelled) return;
    lecture.segments_count = cues.length || lecture.segments_count || 0;
    root.innerHTML = readyMarkup();
    readyBuilt = true;
    bindReady();
    ctx.setTitle(`${lecture.title} — Вектор`);
  }

  function updateProcessing(data) {
    const fill = root.querySelector("[data-progress-fill]");
    const stage = root.querySelector("[data-stage]");
    if (fill) fill.style.width = `${Math.max(2, data.progress || 0)}%`;
    if (stage) stage.textContent = data.stage || "Обработка";
    const active = stageIndex(data.stage, data.progress || 0);
    root.querySelectorAll("[data-step]").forEach((element) => {
      const index = Number(element.dataset.step);
      element.classList.toggle("done", index < active);
      element.classList.toggle("on", index === active);
      const caption = element.querySelector("span");
      if (caption) caption.textContent = index < active ? "Готово" : index === active ? "Сейчас" : "Ожидает";
      const strong = element.querySelector("strong");
      if (strong) strong.innerHTML = `${icon(index < active ? "check" : "clock")} ${STEPS[index].title}`;
    });
    const chip = root.querySelector(".lecture-head .badge");
    if (chip) chip.innerHTML = `<span class="dot"></span>Обработка`;
    const progressBadge = root.querySelector("[data-progress-chip]");
    if (progressBadge) progressBadge.textContent = `${data.progress || 0}%`;
  }

  async function load() {
    if (cancelled) return;
    clearTimeout(pollTimer);
    try {
      const data = await api.lecture(lectureId);
      if (cancelled) return;
      const previousStatus = lecture?.status;
      lecture = data;
      ctx.setTitle(`${data.title} — Вектор`);
      if (data.status === "ready") {
        if (!readyBuilt) await loadReady();
        return;
      }
      if (data.status === "failed") {
        if (!failureBuilt || previousStatus !== "failed") {
          root.innerHTML = failureMarkup(data);
          failureBuilt = true;
          readyBuilt = false;
          setupAside();
          root.querySelectorAll("[data-retry]").forEach((button) => {
            button.addEventListener("click", () => reprocess());
          });
        }
        return;
      }
      if (!root.querySelector("[data-progress-fill]") || previousStatus === "failed") {
        root.innerHTML = processingMarkup(data);
        failureBuilt = false;
        readyBuilt = false;
        setupAside();
      } else {
        updateProcessing(data);
      }
      schedulePoll();
    } catch (error) {
      if (cancelled) return;
      if (error.status === 404) {
        root.innerHTML = `
        <section class="section"><div class="container"><div class="empty-state">
          <span class="empty-icon">${icon("file-video")}</span>
          <h3>Лекция не найдена</h3>
          <p>Возможно, она была удалена или ссылка неверна.</p>
          <a class="btn btn-primary" href="/" data-link>${icon("chevron-left")} В библиотеку</a>
        </div></div></section>`;
        ctx.setTitle("Лекция не найдена — Вектор");
        return;
      }
      root.innerHTML = `
      <section class="section"><div class="container"><div class="empty-state">
        <span class="empty-icon">${icon("alert")}</span>
        <h3>Не удалось загрузить лекцию</h3>
        <p>${escapeHtml(error.message || "Сервер не отвечает.")}</p>
        <div class="chip-row" style="justify-content:center">
          <button class="btn" type="button" data-retry-load>${icon("refresh")} Повторить</button>
          <a class="btn" href="/" data-link>${icon("chevron-left")} В библиотеку</a>
        </div>
      </div></div></section>`;
      root.querySelector("[data-retry-load]")?.addEventListener("click", load);
      schedulePoll();
    }
  }

  load();

  return () => {
    cancelled = true;
    clearTimeout(pollTimer);
    player?.destroy();
    player = null;
  };
}
