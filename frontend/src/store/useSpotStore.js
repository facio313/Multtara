import { create } from 'zustand';
import api, { unwrapList } from '../services/api';

const useSpotStore = create((set) => ({
  spots: [],
  selectedSpot: null,
  loading: false,
  error: null,

  fetchSpots: async (params = {}) => {
    set({ loading: true, error: null });
    try {
      const response = await api.get('/spots/', { params });
      set({ spots: unwrapList(response.data), loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  setSelectedSpot: (spot) => set({ selectedSpot: spot }),
}));

export default useSpotStore;
