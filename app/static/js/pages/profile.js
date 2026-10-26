import { api } from "../api.js";
import { avatarClass, initials, loadAuth, logout, setUser } from "../auth.js";
import { loadFacts, mountFacts } from "../facts.js";
import {
  escapeHtml,
  formatDate,
  formatDuration,
  formatNumber,
  icon,
  plural,
  statusInfo,
  toast,
} from "../utils.js";

const AVATARS = [
  ["lime", "Лайм"],
  ["sky", "Небо"],
  ["violet", "Фиалка"],
  ["amber", "Янтарь"],
  ["coral", "Коралл"],
  ["mint", "Мята"],
];

function skeleton() {
  return `
  <section class="section">
    <div class="container">
      <div class="skeleton" style="height:18px;width:160px;margin-bottom:22px"></div>
      <div class="skeleton" style="height:150px;border-radius:18px;margin-bottom:18px"></div>
      <div class="profile-stats">${Array.from({ length: 4 }, () => '<div class="skeleton" style="height:92px"></div>').join("")}</div>
    </div>
  </section>`;
}

function statMarkup(value, label, iconName) {
  return `
  <div class="profile-stat">
    <span class="profile-stat-icon">${icon(iconName)}</span>
    <strong>${formatNumber(value)}</strong>
    <span>${escapeHtml(label)}</span>
  </div>`;
}

function lectureCard(lecture) {
  const status = statusInfo(lecture.status);
  const summary = (lecture.summary || lecture.description || "").replace(/\s+/g, " ").trim();
  const preview = summary
    ? escapeHtml(summary.length > 120 ? `${summary.slice(0, 120)}…` : summary)
    : escapeHtml(lecture.stage || "Откройте лекцию, чтобы посмотреть детали.");
  return `
  <a class="lecture-card" href="/lecture/${encodeURIComponent(lecture.id)}" data-link>
    <div class="lecture-thumb">
      ${lecture.thumbnail_url
        ? `<img src="${lecture.thumbnail_url}" alt="" loading="lazy">`
        : `<div class="thumb-placeholder">${icon("file-video")}</div>`}
      ${lecture.status === "ready" ? `<span class="thumb-play">${icon("play")}</span>` : ""}
      ${lecture.duration ? `<span class="thumb-duration">${formatDuration(lecture.duration)}</span>` : ""}
    </div>
    <div class="lecture-card-body">
      <div class="chip-row">
        <span class="badge ${status.tone}"><span class="dot"></span>${status.label}</span>
        ${lecture.is_favorite ? `<span class="badge lime">${icon("bookmark")} в избранном</span>` : ""}
      </div>
      <h3>${escapeHtml(lecture.title || "Без названия")}</h3>
      <p>${preview}</p>
      <div class="lecture-card-meta">
        ${lecture.segments_count ? `<span class="meta-item">${icon("list")}${lecture.segments_count} ${plural(lecture.segments_count, ["фрагмент", "фрагмента", "фрагментов"])}</span>` : ""}
        <span class="meta-item">${icon("calendar")}${formatDate(lecture.created_at)}</span>
      </div>
    </div>
  </a>`;
}

export function mount(root, ctx) {
  let cancelled = false;
  let profileData = null;
  let tab = "favorites";
  let authMode = ctx.query.get("mode") === "register" ? "register" : "login";
  let selectedAvatar = "lime";
  let factsCleanup = null;

  ctx.setTitle("Профиль — Вектор");
  root.innerHTML = skeleton();

  function stopFacts() {
    if (typeof factsCleanup === "function") {
      factsCleanup();
      factsCleanup = null;
    }
  }

  function mountFact(selector, count = 6, interval = 12000) {
    const host = root.querySelector(selector);
    if (!host) return;
    loadFacts(count).then((items) => {
      if (cancelled || !host.isConnected) return;
      factsCleanup = mountFacts(host, items, { interval });
    });
  }

  function renderError(error) {
    stopFacts();
    root.innerHTML = `
    <section class="section">
      <div class="container">
        <div class="empty-state">
          <span class="empty-icon">${icon("alert")}</span>
          <h3>Не удалось открыть профиль</h3>
          <p>${escapeHtml(error?.message || "Сервер не отвечает.")}</p>
          <div class="chip-row" style="justify-content:center">
            <button class="btn btn-primary" type="button" data-profile-retry>${icon("refresh")} Повторить</button>
            <a class="btn" href="/" data-link>${icon("chevron-left")} В библиотеку</a>
          </div>
        </div>
      </div>
    </section>`;
    root.querySelector("[data-profile-retry]")?.addEventListener("click", () => {
      root.innerHTML = skeleton();
      loadProfile();
    });
  }

  // ------------------------------------------------------------- вход / регистрация
  function renderAuth() {
    stopFacts();
    profileData = null;
    root.innerHTML = `
    <section class="auth-page">
      <div class="container">
        <nav class="breadcrumb" aria-label="Хлебные крошки">
          <a href="/" data-link>Библиотека</a>
          <span class="sep">/</span>
          <span class="current">Профиль</span>
        </nav>
        <div class="auth-grid">
          <div class="auth-intro">
            <div class="eyebrow">Личный кабинет</div>
            <h1>Сохраняйте <span class="accent">моменты</span>,<br>которые хочется пересмотреть.</h1>
            <p class="hero-lead">
              Аккаунт «Вектора» — это избранное, история ваших загрузок и спокойный доступ
              к лекциям с любого устройства. Без соцсетей и лишних шагов.
            </p>
            <div class="auth-benefits">
              <div class="auth-benefit">
                <span>${icon("bookmark")}</span>
                <div><strong>Избранное</strong><p>Отмечайте лекции и возвращайтесь к ним в один клик.</p></div>
              </div>
              <div class="auth-benefit">
                <span>${icon("upload")}</span>
                <div><strong>Свои загрузки</strong><p>Профиль запоминает, какие лекции добавили именно вы.</p></div>
              </div>
              <div class="auth-benefit">
                <span>${icon("shield")}</span>
                <div><strong>Локально и приватно</strong><p>Пароль хранится в виде хеша, а медиа остаются на вашем сервере.</p></div>
              </div>
            </div>
            <div class="auth-quote">
              ${icon("quote")}
              <p>«Учиться — значит снова и снова возвращаться к тому, что уже почти понял».</p>
              <span>Правило интервального повторения</span>
            </div>
            <div class="fact-slot" data-auth-fact></div>
          </div>

          <section class="card auth-card" aria-labelledby="auth-title">
            <div class="auth-card-head">
              <div class="eyebrow" id="auth-title">Аккаунт</div>
              <h2 data-auth-heading>${authMode === "register" ? "Начнём с простого" : "С возвращением"}</h2>
              <p data-auth-hint>${authMode === "register"
                ? "Создайте аккаунт — это займёт меньше минуты."
                : "Войдите, чтобы открыть избранное и свои лекции."}</p>
            </div>
            <div class="auth-tabs" role="tablist" aria-label="Вход или регистрация">
              <button class="auth-tab${authMode === "login" ? " active" : ""}" type="button" role="tab"
                      aria-selected="${authMode === "login"}" data-auth-tab="login">Вход</button>
              <button class="auth-tab${authMode === "register" ? " active" : ""}" type="button" role="tab"
                      aria-selected="${authMode === "register"}" data-auth-tab="register">Регистрация</button>
            </div>
            <form class="auth-form" data-auth-form novalidate>
              <label class="auth-field${authMode === "register" ? "" : " hidden"}" data-register-only>
                <span class="field-label">Как вас зовут</span>
                <span class="auth-input-wrap">${icon("user")}<input class="input" id="auth-name" name="name" type="text"
                  maxlength="40" autocomplete="name" placeholder="Например, Анна"></span>
              </label>
              <label class="auth-field">
                <span class="field-label">Email</span>
                <span class="auth-input-wrap">${icon("mail")}<input class="input" id="auth-email" name="email" type="email"
                  maxlength="200" autocomplete="email" placeholder="name@example.com" required></span>
              </label>
              <label class="auth-field">
                <span class="field-label">Пароль</span>
                <span class="auth-input-wrap">${icon("lock")}<input class="input" id="auth-password" name="password" type="password"
                  minlength="8" maxlength="200" autocomplete="${authMode === "register" ? "new-password" : "current-password"}"
                  placeholder="Минимум 8 символов" required></span>
              </label>
              <div class="auth-error hidden" data-auth-error role="alert"></div>
              <button class="btn btn-primary btn-lg auth-submit" type="submit" data-auth-submit>
                ${authMode === "register" ? "Создать аккаунт" : "Войти"} ${icon("chevron-right")}
              </button>
            </form>
            <p class="auth-note">${icon("shield")} Мы не отправляем письма и не просим подтверждать email. Для демо-аккаунта достаточно адреса и пароля.</p>
          </section>
        </div>
      </div>
    </section>`;

    const form = root.querySelector("[data-auth-form]");
    const nameInput = root.querySelector("#auth-name");
    const emailInput = root.querySelector("#auth-email");
    const passwordInput = root.querySelector("#auth-password");
    const submit = root.querySelector("[data-auth-submit]");
    const errorBox = root.querySelector("[data-auth-error]");
    const heading = root.querySelector("[data-auth-heading]");
    const hint = root.querySelector("[data-auth-hint]");
    const registerOnly = root.querySelector("[data-register-only]");

    function setMode(mode) {
      authMode = mode;
      root.querySelectorAll("[data-auth-tab]").forEach((button) => {
        const active = button.dataset.authTab === mode;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
      });
      registerOnly.classList.toggle("hidden", mode !== "register");
      passwordInput.autocomplete = mode === "register" ? "new-password" : "current-password";
      submit.innerHTML = `${mode === "register" ? "Создать аккаунт" : "Войти"} ${icon("chevron-right")}`;
      heading.textContent = mode === "register" ? "Начнём с простого" : "С возвращением";
      hint.textContent = mode === "register"
        ? "Создайте аккаунт — это займёт меньше минуты."
        : "Войдите, чтобы открыть избранное и свои лекции.";
      errorBox.classList.add("hidden");
      requestAnimationFrame(() => (mode === "register" ? nameInput : emailInput)?.focus());
    }

    function showError(message) {
      errorBox.textContent = message;
      errorBox.classList.remove("hidden");
    }

    root.querySelectorAll("[data-auth-tab]").forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.authTab));
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const name = nameInput.value.trim();
      const email = emailInput.value.trim();
      const password = passwordInput.value;
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        showError("Введите корректный email, например name@example.com.");
        emailInput.focus();
        return;
      }
      if (authMode === "register" && !name) {
        showError("Напишите, как к вам обращаться.");
        nameInput.focus();
        return;
      }
      if (password.length < 8) {
        showError("Пароль должен содержать минимум 8 символов.");
        passwordInput.focus();
        return;
      }
      errorBox.classList.add("hidden");
      submit.disabled = true;
      submit.innerHTML = `<span class="spinner dark"></span> Подождите…`;
      try {
        const result = authMode === "register"
          ? await api.register({ name, email, password })
          : await api.login({ email, password });
        if (!result?.user) throw new Error("Сервер не вернул данные аккаунта.");
        setUser(result.user);
        toast(authMode === "register" ? "Аккаунт создан — добро пожаловать!" : "Вы вошли в аккаунт.", "success");
        await loadProfile();
      } catch (error) {
        if (cancelled) return;
        showError(error.message || "Не удалось выполнить вход.");
        submit.disabled = false;
        submit.innerHTML = `${authMode === "register" ? "Создать аккаунт" : "Войти"} ${icon("chevron-right")}`;
      }
    });

    mountFact("[data-auth-fact]");
    if (authMode === "register") requestAnimationFrame(() => nameInput?.focus());
    else requestAnimationFrame(() => emailInput?.focus());
  }

  // ------------------------------------------------------------------ профиль
  function emptyMarkup(kind) {
    if (kind === "favorites") {
      return `
      <div class="empty-state profile-empty">
        <span class="empty-icon">${icon("bookmark")}</span>
        <h3>В избранном пока пусто</h3>
        <p>Откройте любую лекцию и нажмите «В избранное» — она появится здесь.</p>
        <a class="btn" href="/" data-link>${icon("book")} Открыть библиотеку</a>
      </div>`;
    }
    return `
    <div class="empty-state profile-empty">
      <span class="empty-icon">${icon("upload")}</span>
      <h3>Вы ещё не загружали лекции</h3>
      <p>Добавьте файл или ссылку — лекция появится здесь и в общей библиотеке.</p>
      <button class="btn btn-primary" type="button" data-profile-upload>${icon("upload")} Загрузить лекцию</button>
    </div>`;
  }

  function renderProfileList() {
    const host = root.querySelector("[data-profile-list]");
    if (!host || !profileData) return;
    const items = tab === "favorites" ? profileData.favorites || [] : profileData.lectures || [];
    root.querySelectorAll("[data-profile-tab]").forEach((button) => {
      const active = button.dataset.profileTab === tab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    host.innerHTML = items.length
      ? `<div class="library-grid profile-grid">${items.map(lectureCard).join("")}</div>`
      : emptyMarkup(tab);
  }

  function renderDashboard() {
    stopFacts();
    const user = profileData.user;
    selectedAvatar = user.avatar || "lime";
    const stats = profileData.stats || {};
    const favorites = profileData.favorites || [];
    const lectures = profileData.lectures || [];
    const swatches = AVATARS.map(([value, label]) => `
      <button class="avatar-swatch ${avatarClass(value)}${value === selectedAvatar ? " selected" : ""}"
              type="button" data-avatar="${value}" aria-label="Цвет аватара: ${label}"
              aria-pressed="${value === selectedAvatar}" title="${label}"></button>`).join("");

    root.innerHTML = `
    <section class="profile-page">
      <div class="container">
        <nav class="breadcrumb" aria-label="Хлебные крошки">
          <a href="/" data-link>Библиотека</a>
          <span class="sep">/</span>
          <span class="current">Профиль</span>
        </nav>

        <header class="profile-hero card">
          <div class="profile-avatar ${avatarClass(user.avatar)}" data-profile-avatar>${escapeHtml(initials(user.name))}</div>
          <div class="profile-id">
            <div class="eyebrow">Профиль</div>
            <h1>${escapeHtml(user.name)}</h1>
            <div class="profile-meta-line">
              <span>${icon("mail")}${escapeHtml(user.email)}</span>
              <span>${icon("calendar")}с ${formatDate(user.created_at)}</span>
            </div>
            ${user.bio ? `<p class="profile-bio">${escapeHtml(user.bio)}</p>` : ""}
          </div>
          <div class="profile-hero-actions">
            <button class="btn btn-ghost" type="button" data-logout>${icon("logout")} Выйти</button>
          </div>
        </header>

        <div class="profile-stats">
          ${statMarkup(stats.favorites, "в избранном", "bookmark")}
          ${statMarkup(stats.uploads, "своих загрузок", "upload")}
          ${statMarkup(stats.views, "просмотров своих лекций", "gauge")}
          ${statMarkup(stats.hours, "часов своего видео", "clock")}
        </div>

        <div class="profile-layout">
          <div class="profile-main">
            <div class="profile-toolbar" role="tablist" aria-label="Материалы профиля">
              <button class="filter-tab${tab === "favorites" ? " active" : ""}" type="button" role="tab"
                      aria-selected="${tab === "favorites"}" data-profile-tab="favorites">
                ${icon("bookmark")} Избранное <span class="count">${favorites.length}</span>
              </button>
              <button class="filter-tab${tab === "lectures" ? " active" : ""}" type="button" role="tab"
                      aria-selected="${tab === "lectures"}" data-profile-tab="lectures">
                ${icon("upload")} Мои лекции <span class="count">${lectures.length}</span>
              </button>
            </div>
            <div class="profile-list" data-profile-list></div>
          </div>

          <aside class="profile-aside">
            <div class="card card-pad profile-settings">
              <div class="profile-settings-head">
                <h3>${icon("settings")} Настройки</h3>
                <p>Имя, описание и цвет аватара видны только в вашем профиле.</p>
              </div>
              <form data-settings-form>
                <label class="auth-field">
                  <span class="field-label">Имя</span>
                  <input class="input" name="name" maxlength="40" required value="${escapeHtml(user.name)}">
                </label>
                <label class="auth-field">
                  <span class="field-label">О себе <span class="muted">(необязательно)</span></span>
                  <textarea class="input textarea" name="bio" maxlength="180" rows="2"
                    placeholder="Что вы изучаете?">${escapeHtml(user.bio || "")}</textarea>
                </label>
                <div class="auth-field">
                  <span class="field-label">Цвет аватара</span>
                  <div class="avatar-palette">${swatches}</div>
                </div>
                <button class="btn btn-sm" type="submit">${icon("check")} Сохранить профиль</button>
              </form>

              <div class="profile-divider"></div>

              <form data-password-form>
                <h4>${icon("lock")} Сменить пароль</h4>
                <label class="auth-field">
                  <span class="field-label">Текущий пароль</span>
                  <input class="input" name="current_password" type="password" autocomplete="current-password" required>
                </label>
                <label class="auth-field">
                  <span class="field-label">Новый пароль</span>
                  <input class="input" name="new_password" type="password" minlength="8" autocomplete="new-password"
                    placeholder="Минимум 8 символов" required>
                </label>
                <button class="btn btn-sm btn-ghost" type="submit">Обновить пароль</button>
              </form>
            </div>

            <div class="profile-fact-card">
              <div class="eyebrow">${icon("lightbulb")} Пока вы здесь</div>
              <div class="fact-slot" data-profile-fact></div>
            </div>
          </aside>
        </div>
      </div>
    </section>`;

    const settingsForm = root.querySelector("[data-settings-form]");
    const passwordForm = root.querySelector("[data-password-form]");
    const avatarEl = root.querySelector("[data-profile-avatar]");

    root.querySelectorAll("[data-profile-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        tab = button.dataset.profileTab;
        renderProfileList();
      });
    });

    root.querySelector("[data-profile-list]").addEventListener("click", (event) => {
      if (event.target.closest("[data-profile-upload]")) ctx.openUpload();
    });

    root.querySelector("[data-logout]").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await logout();
        if (cancelled) return;
        toast("Вы вышли из аккаунта.", "success");
        renderAuth();
      } catch (error) {
        toast(error.message || "Не удалось выйти из аккаунта.", "error");
        button.disabled = false;
      }
    });

    root.querySelectorAll("[data-avatar]").forEach((button) => {
      button.addEventListener("click", () => {
        selectedAvatar = button.dataset.avatar;
        root.querySelectorAll("[data-avatar]").forEach((swatch) => {
          const active = swatch.dataset.avatar === selectedAvatar;
          swatch.classList.toggle("selected", active);
          swatch.setAttribute("aria-pressed", String(active));
        });
        if (avatarEl) avatarEl.className = `profile-avatar ${avatarClass(selectedAvatar)}`;
      });
    });

    settingsForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(settingsForm);
      const name = String(data.get("name") || "").trim();
      const bio = String(data.get("bio") || "").trim();
      if (!name) {
        toast("Имя не может быть пустым.", "error");
        return;
      }
      const submit = settingsForm.querySelector('button[type="submit"]');
      submit.disabled = true;
      try {
        const result = await api.updateProfile({ name, bio, avatar: selectedAvatar });
        if (cancelled) return;
        setUser(result.user);
        toast("Профиль обновлён.", "success");
        await loadProfile();
      } catch (error) {
        if (cancelled) return;
        toast(error.message || "Не удалось сохранить профиль.", "error");
        submit.disabled = false;
      }
    });

    passwordForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(passwordForm);
      const currentPassword = String(data.get("current_password") || "");
      const newPassword = String(data.get("new_password") || "");
      if (newPassword.length < 8) {
        toast("Новый пароль должен содержать минимум 8 символов.", "error");
        return;
      }
      const submit = passwordForm.querySelector('button[type="submit"]');
      submit.disabled = true;
      try {
        const result = await api.changePassword({
          current_password: currentPassword,
          new_password: newPassword,
        });
        if (cancelled) return;
        toast(result.message || "Пароль обновлён.", "success");
        passwordForm.reset();
      } catch (error) {
        if (cancelled) return;
        toast(error.message || "Не удалось изменить пароль.", "error");
      } finally {
        submit.disabled = false;
      }
    });

    renderProfileList();
    mountFact("[data-profile-fact]", 6, 12000);
  }

  async function loadProfile() {
    try {
      const data = await api.profile();
      if (cancelled) return;
      profileData = data;
      if (data.user) setUser(data.user);
      renderDashboard();
    } catch (error) {
      if (cancelled) return;
      if (error.status === 401) {
        setUser(null);
        renderAuth();
        return;
      }
      renderError(error);
    }
  }

  async function boot() {
    const user = await loadAuth();
    if (cancelled) return;
    if (!user) {
      renderAuth();
      return;
    }
    await loadProfile();
  }

  boot();

  return () => {
    cancelled = true;
    stopFacts();
  };
}
