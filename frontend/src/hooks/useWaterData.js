import { useEffect, useMemo } from 'react';
import useSpotStore, { requestKey } from '../store/useSpotStore';
import { findSpotByRouteId } from '../services/waterData';

export function useWaterSpots(activity, options = {}) {
  const loadConditions = options.loadConditions !== false;
  const store = useSpotStore();
  const {
    spots,
    source,
    spotStatus,
    conditionRequests,
    error,
    fetchSpots,
    fetchConditions,
    retryData,
  } = store;
  const apiSpotCount = useMemo(
    () => spots.filter((spot) => spot.apiId !== null).length,
    [spots],
  );
  const key = requestKey({ activity });
  const conditionRequest = conditionRequests[key] ?? { status: 'idle', error: null };

  useEffect(() => {
    fetchSpots();
  }, [fetchSpots]);

  useEffect(() => {
    if (!loadConditions || !activity || spotStatus === 'idle' || spotStatus === 'loading') return;
    fetchConditions({ activity });
  }, [activity, apiSpotCount, fetchConditions, loadConditions, spotStatus]);

  return {
    spots,
    source,
    spotStatus,
    conditionStatus: conditionRequest.status,
    spotError: error,
    conditionError: conditionRequest.error,
    retryData,
  };
}

export function useWaterSpot(id) {
  const store = useSpotStore();
  const {
    spots,
    source,
    spotStatus,
    conditionRequests,
    observationRequests,
    error,
    fetchSpots,
    fetchConditions,
    fetchObservations,
    retryData,
  } = store;
  const spot = useMemo(
    () => findSpotByRouteId(spots, id),
    [id, spots],
  );
  const apiId = spot?.apiId ?? null;
  const scoreKey = requestKey({ spot: apiId });
  const conditionRequest = conditionRequests[scoreKey] ?? { status: 'idle', error: null };
  const observationRequest = observationRequests[String(apiId)] ?? { status: 'idle', error: null };

  useEffect(() => {
    fetchSpots();
  }, [fetchSpots]);

  useEffect(() => {
    if (spotStatus === 'idle' || spotStatus === 'loading' || apiId === null) return;
    fetchConditions({ spot: apiId });
    fetchObservations(apiId);
  }, [apiId, fetchConditions, fetchObservations, spotStatus]);

  return {
    spot,
    source,
    spotStatus,
    conditionStatus: conditionRequest.status,
    observationStatus: observationRequest.status,
    spotError: error,
    conditionError: conditionRequest.error,
    observationError: observationRequest.error,
    retryData,
  };
}
