import { api } from "./api.js";
import { escapeHtml, formatBytes, icon, toast } from "./utils.js";

const LANGUAGES = [
  ["auto", "Определить автоматически"],
  ["ru", "Русский"],
  ["en", "English"],
  ["kk", "Қазақша"],
  ["de", "Deutsch"],
  ["fr", "Français"],
  ["es", "Español"],
];

const EXTENSIONS = [
  ".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi",
  ".mp3", ".m4a", ".wav", ".ogg", ".opus",
];

function languageOptions() {
  return LANGUAGES.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
}

export function openUpload({ navigate, onCreated } = {}) {
  const root = document.getElementById("modal-root");
  if (!root || root.querySelector(".modal-backdrop")) return null;

  const previousFocus = document.activeElement;
  let activeTab = "file";
  let selectedFile = null;
  let uploading = false;

  root.innerHTML = `
  <div class="modal-backdrop" data-backdrop>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="upload-modal-title" tabindex="-1">
      <div class="modal-head">
        <div>
          <h2 id="upload-modal-title">Добавить лекцию</h2>
          <p>Загрузите файл или вставьте ссылку — «Вектор» сделает всё остальное.</p>
        </div>
        <button class="modal-close" type="button" data-close aria-label="Закрыть">
          ${icon("x")}
        </button>
      </div>
      <div class="modal-body">
        <div class="modal-tabs" role="tablist" aria-label="Способ добавления">
          <button class="modal-tab active" type="button" role="tab" aria-selected="true" data-tab="file">Файл</button>
          <button class="modal-tab" type="button" role="tab" aria-selected="false" data-tab="link">Ссылка</button>
        </div>

        <form data-panel="file" novalidate>
          <label class="dropzone" data-drop tabindex="0" role="button" aria-label="Выбрать файл лекции">
            <span class="up-icon">${icon("upload")}</span>
            <strong>Перетащите видео сюда</strong>
            <span>или нажмите, чтобы выбрать файл</span>
            <span class="formats">MP4 · WEBM · MOV · MKV · MP3 · M4A · WAV</span>
          </label>
          <input type="file" data-file-input accept="video/*,audio/*,.mkv,.m4v,.avi,.ogg,.opus" hidden>
          <div data-picked></div>
          <div class="form-grid">
            <div>
              <label class="field-label" for="upload-title">Название</label>
              <input class="input" id="upload-title" name="title" maxlength="240" placeholder="Например, «Производная и её смысл»">
            </div>
            <div>
              <label class="field-label" for="upload-language">Язык речи</label>
              <select class="select" id="upload-language" name="language">${languageOptions()}</select>
            </div>
          </div>
          <div class="upload-progress" data-progress>
            <div class="line"><span>Загрузка на сервер</span><span data-pct>0%</span></div>
            <div class="progress-track"><div class="progress-fill" data-fill style="width:0"></div></div>
          </div>
          <div class="upload-error hidden" data-error role="alert"></div>
          <div class="modal-actions">
            <button class="btn" type="button" data-cancel>Отмена</button>
            <button class="btn btn-primary" type="submit" data-submit disabled>
              ${icon("upload")} Загрузить и обработать
            </button>
          </div>
        </form>

        <form data-panel="link" class="hidden" novalidate>
          <div>
            <label class="field-label" for="import-url">Ссылка на видео</label>
            <input class="input" id="import-url" name="url" type="url" maxlength="2000"
                   placeholder="https://www.youtube.com/watch?v=… или https://vk.com/video…" autocomplete="off">
          </div>
          <div class="form-grid">
            <div>
              <label class="field-label" for="import-title">Название <span class="muted">(необязательно)</span></label>
              <input class="input" id="import-title" name="title" maxlength="240" placeholder="Извлечётся из видео">
            </div>
            <div>
              <label class="field-label" for="import-language">Язык речи</label>
              <select class="select" id="import-language" name="language">${languageOptions()}</select>
            </div>
          </div>
          <p class="import-note">
            <strong>Как это работает.</strong> Сервер скачает видео через yt-dlp, извлечёт аудио и запустит
            распознавание. Поддерживаются YouTube, Vimeo, VK Видео, Rutube, Dailymotion и прямые ссылки
            на MP4/WebM. Нужен доступ в интернет; файл сохраняется локально.
          </p>
          <div class="upload-progress" data-progress>
            <div class="line"><span>Добавляем в очередь</span><span>…</span></div>
            <div class="progress-track"><div class="progress-fill" data-fill style="width:35%"></div></div>
          </div>
          <div class="upload-error hidden" data-error role="alert"></div>
          <div class="modal-actions">
            <button class="btn" type="button" data-cancel>Отмена</button>
            <button class="btn btn-primary" type="submit" data-submit>
              ${icon("youtube")} Импортировать
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>`;

  const backdrop = root.querySelector("[data-backdrop]");
  const modal = root.querySelector(".modal");
  const tabs = Array.from(root.querySelectorAll("[data-tab]"));
  const panels = Array.from(root.querySelectorAll("[data-panel]"));
  const fileForm = root.querySelector('[data-panel="file"]');
  const linkForm = root.querySelector('[data-panel="link"]');
  const fileInput = root.querySelector("[data-file-input]");
  const dropzone = root.querySelector("[data-drop]");
  const picked = root.querySelector("[data-picked]");
  const titleInput = root.querySelector("#upload-title");
  const fileSubmit = fileForm.querySelector("[data-submit]");
  const fileError = fileForm.querySelector("[data-error]");
  const fileProgress = fileForm.querySelector("[data-progress]");
  const fileFill = fileForm.querySelector("[data-fill]");
  const filePct = fileForm.querySelector("[data-pct]");
  const linkSubmit = linkForm.querySelector("[data-submit]");

  function setTab(tab) {
    activeTab = tab;
    tabs.forEach((button) => {
      const active = button.dataset.tab === tab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    panels.forEach((panel) => panel.classList.toggle("hidden", panel.dataset.panel !== tab));
    if (tab === "link") {
      requestAnimationFrame(() => root.querySelector("#import-url")?.focus());
    } else {
      dropzone.focus();
    }
  }

  function showError(form, message) {
    const box = form.querySelector("[data-error]");
    if (!box) return;
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function hideError(form) {
    const box = form.querySelector("[data-error]");
    if (box) box.classList.add("hidden");
  }

  function chooseFile(file) {
    if (!file) return;
    const name = file.name || "lecture";
    const extension = name.slice(name.lastIndexOf(".")).toLowerCase();
    const looksLikeMedia = file.type.startsWith("video/") || file.type.startsWith("audio/") || EXTENSIONS.includes(extension);
    if (!looksLikeMedia) {
      showError(fileForm, "Поддерживаются видео и аудио: MP4, WebM, MOV, MKV, MP3, M4A или WAV.");
      return;
    }
    selectedFile = file;
    hideError(fileForm);
    dropzone.classList.add("hidden");
    picked.innerHTML = `
      <div class="file-picked">
        ${icon("file-video")}
        <span class="name">${escapeHtml(name)}</span>
        <span class="size">${formatBytes(file.size)}</span>
        <button class="btn btn-ghost btn-sm" type="button" data-replace>Заменить</button>
      </div>`;
    picked.querySelector("[data-replace]").addEventListener("click", () => {
      selectedFile = null;
      dropzone.classList.remove("hidden");
      picked.innerHTML = "";
      fileSubmit.disabled = true;
      fileInput.click();
    });
    if (!titleInput.value.trim()) {
      titleInput.value = name.replace(/\.[^.]+$/, "").replaceAll("_", " ").slice(0, 240);
    }
    fileSubmit.disabled = false;
  }

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener("change", () => chooseFile(fileInput.files?.[0]));

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("drag");
    });
  });
  dropzone.addEventListener("drop", (event) => chooseFile(event.dataTransfer?.files?.[0]));

  tabs.forEach((button) => button.addEventListener("click", () => setTab(button.dataset.tab)));

  function setBusy(form, busy) {
    uploading = busy;
    const submit = form.querySelector("[data-submit]");
    const cancel = form.querySelector("[data-cancel]");
    const close = root.querySelector("[data-close]");
    submit.disabled = busy;
    cancel.disabled = busy;
    close.disabled = busy;
    submit.innerHTML = busy ? `<span class="spinner dark"></span> Обрабатываем…` : submit.dataset.label;
  }

  [fileSubmit, linkSubmit].forEach((button) => {
    button.dataset.label = button.innerHTML;
  });

  fileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (uploading) return;
    if (!selectedFile) {
      showError(fileForm, "Сначала выберите файл лекции.");
      return;
    }
    hideError(fileForm);
    fileProgress.classList.add("visible");
    fileFill.style.width = "0%";
    filePct.textContent = "0%";
    fileSubmit.disabled = true;
    setBusy(fileForm, true);
    const title = fileForm.querySelector('[name="title"]').value.trim();
    const language = fileForm.querySelector('[name="language"]').value;
    try {
      const lecture = await api.upload(selectedFile, {
        title,
        language,
        onProgress: (percent) => {
          const shown = Math.max(1, Math.min(99, percent));
          fileFill.style.width = `${shown}%`;
          filePct.textContent = `${shown}%`;
        },
      });
      fileFill.style.width = "100%";
      filePct.textContent = "100%";
      close(true);
      toast("Лекция загружена — начинаем обработку.", "success");
      if (typeof onCreated === "function") onCreated(lecture);
      else navigate(`/lecture/${lecture.id}`);
    } catch (error) {
      fileProgress.classList.remove("visible");
      showError(fileForm, error.message || "Не удалось загрузить файл.");
      fileSubmit.disabled = false;
      setBusy(fileForm, false);
    }
  });

  linkForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (uploading) return;
    hideError(linkForm);
    const url = linkForm.querySelector('[name="url"]').value.trim();
    const title = linkForm.querySelector('[name="title"]').value.trim();
    const language = linkForm.querySelector('[name="language"]').value;
    if (!/^https?:\/\//i.test(url)) {
      showError(linkForm, "Вставьте полную ссылку, начинающуюся с http:// или https://.");
      return;
    }
    setBusy(linkForm, true);
    linkForm.querySelector("[data-progress]").classList.add("visible");
    try {
      const lecture = await api.importUrl({ url, title, language });
      close(true);
      toast("Ссылка добавлена — видео скачается и обработается.", "success");
      if (typeof onCreated === "function") onCreated(lecture);
      else navigate(`/lecture/${lecture.id}`);
    } catch (error) {
      linkForm.querySelector("[data-progress]").classList.remove("visible");
      showError(linkForm, error.message || "Не удалось импортировать видео.");
      setBusy(linkForm, false);
    }
  });

  function close(force = false) {
    if (uploading && !force) {
      toast("Дождитесь завершения загрузки.", "info");
      return;
    }
    document.removeEventListener("keydown", onKeyDown, true);
    root.innerHTML = "";
    if (previousFocus instanceof HTMLElement) previousFocus.focus();
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      modal.querySelectorAll('button:not([disabled]), input:not([disabled]):not([type="hidden"]), select, textarea, [tabindex="0"]'),
    ).filter((element) => !element.classList.contains("hidden") && element.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  root.querySelectorAll("[data-cancel]").forEach((button) => button.addEventListener("click", () => close()));
  root.querySelector("[data-close]").addEventListener("click", () => close());
  backdrop.addEventListener("mousedown", (event) => {
    if (event.target === backdrop) close();
  });
  document.addEventListener("keydown", onKeyDown, true);

  requestAnimationFrame(() => dropzone.focus());
  return { close, isOpen: () => Boolean(root.querySelector(".modal-backdrop")), activeTab: () => activeTab };
}
