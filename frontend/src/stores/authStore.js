import { create } from 'zustand';
import api, { refreshCsrf } from '../services/api';
import { currentPosition } from '../utils/geolocation';
import {
  readSafetyCards,
  upsertSafetyCard,
  writeSafetyCards,
} from '../utils/safetyCardCache';

function fieldError(data) {
  if (!data || typeof data !== 'object') return '요청을 처리하지 못했습니다.';
  if (typeof data.detail === 'string') return data.detail;
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && value[0]) return String(value[0]);
    if (typeof value === 'string') return value;
  }
  return '요청을 처리하지 못했습니다.';
}

const useAuthStore = create((set, get) => ({
  user: null,
  passport: null,
  safetyCards: [],
  ready: false,

  async loadPassport() {
    if (!get().user) {
      set({ passport: null });
      return;
    }
    try {
      const { data } = await api.get('/passport/');
      set({ passport: data });
    } catch {
      set({ passport: null });
    }
  },

  async loadSafetyCards() {
    const user = get().user;
    if (!user) {
      set({ safetyCards: [] });
      return;
    }
    const cached = readSafetyCards(user.id);
    set({ safetyCards: cached });
    try {
      const { data } = await api.get('/safety-card/');
      const rows = Array.isArray(data) ? data : [];
      writeSafetyCards(user.id, rows);
      set({ safetyCards: rows });
    } catch {
      set({ safetyCards: cached });
    }
  },

  async bootstrap() {
    try {
      await refreshCsrf();
      const { data } = await api.get('/auth/me/');
      set({ user: data, ready: true });
      await Promise.all([get().loadPassport(), get().loadSafetyCards()]);
    } catch {
      set({ user: null, passport: null, safetyCards: [], ready: true });
    }
  },

  async register(payload) {
    await refreshCsrf();
    try {
      const { data } = await api.post('/auth/register/', payload);
      set({ user: data });
      await Promise.all([get().loadPassport(), get().loadSafetyCards()]);
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
      await Promise.all([get().loadPassport(), get().loadSafetyCards()]);
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
    set({ user: null, passport: null, safetyCards: [] });
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

  async checkin(spotId) {
    await refreshCsrf();
    let coords;
    try {
      coords = await currentPosition();
    } catch (error) {
      return { ok: false, message: error.message || '위치를 확인하지 못했습니다.' };
    }
    try {
      const { data } = await api.post('/passport/checkin/', {
        spot_id: spotId,
        ...coords,
      });
      set({ passport: data });
      return { ok: true, data };
    } catch (error) {
      return { ok: false, message: fieldError(error.response?.data) };
    }
  },

  async saveSafetyCard(spotId, sharedWith = []) {
    await refreshCsrf();
    const user = get().user;
    try {
      const { data } = await api.post('/safety-card/', {
        spot_id: spotId,
        shared_with: sharedWith.filter(Boolean),
      });
      if (user) {
        set({ safetyCards: upsertSafetyCard(user.id, data) });
      }
      return { ok: true, data };
    } catch (error) {
      return { ok: false, message: fieldError(error.response?.data) };
    }
  },

  cachedSafetyCard(cardId) {
    const user = get().user;
    return (
      get().safetyCards.find((row) => String(row.id) === String(cardId)) ||
      (user ? readSafetyCards(user.id).find((row) => String(row.id) === String(cardId)) : null)
    );
  },
}));

export default useAuthStore;
