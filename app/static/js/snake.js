import { icon } from "./utils.js";

const COLS = 18;
const ROWS = 12;
const CELL = 20;
const WIDTH = COLS * CELL;
const HEIGHT = ROWS * CELL;
const BASE_STEP = 130;
const MIN_STEP = 75;
const BEST_KEY = "vector.snake.best";

const DIRECTIONS = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};

function readBest() {
  try {
    return Math.max(0, Number(localStorage.getItem(BEST_KEY)) || 0);
  } catch {
    return 0;
  }
}

function saveBest(value) {
  try {
    localStorage.setItem(BEST_KEY, String(value));
  } catch {
    /* приватный режим — рекорд просто не сохранится */
  }
}

function markup() {
  return `
  <div class="snake-card">
    <div class="snake-head">
      <div>
        <div class="snake-kicker">${icon("gamepad")} Пока ждём</div>
        <h3>Змейка</h3>
      </div>
      <div class="snake-scores" aria-live="polite">
        <span>Счёт<strong data-snake-score>0</strong></span>
        <span>Рекорд<strong data-snake-best>0</strong></span>
      </div>
    </div>
    <div class="snake-stage" data-snake-stage>
      <canvas width="${WIDTH}" height="${HEIGHT}" tabindex="0"
              aria-label="Поле игры «Змейка». Управляйте стрелками или WASD, пробел — пауза."></canvas>
      <div class="snake-overlay" data-snake-overlay>
        <strong data-snake-title>Готовы?</strong>
        <span data-snake-text>Стрелки, WASD, свайп или кнопки внизу</span>
        <button class="btn btn-primary btn-sm" type="button" data-snake-action>
          ${icon("play")} Играть
        </button>
      </div>
    </div>
    <div class="snake-foot">
      <div class="snake-hints">
        Стрелки / WASD<br><kbd>Space</kbd> — пауза
      </div>
      <div class="snake-pad" aria-label="Кнопки управления змейкой">
        <button type="button" data-dir="up" aria-label="Вверх">↑</button>
        <button type="button" data-dir="left" aria-label="Влево">←</button>
        <button type="button" data-dir="down" aria-label="Вниз">↓</button>
        <button type="button" data-dir="right" aria-label="Вправо">→</button>
      </div>
    </div>
  </div>`;
}

/**
 * Монтирует мини-игру «Змейка» в указанный контейнер.
 * Возвращает функцию очистки — её нужно вызвать при закрытии модалки или смене страницы.
 */
export function mountSnake(host) {
  if (!host) return () => {};

  host.innerHTML = markup();

  const canvas = host.querySelector("canvas");
  const stage = host.querySelector("[data-snake-stage]");
  const overlay = host.querySelector("[data-snake-overlay]");
  const overlayTitle = host.querySelector("[data-snake-title]");
  const overlayText = host.querySelector("[data-snake-text]");
  const action = host.querySelector("[data-snake-action]");
  const scoreNode = host.querySelector("[data-snake-score]");
  const bestNode = host.querySelector("[data-snake-best]");
  const context = canvas.getContext("2d");

  const ratio = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = WIDTH * ratio;
  canvas.height = HEIGHT * ratio;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);

  let best = readBest();
  let snake = [];
  let direction = DIRECTIONS.right;
  let queued = direction;
  let food = { x: 0, y: 0 };
  let score = 0;
  let step = BASE_STEP;
  let timer = null;
  let state = "idle";
  let pointer = null;

  function updateScores() {
    scoreNode.textContent = String(score);
    bestNode.textContent = String(best);
  }

  function reset() {
    snake = [
      { x: 7, y: 6 },
      { x: 6, y: 6 },
      { x: 5, y: 6 },
      { x: 4, y: 6 },
    ];
    direction = DIRECTIONS.right;
    queued = direction;
    score = 0;
    step = BASE_STEP;
    food = spawnFood();
    updateScores();
  }

  function spawnFood() {
    const free = [];
    for (let y = 0; y < ROWS; y += 1) {
      for (let x = 0; x < COLS; x += 1) {
        if (!snake.some((part) => part.x === x && part.y === y)) free.push({ x, y });
      }
    }
    if (!free.length) return null;
    return free[Math.floor(Math.random() * free.length)];
  }

  function showOverlay(title, text, label) {
    overlayTitle.textContent = title;
    overlayText.textContent = text;
    action.innerHTML = `${icon(state === "paused" ? "play" : state === "over" ? "refresh" : "play")} ${label}`;
    overlay.hidden = false;
  }

  function hideOverlay() {
    overlay.hidden = true;
  }

  function drawGrid() {
    context.fillStyle = "#0a0d0b";
    context.fillRect(0, 0, WIDTH, HEIGHT);
    context.strokeStyle = "rgba(200, 245, 96, .045)";
    context.lineWidth = 1;
    for (let x = 1; x < COLS; x += 1) {
      context.beginPath();
      context.moveTo(x * CELL + 0.5, 0);
      context.lineTo(x * CELL + 0.5, HEIGHT);
      context.stroke();
    }
    for (let y = 1; y < ROWS; y += 1) {
      context.beginPath();
      context.moveTo(0, y * CELL + 0.5);
      context.lineTo(WIDTH, y * CELL + 0.5);
      context.stroke();
    }
  }

  function roundedCell(x, y, color, inset = 1.5) {
    const size = CELL - inset * 2;
    context.fillStyle = color;
    context.beginPath();
    if (typeof context.roundRect === "function") {
      context.roundRect(x * CELL + inset, y * CELL + inset, size, size, 5);
    } else {
      context.rect(x * CELL + inset, y * CELL + inset, size, size);
    }
    context.fill();
  }

  function draw() {
    drawGrid();

    if (food) {
      context.save();
      context.shadowColor = "rgba(243, 201, 105, .65)";
      context.shadowBlur = 10;
      roundedCell(food.x, food.y, "#f3c969", 4);
      context.restore();
      context.fillStyle = "rgba(26, 36, 8, .55)";
      context.fillRect(food.x * CELL + 9, food.y * CELL + 6, 1.5, 3);
    }

    snake.forEach((part, index) => {
      const head = index === 0;
      roundedCell(part.x, part.y, head ? "#ddff92" : "#a9d84d", head ? 1 : 2);
    });

    if (snake.length) {
      const head = snake[0];
      const eye = 4;
      const cx = head.x * CELL + CELL / 2;
      const cy = head.y * CELL + CELL / 2;
      const offsetX = direction.y !== 0 ? eye : direction.x * 2;
      const offsetY = direction.x !== 0 ? eye : direction.y * 2;
      context.fillStyle = "#1a2408";
      [1, -1].forEach((side) => {
        context.beginPath();
        context.arc(cx + offsetX * side, cy + offsetY * side, 1.6, 0, Math.PI * 2);
        context.fill();
      });
    }
  }

  function clearTimer() {
    if (timer) clearTimeout(timer);
    timer = null;
  }

  function schedule() {
    clearTimer();
    if (state === "running") timer = setTimeout(tick, step);
  }

  function start() {
    reset();
    state = "running";
    hideOverlay();
    draw();
    schedule();
    canvas.focus({ preventScroll: true });
  }

  function pause() {
    if (state !== "running") return;
    state = "paused";
    clearTimer();
    showOverlay("Пауза", "Продолжите, когда будете готовы", "Продолжить");
    draw();
  }

  function resume() {
    if (state !== "paused") return;
    state = "running";
    hideOverlay();
    draw();
    schedule();
    canvas.focus({ preventScroll: true });
  }

  function finish(reason = "crash") {
    state = "over";
    clearTimer();
    const record = score > best;
    if (record) {
      best = score;
      saveBest(best);
    }
    updateScores();
    if (reason === "win") {
      showOverlay("Поле заполнено!", `Победа! Счёт: ${score}`, "Ещё раз");
    } else {
      showOverlay(
        "Игра окончена",
        record ? `Новый рекорд: ${score}!` : `Счёт: ${score}`,
        "Ещё раз",
      );
    }
    draw();
  }

  function tick() {
    if (state !== "running") return;
    direction = queued;
    const head = { x: snake[0].x + direction.x, y: snake[0].y + direction.y };
    const willEat = Boolean(food) && head.x === food.x && head.y === food.y;
    const body = willEat ? snake : snake.slice(0, -1);
    const hitWall = head.x < 0 || head.y < 0 || head.x >= COLS || head.y >= ROWS;
    const hitSelf = body.some((part) => part.x === head.x && part.y === head.y);
    if (hitWall || hitSelf) {
      finish();
      return;
    }

    snake.unshift(head);
    if (willEat) {
      score += 1;
      step = Math.max(MIN_STEP, BASE_STEP - score * 3);
      food = spawnFood();
      updateScores();
      if (!food) {
        finish("win");
        return;
      }
    } else {
      snake.pop();
    }

    draw();
    schedule();
  }

  function setDirection(name) {
    const next = DIRECTIONS[name];
    if (!next) return;
    if (next.x === -direction.x && next.y === -direction.y) return;
    queued = next;
  }

  function onKeyDown(event) {
    const codes = {
      ArrowUp: "up", KeyW: "up",
      ArrowDown: "down", KeyS: "down",
      ArrowLeft: "left", KeyA: "left",
      ArrowRight: "right", KeyD: "right",
    };
    if (event.code === "Space") {
      event.preventDefault();
      if (state === "running") pause();
      else if (state === "paused") resume();
      else start();
      return;
    }
    const mapped = codes[event.code];
    if (!mapped) return;
    event.preventDefault();
    if (state === "idle" || state === "over") start();
    else if (state === "paused") resume();
    setDirection(mapped);
  }

  function onAction() {
    if (state === "running") pause();
    else if (state === "paused") resume();
    else start();
  }

  function onPointerDown(event) {
    pointer = { x: event.clientX, y: event.clientY };
  }

  function onPointerUp(event) {
    if (!pointer) return;
    const dx = event.clientX - pointer.x;
    const dy = event.clientY - pointer.y;
    pointer = null;
    if (Math.abs(dx) < 18 && Math.abs(dy) < 18) return;
    if (Math.abs(dx) > Math.abs(dy)) setDirection(dx > 0 ? "right" : "left");
    else setDirection(dy > 0 ? "down" : "up");
  }

  function onVisibility() {
    if (document.hidden) pause();
  }

  function onFocusOut() {
    setTimeout(() => {
      if (state === "running" && !host.contains(document.activeElement)) pause();
    }, 0);
  }

  canvas.addEventListener("keydown", onKeyDown);
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointerup", onPointerUp);
  stage.addEventListener("pointerdown", onPointerDown);
  stage.addEventListener("pointerup", onPointerUp);
  action.addEventListener("click", onAction);
  host.addEventListener("focusout", onFocusOut);
  document.addEventListener("visibilitychange", onVisibility);

  host.querySelectorAll("[data-dir]").forEach((button) => {
    button.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      if (state === "idle" || state === "over") start();
      else if (state === "paused") resume();
      setDirection(button.dataset.dir);
      canvas.focus({ preventScroll: true });
    });
  });

  reset();
  draw();
  updateScores();

  return () => {
    state = "idle";
    clearTimer();
    document.removeEventListener("visibilitychange", onVisibility);
    host.removeEventListener("focusout", onFocusOut);
    host.innerHTML = "";
  };
}
