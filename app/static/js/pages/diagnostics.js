import { api } from "../api.js";
import { escapeHtml, formatBytes, formatDate, formatNumber, icon } from "../utils.js";

function row(label, value, mono = false) {
  return `<div class="diag-row"><span>${escapeHtml(label)}</span><span${mono ? ' class="mono"' : ""}>${value}</span></div>`;
}

function badge(ok, labels = ["Работает", "Недоступно"]) {
  return `<span class="badge ${ok ? "lime" : "red"}"><span class="dot"></span>${ok ? labels[0] : labels[1]}</span>`;
}

function card({ iconName, title, badgeMarkup, rows = [], note = "" }) {
  return `
  <div class="diag-card">
    <div class="diag-head">
      ${icon(iconName)}
      <h3>${escapeHtml(title)}</h3>
      ${badgeMarkup || ""}
    </div>
    ${rows.join("")}
    ${note ? `<div class="diag-note">${note}</div>` : ""}
  </div>`;
}

function diskBar(disk) {
  if (!disk?.total) return "";
  const used = Number(disk.used) || 0;
  const total = Number(disk.total) || 0;
  const percent = total ? Math.round((used / total) * 100) : 0;
  return `
  <div class="diag-disk">
    <div class="diag-row" style="padding-top:8px"><span>Свободно</span><span>${formatBytes(disk.free)} из ${formatBytes(total)}</span></div>
    <div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div>
  </div>`;
}

export function mount(root, ctx) {
  let cancelled = false;
  let timer = null;
  let busy = false;

  ctx.setTitle("Диагностика — Вектор");

  root.innerHTML = `
  <section class="settings-page">
    <div class="container">
      <nav class="breadcrumb" aria-label="Хлебные крошки">
        <a href="/" data-link>Библиотека</a>
        <span class="sep">/</span>
        <span class="current">Диагностика</span>
      </nav>
      <div class="diag-title">
        <div>
          <div class="eyebrow">Система</div>
          <h1>Диагностика «Вектора»</h1>
          <p class="muted">Состояние моделей, медиаинструментов и индекса. Всё работает локально — без облачных зависимостей.</p>
        </div>
        <div class="diag-actions">
          <span class="diag-updated mono" data-updated>Проверяем…</span>
          <button class="btn" type="button" data-refresh>${icon("refresh")} Обновить</button>
        </div>
      </div>
      <div class="diag-status" id="diag-status">
        <span class="health-dot"></span>
        <span>Проверяем состояние…</span>
      </div>
      <div class="settings-grid" id="diag-grid">
        ${Array.from({ length: 6 }, () => '<div class="skeleton" style="height:190px;border-radius:14px"></div>').join("")}
      </div>
      <div id="diag-warnings"></div>
      <div class="diag-footer">
        <span>${icon("shield")} Файлы и расшифровки не покидают этот сервер.</span>
        <span class="mono">Вектор · Киберрывок · Осень 2026</span>
      </div>
    </div>
  </section>`;

  const grid = root.querySelector("#diag-grid");
  const statusBox = root.querySelector("#diag-status");
  const warningsBox = root.querySelector("#diag-warnings");
  const updatedBox = root.querySelector("[data-updated]");
  const refreshButton = root.querySelector("[data-refresh]");

  function render(data) {
    const { health, stats, meta, ffmpeg } = data;
    const asr = health?.asr || {};
    const embeddings = health?.embeddings || {};
    const llm = health?.llm || {};
    const pipeline = health?.pipeline || {};
    const disk = stats?.disk || {};
    const warnings = health?.warnings || [];
    const ok = health?.status === "ok" && warnings.length === 0;

    statusBox.innerHTML = `
      <span class="health-dot ${ok ? "" : warnings.length ? "warn" : "bad"}"></span>
      <span>${ok ? "Все системы готовы" : "Есть предупреждения — проверьте список ниже"}</span>
      <span class="mono" style="margin-left:auto;color:var(--muted-2)">${health?.status === "ok" ? "status: ok" : `status: ${escapeHtml(health?.status || "unknown")}`}</span>`;

    const ffmpegVersion = ffmpeg?.version || "";
    const versionLine = ffmpegVersion.replace("ffmpeg version ", "").split(" Copyright")[0];

    grid.innerHTML = [
      card({
        iconName: "server",
        title: "Сервер",
        badgeMarkup: badge(Boolean(health?.db?.ok), ["База доступна", "База недоступна"]),
        rows: [
          row("Версия", escapeHtml(health?.version || meta?.version || "—")),
          row("Режим", "локальный", true),
          row("База данных", escapeHtml(String(health?.db?.path || "—").split(/[\\/]/).pop() || "—"), true),
          row("Лимит загрузки", `${formatNumber(meta?.max_upload_mb || 0)} МБ`),
        ],
      }),
      card({
        iconName: "file-video",
        title: "Медиа",
        badgeMarkup: badge(Boolean(health?.ffmpeg), ["ffmpeg готов", "Нет ffmpeg"]),
        rows: [
          row("ffmpeg", ffmpegVersion ? "найден" : "не найден"),
          row("Версия", escapeHtml(versionLine || "—"), true),
          row("ffprobe", health?.ffmpeg ? "найден" : "не найден"),
          row("Макс. длительность", "4 часа"),
        ],
        note: ffmpegVersion ? "" : "Положите ffmpeg и ffprobe в <span class=\"mono\">tools/ffmpeg/bin</span> или добавьте в PATH.",
      }),
      card({
        iconName: "mic",
        title: "Распознавание речи",
        badgeMarkup: badge(Boolean(asr.ready && asr.model_present), ["Whisper готов", "Модель не готова"]),
        rows: [
          row("Движок", escapeHtml(asr.provider || "faster-whisper")),
          row("Модель", escapeHtml(asr.model || "—")),
          row("Веса", asr.model_present ? "загружены локально" : "нет, скачаются при первом запуске"),
          row("Вычисления", `${escapeHtml(asr.compute_type || "int8")} · ${asr.cpu_threads || "—"} потоков`, true),
        ],
      }),
      card({
        iconName: "brain",
        title: "Смысловой индекс",
        badgeMarkup: badge(Boolean(embeddings.model_present), ["Эмбеддинги готовы", "Лексический резерв"]),
        rows: [
          row("Активный бэкенд", escapeHtml(embeddings.active || "—"), true),
          row("Модель", escapeHtml(embeddings.model || "—")),
          row("Размерность", String(embeddings.dim || "—")),
          row("Фрагментов в базе", formatNumber(stats?.segments || 0)),
          row("Глав собрано", formatNumber(stats?.chapters || 0)),
        ],
        note: embeddings.active === "hashing" ? "Семантическая модель не найдена — поиск использует лексический резерв. Запустите setup для загрузки модели." : "",
      }),
      card({
        iconName: "sparkles",
        title: "Генерация ответов",
        badgeMarkup: badge(Boolean(llm.configured), ["LLM подключена", "Локальный режим"]),
        rows: [
          row("Статус", llm.configured ? "внешняя LLM" : "локальные алгоритмы"),
          row("Модель", escapeHtml(llm.model || "TextRank + TextWeights")),
          row("Endpoint", escapeHtml(llm.base_url || "—"), true),
          row("Конспект и Q&A", llm.configured ? "с уточнением LLM" : "полностью локально"),
        ],
        note: llm.configured ? "" : "Подключение OpenAI-совместимой LLM опционально: задайте LLM_ENABLED, LLM_BASE_URL и LLM_MODEL.",
      }),
      card({
        iconName: "database",
        title: "Библиотека и диск",
        badgeMarkup: `<span class="badge">${formatNumber(stats?.lectures || 0)} лекций</span>`,
        rows: [
          row("Готово", formatNumber(stats?.ready || 0)),
          row("В обработке", formatNumber(stats?.processing || 0)),
          row("Часов видео", String(stats?.hours ?? "0").replace(".", ",")),
          row("Размер базы", formatBytes(stats?.db_size || 0)),
          row("Просмотры", formatNumber(stats?.views || 0)),
          diskBar(disk),
        ],
      }),
    ].join("");

    if (warnings.length) {
      warningsBox.innerHTML = `
      <div class="diag-warnings">
        <h4>${icon("alert")} Предупреждения</h4>
        <ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>
        ${pipeline.ffmpeg === false ? '<p class="diag-warning-note">Без ffmpeg загрузка и обработка видео недоступны. Установите бинарники и перезапустите сервер.</p>' : ""}
      </div>`;
    } else {
      warningsBox.innerHTML = `
      <div class="diag-ok">
        ${icon("check")}
        <div>
          <strong>Проверка пройдена</strong>
          <span>База данных, ffmpeg, модель распознавания и смысловой индекс доступны.</span>
        </div>
      </div>`;
    }

    updatedBox.textContent = `Проверено: ${new Date().toLocaleTimeString("ru-RU")}`;
    updatedBox.title = formatDate(new Date().toISOString(), true);
  }

  async function load() {
    if (busy || cancelled) return;
    busy = true;
    refreshButton.disabled = true;
    refreshButton.innerHTML = `<span class="spinner" style="width:14px;height:14px"></span> Проверяем…`;
    try {
      const [health, stats, meta, ffmpeg] = await Promise.all([
        api.health(),
        api.stats().catch(() => null),
        api.meta().catch(() => null),
        api.ffmpeg().catch(() => null),
      ]);
      if (cancelled) return;
      render({ health, stats, meta, ffmpeg });
    } catch (error) {
      if (cancelled) return;
      console.error("diagnostics failed", error);
      statusBox.innerHTML = `<span class="health-dot bad"></span><span>Сервер не отвечает: ${escapeHtml(error.message || "неизвестная ошибка")}</span>`;
      grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <span class="empty-icon">${icon("alert")}</span>
        <h3>Не удалось получить диагностику</h3>
        <p>Проверьте, что приложение запущено, и обновите страницу.</p>
        <button class="btn" type="button" data-retry>${icon("refresh")} Повторить</button>
      </div>`;
      grid.querySelector("[data-retry]")?.addEventListener("click", load);
      updatedBox.textContent = "Нет связи";
    } finally {
      busy = false;
      refreshButton.disabled = false;
      refreshButton.innerHTML = `${icon("refresh")} Обновить`;
    }
  }

  refreshButton.addEventListener("click", load);
  load();
  timer = setInterval(load, 30000);

  return () => {
    cancelled = true;
    clearInterval(timer);
    refreshButton.removeEventListener("click", load);
  };
}
