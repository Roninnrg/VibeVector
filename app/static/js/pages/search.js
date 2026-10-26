import { api } from "../api.js";
import {
  debounce,
  escapeHtml,
  formatDate,
  formatDuration,
  formatTime,
  icon,
  plural,
  statusInfo,
  toast,
} from "../utils.js";

const QUICK_QUERIES = [
  "теорема Пифагора",
  "как сеть учится",
  "что такое градиент",
  "египетский треугольник",
  "примеры применения",
  "обучение с учителем",
];

function skeletonResults(count = 4) {
  return `<div class="result-list">${Array.from({ length: count }, () => `
    <div class="result-card" style="grid-template-columns:62px minmax(0,1fr)">
      <div class="skeleton" style="height:24px;width:46px"></div>
      <div style="display:flex;flex-direction:column;gap:9px">
        <div class="skeleton" style="height:11px;width:32%"></div>
        <div class="skeleton" style="height:13px;width:94%"></div>
        <div class="skeleton" style="height:13px;width:78%"></div>
        <div class="skeleton" style="height:10px;width:44%"></div>
      </div>
    </div>`).join("")}</div>`;
}

function scoreTone(item) {
  if (item.score >= 0.55) return "lime";
  if (item.score >= 0.32) return "";
  return "amber";
}

export function mount(root, ctx) {
  let cancelled = false;
  let controller = null;
  let searchToken = 0;
  let lectures = [];
  let stats = null;
  let lastResult = null;
  let lectureId = ctx.query.get("lecture") || "";
  let initialQuery = (ctx.query.get("q") || "").trim();
  let debounceTimer = null;

  root.innerHTML = `
  <section class="search-page">
    <div class="container">
      <div class="search-head">
        <nav class="breadcrumb" aria-label="Хлебные крошки">
          <a href="/" data-link>Библиотека</a>
          <span class="sep">/</span>
          <span class="current">Поиск по смыслу</span>
        </nav>
        <div class="eyebrow">Семантический поиск</div>
        <h1>Найдите <em>момент</em>, а не таймкод.</h1>
        <div class="search-meta" id="search-meta">
          <span>Опишите мысль своими словами — «Вектор» найдёт её в расшифровках.</span>
        </div>
      </div>

      <div class="search-layout">
        <div class="search-main">
          <form class="search-form" id="search-form" role="search" autocomplete="off">
            <div class="field">
              <label class="sr-only" for="search-q">Что найти в лекциях?</label>
              ${icon("search")}
              <input id="search-q" name="q" type="search" maxlength="500"
                     placeholder="Например: почему производная — это скорость изменения?"
                     value="${escapeHtml(initialQuery)}">
            </div>
            <button class="btn btn-primary" type="submit">${icon("search")} Найти</button>
          </form>
          <div id="search-body">${skeletonResults()}</div>
        </div>

        <aside class="search-aside">
          <div class="aside-card">
            <h4>Искать в лекциях</h4>
            <div id="aside-lectures" class="aside-list">
              <div class="skeleton" style="height:26px;margin-bottom:6px"></div>
              <div class="skeleton" style="height:26px"></div>
            </div>
          </div>
          <div class="aside-card">
            <h4>Как искать</h4>
            <div class="aside-tip">
              Формулируйте <strong>смысл</strong>, а не ключевые слова: «объяснение градиентного спуска на пальцах».<br><br>
              Добавьте контекст: <strong>«пример»</strong>, <strong>«доказательство»</strong>, <strong>«формула»</strong>.<br><br>
              Каждый результат открывается на нужной секунде с подсвеченными субтитрами.
            </div>
          </div>
          <div class="aside-card hidden" id="trending-card">
            <h4>Частые запросы</h4>
            <div class="chip-row" id="trending-list"></div>
          </div>
        </aside>
      </div>
    </div>
  </section>`;

  const form = root.querySelector("#search-form");
  const input = root.querySelector("#search-q");
  const body = root.querySelector("#search-body");
  const meta = root.querySelector("#search-meta");
  const lecturesBox = root.querySelector("#aside-lectures");
  const trendingCard = root.querySelector("#trending-card");
  const trendingList = root.querySelector("#trending-list");

  function updateUrl() {
    const params = new URLSearchParams();
    const query = input.value.trim();
    if (query) params.set("q", query);
    if (lectureId) params.set("lecture", lectureId);
    const suffix = params.toString();
    window.history.replaceState({ vector: true }, "", `/search${suffix ? `?${suffix}` : ""}`);
    const headerInput = document.getElementById("global-q");
    if (headerInput && document.activeElement !== headerInput) headerInput.value = query;
    ctx.setTitle(query ? `«${query}» — поиск — Вектор` : "Поиск по лекциям — Вектор");
  }

  function lectureName(id) {
    return lectures.find((lecture) => lecture.id === id)?.title || "";
  }

  function renderMeta(result) {
    const activeLecture = lectureName(lectureId);
    const parts = [];
    if (result) {
      const count = result.count || 0;
      parts.push(`<span><strong style="color:var(--ink)">${count}</strong> ${plural(count, ["фрагмент", "фрагмента", "фрагментов"])}</span>`);
      parts.push(`<span class="took">${result.took_ms} мс · ${result.mode === "hashing" ? "лексический индекс" : "гибридный индекс"}</span>`);
      if (activeLecture) parts.push(`<span class="badge">${icon("book")} ${escapeHtml(activeLecture)}</span>`);
    } else {
      parts.push("<span>Опишите мысль своими словами — «Вектор» найдёт её в расшифровках.</span>");
    }
    meta.innerHTML = parts.join("");
  }

  function resultCard(item, query) {
    const href = `/lecture/${encodeURIComponent(item.lecture_id)}?t=${Math.max(0, Math.floor(item.start))}`
      + (query ? `&q=${encodeURIComponent(query)}` : "")
      + "#transcript";
    const percent = Math.max(0, Math.min(100, item.score_percent || 0));
    const duration = Math.max(1, Math.round((item.end || 0) - (item.start || 0)));
    const tone = scoreTone(item);
    return `
    <a class="result-card" href="${href}" data-link aria-label="Открыть момент ${formatTime(item.start)} в лекции «${escapeHtml(item.lecture_title)}»">
      <div class="result-time">
        <span class="t">${formatTime(item.start)}</span>
        <span class="dur">${duration} с</span>
      </div>
      <div class="result-body">
        <div class="result-lecture">
          ${icon("book")}
          <span>${escapeHtml(item.lecture_title)}</span>
          ${item.lecture_language ? `<span class="badge" style="height:18px;font-size:9px">${escapeHtml(item.lecture_language.toUpperCase())}</span>` : ""}
        </div>
        <p>${item.snippet_html || escapeHtml(item.text)}</p>
        <div class="result-foot">
          <span class="relevance" title="Итоговая релевантность: смысл, слова и покрытие запроса">
            <span class="track"><span class="fill" style="width:${percent}%"></span></span>
            ${percent}%
          </span>
          ${item.dense ? `<span class="badge ${tone}">смысл ${Math.round(item.dense * 100)}</span>` : ""}
          <span class="spacer"></span>
          <span class="result-link">Открыть момент ${icon("chevron-right")}</span>
        </div>
      </div>
    </a>`;
  }

  function discoveryMarkup() {
    const ready = lectures.filter((lecture) => lecture.status === "ready");
    return `
    <div class="empty-state search-empty">
      <span class="empty-icon">${icon("sparkles")}</span>
      <h3>Спросите по-человечески</h3>
      <p>Не нужно помнить таймкод или точную формулировку. Опишите, что хотите вспомнить, — поиск сравнит смысл запроса с каждой репликой лекции.</p>
      <div class="chip-row" style="justify-content:center;max-width:560px">
        ${QUICK_QUERIES.map((query) => `<button class="chip" type="button" data-query="${escapeHtml(query)}">${icon("search")}${escapeHtml(query)}</button>`).join("")}
      </div>
      ${ready.length ? `<div class="search-empty-foot">Готовы к поиску: <strong>${ready.length}</strong> ${plural(ready.length, ["лекция", "лекции", "лекций"])} · ${ready.reduce((total, lecture) => total + (lecture.segments_count || 0), 0)} ${plural(ready.reduce((total, lecture) => total + (lecture.segments_count || 0), 0), ["фрагмент", "фрагмента", "фрагментов"])}</div>` : `
      <div class="search-empty-foot">Пока нет готовых лекций. <button class="btn btn-sm btn-primary" type="button" data-open-upload>${icon("upload")} Добавить лекцию</button></div>`}
    </div>`;
  }

  function noResultsMarkup(query) {
    const filterName = lectureName(lectureId);
    return `
    <div class="empty-state search-empty">
      <span class="empty-icon">${icon("search")}</span>
      <h3>Ничего не нашлось</h3>
      <p>${filterName
        ? `В лекции «${escapeHtml(filterName)}» нет подходящих фрагментов. Попробуйте искать по всем лекциям или переформулируйте запрос.`
        : "Попробуйте описать мысль иначе, убрать лишние детали или поискать по более общему запросу."}</p>
      <div class="chip-row" style="justify-content:center">
        ${filterName ? `<button class="btn btn-sm" type="button" data-clear-filter>${icon("layers")} Искать везде</button>` : ""}
        ${QUICK_QUERIES.slice(0, 3).map((item) => `<button class="chip" type="button" data-query="${escapeHtml(item)}">${escapeHtml(item)}</button>`).join("")}
      </div>
      ${query ? `<div class="search-empty-foot">Запрос: «${escapeHtml(query)}»</div>` : ""}
    </div>`;
  }

  function statusBanner(message, tone = "amber") {
    return `<div class="search-banner ${tone}">${icon("info")}<span>${message}</span></div>`;
  }

  function renderResults(result, query) {
    if (!result || !result.count) {
      body.innerHTML = noResultsMarkup(query);
      return;
    }
    const cards = result.results.map((item) => resultCard(item, query)).join("");
    const filterChip = lectureId
      ? `<div class="search-filter-row">
           <span class="badge lime">${icon("book")} ${escapeHtml(lectureName(lectureId) || "Выбранная лекция")}</span>
           <button class="btn btn-ghost btn-sm" type="button" data-clear-filter>${icon("x")} Искать везде</button>
         </div>`
      : "";
    const low = result.low_confidence
      ? statusBanner("Точного совпадения может не быть — ниже ближайшие по смыслу фрагменты. Попробуйте уточнить запрос.", "amber")
      : "";
    body.innerHTML = `${filterChip}${low}<div class="result-list">${cards}</div>`;
  }

  function renderAsideLectures() {
    const all = `${icon("layers")}<span>Все лекции</span><span class="count">${lectures.length}</span>`;
    const items = lectures.map((lecture) => {
      const status = statusInfo(lecture.status);
      const ready = lecture.status === "ready";
      return `
      <button class="aside-lecture${lecture.id === lectureId ? " active" : ""}" type="button" data-lecture="${escapeHtml(lecture.id)}" ${ready ? "" : "disabled"}
              title="${escapeHtml(lecture.title)}">
        ${icon(ready ? "book" : "clock")}
        <span class="name">${escapeHtml(lecture.title)}</span>
        ${ready
          ? `<span class="count">${lecture.segments_count || 0}</span>`
          : `<span class="badge ${status.tone}" style="height:18px;font-size:9px">${status.label}</span>`}
      </button>`;
    }).join("");
    lecturesBox.innerHTML = `
      <button class="aside-lecture${lectureId ? "" : " active"}" type="button" data-lecture="">
        ${all}
      </button>
      ${items || '<div class="aside-tip">Готовых лекций пока нет.</div>'}`;
  }

  async function loadAside() {
    try {
      const [list, statsData] = await Promise.all([
        api.lectures({ limit: 200 }),
        api.stats().catch(() => null),
      ]);
      if (cancelled) return;
      lectures = list.items || [];
      stats = statsData;
      if (lectureId && !lectures.some((lecture) => lecture.id === lectureId && lecture.status === "ready")) {
        lectureId = "";
      }
      renderAsideLectures();
      if (stats?.trending?.length) {
        trendingCard.classList.remove("hidden");
        trendingList.innerHTML = stats.trending
          .slice(0, 6)
          .map((item) => `<button class="chip" type="button" data-query="${escapeHtml(item.query)}">${escapeHtml(item.query)}</button>`)
          .join("");
      }
      if (!initialQuery) {
        body.innerHTML = discoveryMarkup();
        renderMeta(null);
      }
    } catch (error) {
      if (cancelled) return;
      lecturesBox.innerHTML = `<div class="aside-tip">Не удалось загрузить список лекций.</div>`;
      if (!initialQuery) toast(error.message || "Не удалось загрузить библиотеку", "error");
    }
  }

  async function runSearch({ updateHistory = true } = {}) {
    const query = input.value.trim();
    if (!query) {
      controller?.abort();
      controller = null;
      lastResult = null;
      body.innerHTML = discoveryMarkup();
      renderMeta(null);
      if (updateHistory) updateUrl();
      return;
    }
    if (updateHistory) updateUrl();
    else ctx.setTitle(`«${query}» — поиск — Вектор`);

    controller?.abort();
    controller = new AbortController();
    const token = ++searchToken;
    body.innerHTML = skeletonResults();
    renderMeta(null);
    meta.innerHTML = `<span><span class="spinner" style="width:13px;height:13px;display:inline-block;vertical-align:-2px;margin-right:6px"></span>Ищем по смыслу…</span>`;
    try {
      const result = await api.search(query, {
        limit: 14,
        ...(lectureId ? { lecture_id: lectureId } : {}),
      });
      if (cancelled || token !== searchToken) return;
      lastResult = result;
      renderResults(result, query);
      renderMeta(result);
    } catch (error) {
      if (cancelled || token !== searchToken || error.name === "AbortError") return;
      body.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">${icon("alert")}</span>
        <h3>Поиск не отвечает</h3>
        <p>${escapeHtml(error.message || "Не удалось выполнить запрос.")}</p>
        <button class="btn" type="button" data-retry>${icon("refresh")} Повторить</button>
      </div>`;
      renderMeta(null);
    }
  }

  function setLecture(id) {
    lectureId = id;
    renderAsideLectures();
    renderMeta(lastResult);
    runSearch({ updateHistory: true });
  }

  const onInput = debounce(() => {
    if (cancelled) return;
    const value = input.value.trim();
    if (value.length >= 3) runSearch({ updateHistory: false });
    else if (!value) runSearch({ updateHistory: false });
  }, 420);

  input.addEventListener("input", onInput);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    clearTimeout(debounceTimer);
    runSearch({ updateHistory: true });
  });

  function onClick(event) {
    const queryButton = event.target.closest("[data-query]");
    if (queryButton) {
      input.value = queryButton.dataset.query || "";
      runSearch({ updateHistory: true });
      return;
    }
    const lectureButton = event.target.closest("[data-lecture]");
    if (lectureButton) {
      setLecture(lectureButton.dataset.lecture || "");
      return;
    }
    if (event.target.closest("[data-clear-filter]")) {
      setLecture("");
      return;
    }
    if (event.target.closest("[data-retry]")) {
      runSearch({ updateHistory: false });
      return;
    }
    if (event.target.closest("[data-open-upload]")) {
      ctx.openUpload({
        onCreated: (lecture) => ctx.navigate(`/lecture/${encodeURIComponent(lecture.id)}`),
      });
    }
  }

  root.addEventListener("click", onClick);

  loadAside();
  if (initialQuery) runSearch({ updateHistory: false });

  return () => {
    cancelled = true;
    controller?.abort();
    clearTimeout(debounceTimer);
    root.removeEventListener("click", onClick);
    input.removeEventListener("input", onInput);
  };
}
