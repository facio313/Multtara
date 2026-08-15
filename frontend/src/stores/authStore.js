import { create } from 'zustand';
import api, { refreshCsrf } from '../services/api';

function fieldError(data) {
  if (!data || typeof data !== 'object') return '요청을 처리하지 못했습니다.';
  if (typeof data.detail === 'string') return data.detail;
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && value[0]) return String(value[0]);
    if (typeof value === 'string') return value;
  }
  return '요청을 처리하지 못했습니다.';
}

const useAuthStore = create((set) => ({
  user: null,
  ready: false,

  async bootstrap() {
    try {
      await refreshCsrf();
      const { data } = await api.get('/auth/me/');
      set({ user: data, ready: true });
    } catch {
      set({ user: null, ready: true });
    }
  },

  async register(payload) {
    await refreshCsrf();
    try {
      const { data } = await api.post('/auth/register/', payload);
      set({ user: data });
      return { ok: true };
    } catch (error) {
      return { ok: false, message: fieldError(error.response?.data) };
    }
  },

  async login(payload) {
    await refreshCsrf();
    try {
      const { data } = await api.post('/auth/login/', payload);
      set({ user: data });
      return { ok: true };
    } catch (error) {
      return { ok: false, message: fieldError(error.response?.data) };
    }
  },

  async logout() {
    await refreshCsrf();
    try {
      await api.post('/auth/logout/');
    } catch {
      // Session is cleared locally even if the network call fails.
    }
    set({ user: null });
  },

  async changePassword(payload) {
    await refreshCsrf();
    try {
      await api.post('/auth/password/', payload);
      return { ok: true };
    } catch (error) {
      return { ok: false, message: fieldError(error.response?.data) };
    }
  },
}));

export default useAuthStore;
