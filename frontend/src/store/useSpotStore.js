import { create } from 'zustand';
import { spots as demoSpots } from '../data/pongdangData';
import { getCollectionWithFallback } from '../services/api';

const useSpotStore = create((set) => ({
  spots: [],
  selectedSpot: null,
  source: 'demo',
  loading: false,
  error: null,

  fetchSpots: async (params = {}) => {
    set({ loading: true, error: null });
    try {
      const result = await getCollectionWithFallback('spots/', demoSpots, { params });
      set({
        spots: result.data,
        source: result.source,
        error: result.error,
        loading: false,
      });
    } catch (error) {
      set({ spots: demoSpots, source: 'demo', error: { kind: 'client', message: error.message }, loading: false });
    }
  },

  setSelectedSpot: (spot) => set({ selectedSpot: spot }),
}));

export default useSpotStore;
