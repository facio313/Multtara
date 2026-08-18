import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowUpRight,
  BadgeCheck,
  Camera,
  CircleOff,
  Clock3,
  ExternalLink,
  Info,
  MapPin,
  Maximize2,
  RotateCcw,
  Search,
  ShieldCheck,
  Waves,
  X,
} from 'lucide-react';
import { livecams } from '../data/pongdangData';
import { useWaterSpots } from '../hooks/useWaterData';
import { localizedSafety, useI18n } from '../i18n';
import { buildLivecamCards } from '../services/livecamData';
import './LivecamPage.css';

const STATUS_FILTERS = ['all', 'official', 'unknown', 'demo'];
const ALL_REGIONS = '__all__';

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
  if (cam.availability === 'official') {
    return {
      icon: BadgeCheck,
      tone: 'official',
      label: t('livecam.status.official.label'),
      description: t('livecam.status.official.description'),
    };
  }
  if (cam.availability === 'unknown') {
    return {
      icon: Info,
      tone: 'unknown',
      label: t('livecam.status.unknown.label'),
      description: t('livecam.status.unknown.description'),
    };
  }
  return {
    icon: Camera,
    tone: 'demo',
    label: t('livecam.status.demo.label'),
    description: t('livecam.status.demo.description'),
  };
};

const formatCondition = (value, suffix = '') => {
  if (value === null || value === undefined || value === '') return null;
  return typeof value === 'number' ? `${value}${suffix}` : String(value);
};

function formatUpdatedLabel(cam, t, intlLocale) {
  if (cam.availability === 'demo') return t('livecam.updated.demo');
  if (!cam.verifiedAt) return t('livecam.updated.unknown');
  const date = new Date(cam.verifiedAt);
  if (Number.isNaN(date.getTime())) return t('livecam.updated.unknown');
  return t('livecam.updated.catalog', {
    date: new Intl.DateTimeFormat(intlLocale, { dateStyle: 'medium' }).format(date),
  });
}

function Poster({ cam, failed, focused = false, onError, t }) {
  if (cam.poster && !failed) {
    return (
      <img
        src={cam.poster}
        alt={t(focused ? 'livecam.poster.focusAlt' : 'livecam.poster.staticAlt', { name: cam.name })}
        loading={focused ? undefined : 'lazy'}
        onError={onError}
      />
    );
  }
  return (
    <div className="livecam-poster-fallback" role="img" aria-label={`${cam.name} ${t('livecam.poster.pending')}`}>
      <Waves aria-hidden="true" />
      <span>{t('livecam.poster.pending')}</span>
    </div>
  );
}

function LivecamPage() {
  const { intlLocale, t } = useI18n();
  const {
    spots,
    spotStatus,
    retryData,
  } = useWaterSpots(null, { loadConditions: false });
  const [statusFilter, setStatusFilter] = useState('all');
  const [regionFilter, setRegionFilter] = useState(ALL_REGIONS);
  const [query, setQuery] = useState('');
  const [focusedId, setFocusedId] = useState(null);
  const [failedPosters, setFailedPosters] = useState([]);
  const focusPanelRef = useRef(null);
  const closeButtonRef = useRef(null);
  const lastTriggerRef = useRef(null);

  const cameras = useMemo(() => buildLivecamCards(spots, livecams), [spots]);
  const regionOptions = useMemo(
    () => [...new Set(cameras.map((cam) => cam.region).filter(Boolean))],
    [cameras],
  );
  const filteredCams = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase(intlLocale);
    return cameras.filter((cam) => {
      const statusMatches = statusFilter === 'all' || cam.availability === statusFilter;
      const regionMatches = regionFilter === ALL_REGIONS || cam.region === regionFilter;
      const searchableText = [cam.name, cam.region, cam.spot?.typeLabel, ...cam.tags]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase(intlLocale);
      return statusMatches && regionMatches
        && (!normalizedQuery || searchableText.includes(normalizedQuery));
    });
  }, [cameras, intlLocale, query, regionFilter, statusFilter]);

  const focusedCam = cameras.find((cam) => cam.id === focusedId) || null;
  const officialCount = cameras.filter((cam) => cam.availability === 'official').length;
  const dataState = ['idle', 'loading'].includes(spotStatus)
    ? 'loading'
    : spotStatus === 'error'
      ? 'error'
      : spotStatus === 'empty'
        ? 'empty'
        : 'ready';

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
        'a[href], button:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])',
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
          <span className="livecam-eyebrow">{t('livecam.eyebrow.hero')}</span>
          <h1 id="livecam-title">{t('livecam.hero.title')}</h1>
          <p>{t('livecam.hero.description')}</p>
        </div>

        <dl className="livecam-hero__stats" aria-label={t('livecam.stats.label')}>
          <div>
            <dt>{t('livecam.stats.registered')}</dt>
            <dd>{cameras.length}</dd>
          </div>
          <div>
            <dt>{t('livecam.stats.official')}</dt>
            <dd>{officialCount}</dd>
          </div>
          <div>
            <dt>{t('livecam.stats.autoplay')}</dt>
            <dd>{t('livecam.autoplay.off')}</dd>
          </div>
        </dl>
      </header>

      <div className={`livecam-data-notice livecam-data-notice--${dataState}`} role="status" aria-live="polite">
        {dataState === 'error' ? <AlertTriangle aria-hidden="true" /> : <Info aria-hidden="true" />}
        <div>
          <strong>{t(`livecam.data.${dataState}.title`)}</strong>
          <span>{t(`livecam.data.${dataState}.description`)}</span>
        </div>
        {dataState === 'error' && (
          <button type="button" onClick={retryData}>{t('common.retry')}</button>
        )}
      </div>

      <section className="livecam-toolbar" aria-labelledby="livecam-filter-title">
        <div className="livecam-toolbar__heading">
          <div>
            <span className="livecam-eyebrow">{t('livecam.eyebrow.filters')}</span>
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

          <label className="livecam-region-filter" htmlFor="livecam-region-select">
            <span>{t('livecam.filters.region')}</span>
            <select
              id="livecam-region-select"
              value={regionFilter}
              onChange={(event) => setRegionFilter(event.target.value)}
            >
              <option value={ALL_REGIONS}>{t('livecam.filters.allRegions')}</option>
              {regionOptions.map((region) => (
                <option key={region} value={region}>{region}</option>
              ))}
            </select>
          </label>

          <label className="livecam-search" htmlFor="livecam-search-input">
            <span className="sr-only">{t('livecam.search.label')}</span>
            <Search aria-hidden="true" />
            <input
              id="livecam-search-input"
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
            <span className="livecam-eyebrow">{t('livecam.eyebrow.results')}</span>
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
              const waterTemp = formatCondition(cam.conditions.waterTemp, '°C');
              const waveHeight = formatCondition(cam.conditions.waveHeight, 'm');
              const crowd = formatCondition(cam.conditions.crowd);
              const indexTone = getIndexTone(cam.waterIndex);
              const statusMeta = getStatusMeta(cam, t);
              const StatusIcon = statusMeta.icon;

              return (
                <article
                  className="livecam-card"
                  key={cam.id}
                  style={{ '--livecam-visual': cam.spot?.visual?.gradient || 'linear-gradient(145deg, #0b4f58, #69cbb7)' }}
                >
                  <div className="livecam-card__poster">
                    <Poster
                      cam={cam}
                      failed={posterFailed}
                      onError={() => markPosterFailed(cam.id)}
                      t={t}
                    />

                    <div className="livecam-card__overlay">
                      <span className={`livecam-state-badge livecam-state-badge--${statusMeta.tone}`}>
                        <StatusIcon aria-hidden="true" />
                        {statusMeta.label}
                      </span>
                      <span className={`livecam-index-badge livecam-index-badge--${indexTone}`}>
                        <small>{t('livecam.index.short')}</small>
                        <strong>{cam.waterIndex ?? '—'}</strong>
                      </span>
                    </div>

                    <span className="livecam-poster-kind">{t('livecam.poster.demoBadge')}</span>
                    <button
                      type="button"
                      className="livecam-focus-button"
                      aria-label={`${cam.name || t('livecam.place.unknown')} ${t('livecam.focus.open')}`}
                      aria-haspopup="dialog"
                      aria-controls="livecam-focus-dialog"
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
                        <p><MapPin aria-hidden="true" /> {cam.region || t('livecam.region.unknown')}</p>
                        <h3>{cam.name || t('livecam.place.unknown')}</h3>
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
                      <span>{cam.safety?.level
                        ? localizedSafety(t, cam.safety.level).label
                        : t('livecam.safety.missing')}</span>
                    </div>

                    {cam.tags.length > 0 && (
                      <ul className="livecam-tags" aria-label={t('livecam.tags')}>
                        {cam.tags.slice(0, 4).map((tag) => <li key={tag}>#{tag}</li>)}
                      </ul>
                    )}

                    <div className="livecam-card__footer">
                      <span><Clock3 aria-hidden="true" /> {formatUpdatedLabel(cam, t, intlLocale)}</span>
                      <div>
                        {cam.spot?.id && (
                          <Link to={`/spot/${cam.spot.id}`}>
                            {t('common.details')} <ArrowUpRight aria-hidden="true" />
                          </Link>
                        )}
                        {cam.officialUrl ? (
                          <a href={cam.officialUrl} target="_blank" rel="noopener noreferrer">
                            {t('livecam.link.official')} <ExternalLink aria-hidden="true" />
                          </a>
                        ) : (
                          <span className="livecam-link-unavailable">{t('livecam.link.unknown')}</span>
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

      {focusedCam && (() => {
        const statusMeta = getStatusMeta(focusedCam, t);
        const StatusIcon = statusMeta.icon;
        return (
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
                {focusedCam.embedUrl ? (
                  <iframe
                    src={focusedCam.embedUrl}
                    title={t('livecam.embed.title', { name: focusedCam.name })}
                    allow="encrypted-media; picture-in-picture; fullscreen"
                    allowFullScreen
                    loading="lazy"
                    referrerPolicy="strict-origin-when-cross-origin"
                    sandbox="allow-scripts allow-same-origin allow-presentation"
                  />
                ) : (
                  <Poster
                    cam={focusedCam}
                    failed={failedPosters.includes(focusedCam.id)}
                    focused
                    onError={() => markPosterFailed(focusedCam.id)}
                    t={t}
                  />
                )}
                <div className="livecam-focus-media__status">
                  <span className={`livecam-state-badge livecam-state-badge--${statusMeta.tone}`}>
                    <StatusIcon aria-hidden="true" />
                    {statusMeta.label}
                  </span>
                  <span>{t('livecam.autoplay.none')}</span>
                </div>
              </div>

              <div className="livecam-focus-copy">
                <span className="livecam-eyebrow">{t('livecam.eyebrow.focus')}</span>
                <h2 id="livecam-focus-title">{focusedCam.name || t('livecam.place.unknown')}</h2>
                <p id="livecam-focus-description">{statusMeta.description}</p>

                <div className="livecam-focus-summary">
                  <div>
                    <span>{t('livecam.index.title')}</span>
                    <strong>{focusedCam.waterIndex ?? '—'}</strong>
                    <small>{getIndexLabel(t, focusedCam.waterIndex)}</small>
                  </div>
                  <div>
                    <span>{t('livecam.filters.region')}</span>
                    <strong>{focusedCam.region || t('livecam.region.unknown')}</strong>
                    <small>{formatUpdatedLabel(focusedCam, t, intlLocale)}</small>
                  </div>
                </div>

                <div className="livecam-focus-actions">
                  {focusedCam.spot?.id && (
                    <Link to={`/spot/${focusedCam.spot.id}`} onClick={closeFocusMode}>
                      {t('livecam.place.details')} <ArrowUpRight aria-hidden="true" />
                    </Link>
                  )}
                  {focusedCam.officialUrl ? (
                    <a href={focusedCam.officialUrl} target="_blank" rel="noopener noreferrer">
                      {t('livecam.provider.open')} <ExternalLink aria-hidden="true" />
                    </a>
                  ) : (
                    <span>{t('livecam.provider.missing')}</span>
                  )}
                </div>
              </div>
            </section>
          </div>
        );
      })()}
    </div>
  );
}

export default LivecamPage;
