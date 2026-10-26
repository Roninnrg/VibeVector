import { escapeHtml, formatTime, icon, localGet, localSet } from "./utils.js";

const RATES = [1, 1.25, 1.5, 1.75, 2, 0.75];

export function playerMarkup({ poster = "", chapters = [] } = {}) {
  return `
  <div class="player-shell paused" data-player>
    <div class="player-stage" data-stage>
      <video data-video playsinline preload="metadata"${poster ? ` poster="${escapeHtml(poster)}"` : ""}></video>
      <div class="player-center">
        <button class="player-big-btn" type="button" data-action="toggle" aria-label="Смотреть">
          ${icon("play")}
        </button>
      </div>
      <div class="subtitle-overlay hidden" data-subtitles><span data-subtitle-text></span></div>
      <div class="player-controls">
        <div class="timeline-wrap" data-timeline role="slider" tabindex="0"
             aria-label="Позиция воспроизведения" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0">
          <div class="timeline">
            <div class="timeline-buffer" data-buffer></div>
            <div class="timeline-progress" data-progress></div>
            <div class="timeline-thumb" data-thumb></div>
          </div>
          <div class="timeline-tooltip" data-tooltip>00:00</div>
        </div>
        <div class="controls-row">
          <button class="pc-btn play" type="button" data-action="toggle" aria-label="Воспроизвести">
            ${icon("play")}
          </button>
          <button class="pc-btn" type="button" data-action="back" aria-label="Назад на 10 секунд" title="Назад на 10 секунд (J)">
            ${icon("back-10")}
          </button>
          <button class="pc-btn" type="button" data-action="forward" aria-label="Вперёд на 10 секунд" title="Вперёд на 10 секунд (L)">
            ${icon("forward-10")}
          </button>
          <span class="pc-time"><span data-current>00:00</span> <span class="dim">/</span> <span data-duration>00:00</span></span>
          <span class="pc-spacer"></span>
          <button class="pc-btn pc-speed" type="button" data-action="speed" aria-label="Скорость воспроизведения" title="Скорость">1×</button>
          <button class="pc-btn" type="button" data-action="captions" aria-label="Субтитры" title="Субтитры (C)">
            ${icon("subtitles")}
          </button>
          <div class="volume-wrap">
            <button class="pc-btn" type="button" data-action="mute" aria-label="Звук" title="Звук (M)">
              ${icon("volume")}
            </button>
            <input class="volume-slider" data-volume type="range" min="0" max="1" step="0.01"
                   value="0.9" aria-label="Громкость">
          </div>
          <button class="pc-btn" type="button" data-action="fullscreen" aria-label="Во весь экран" title="Во весь экран (F)">
            ${icon("maximize")}
          </button>
        </div>
      </div>
    </div>
    <div class="player-meta-bar">
      <span class="left">${icon("subtitles")} Субтитры синхронизированы с расшифровкой</span>
      <span class="right">
        <button class="resume-btn hidden" type="button" data-action="resume">${icon("clock")} Продолжить просмотр</button>
      </span>
    </div>
  </div>`;
}

export class VectorPlayer {
  constructor(root, options = {}) {
    this.root = root;
    this.options = options;
    this.video = root.querySelector("[data-video]");
    this.stage = root.querySelector("[data-stage]");
    this.timeline = root.querySelector("[data-timeline]");
    this.progress = root.querySelector("[data-progress]");
    this.buffer = root.querySelector("[data-buffer]");
    this.thumb = root.querySelector("[data-thumb]");
    this.tooltip = root.querySelector("[data-tooltip]");
    this.subtitles = root.querySelector("[data-subtitles]");
    this.subtitleText = root.querySelector("[data-subtitle-text]");
    this.currentLabel = root.querySelector("[data-current]");
    this.durationLabel = root.querySelector("[data-duration]");
    this.captionsButton = root.querySelector('[data-action="captions"]');
    this.volumeButton = root.querySelector('[data-action="mute"]');
    this.volumeSlider = root.querySelector("[data-volume]");
    this.speedButton = root.querySelector('[data-action="speed"]');
    this.resumeButton = root.querySelector('[data-action="resume"]');
    this.toggleButtons = root.querySelectorAll('[data-action="toggle"]');

    this.cues = Array.isArray(options.cues) ? options.cues : [];
    this.chapters = Array.isArray(options.chapters) ? options.chapters : [];
    this.lectureId = options.lectureId || "lecture";
    this.captionsEnabled = localGet("vector:captions", "on") !== "off";
    this.cueIndex = -1;
    this.chapterIndex = -1;
    this.dragging = false;
    this.idleTimer = null;
    this.lastSaved = 0;
    this.destroyed = false;
    this.pending = null;
    this.savedPosition = Number(localGet(`vector:pos:${this.lectureId}`, 0)) || 0;
    this.handlers = [];

    this.video.src = options.src;
    if (options.title) this.video.setAttribute("aria-label", options.title);
    this.video.volume = Math.min(1, Math.max(0, Number(localGet("vector:volume", 0.9)) || 0.9));
    if (localGet("vector:muted", "0") === "1") this.video.muted = true;
    this.volumeSlider.value = String(this.video.muted ? 0 : this.video.volume);

    this.renderMarks();
    this.bind();
    this.syncCaptionsButton();
    this.syncVolumeButton();
    this.syncSpeed();
    this.root.classList.add("paused");

    if (options.startAt != null && Number.isFinite(Number(options.startAt))) {
      this.seekTo(Number(options.startAt), Boolean(options.autoplayStart));
    }
  }

  bind() {
    const add = (target, event, handler, options) => {
      target.addEventListener(event, handler, options);
      this.handlers.push(() => target.removeEventListener(event, handler, options));
    };

    add(this.video, "click", () => this.toggle());
    add(this.video, "play", () => {
      this.root.classList.add("playing");
      this.root.classList.remove("paused");
      this.setToggleIcon(true);
      this.wake();
    });
    add(this.video, "pause", () => {
      this.root.classList.remove("playing");
      this.root.classList.add("paused");
      this.setToggleIcon(false);
      this.root.classList.remove("idle");
      clearTimeout(this.idleTimer);
      this.savePosition();
    });
    add(this.video, "ended", () => {
      this.root.classList.remove("playing");
      this.root.classList.add("paused");
      this.root.classList.remove("idle");
      this.setToggleIcon(false);
      this.savePosition(true);
    });
    add(this.video, "loadedmetadata", () => {
      const duration = this.duration;
      this.timeline.setAttribute("aria-valuemax", String(Math.round(duration)));
      this.durationLabel.textContent = formatTime(duration);
      if (this.pending) {
        const pending = this.pending;
        this.pending = null;
        this.video.currentTime = Math.min(Math.max(0, pending.time), Math.max(0, duration - 0.2));
        if (pending.play) this.play();
      }
      if (this.options.startAt == null) this.offerResume();
      else this.resumeButton?.classList.add("hidden");
      if (this.options.title && "mediaSession" in navigator) {
        try {
          navigator.mediaSession.metadata = new MediaMetadata({
            title: this.options.title,
            artist: "Вектор",
            album: "Видеолекции",
          });
        } catch {
          /* ignore */
        }
      }
    });
    add(this.video, "timeupdate", () => this.onTime());
    add(this.video, "progress", () => this.updateBuffer());
    add(this.video, "error", () => {
      if (this.destroyed) return;
      if (typeof this.options.onError === "function") {
        this.options.onError("Не удалось загрузить видео. Проверьте, что медиафайл доступен.");
      }
    });
    add(this.video, "volumechange", () => {
      this.volumeSlider.value = String(this.video.muted ? 0 : this.video.volume);
      this.syncVolumeButton();
      localSet("vector:volume", this.video.volume);
      localSet("vector:muted", this.video.muted ? "1" : "0");
    });

    add(this.timeline, "pointerdown", (event) => {
      if (!this.duration) return;
      event.preventDefault();
      this.dragging = true;
      this.timeline.setPointerCapture(event.pointerId);
      this.seekFromPointer(event);
    });
    add(this.timeline, "pointermove", (event) => {
      this.updateTooltip(event);
      if (this.dragging) this.seekFromPointer(event);
    });
    add(this.timeline, "pointerup", (event) => {
      this.dragging = false;
      if (this.timeline.hasPointerCapture(event.pointerId)) {
        this.timeline.releasePointerCapture(event.pointerId);
      }
    });
    add(this.timeline, "pointercancel", () => { this.dragging = false; });
    add(this.timeline, "keydown", (event) => {
      if (!this.duration) return;
      const step = event.shiftKey ? 10 : 5;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        event.stopPropagation();
        this.seekBy(-step);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        event.stopPropagation();
        this.seekBy(step);
      } else if (event.key === "Home") {
        event.preventDefault();
        this.seekTo(0);
      } else if (event.key === "End") {
        event.preventDefault();
        this.seekTo(this.duration - 0.1);
      }
    });
    add(this.timeline, "pointerleave", () => {
      if (!this.dragging) this.tooltip.style.opacity = "0";
    });

    this.root.addEventListener("click", this.onClick = (event) => {
      const button = event.target.closest("[data-action]");
      if (!button || !this.root.contains(button)) return;
      const action = button.dataset.action;
      if (action === "toggle") this.toggle();
      else if (action === "back") this.seekBy(-10);
      else if (action === "forward") this.seekBy(10);
      else if (action === "speed") this.cycleSpeed();
      else if (action === "captions") this.toggleCaptions();
      else if (action === "mute") this.toggleMute();
      else if (action === "fullscreen") this.toggleFullscreen();
      else if (action === "resume") this.resume();
    });
    this.handlers.push(() => this.root.removeEventListener("click", this.onClick));

    add(this.volumeSlider, "input", () => {
      this.video.muted = false;
      this.video.volume = Number(this.volumeSlider.value);
    });
    add(this.stage, "dblclick", (event) => {
      if (event.target.closest("button, input")) return;
      this.toggleFullscreen();
    });
    add(this.stage, "mousemove", () => this.wake());
    add(this.stage, "touchstart", () => this.wake(), { passive: true });
    add(this.stage, "mouseleave", () => {
      if (!this.video.paused) this.root.classList.add("idle");
    });
    add(document, "fullscreenchange", () => {
      const active = document.fullscreenElement === this.stage;
      const button = this.root.querySelector('[data-action="fullscreen"]');
      if (button) button.innerHTML = icon(active ? "minimize" : "maximize");
    });
    add(document, "keydown", this.onKeyDown = (event) => this.handleKey(event));
    add(window, "beforeunload", () => this.savePosition());
  }

  get duration() {
    return Number(this.video.duration) || 0;
  }

  get currentTime() {
    return Number(this.video.currentTime) || 0;
  }

  renderMarks() {
    const timeline = this.root.querySelector(".timeline");
    if (!timeline) return;
    const max = Number(this.options.duration) || 0;
    const duration = max || this.duration;
    if (duration > 0) {
      this.chapters.forEach((chapter) => {
        if (!chapter.start || chapter.start <= 0) return;
        const mark = document.createElement("span");
        mark.className = "timeline-mark chapter";
        mark.style.left = `${Math.min(100, (chapter.start / duration) * 100)}%`;
        mark.title = chapter.title || "";
        timeline.append(mark);
      });
      if (this.options.hitStart != null && this.options.hitStart > 0) {
        const mark = document.createElement("span");
        mark.className = "timeline-mark hit";
        mark.style.left = `${Math.min(100, (this.options.hitStart / duration) * 100)}%`;
        mark.title = "Найденный фрагмент";
        timeline.append(mark);
      }
    }
  }

  setToggleIcon(playing) {
    this.toggleButtons.forEach((button) => {
      button.innerHTML = icon(playing ? "pause" : "play");
      button.setAttribute("aria-label", playing ? "Пауза" : "Воспроизвести");
    });
  }

  play() {
    const promise = this.video.play();
    if (promise && typeof promise.catch === "function") {
      promise.catch(() => {
        if (typeof this.options.onError === "function") {
          this.options.onError("Браузер заблокировал автовоспроизведение. Нажмите Play.");
        }
      });
    }
  }

  pause() {
    this.video.pause();
  }

  toggle() {
    if (this.video.paused) this.play();
    else this.pause();
  }

  seekBy(seconds) {
    if (!this.duration) return;
    this.seekTo(this.currentTime + seconds);
  }

  seekTo(seconds, autoplay = false) {
    const requested = Math.max(0, Number(seconds) || 0);
    if (this.video.readyState === 0) {
      this.pending = { time: requested, play: autoplay };
      return;
    }
    const target = Math.min(requested, Math.max(0, this.duration - 0.1));
    this.video.currentTime = target;
    this.updateProgress();
    if (autoplay) this.play();
  }

  seekFromPointer(event) {
    const rect = this.timeline.getBoundingClientRect();
    if (!rect.width) return;
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    this.video.currentTime = ratio * this.duration;
    this.updateProgress();
  }

  updateTooltip(event) {
    const rect = this.timeline.getBoundingClientRect();
    if (!rect.width) return;
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    this.tooltip.textContent = formatTime(ratio * this.duration);
    this.tooltip.style.left = `${ratio * 100}%`;
    this.tooltip.style.opacity = "1";
  }

  updateProgress() {
    const duration = this.duration || 1;
    const ratio = Math.max(0, Math.min(1, this.currentTime / duration));
    const percent = `${ratio * 100}%`;
    this.progress.style.width = percent;
    this.thumb.style.left = percent;
    this.currentLabel.textContent = formatTime(this.currentTime);
    this.timeline.setAttribute("aria-valuenow", String(Math.round(this.currentTime)));
    this.timeline.setAttribute("aria-valuetext", `${formatTime(this.currentTime)} из ${formatTime(duration)}`);
    const outline = Number(localGet(`vector:pos:${this.lectureId}`, 0));
    if (!duration || outline <= 0) return;
  }

  updateBuffer() {
    const duration = this.duration;
    if (!duration || !this.video.buffered.length) return;
    let end = 0;
    for (let index = 0; index < this.video.buffered.length; index += 1) {
      if (this.video.buffered.start(index) <= this.currentTime) {
        end = Math.max(end, this.video.buffered.end(index));
      }
    }
    this.buffer.style.width = `${Math.min(100, (end / duration) * 100)}%`;
  }

  onTime() {
    this.updateProgress();
    this.updateBuffer();
    this.updateSubtitle();
    this.updateChapter();
    if (typeof this.options.onTime === "function") {
      this.options.onTime(this.currentTime, this.duration);
    }
    if (this.currentTime - this.lastSaved >= 4) this.savePosition();
  }

  updateSubtitle() {
    const cue = this.currentCue();
    const text = cue && this.captionsEnabled ? cue.text : "";
    if (text) {
      if (this.subtitleText.textContent !== text) this.subtitleText.textContent = text;
      this.subtitles.classList.remove("hidden");
    } else {
      this.subtitles.classList.add("hidden");
    }
  }

  currentCue() {
    if (!this.cues.length) return null;
    const time = this.currentTime;
    let low = 0;
    let high = this.cues.length - 1;
    let found = -1;
    while (low <= high) {
      const middle = (low + high) >> 1;
      const cue = this.cues[middle];
      if (time < cue.start) high = middle - 1;
      else if (time >= cue.end) low = middle + 1;
      else {
        found = middle;
        break;
      }
    }
    if (found !== this.cueIndex) {
      this.cueIndex = found;
      if (typeof this.options.onCue === "function") {
        this.options.onCue(found, found >= 0 ? this.cues[found] : null);
      }
    }
    return found >= 0 ? this.cues[found] : null;
  }

  updateChapter() {
    if (!this.chapters.length) return;
    let index = 0;
    this.chapters.forEach((chapter, position) => {
      if (this.currentTime >= chapter.start) index = position;
    });
    if (index !== this.chapterIndex) {
      this.chapterIndex = index;
      if (typeof this.options.onChapter === "function") {
        this.options.onChapter(index, this.chapters[index]);
      }
    }
  }

  toggleCaptions() {
    this.captionsEnabled = !this.captionsEnabled;
    localSet("vector:captions", this.captionsEnabled ? "on" : "off");
    this.syncCaptionsButton();
    this.updateSubtitle();
  }

  syncCaptionsButton() {
    if (!this.captionsButton) return;
    this.captionsButton.classList.toggle("active", this.captionsEnabled);
    this.captionsButton.setAttribute("aria-pressed", String(this.captionsEnabled));
  }

  toggleMute() {
    this.video.muted = !this.video.muted;
    if (!this.video.muted && this.video.volume === 0) this.video.volume = 0.6;
  }

  syncVolumeButton() {
    if (!this.volumeButton) return;
    const muted = this.video.muted || this.video.volume === 0;
    this.volumeButton.innerHTML = icon(muted ? "volume-x" : "volume");
    this.volumeButton.setAttribute("aria-pressed", String(muted));
    this.volumeButton.setAttribute("aria-label", muted ? "Включить звук" : "Выключить звук");
  }

  cycleSpeed() {
    const current = this.video.playbackRate || 1;
    const index = RATES.findIndex((rate) => Math.abs(rate - current) < 0.01);
    const next = RATES[(index + 1) % RATES.length];
    this.video.playbackRate = next;
    this.syncSpeed();
  }

  syncSpeed() {
    if (!this.speedButton) return;
    const rate = this.video.playbackRate || 1;
    this.speedButton.textContent = `${String(rate).replace(".", ",")}×`;
    this.speedButton.title = `Скорость: ${rate}×`;
  }

  toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
      return;
    }
    if (this.stage.requestFullscreen) {
      this.stage.requestFullscreen().catch(() => {});
    } else if (this.video.webkitEnterFullscreen) {
      this.video.webkitEnterFullscreen();
    }
  }

  offerResume() {
    if (!this.resumeButton) return;
    const duration = this.duration;
    if (this.savedPosition > 5 && (!duration || this.savedPosition < duration - 10)) {
      this.resumeButton.classList.remove("hidden");
      this.resumeButton.innerHTML = `${icon("clock")} Продолжить с ${formatTime(this.savedPosition)}`;
    } else {
      this.resumeButton.classList.add("hidden");
    }
  }

  resume() {
    this.seekTo(this.savedPosition, true);
    this.resumeButton?.classList.add("hidden");
  }

  savePosition(ended = false) {
    if (ended) {
      localSet(`vector:pos:${this.lectureId}`, 0);
    } else if (this.currentTime > 3 && this.currentTime < this.duration - 3) {
      localSet(`vector:pos:${this.lectureId}`, Math.round(this.currentTime));
    }
    this.lastSaved = this.currentTime;
  }

  wake() {
    this.root.classList.remove("idle");
    clearTimeout(this.idleTimer);
    if (this.video.paused) return;
    this.idleTimer = setTimeout(() => {
      if (!this.video.paused) this.root.classList.add("idle");
    }, 2400);
  }

  handleKey(event) {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    if (document.querySelector(".modal-backdrop")) return;
    const target = event.target;
    if (target instanceof Element) {
      if (target.closest("input, textarea, select, [contenteditable=true], [data-timeline]")) return;
      if (target.closest("a, button") && (event.key === " " || event.key === "Enter")) return;
    }
    if (!document.body.contains(this.root)) return;
    const key = event.key.toLowerCase();
    if (event.code === "Space" || key === "k") {
      event.preventDefault();
      this.toggle();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      this.seekBy(-5);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      this.seekBy(5);
    } else if (key === "j") {
      this.seekBy(-10);
    } else if (key === "l") {
      this.seekBy(10);
    } else if (key === "m") {
      this.toggleMute();
    } else if (key === "f") {
      this.toggleFullscreen();
    } else if (key === "c") {
      this.toggleCaptions();
    }
  }

  destroy() {
    this.destroyed = true;
    this.savePosition();
    clearTimeout(this.idleTimer);
    this.handlers.forEach((remove) => remove());
    this.handlers = [];
    this.video.pause();
    this.video.removeAttribute("src");
    this.video.load();
  }
}
