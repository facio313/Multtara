import { create } from 'zustand';
import {
  classifyAccountError,
  deleteAccount,
  getCurrentUser,
  isMissingSession,
  loginAccount,
  logoutAccount,
  registerAccount,
  ssoLoginAccount,
  updateAccount,
} from '../services/accountApi.js';
import { runtimeConfig } from '../services/api.js';

const useSessionStore = create((set, get) => ({
  status: 'idle',
  user: null,
  error: null,

  ensureSession: async ({ force = false } = {}) => {
    if (!force && ['loading', 'guest', 'authenticated'].includes(get().status)) return get().user;
    set({ status: 'loading', error: null });
    try {
      const user = await getCurrentUser();
      set({ status: 'authenticated', user, error: null });
      return user;
    } catch (error) {
      if (isMissingSession(error)) {
        if (runtimeConfig.ssoEnabled) {
          try {
            const user = await ssoLoginAccount();
            set({ status: 'authenticated', user, error: null });
            return user;
          } catch (ssoError) {
            set({ status: 'error', user: null, error: classifyAccountError(ssoError, 'session') });
            return null;
          }
        }
        set({ status: 'guest', user: null, error: null });
        return null;
      }
      set({ status: 'error', user: null, error: classifyAccountError(error, 'session') });
      return null;
    }
  },

  login: async (payload) => {
    const user = await loginAccount(payload);
    set({ status: 'authenticated', user, error: null });
    return user;
  },

  register: async (payload) => {
    const user = await registerAccount(payload);
    set({ status: 'authenticated', user, error: null });
    return user;
  },

  logout: async () => {
    await logoutAccount();
    set({ status: 'guest', user: null, error: null });
  },

  updateProfile: async (payload) => {
    const user = await updateAccount(payload);
    set({ status: 'authenticated', user, error: null });
    return user;
  },

  removeAccount: async (payload) => {
    await deleteAccount(payload);
    set({ status: 'guest', user: null, error: null });
  },
}));

export default useSessionStore;
