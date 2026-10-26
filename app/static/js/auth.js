import { api } from "./api.js";

let user = null;
let loaded = false;
let pending = null;
const listeners = new Set();

export function getUser() {
  return user;
}

export function isAuthLoaded() {
  return loaded;
}

export function setUser(next) {
  user = next || null;
  loaded = true;
  listeners.forEach((listener) => {
    try {
      listener(user);
    } catch (error) {
      console.warn("Не удалось обновить состояние аккаунта", error);
    }
  });
}

export function subscribeAuth(listener) {
  listeners.add(listener);
  listener(user);
  return () => listeners.delete(listener);
}

export async function loadAuth(force = false) {
  if (loaded && !force) return user;
  if (pending) return pending;
  pending = (async () => {
    try {
      const data = await api.me();
      setUser(data?.user || null);
    } catch {
      setUser(null);
    } finally {
      pending = null;
    }
    return user;
  })();
  return pending;
}

export async function logout() {
  try {
    await api.logout();
  } finally {
    setUser(null);
  }
}

export function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "В";
  return `${parts[0][0] || ""}${parts[1]?.[0] || ""}`.toUpperCase();
}

export function avatarClass(value) {
  const allowed = ["lime", "sky", "violet", "amber", "coral", "mint"];
  return `avatar-${allowed.includes(value) ? value : "lime"}`;
}
