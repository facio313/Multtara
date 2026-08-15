import { Globe2 } from 'lucide-react';
import { useI18n } from '../../i18n';

const localeOptions = [
  { value: 'ko', label: 'KO' },
  { value: 'en', label: 'EN' },
  { value: 'ja', label: 'JA' },
  { value: 'zh', label: 'ZH' },
];

function LocaleSelector({ mobile = false, className = '' }) {
  const { locale, setLocale, t } = useI18n();
  const classes = [
    'locale-selector',
    mobile ? 'locale-selector-mobile' : '',
    className,
  ].filter(Boolean).join(' ');

  return (
    <label className={classes}>
      <Globe2 size={15} aria-hidden="true" />
      <span className="sr-only">{t('locale.label')}</span>
      <select
        value={locale}
        onChange={(event) => setLocale(event.target.value)}
        aria-label={t('locale.label')}
      >
        {localeOptions.map((option) => (
          <option key={option.value} value={option.value}>
            {mobile ? option.label : `${option.label} · ${t(`locale.${option.value}`)}`}
          </option>
        ))}
      </select>
    </label>
  );
}

export default LocaleSelector;
