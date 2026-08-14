import { create } from 'zustand';
import api from '../services/api';

const useSpotStore = create((set) => ({
  spots: [],
  selectedSpot: null,
  loading: false,
  error: null,

  fetchSpots: async (params = {}) => {
    set({ loading: true, error: null });
    try {
      // Mock for now until API is ready
      // const response = await api.get('/spots/', { params });
      // set({ spots: response.data.results, loading: false });
      set({ spots: [], loading: false }); 
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  setSelectedSpot: (spot) => set({ selectedSpot: spot }),
}));

export default useSpotStore;
