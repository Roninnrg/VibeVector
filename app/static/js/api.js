export class ApiError extends Error {
  constructor(message, status = 0, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function request(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  let body = options.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, { ...options, headers, body });
  } catch {
    throw new ApiError("Не удалось связаться с сервером «Вектор».", 0);
  }
  const type = response.headers.get("content-type") || "";
  const payload = type.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail : payload;
    throw new ApiError(
      typeof detail === "string" && detail ? detail : `Ошибка запроса (${response.status}).`,
      response.status,
      payload,
    );
  }
  return payload;
}

function queryString(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

export const api = {
  stats: () => request("/api/stats"),
  meta: () => request("/api/meta"),
  health: () => request("/api/health"),
  ffmpeg: () => request("/api/diagnostics/ffmpeg"),

  lectures: (params = {}) => request(`/api/lectures${queryString(params)}`),
  lecture: (id) => request(`/api/lectures/${encodeURIComponent(id)}`),
  transcript: (id, words = false) =>
    request(`/api/lectures/${encodeURIComponent(id)}/transcript${words ? "?words=true" : ""}`),
  updateLecture: (id, payload) =>
    request(`/api/lectures/${encodeURIComponent(id)}`, { method: "PATCH", body: payload }),
  deleteLecture: (id, signal) =>
    request(`/api/lectures/${encodeURIComponent(id)}`, { method: "DELETE", signal }),
  reprocess: (id) =>
    request(`/api/lectures/${encodeURIComponent(id)}/reprocess`, { method: "POST" }),

  search: (q, params = {}) => request(`/api/search${queryString({ q, ...params })}`),
  suggest: (q) => request(`/api/search/suggest${queryString({ q })}`),
  ask: (id, question, limit = 5) =>
    request(`/api/lectures/${encodeURIComponent(id)}/ask`, {
      method: "POST",
      body: { question, limit },
    }),

  importUrl: (payload) =>
    request("/api/lectures/import", { method: "POST", body: payload }),

  facts: (limit = 8) => request(`/api/facts?limit=${encodeURIComponent(limit)}`),

  me: () => request("/api/auth/me"),
  register: (payload) => request("/api/auth/register", { method: "POST", body: payload }),
  login: (payload) => request("/api/auth/login", { method: "POST", body: payload }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  updateProfile: (payload) =>
    request("/api/auth/profile", { method: "PATCH", body: payload }),
  changePassword: (payload) =>
    request("/api/auth/password", { method: "POST", body: payload }),
  profile: () => request("/api/profile"),
  favorites: () => request("/api/favorites"),
  toggleFavorite: (id) =>
    request(`/api/favorites/${encodeURIComponent(id)}`, { method: "POST" }),

  exportUrl: (id) => `/api/lectures/${encodeURIComponent(id)}/export`,
  subtitlesUrl: (id, format = "vtt", download = false) =>
    `/api/lectures/${encodeURIComponent(id)}/subtitles.${format}${download ? "?download=true" : ""}`,
  mediaUrl: (id) => `/api/lectures/${encodeURIComponent(id)}/media`,
  thumbnailUrl: (id) => `/api/lectures/${encodeURIComponent(id)}/thumbnail`,

  upload(file, { title = "", description = "", language = "auto", onProgress, signal } = {}) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("title", title);
      form.append("description", description);
      form.append("language", language);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/lectures/upload");
      xhr.responseType = "json";
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      });
      xhr.addEventListener("load", () => {
        const payload = xhr.response;
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload);
        } else {
          const detail = payload && payload.detail ? payload.detail : `Ошибка загрузки (${xhr.status}).`;
          reject(new ApiError(detail, xhr.status, payload));
        }
      });
      xhr.addEventListener("error", () => reject(new ApiError("Соединение прервано во время загрузки.")));
      xhr.addEventListener("abort", () => reject(new ApiError("Загрузка отменена.", 0)));
      if (signal) {
        signal.addEventListener("abort", () => xhr.abort(), { once: true });
      }
      xhr.send(form);
    });
  },
};
