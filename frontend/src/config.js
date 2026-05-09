const DEFAULT_LOCAL_API_BASE = 'http://127.0.0.1:8000';
const DEFAULT_PRODUCTION_API_BASE = 'https://g-dam.onrender.com';

const configuredApiBase = import.meta.env.VITE_API_BASE_URL;
const fallbackApiBase = import.meta.env.DEV
  ? DEFAULT_LOCAL_API_BASE
  : DEFAULT_PRODUCTION_API_BASE;

export const API_BASE = (configuredApiBase || fallbackApiBase).replace(/\/+$/, '');

export function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE}${normalizedPath}`;
}
