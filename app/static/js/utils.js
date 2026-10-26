export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function icon(name, className = "") {
  const extra = className ? ` ${className}` : "";
  return `<svg class="icon${extra}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

export function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

export function formatTime(seconds, forceHours = false) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return forceHours ? "00:00:00" : "00:00";
  const total = Math.floor(value);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (number) => String(number).padStart(2, "0");
  if (hours > 0 || forceHours) return `${hours}:${pad(minutes)}:${pad(secs)}`;
  return `${pad(minutes)}:${pad(secs)}`;
}

export function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "—";
  const total = Math.round(value);
  const hours = Math.floor(total / 3600);
  const minutes = Math.round((total % 3600) / 60);
  if (hours > 0) return minutes ? `${hours} ч ${minutes} мин` : `${hours} ч`;
  if (minutes > 0) return `${minutes} мин`;
  return `${total} с`;
}

export function formatClockText(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "—";
  const hours = value / 3600;
  if (hours >= 1) return `${hours.toFixed(1).replace(".", ",")} ч`;
  const minutes = Math.max(1, Math.round(value / 60));
  return `${minutes} мин`;
}

const MONTHS = [
  "янв", "фев", "мар", "апр", "мая", "июн",
  "июл", "авг", "сен", "окт", "ноя", "дек",
];

export function formatDate(iso, withTime = false) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const base = `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
  if (!withTime) return base;
  return `${base}, ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value) || 0);
}

export function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  const size = value / 1024 ** index;
  return `${size >= 10 || index === 0 ? Math.round(size) : size.toFixed(1).replace(".", ",")} ${units[index]}`;
}

export function plural(count, forms) {
  const value = Math.abs(Number(count)) % 100;
  const last = value % 10;
  if (value > 10 && value < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

export function debounce(fn, delay = 220) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

export function statusInfo(status) {
  switch (status) {
    case "ready":
      return { label: "Готово", tone: "lime" };
    case "processing":
      return { label: "Обработка", tone: "amber" };
    case "queued":
      return { label: "В очереди", tone: "" };
    case "failed":
      return { label: "Ошибка", tone: "red" };
    default:
      return { label: status || "Неизвестно", tone: "" };
  }
}

export function markText(text, query) {
  const safe = escapeHtml(text);
  const terms = String(query || "")
    .split(/\s+/)
    .map((term) => term.trim())
    .filter((term) => term.length >= 2)
    .sort((a, b) => b.length - a.length);
  if (!terms.length) return safe;
  const expression = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "giu");
  return safe.replace(expression, "<mark>$1</mark>");
}

export function localGet(key, fallback = null) {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value;
  } catch {
    return fallback;
  }
}

export function localSet(key, value) {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    /* хранилище недоступно — не критично */
  }
}

export function localRemove(key) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export async function copyText(text, message = "Скопировано") {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  toast(message, "success");
}

export function toast(message, type = "info", timeout = 3800) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  const iconName = type === "error" ? "alert" : type === "success" ? "check" : "info";
  node.innerHTML = `${icon(iconName)}<span>${escapeHtml(message)}</span>`;
  root.append(node);
  const remove = () => {
    node.classList.add("leaving");
    setTimeout(() => node.remove(), 220);
  };
  setTimeout(remove, timeout);
  node.addEventListener("click", remove, { once: true });
}

export function setMeta(name, content) {
  let element = document.querySelector(`meta[name="${name}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.name = name;
    document.head.append(element);
  }
  element.content = content;
}

export function scrollToTop() {
  window.scrollTo({ top: 0, left: 0, behavior: "instant" });
}
