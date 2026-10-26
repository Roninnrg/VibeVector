import { api } from "./api.js";
import { escapeHtml, icon } from "./utils.js";

/** Резервные факты на случай, если API недоступен. */
export const FALLBACK_FACTS = [
  {
    id: "fallback-ebbinghaus",
    category: "Память",
    text: "Без повторения за первые сутки забывается большая часть нового материала. Короткое возвращение к конспекту через день часто полезнее, чем час зубрёжки сразу после лекции.",
    source: "Кривая забывания, Г. Эббингауз",
  },
  {
    id: "fallback-testing",
    category: "Обучение",
    text: "Попытка вспомнить материал без подсказки укрепляет память сильнее, чем повторное чтение. Поэтому вопросы к лекции — не проверка, а часть обучения.",
    source: "Roediger & Karpicke, 2006",
  },
  {
    id: "fallback-embeddings",
    category: "AI",
    text: "Смысловой поиск сравнивает не слова, а векторы. Поэтому запрос «как сеть учится» может найти фрагмент про градиентный спуск, даже если слово «учится» там не встречается.",
    source: "Векторные представления текста",
  },
  {
    id: "fallback-whisper",
    category: "Речь",
    text: "Whisper обучали примерно на 680 тысячах часов многоязычной речи. Поэтому одна модель умеет распознавать десятки языков, включая смешанную речь.",
    source: "OpenAI, 2022",
  },
  {
    id: "fallback-textrank",
    category: "AI",
    text: "TextRank собирает конспект без нейросети: он строит граф связей между предложениями и выбирает самые «центральные» из них. Быстро, локально и без интернета.",
    source: "Mihalcea & Tarau, 2004",
  },
  {
    id: "fallback-lemma",
    category: "Речь",
    text: "Лемматизация приводит слова к начальной форме: «лекции», «лекцией» и «лекциям» становятся одним словом. Это помогает поиску не зависеть от падежей.",
    source: "Компьютерная лингвистика",
  },
  {
    id: "fallback-sleep",
    category: "Память",
    text: "Во сне мозг продолжает обрабатывать впечатления дня. Достаточный сон после учёбы помогает закрепить новые связи между фактами.",
    source: "Исследования консолидации памяти",
  },
  {
    id: "fallback-timecode",
    category: "Вектор",
    text: "Таймкод — это не просто метка. Он превращает текст лекции в навигацию: можно открыть плеер ровно там, где прозвучала нужная мысль.",
    source: "Как работает «Вектор»",
  },
];

export async function loadFacts(limit = 8) {
  try {
    const data = await api.facts(limit);
    if (Array.isArray(data?.items) && data.items.length) return data.items;
  } catch {
    /* показываем локальный набор */
  }
  return FALLBACK_FACTS.slice(0, Math.max(1, Math.min(limit, FALLBACK_FACTS.length)));
}

function factMarkup(item, index, total) {
  return `
  <div class="fact-card" data-fact-card>
    <div class="fact-head">
      <span class="fact-kicker">${icon("lightbulb")} ${escapeHtml(item.category || "Интересный факт")}</span>
      <span class="fact-index">${index + 1} / ${total}</span>
    </div>
    <p class="fact-text">${escapeHtml(item.text)}</p>
    <div class="fact-foot">
      <span class="fact-source">${escapeHtml(item.source || "«Вектор»")}</span>
      ${total > 1 ? `<button class="fact-next" type="button" data-fact-next aria-label="Показать следующий факт">
        Ещё факт ${icon("chevron-right")}
      </button>` : ""}
    </div>
  </div>`;
}

/**
 * Показывает карточку факта и переключает факты по таймеру.
 * Возвращает функцию остановки — её нужно вызвать при закрытии модалки или смене страницы.
 */
export function mountFacts(host, items, { interval = 9000 } = {}) {
  if (!host || !Array.isArray(items) || !items.length) return () => {};
  let index = Math.floor(Math.random() * items.length);
  let timer = null;

  function render() {
    host.innerHTML = factMarkup(items[index], index, items.length);
  }

  function advance(step = 1) {
    index = (index + step + items.length) % items.length;
    render();
    startTimer();
  }

  function startTimer() {
    clearInterval(timer);
    if (items.length < 2 || interval <= 0) return;
    timer = setInterval(() => advance(1), interval);
  }

  function onClick(event) {
    if (event.target.closest("[data-fact-next]")) {
      event.preventDefault();
      advance(1);
    }
  }

  function onVisibility() {
    if (document.hidden) clearInterval(timer);
    else startTimer();
  }

  host.addEventListener("click", onClick);
  document.addEventListener("visibilitychange", onVisibility);
  render();
  startTimer();

  return () => {
    clearInterval(timer);
    host.removeEventListener("click", onClick);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
