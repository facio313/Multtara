import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1/',
  timeout: 10000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
});

let csrfToken = '';

export function setCsrfToken(token) {
  csrfToken = token || '';
}

export async function refreshCsrf() {
  const response = await api.get('/auth/csrf/');
  setCsrfToken(response.data.csrfToken);
  return csrfToken;
}

api.interceptors.request.use((config) => {
  const method = (config.method || 'get').toLowerCase();
  if (csrfToken && ['post', 'put', 'patch', 'delete'].includes(method)) {
    config.headers['X-CSRFToken'] = csrfToken;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;
    const url = String(error.config?.url || '');
    const alreadyRetried = error.config?._csrfRetry;
    if (status === 403 && !alreadyRetried && !url.includes('/auth/csrf/')) {
      try {
        await refreshCsrf();
        error.config._csrfRetry = true;
        return api.request(error.config);
      } catch {
        return Promise.reject(error);
      }
    }
    if (status !== 401) {
      console.error('API Error:', error.response?.data || error.message);
    }
    return Promise.reject(error);
  }
);

export function unwrapList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

export default api;
