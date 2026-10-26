import { api } from "./api.js";
import { openUpload } from "./upload.js";
import { mount as mountHome } from "./pages/home.js";
import { mount as mountSearch } from "./pages/search.js";
import { mount as mountLecture } from "./pages/lecture.js";
import { mount as mountDiagnostics } from "./pages/diagnostics.js";
import { icon, scrollToTop } from "./utils.js";

const main = document.getElementById("main");
const globalForm = document.getElementById("global-search");
const globalInput = document.getElementById("global-q");
const uploadButton = document.getElementById("open-upload");
const modeChip = document.getElementById("mode-chip");
const modeLabel = document.getElementById("mode-label");

const ROUTES = [
  { pattern: /^\/$/, mount: mountHome, title: "Вектор — найдите момент, а не таймкод", nav: "home" },
  { pattern: /^\/search$/, mount: mountSearch, title: "Поиск по лекциям — Вектор", nav: "search" },
  { pattern: /^\/lecture\/([^/]+)$/, mount: mountLecture, title: "Лекция — Вектор", nav: "home" },
  { pattern: /^\/diagnostics$/, mount: mountDiagnostics, title: "Диагностика — Вектор", nav: "diagnostics" },
];

const BASE_TITLE = "Вектор — найдите момент, а не таймкод";

let cleanup = null;
let renderToken = 0;
let healthTimer = null;

function normalizePath(pathname) {
  const value = pathname.replace(/\/+$/, "");
  return value || "/";
}

function currentUrl() {
  return new URL(window.location.href);
}

function syncHeader(query) {
  if (document.activeElement !== globalInput) {
    globalInput.value = query.get("q") || "";
  }
  globalForm?.classList.toggle("has-value", Boolean(globalInput?.value));
}

function setActiveNav(name) {
  document.querySelectorAll("[data-nav]").forEach((link) => {
    const active = link.dataset.nav === name;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function setTitle(title) {
  document.title = title || BASE_TITLE;
}

function notFoundMarkup() {
  return `
  <section class="section">
    <div class="container">
      <div class="empty-state">
        <span class="empty-icon">${icon("alert")}</span>
        <h3>Страница не найдена</h3>
        <p>Возможно, ссылка устарела или в адресе опечатка. Вернитесь в библиотеку или найдите нужный момент в поиске.</p>
        <div class="chip-row" style="justify-content:center">
          <a class="btn btn-primary" href="/" data-link>${icon("book")} В библиотеку</a>
          <a class="btn" href="/search" data-link>${icon("search")} Поиск</a>
        </div>
      </div>
    </div>
  </section>`;
}

function errorMarkup(error) {
  return `
  <section class="section">
    <div class="container">
      <div class="empty-state">
        <span class="empty-icon">${icon("alert")}</span>
        <h3>Не удалось открыть страницу</h3>
        <p>${String(error?.message || error || "Неизвестная ошибка").replaceAll("<", "&lt;")}</p>
        <button class="btn" type="button" data-reload-page>${icon("refresh")} Обновить</button>
      </div>
    </div>
  </section>`;
}

function renderRoute() {
  renderToken += 1;
  const token = renderToken;
  const url = currentUrl();
  const path = normalizePath(url.pathname);

  if (typeof cleanup === "function") {
    try {
      cleanup();
    } catch (error) {
      console.warn("Не удалось корректно завершить страницу", error);
    }
  }
  cleanup = null;

  let matched = null;
  let params = [];
  for (const route of ROUTES) {
    const result = path.match(route.pattern);
    if (result) {
      matched = route;
      params = result.slice(1).map((value) => decodeURIComponent(value));
      break;
    }
  }

  main.innerHTML = '<div id="page" class="page-enter"></div>';
  const root = main.querySelector("#page");
  main.focus({ preventScroll: true });

  setActiveNav(matched?.nav || "");
  setTitle(matched ? matched.title : "Страница не найдена — Вектор");
  syncHeader(url.searchParams);

  if (!matched) {
    root.innerHTML = notFoundMarkup();
    root.querySelector("[data-reload-page]")?.addEventListener("click", () => window.location.reload());
    scrollToTop();
    return;
  }

  const ctx = {
    url,
    path,
    params,
    query: url.searchParams,
    navigate,
    openUpload: launchUpload,
    setTitle,
    setActiveNav,
    refreshHealth,
  };

  try {
    const result = matched.mount(root, ctx);
    if (typeof result === "function") cleanup = result;
    else if (result && typeof result.cleanup === "function") cleanup = result.cleanup;
  } catch (error) {
    console.error(error);
    root.innerHTML = errorMarkup(error);
    root.querySelector("[data-reload-page]")?.addEventListener("click", () => window.location.reload());
  }

  if (token !== renderToken) return;

  if (!url.hash || url.hash === "#main") {
    scrollToTop();
  } else {
    requestAnimationFrame(() => {
      const target = document.querySelector(url.hash);
      if (target) target.scrollIntoView({ block: "start" });
      else scrollToTop();
    });
  }
}

function navigate(target, { replace = false } = {}) {
  let url;
  try {
    url = new URL(target, window.location.origin);
  } catch {
    return;
  }
  if (url.origin !== window.location.origin) {
    window.location.href = url.href;
    return;
  }
  const state = { vector: true };
  if (replace) window.history.replaceState(state, "", url.href);
  else window.history.pushState(state, "", url.href);
  renderRoute();
}

function launchUpload(options = {}) {
  openUpload({
    navigate,
    ...options,
    onCreated: options.onCreated || ((lecture) => {
      navigate(`/lecture/${encodeURIComponent(lecture.id)}`);
    }),
  });
}

async function refreshHealth() {
  if (!modeChip || !modeLabel) return;
  try {
    const health = await api.health();
    const warnings = Array.isArray(health.warnings) ? health.warnings : [];
    const llm = Boolean(health.llm?.configured);
    const degraded = health.status !== "ok" || warnings.length > 0;
    modeChip.classList.toggle("offline", degraded);
    modeLabel.textContent = degraded
      ? "Требует внимания"
      : llm
        ? "Локально + LLM"
        : "Локальный режим";
    modeChip.title = degraded
      ? warnings.join("\n") || "Есть предупреждения — откройте диагностику."
      : llm
        ? "Расшифровка и индекс локально, конспекты и ответы — через подключённую LLM."
        : "Расшифровка, индекс и поиск выполняются локально, без внешних сервисов.";
    modeChip.dataset.state = degraded ? "warn" : "ok";
  } catch {
    modeChip.classList.add("offline");
    modeLabel.textContent = "Нет связи";
    modeChip.title = "Сервер «Вектор» не отвечает. Проверьте, что приложение запущено.";
    modeChip.dataset.state = "error";
  }
}

// ------------------------------------------------------------------ listeners
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-link]");
  if (!link) return;
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  const href = link.getAttribute("href");
  if (!href || href.startsWith("http") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
  if (href.startsWith("#")) return;
  event.preventDefault();
  navigate(href);
});

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  if (key === "k" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    globalInput?.focus();
    globalInput?.select();
  }
});

globalForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = globalInput.value.trim();
  if (!query) {
    globalInput.focus();
    return;
  }
  globalInput.blur();
  navigate(`/search?q=${encodeURIComponent(query)}`);
});

globalInput?.addEventListener("input", () => {
  globalForm.classList.toggle("has-value", Boolean(globalInput.value.trim()));
});

uploadButton?.addEventListener("click", () => launchUpload());

modeChip?.addEventListener("click", () => navigate("/diagnostics"));
modeChip?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    navigate("/diagnostics");
  }
});

window.addEventListener("popstate", () => renderRoute());

window.addEventListener("online", refreshHealth);
window.addEventListener("offline", () => {
  modeChip?.classList.add("offline");
  if (modeLabel) modeLabel.textContent = "Нет сети";
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshHealth();
});

// ------------------------------------------------------------------ boot
syncHeader(currentUrl().searchParams);
refreshHealth();
clearInterval(healthTimer);
healthTimer = setInterval(refreshHealth, 60000);

if (!window.history.state?.vector) {
  window.history.replaceState({ vector: true }, "", window.location.href);
}
renderRoute();
