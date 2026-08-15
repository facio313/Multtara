import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { I18nContext } from './context';
import {
  HTML_LANG,
  INTL_LOCALE,
  LOCALE_STORAGE_KEY,
  normalizeLocale,
} from './runtime';
import { messages } from './messages';

function readInitialLocale() {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored) return normalizeLocale(stored);
  } catch {
    // A blocked storage surface must not prevent the application from loading.
  }
  return 'ko';
}

function interpolate(template, variables) {
  if (!variables || typeof variables !== 'object') return template;
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name) => {
    const value = variables[name];
    return value === null || value === undefined ? match : String(value);
  });
}

export function I18nProvider({ children }) {
  const [locale, setLocaleState] = useState(readInitialLocale);

  useEffect(() => {
    document.documentElement.lang = HTML_LANG[locale];
  }, [locale]);

  const setLocale = useCallback((nextLocale) => {
    const normalized = normalizeLocale(nextLocale);
    setLocaleState(normalized);
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, normalized);
    } catch {
      // The selected language still works for this session when storage is blocked.
    }
  }, []);

  const t = useCallback((key, variables) => {
    const localized = messages[locale]?.[key];
    const fallback = messages.ko[key];
    const template = typeof localized === 'string'
      ? localized
      : (typeof fallback === 'string' ? fallback : key);
    return interpolate(template, variables);
  }, [locale]);

  const value = useMemo(() => ({
    locale,
    htmlLang: HTML_LANG[locale],
    intlLocale: INTL_LOCALE[locale],
    setLocale,
    t,
  }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
