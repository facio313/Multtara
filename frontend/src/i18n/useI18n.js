import { useContext } from 'react';
import { I18nContext } from './context';

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error('useI18n must be used inside I18nProvider');
  return value;
}

export function localizedDataState(t, state, short = false) {
  const key = `dataState.${state}.${short ? 'short' : 'label'}`;
  return t(key);
}

export function localizedSafety(t, level) {
  const safeLevel = ['clear', 'caution', 'stop', 'unknown', 'demo'].includes(level)
    ? level
    : 'unknown';
  return {
    label: t(`safety.${safeLevel}.label`),
    message: t(`safety.${safeLevel}.message`),
  };
}
