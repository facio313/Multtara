import { create } from 'zustand';
import { spots as demoSpots } from '../data/pongdangData';
import {
  applyConditionScores,
  applyObservations,
  fetchLatestConditionScores,
  fetchMergedSpots,
  fetchSpotObservations,
  mergeSpotsWithDemo,
} from '../services/waterData';

const initialSpots = mergeSpotsWithDemo([], demoSpots);

function requestKey({ spot, activity } = {}) {
  return `spot:${spot ?? 'all'}|activity:${activity ?? 'all'}`;
}

const useSpotStore = create((set, get) => ({
  spots: initialSpots,
  selectedSpot: null,
  source: 'demo',
  spotStatus: 'idle',
  conditionRequests: {},
  observationRequests: {},
  loading: false,
  error: null,

  fetchSpots: async (params = {}, { force = false } = {}) => {
    const currentStatus = get().spotStatus;
    if (!force && currentStatus !== 'idle') return;

    set({ spotStatus: 'loading', loading: true, error: null });
    const result = await fetchMergedSpots(demoSpots, params);
    set({
      spots: result.data,
      source: result.source,
      spotStatus: result.status,
      error: result.error,
      loading: false,
    });
  },

  fetchConditions: async (params = {}, { force = false } = {}) => {
    const key = requestKey(params);
    const existing = get().conditionRequests[key];
    if (!force && ['loading', 'ready', 'empty'].includes(existing?.status)) return;

    const hasApiSpots = get().spots.some((spot) => spot.apiId !== null);
    if (!hasApiSpots) {
      set((state) => ({
        conditionRequests: {
          ...state.conditionRequests,
          [key]: { status: 'empty', error: null },
        },
      }));
      return;
    }

    set((state) => ({
      conditionRequests: {
        ...state.conditionRequests,
        [key]: { status: 'loading', error: null },
      },
    }));

    const result = await fetchLatestConditionScores(params);
    set((state) => ({
      spots: result.data.length > 0
        ? applyConditionScores(state.spots, result.data)
        : state.spots,
      conditionRequests: {
        ...state.conditionRequests,
        [key]: { status: result.status, error: result.error },
      },
    }));
  },

  fetchObservations: async (spotApiId, { force = false } = {}) => {
    const key = String(spotApiId);
    const existing = get().observationRequests[key];
    if (!force && ['loading', 'ready', 'empty'].includes(existing?.status)) return;

    set((state) => ({
      observationRequests: {
        ...state.observationRequests,
        [key]: { status: 'loading', error: null },
      },
    }));

    const result = await fetchSpotObservations(spotApiId);
    set((state) => ({
      spots: result.data.length > 0
        ? applyObservations(state.spots, spotApiId, result.data)
        : state.spots,
      observationRequests: {
        ...state.observationRequests,
        [key]: { status: result.status, error: result.error },
      },
    }));
  },

  retryData: async () => {
    set({
      spotStatus: 'idle',
      conditionRequests: {},
      observationRequests: {},
    });
    await get().fetchSpots({}, { force: true });
  },

  setSelectedSpot: (spot) => set({ selectedSpot: spot }),
}));

export { requestKey };
export default useSpotStore;
