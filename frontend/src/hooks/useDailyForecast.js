import { useCallback, useEffect, useState } from 'react';
import {
  classifyDailyForecastError,
  getDailyForecast,
  isDailyForecastRequestCanceled,
} from '../services/dailyForecastApi';

export function useDailyForecast({
  spot,
  activity,
  participantProfile = 'general',
  participantSkillLevel = 'unspecified',
  startDate,
  days = 7,
  enabled = true,
}) {
  const [reload, setReload] = useState(0);
  const [state, setState] = useState({ requestKey: '', status: 'idle', data: null, error: null });
  const requestKey = enabled && spot
    ? [spot, activity, participantProfile, participantSkillLevel, startDate || '', days, reload].join('|')
    : '';

  useEffect(() => {
    if (!requestKey) return undefined;
    const controller = new AbortController();
    void getDailyForecast({
      spot,
      activity,
      participantProfile,
      participantSkillLevel,
      startDate,
      days,
    }, { signal: controller.signal })
      .then((data) => setState({ requestKey, status: 'ready', data, error: null }))
      .catch((error) => {
        if (isDailyForecastRequestCanceled(error)) return;
        setState({
          requestKey,
          status: 'error',
          data: null,
          error: classifyDailyForecastError(error),
        });
      });
    return () => controller.abort();
  }, [activity, days, participantProfile, participantSkillLevel, requestKey, spot, startDate]);

  const retry = useCallback(() => setReload((value) => value + 1), []);
  if (!requestKey) return { status: 'idle', data: null, error: null, retry };
  if (state.requestKey !== requestKey) {
    return { status: 'loading', data: null, error: null, retry };
  }
  return { status: state.status, data: state.data, error: state.error, retry };
}
