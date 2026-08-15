export const SUPPORTED_LOCALES = Object.freeze(['ko', 'en', 'ja', 'zh']);
export const LOCALE_STORAGE_KEY = 'pongdang:locale';

export const HTML_LANG = Object.freeze({
  ko: 'ko-KR',
  en: 'en',
  ja: 'ja',
  zh: 'zh-Hans',
});

export const INTL_LOCALE = Object.freeze({
  ko: 'ko-KR',
  en: 'en-US',
  ja: 'ja-JP',
  zh: 'zh-CN',
});

export function normalizeLocale(value) {
  if (typeof value !== 'string') return 'ko';
  const normalized = value.trim().toLowerCase().replace('_', '-');
  if (normalized.startsWith('ko')) return 'ko';
  if (normalized.startsWith('en')) return 'en';
  if (normalized.startsWith('ja')) return 'ja';
  if (normalized.startsWith('zh')) return 'zh';
  return 'ko';
}
