const DEFAULT_LOCAL_API_BASE = 'http://127.0.0.1:8000';
const DEFAULT_PRODUCTION_API_BASE = 'https://g-dam.onrender.com';

function normalizeApiBase(value) {
  const trimmed = String(value || '').trim();

  if (!trimmed || trimmed === '/') {
    return '';
  }

  if (!/^https?:\/\//i.test(trimmed)) {
    console.warn(
      `Ignoring invalid VITE_API_BASE_URL "${trimmed}". Use a full URL like https://g-dam.onrender.com.`
    );
    return '';
  }

  return trimmed.replace(/\/+$/, '');
}

export const API_BASE_URL =
  normalizeApiBase(import.meta.env.VITE_API_BASE_URL) ||
  (import.meta.env.DEV ? DEFAULT_LOCAL_API_BASE : DEFAULT_PRODUCTION_API_BASE);

export const API_BASE = API_BASE_URL;

export function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}
