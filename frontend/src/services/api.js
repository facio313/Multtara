import axios from 'axios';

const runtimeEnv = import.meta.env ?? {};
const rawBaseUrl = runtimeEnv.VITE_API_BASE_URL?.trim() || '/api/v1/';
const apiBaseUrl = rawBaseUrl.endsWith('/') ? rawBaseUrl : `${rawBaseUrl}/`;

export const runtimeConfig = Object.freeze({
  apiBaseUrl,
  kakaoMapConfigured: Boolean(runtimeEnv.VITE_KAKAO_MAP_KEY?.trim()),
});

const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10000,
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
