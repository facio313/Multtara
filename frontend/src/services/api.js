import axios from 'axios';

const runtimeEnv = import.meta.env ?? {};
const rawBaseUrl = runtimeEnv.VITE_API_BASE_URL?.trim() || '/api/v1/';
const apiBaseUrl = rawBaseUrl.endsWith('/') ? rawBaseUrl : `${rawBaseUrl}/`;
const csrfCookieName = runtimeEnv.VITE_CSRF_COOKIE_NAME?.trim() || 'pongdang_csrftoken';

export const runtimeConfig = Object.freeze({
  apiBaseUrl,
  csrfCookieName,
  kakaoMapConfigured: Boolean(runtimeEnv.VITE_KAKAO_MAP_KEY?.trim()),
  ssoEnabled: runtimeEnv.VITE_SSO_ENABLED === 'true',
});

const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10000,
  withCredentials: true,
  withXSRFToken: true,
  xsrfCookieName: csrfCookieName,
  xsrfHeaderName: 'X-CSRFToken',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error),
);

const normalizeCollection = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
};

/**
 * Keep the product usable when a local backend or provider is unavailable.
 * Callers must visibly label `source === 'demo'`; fallback records are not live data.
 */
export async function getCollectionWithFallback(path, fallback = [], options = {}) {
  try {
    const response = await api.get(path, options);
    return {
      data: normalizeCollection(response.data),
      source: 'api',
      error: null,
    };
  } catch (error) {
    return {
      data: fallback,
      source: 'demo',
      error: {
        kind: error.response ? 'response' : 'network',
        status: error.response?.status ?? null,
      },
    };
  }
}

export default api;
