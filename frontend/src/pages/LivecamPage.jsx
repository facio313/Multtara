import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  BadgeCheck,
  Camera,
  CircleOff,
  Clock3,
  ExternalLink,
  Info,
  MapPin,
  Maximize2,
  Radio,
  RotateCcw,
  Search,
  ShieldCheck,
  Waves,
  X,
} from 'lucide-react';
import { livecams, spots } from '../data/pongdangData';
import { localizedSafety, useI18n } from '../i18n';
import './LivecamPage.css';

const STATUS_FILTERS = ['all', 'official', 'poster'];
const ALL_REGIONS = '__all__';

const toArray = (value) => (Array.isArray(value) ? value : []);

const toScore = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(100, Math.max(0, Math.round(parsed))) : null;
};

const safeOfficialUrl = (value) => {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const parsed = new URL(value);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
};

const getIndexTone = (score) => {
  if (score === null) return 'unknown';
  if (score >= 90) return 'excellent';
  if (score >= 80) return 'good';
  if (score >= 65) return 'fair';
  return 'caution';
};

const getIndexLabel = (t, score) => {
  const tone = getIndexTone(score);
  return tone === 'unknown' ? t('common.noData') : t(`forecast.status.${tone}`);
};

const getStatusMeta = (cam, t) => {
  const status = String(cam.status || '').toLowerCase();
  if (cam.isLive) {
    return {
      tone: 'official',
      label: t('livecam.status.official.label'),
      description: t('livecam.status.official.description'),
    };
  }
  if (status.includes('offline') || status.includes('중단') || status.includes('오프라인')) {
    return {
      tone: 'offline',
      label: t('livecam.status.offline.label'),
      description: t('livecam.status.offline.description'),
    };
  }
  return {
    tone: 'demo',
    label: t('livecam.status.demo.label'),
    description: t('livecam.status.demo.description'),
  };
};

const formatCondition = (value, suffix = '') => {
  if (value === null || value === undefined || value === '') return null;
  return typeof value === 'number' ? `${value}${suffix}` : String(value);
};

const SPOT_BY_ID = new Map(toArray(spots).map((spot) => [String(spot.id), spot]));

const CAM_DATA = toArray(livecams).map((cam, index) => {
  const spot = SPOT_BY_ID.get(String(cam?.spotId)) || null;
  const waterIndex = toScore(cam?.waterIndex ?? spot?.index);
  return {
    ...cam,
    id: cam?.id ?? `livecam-${index}`,
    name: String(cam?.name || spot?.name || `물멍 카메라 ${index + 1}`),
    region: String(cam?.region || spot?.region || '지역 미정'),
    status: cam?.status || 'demo',
    isLive: Boolean(cam?.isLive),
    waterIndex,
    poster: typeof cam?.poster === 'string' ? cam.poster : '',
    tags: toArray(cam?.tags),
    updatedLabel: String(cam?.updatedLabel || spot?.freshness?.updatedLabel || '고정 데모'),
    officialUrl: safeOfficialUrl(cam?.officialUrl),
    spot,
  };
});

const REGION_OPTIONS = [...new Set(CAM_DATA.map((cam) => cam.region).filter(Boolean))];

function LivecamPage() {
  const { t } = useI18n();
  const [statusFilter, setStatusFilter] = useState('all');
  const [regionFilter, setRegionFilter] = useState(ALL_REGIONS);
  const [query, setQuery] = useState('');
  const [focusedId, setFocusedId] = useState(null);
  const [failedPosters, setFailedPosters] = useState([]);
  const focusPanelRef = useRef(null);
  const closeButtonRef = useRef(null);
  const lastTriggerRef = useRef(null);

  const filteredCams = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR');
    return CAM_DATA.filter((cam) => {
      const statusMatches = statusFilter === 'all'
        || (statusFilter === 'official' && cam.isLive)
        || (statusFilter === 'poster' && !cam.isLive);
      const regionMatches = regionFilter === ALL_REGIONS || cam.region === regionFilter;
      const searchableText = [cam.name, cam.region, cam.spot?.typeLabel, ...cam.tags]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase('ko-KR');
      const queryMatches = !normalizedQuery || searchableText.includes(normalizedQuery);
      return statusMatches && regionMatches && queryMatches;
    });
  }, [query, regionFilter, statusFilter]);

  const focusedCam = CAM_DATA.find((cam) => cam.id === focusedId) || null;
  const officialCount = CAM_DATA.filter((cam) => cam.isLive).length;

  const closeFocusMode = useCallback(() => {
    setFocusedId(null);
    window.requestAnimationFrame(() => lastTriggerRef.current?.focus());
  }, []);

  const openFocusMode = (camId, trigger) => {
    lastTriggerRef.current = trigger;
    setFocusedId(camId);
  };

  useEffect(() => {
    if (!focusedCam) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeFocusMode();
        return;
      }

      if (event.key !== 'Tab' || !focusPanelRef.current) return;
      const focusable = [...focusPanelRef.current.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [closeFocusMode, focusedCam]);

  const markPosterFailed = (camId) => {
    setFailedPosters((current) => current.includes(camId) ? current : [...current, camId]);
  };

  const resetFilters = () => {
    setStatusFilter('all');
    setRegionFilter(ALL_REGIONS);
    setQuery('');
  };

  return (
    <div className="livecam-page">
      <header className="livecam-hero" aria-labelledby="livecam-title">
        <div className="livecam-hero__copy">
          <span className="livecam-eyebrow">WATER WINDOW</span>
          <h1 id="livecam-title">{t('livecam.hero.title')}</h1>
          <p>{t('livecam.hero.description')}</p>
        </div>

        <dl className="livecam-hero__stats" aria-label={t('livecam.stats.label')}>
          <div>
            <dt>{t('livecam.stats.registered')}</dt>
            <dd>{CAM_DATA.length}</dd>
          </div>
          <div>
            <dt>{t('livecam.stats.official')}</dt>
            <dd>{officialCount}</dd>
          </div>
          <div>
            <dt>{t('livecam.stats.autoplay')}</dt>
            <dd>OFF</dd>
          </div>
        </dl>
      </header>

      <section className="livecam-toolbar" aria-labelledby="livecam-filter-title">
        <div className="livecam-toolbar__heading">
          <div>
            <span className="livecam-eyebrow">LIVE &amp; POSTER VIEW</span>
            <h2 id="livecam-filter-title">{t('livecam.filters.title')}</h2>
          </div>
          <span className="livecam-result-count" aria-live="polite">
            {t('common.countViews', { count: filteredCams.length })}
          </span>
        </div>

        <div className="livecam-filter-row">
          <fieldset className="livecam-status-filter">
            <legend>{t('livecam.filters.status')}</legend>
            <div>
              {STATUS_FILTERS.map((filterId) => (
                <button
                  type="button"
                  key={filterId}
                  className={statusFilter === filterId ? 'is-active' : ''}
                  aria-pressed={statusFilter === filterId}
                  onClick={() => setStatusFilter(filterId)}
                >
                  {t(`livecam.filters.${filterId}`)}
                </button>
              ))}
            </div>
          </fieldset>

          <label className="livecam-region-filter">
            <span>{t('livecam.filters.region')}</span>
            <select value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)}>
              <option value={ALL_REGIONS}>{t('livecam.filters.allRegions')}</option>
              {REGION_OPTIONS.map((region) => (
                <option key={region} value={region}>{region}</option>
              ))}
            </select>
          </label>

          <label className="livecam-search">
            <span className="sr-only">{t('livecam.search.label')}</span>
            <Search aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('livecam.search.placeholder')}
              autoComplete="off"
            />
          </label>
        </div>
      </section>

      <section className="livecam-results" aria-labelledby="livecam-results-title">
        <div className="livecam-results__heading">
          <div>
            <span className="livecam-eyebrow">CURATED WATER VIEWS</span>
            <h2 id="livecam-results-title">{t('livecam.results.title')}</h2>
          </div>
          <p>
            <Info aria-hidden="true" />
            {t('livecam.results.policy')}
          </p>
        </div>

        {filteredCams.length ? (
          <div className="livecam-grid">
            {filteredCams.map((cam) => {
              const posterFailed = failedPosters.includes(cam.id);
              const safety = cam.spot?.safety;
              const conditions = cam.spot?.conditions || {};
              const waterTemp = formatCondition(conditions.waterTemp, '°C');
              const waveHeight = formatCondition(conditions.waveHeight, 'm');
              const crowd = formatCondition(conditions.crowd);
              const indexTone = getIndexTone(cam.waterIndex);
              const statusMeta = getStatusMeta(cam, t);

              return (
                <article
                  className="livecam-card"
                  key={cam.id}
                  style={{ '--livecam-visual': cam.spot?.visual?.gradient || 'linear-gradient(145deg, #0b4f58, #69cbb7)' }}
                >
                  <div className="livecam-card__poster">
                    {cam.poster && !posterFailed ? (
                      <img
                        src={cam.poster}
                        alt={t('livecam.poster.staticAlt', { name: cam.name })}
                        loading="lazy"
                        onError={() => markPosterFailed(cam.id)}
                      />
                    ) : (
                      <div className="livecam-poster-fallback" role="img" aria-label={`${cam.name} ${t('livecam.poster.pending')}`}>
                        <Waves aria-hidden="true" />
                        <span>{t('livecam.poster.pending')}</span>
                      </div>
                    )}

                    <div className="livecam-card__overlay">
                      <span className={`livecam-state-badge livecam-state-badge--${statusMeta.tone}`}>
                        {cam.isLive ? <Radio aria-hidden="true" /> : <Camera aria-hidden="true" />}
                        {statusMeta.label}
                      </span>
                      <span className={`livecam-index-badge livecam-index-badge--${indexTone}`}>
                        <small>INDEX</small>
                        <strong>{cam.waterIndex ?? '—'}</strong>
                      </span>
                    </div>

                    <button
                      type="button"
                      className="livecam-focus-button"
                      aria-label={`${cam.name} ${t('livecam.focus.open')}`}
                      aria-haspopup="dialog"
                      aria-expanded={focusedId === cam.id}
                      onClick={(event) => openFocusMode(cam.id, event.currentTarget)}
                    >
                      <Maximize2 aria-hidden="true" />
                      <span>{t('livecam.focus.open')}</span>
                    </button>
                  </div>

                  <div className="livecam-card__body">
                    <div className="livecam-card__title-row">
                      <div>
                        <p><MapPin aria-hidden="true" /> {cam.region}</p>
                        <h3>{cam.name}</h3>
                      </div>
                      <span className={`livecam-index-label livecam-index-label--${indexTone}`}>
                        {getIndexLabel(t, cam.waterIndex)}
                      </span>
                    </div>

                    <p className="livecam-status-description">{statusMeta.description}</p>

                    <dl className="livecam-condition-list">
                      <div>
                        <dt>{t('metric.waterTemp')}</dt>
                        <dd>{waterTemp || t('common.noData')}</dd>
                      </div>
                      <div>
                        <dt>{t('metric.waveHeight')}</dt>
                        <dd>{waveHeight || t('common.noData')}</dd>
                      </div>
                      <div>
                        <dt>{t('metric.crowd')}</dt>
                        <dd>{crowd || t('common.noData')}</dd>
                      </div>
                    </dl>

                    <div className="livecam-safety-row">
                      <ShieldCheck aria-hidden="true" />
                      <span>{safety?.level ? localizedSafety(t, safety.level).label : t('livecam.safety.missing')}</span>
                    </div>

                    {cam.tags.length > 0 && (
                      <ul className="livecam-tags" aria-label={t('livecam.tags')}>
                        {cam.tags.slice(0, 4).map((tag) => <li key={tag}>#{tag}</li>)}
                      </ul>
                    )}

                    <div className="livecam-card__footer">
                      <span><Clock3 aria-hidden="true" /> {cam.updatedLabel}</span>
                      <div>
                        {cam.spot?.id && (
                          <Link to={`/spot/${cam.spot.id}`}>
                            {t('common.details')} <ArrowUpRight aria-hidden="true" />
                          </Link>
                        )}
                        {cam.officialUrl ? (
                          <a href={cam.officialUrl} target="_blank" rel="noreferrer">
                            {t('livecam.link.official')} <ExternalLink aria-hidden="true" />
                          </a>
                        ) : (
                          <span className="livecam-link-unavailable">{t('livecam.link.pending')}</span>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="livecam-empty" role="status">
            <CircleOff aria-hidden="true" />
            <h3>{t('livecam.empty.title')}</h3>
            <p>{t('livecam.empty.description')}</p>
            <button type="button" onClick={resetFilters}>
              <RotateCcw aria-hidden="true" /> {t('common.resetFilters')}
            </button>
          </div>
        )}
      </section>

      <aside className="livecam-integrity-note" aria-label={t('livecam.integrity.title')}>
        <BadgeCheck aria-hidden="true" />
        <div>
          <strong>{t('livecam.integrity.title')}</strong>
          <p>{t('livecam.integrity.description')}</p>
        </div>
      </aside>

      {focusedCam && (
        <div
          className="livecam-focus-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeFocusMode();
          }}
        >
          <section
            id="livecam-focus-dialog"
            ref={focusPanelRef}
            className="livecam-focus-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="livecam-focus-title"
            aria-describedby="livecam-focus-description"
          >
            <button
              type="button"
              ref={closeButtonRef}
              className="livecam-focus-close"
              onClick={closeFocusMode}
            >
              <X aria-hidden="true" />
              <span>{t('common.close')}</span>
            </button>

            <div
              className="livecam-focus-media"
              style={{ '--livecam-visual': focusedCam.spot?.visual?.gradient || 'linear-gradient(145deg, #0b4f58, #69cbb7)' }}
            >
              {focusedCam.poster && !failedPosters.includes(focusedCam.id) ? (
                <img
                  src={focusedCam.poster}
                  alt={t('livecam.poster.focusAlt', { name: focusedCam.name })}
                  onError={() => markPosterFailed(focusedCam.id)}
                />
              ) : (
                <div className="livecam-poster-fallback" role="img" aria-label={`${focusedCam.name} ${t('livecam.poster.pending')}`}>
                  <Waves aria-hidden="true" />
                  <span>{t('livecam.poster.pending')}</span>
                </div>
              )}
              <div className="livecam-focus-media__status">
                <span className={`livecam-state-badge livecam-state-badge--${getStatusMeta(focusedCam, t).tone}`}>
                  {focusedCam.isLive ? <Radio aria-hidden="true" /> : <Camera aria-hidden="true" />}
                  {getStatusMeta(focusedCam, t).label}
                </span>
                <span>{t('livecam.autoplay.none')}</span>
              </div>
            </div>

            <div className="livecam-focus-copy">
              <span className="livecam-eyebrow">FOCUS WATER VIEW</span>
              <h2 id="livecam-focus-title">{focusedCam.name}</h2>
              <p id="livecam-focus-description">{getStatusMeta(focusedCam, t).description}</p>

              <div className="livecam-focus-summary">
                <div>
                  <span>Water Index</span>
                  <strong>{focusedCam.waterIndex ?? '—'}</strong>
                  <small>{getIndexLabel(t, focusedCam.waterIndex)}</small>
                </div>
                <div>
                  <span>{t('livecam.filters.region')}</span>
                  <strong>{focusedCam.region}</strong>
                  <small>{focusedCam.updatedLabel}</small>
                </div>
              </div>

              <div className="livecam-focus-actions">
                {focusedCam.spot?.id && (
                  <Link to={`/spot/${focusedCam.spot.id}`} onClick={closeFocusMode}>
                    {t('livecam.place.details')} <ArrowUpRight aria-hidden="true" />
                  </Link>
                )}
                {focusedCam.officialUrl ? (
                  <a href={focusedCam.officialUrl} target="_blank" rel="noreferrer">
                    {t('livecam.provider.open')} <ExternalLink aria-hidden="true" />
                  </a>
                ) : (
                  <span>{t('livecam.provider.missing')}</span>
                )}
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default LivecamPage;
