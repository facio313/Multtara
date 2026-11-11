import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Accessibility,
  ArrowLeft,
  ArrowRight,
  Bath,
  CalendarDays,
  Camera,
  Check,
  ChevronRight,
  Clock3,
  CloudSun,
  Download,
  Droplets,
  ExternalLink,
  Heart,
  Info,
  MapPin,
  Navigation2,
  ParkingCircle,
  Radio,
  ShieldAlert,
  ShieldCheck,
  ShowerHead,
  Sparkles,
  ThermometerSun,
  Utensils,
  Waves,
  Wind,
} from 'lucide-react';
import { activityOptions, livecams } from '../data/pongdangData';
import { useDailyForecast } from '../hooks/useDailyForecast';
import { useWaterSpot } from '../hooks/useWaterData';
import { localizedDataState, localizedSafety, useI18n } from '../i18n';
import { bestEligibleForecast } from '../services/dailyForecastApi';
import {
  formatGateReason,
  formatMetricName,
  getSpotActivityView,
  isRecommendationEligible,
  scoreLabel,
} from '../services/waterData';
import './SpotDetailPage.css';

function facilityItems(t) {
  return {
    beach: [
      { icon: ShowerHead, title: t('spot.facility.shower.title'), meta: t('spot.facility.confirmBeforeVisit'), tag: t('spot.facility.tag.beach') },
      { icon: Bath, title: t('spot.facility.changing.title'), meta: t('spot.facility.hoursNote'), tag: t('spot.facility.tag.afterSwim') },
      { icon: ParkingCircle, title: t('spot.facility.parking.title'), meta: t('spot.facility.crowdNote'), tag: t('spot.facility.tag.travel') },
      { icon: Utensils, title: t('spot.facility.meal.title'), meta: t('spot.facility.mealPending'), tag: t('spot.facility.tag.food') },
    ],
    facility: [
      { icon: Bath, title: t('spot.facility.hours.title'), meta: t('spot.facility.hoursNote'), tag: t('spot.facility.tag.venue') },
      { icon: Accessibility, title: t('spot.facility.access.title'), meta: t('spot.facility.accessNote'), tag: t('spot.facility.tag.access') },
      { icon: ParkingCircle, title: t('spot.facility.entry.title'), meta: t('spot.facility.crowdNote'), tag: t('spot.facility.tag.travel') },
      { icon: Utensils, title: t('spot.facility.meal.title'), meta: t('spot.facility.mealPending'), tag: t('spot.facility.tag.food') },
    ],
    valley: [
      { icon: ShieldAlert, title: t('spot.facility.evacuation.title'), meta: t('spot.facility.evacuationNote'), tag: t('spot.facility.tag.safety') },
      { icon: ParkingCircle, title: t('spot.facility.entry.title'), meta: t('spot.facility.controlNote'), tag: t('spot.facility.tag.travel') },
      { icon: ShowerHead, title: t('spot.facility.wash.title'), meta: t('spot.facility.nearbyPending'), tag: t('spot.facility.tag.afterSwim') },
      { icon: Utensils, title: t('spot.facility.meal.title'), meta: t('spot.facility.mealPending'), tag: t('spot.facility.tag.food') },
    ],
    mudflat: [
      { icon: Clock3, title: t('spot.facility.return.title'), meta: t('spot.facility.tideNote'), tag: t('spot.facility.tag.safety') },
      { icon: ShowerHead, title: t('spot.facility.wash.title'), meta: t('spot.facility.confirmBeforeVisit'), tag: t('spot.facility.tag.afterActivity') },
      { icon: ParkingCircle, title: t('spot.facility.entry.title'), meta: t('spot.facility.siteNote'), tag: t('spot.facility.tag.travel') },
      { icon: Utensils, title: t('spot.facility.meal.title'), meta: t('spot.facility.mealPending'), tag: t('spot.facility.tag.food') },
    ],
    default: [
      { icon: Accessibility, title: t('spot.facility.access.title'), meta: t('spot.facility.accessPending'), tag: t('spot.facility.tag.access') },
      { icon: ParkingCircle, title: t('spot.facility.entry.title'), meta: t('spot.facility.confirmBeforeVisit'), tag: t('spot.facility.tag.travel') },
      { icon: ShieldCheck, title: t('spot.facility.safetyPoint.title'), meta: t('spot.facility.officialFirst'), tag: t('spot.facility.tag.safety') },
      { icon: Utensils, title: t('spot.facility.meal.title'), meta: t('spot.facility.mealPending'), tag: t('spot.facility.tag.food') },
    ],
  };
}

const FACILITY_GROUP_BY_TYPE = Object.freeze({
  beach: 'beach',
  coastal_road: 'beach',
  hotspring: 'facility',
  pool: 'facility',
  waterpark: 'facility',
  river: 'valley',
  valley: 'valley',
  lake: 'valley',
  waterfall: 'valley',
  riverside: 'valley',
  reservoir: 'valley',
  mudflat: 'mudflat',
});

function readFavorite(id) {
  try {
    return localStorage.getItem(`pongdang-favorite-${id}`) === 'true';
  } catch {
    return false;
  }
}

function writeFavorite(id, value) {
  try {
    localStorage.setItem(`pongdang-favorite-${id}`, String(value));
  } catch {
    // The UI remains usable when storage is blocked or full.
  }
}

function defaultActivityForSpot(spot) {
  if (!spot) return 'swim';
  const preferred = {
    hotspring: 'onsen',
    pool: 'onsen',
    waterpark: 'onsen',
    mudflat: 'mudflat',
    river: 'rafting',
    valley: 'rafting',
    lake: 'rafting',
    riverside: 'rafting',
    reservoir: 'rafting',
  }[spot.type] ?? 'swim';
  if (
    spot.conditionRecords?.[preferred]
    || (spot.scores?.[preferred] !== null && spot.scores?.[preferred] !== undefined)
  ) return preferred;
  return activityOptions.find((activity) => (
    spot.conditionRecords?.[activity.id]
    || (spot.scores?.[activity.id] !== null && spot.scores?.[activity.id] !== undefined)
  ))?.id ?? preferred;
}

function formatDateTime(value, locale, fallback) {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function formatForecastDate(value, locale, fallback) {
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    month: 'numeric',
    day: 'numeric',
  }).format(date);
}

function TypeSpecificPanel({ spot }) {
  const { t } = useI18n();
  if (['hotspring', 'pool', 'waterpark'].includes(spot.type)) {
    return (
      <section className="detail-panel type-panel type-hotspring">
        <div className="detail-section-heading">
          <div><span>FACILITY FIT</span><h2>{t('spot.type.hotspring.title')}</h2></div>
          <Sparkles size={21} />
        </div>
        <div className="benefit-grid">
          <div><span>{t('spot.type.hotspring.ingredientLabel')}</span><strong>{t('common.noData')}</strong><p>{t('spot.type.hotspring.ingredientNote')}</p></div>
          <div><span>WELLNESS</span><strong>{t('spot.type.hotspring.wellness')}</strong><p>{t('spot.type.hotspringDisclaimer')}</p></div>
          <div><span>{t('spot.type.hotspring.indoorLabel')}</span><strong>{t('spot.type.hotspring.indoorValue')}</strong><p>{t('spot.type.hotspring.indoorNote')}</p></div>
        </div>
      </section>
    );
  }

  if (spot.type === 'mudflat') {
    return (
      <section className="detail-panel type-panel type-tidal">
        <div className="detail-section-heading">
          <div><span>CATCH GUIDE</span><h2>{t('spot.type.mudflat.title')}</h2></div>
          <Clock3 size={21} />
        </div>
        <div className="catch-grid">
          <div><span>{t('spot.type.mudflat.nowLabel')}</span><strong>{t('common.noData')}</strong></div>
          <div className="catch-warning"><span>{t('spot.type.mudflat.checkLabel')}</span><strong>{t('spot.type.mudflat.checkValue')}</strong></div>
        </div>
      </section>
    );
  }

  if (['river', 'valley', 'lake', 'waterfall', 'riverside', 'reservoir'].includes(spot.type)) {
    return (
      <section className="detail-panel type-panel type-valley">
        <div className="detail-section-heading">
          <div><span>VALLEY RADAR</span><h2>{t('spot.type.valley.title')}</h2></div>
          <ShieldAlert size={21} />
        </div>
        <div className="radar-track" aria-label={t('spot.type.valley.radarUnavailable')}>
          <span className="radar-fill" />
          <span className="radar-marker" />
        </div>
        <div className="radar-labels"><span>{t('spot.type.valley.safe')}</span><strong>{t('common.noData')}</strong><span>{t('spot.type.valley.danger')}</span></div>
        <p>{t('spot.type.valleyDisclaimer')}</p>
      </section>
    );
  }

  return (
    <section className="detail-panel type-panel type-sea">
      <div className="detail-section-heading">
        <div><span>GOLDEN MOMENT</span><h2>{t('spot.type.sea.title')}</h2></div>
        <Camera size={21} />
      </div>
      <div className="golden-grid">
        <div><span>{t('spot.type.sea.sunsetLabel')}</span><strong>{t('common.noData')}</strong><p>{t('spot.type.sea.sunsetNote')}</p></div>
        <div><span>{t('spot.type.sea.asmrLabel')}</span><strong>{t('common.noData')}</strong><p>{t('spot.type.sea.asmrNote')}</p></div>
        <div><span>{t('spot.type.sea.qualityLabel')}</span><strong>{t('spot.type.sea.qualityPending')}</strong><p>{t('spot.type.sea.qualityNote')}</p></div>
      </div>
    </section>
  );
}

function SpotDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { intlLocale, t } = useI18n();
  const {
    spot,
    spotStatus,
    conditionStatus,
    observationStatus,
    retryData,
  } = useWaterSpot(id);
  const [requestedActivity, setRequestedActivity] = useState(null);
  const [saved, setSaved] = useState(() => readFavorite(id));
  const forecastActivity = requestedActivity ?? defaultActivityForSpot(spot);
  const dailyForecast = useDailyForecast({
    spot: spot?.apiId,
    activity: forecastActivity,
    participantProfile: 'general',
    days: 7,
    enabled: Number.isInteger(Number(spot?.apiId)) && Number(spot?.apiId) > 0,
  });

  if (!spot) {
    if (spotStatus === 'idle' || spotStatus === 'loading') {
      return (
        <div className="detail-not-found detail-loading" role="status" aria-live="polite">
          <Droplets size={34} />
          <h1>{t('spot.loading.title')}</h1>
          <p>{t('spot.loading.description')}</p>
        </div>
      );
    }
    return (
      <div className="detail-not-found">
        <Droplets size={34} />
        <h1>{t('spot.notFound.title')}</h1>
        <p>{t('spot.notFound.description')}</p>
        <Link to="/map">{t('spot.notFound.cta')} <ArrowRight size={16} /></Link>
      </div>
    );
  }

  const selectedActivity = forecastActivity;
  const selectedView = getSpotActivityView(spot, selectedActivity);
  const selectedSafety = localizedSafety(t, selectedView.safety.level);
  const forecastRows = dailyForecast.data?.results ?? [];
  const bestForecast = bestEligibleForecast(forecastRows);
  const facilities = facilityItems(t)[FACILITY_GROUP_BY_TYPE[spot.type]] ?? facilityItems(t).default;
  const availableActivities = activityOptions.filter((activity) => (
    spot.conditionRecords?.[activity.id]
    || (spot.scores?.[activity.id] !== null && spot.scores?.[activity.id] !== undefined)
  ));
  const livecam = livecams.find((cam) => cam.id === spot.livecamId);
  const detailDataError = spotStatus === 'error'
    || conditionStatus === 'error'
    || observationStatus === 'error';
  const detailDataLoading = !detailDataError && (['idle', 'loading'].includes(spotStatus)
    || (
      spot.apiId !== null
      && (
        ['idle', 'loading'].includes(conditionStatus)
        || ['idle', 'loading'].includes(observationStatus)
      )
    ));

  const moveActivityTab = (event, currentIndex) => {
    let nextIndex;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextIndex = (currentIndex + 1) % availableActivities.length;
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextIndex = (currentIndex - 1 + availableActivities.length) % availableActivities.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = availableActivities.length - 1;
    } else {
      return;
    }

    event.preventDefault();
    const nextActivity = availableActivities[nextIndex];
    setRequestedActivity(nextActivity.id);
    window.requestAnimationFrame(() => {
      document.getElementById(`activity-tab-${nextActivity.id}`)?.focus();
    });
  };

  const toggleSaved = () => {
    const next = !saved;
    setSaved(next);
    writeFavorite(id, next);
  };

  const downloadSafetyCard = () => {
    const content = [
      `${t('spot.card.title')} — ${spot.name}`,
      `${t('spot.card.address')}: ${spot.address}`,
      `${t('spot.card.activity')}: ${t(`activity.${selectedActivity}`)}`,
      `${t('spot.card.safety')}: ${selectedSafety.label}`,
      `${t('spot.card.score')}: ${selectedView.score === null ? t('common.scoreMissing') : selectedView.score}`,
      `${t('spot.card.data')}: ${localizedDataState(t, selectedView.dataState)}`,
      selectedSafety.message,
      ...selectedView.reasons.map((reason) => `${t('spot.card.reason')}: ${reason.code} — ${formatGateReason(reason.code, t)}`),
      `${t('spot.evidence.provider')}: ${selectedView.provenance.provider}`,
      `${t('spot.evidence.scope')}: ${selectedView.provenance.spatialScope}`,
      `${t('spot.card.updated')}: ${selectedView.provenance.updatedLabel}`,
      t('common.scoreNotSafety'),
      t('common.officialFirst'),
    ].join('\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `pongdang-${spot.slug}-safety.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="spot-detail-page">
      <header className="detail-visual" style={{ '--detail-accent': spot.visual.accent }}>
        {spot.imageUrl
          ? <img src={spot.imageUrl} alt={`${spot.name}의 물 풍경`} />
          : <div className="detail-image-placeholder" aria-hidden="true">{spot.visual.icon}</div>}
        <div className="detail-visual-shade" />
        <div className="detail-top-actions">
          <button type="button" onClick={() => navigate(-1)} aria-label={t('spot.back')}><ArrowLeft size={20} /></button>
          <button type="button" className={saved ? 'saved' : ''} onClick={toggleSaved} aria-pressed={saved}>
            <Heart size={19} fill={saved ? 'currentColor' : 'none'} />
            {saved ? t('common.saved') : t('common.save')}
          </button>
        </div>

        <div className="detail-title-block">
          <div className="detail-badges">
            <span>{spot.typeLabel}</span>
            {spot.isGangneungMvp && <span>강릉 MVP</span>}
            <span className={`demo state-${selectedView.dataState}`}>
              {localizedDataState(t, selectedView.dataState)}
            </span>
          </div>
          <h1>{spot.name}</h1>
          <p><MapPin size={16} /> {spot.address}</p>
          <div className="detail-tags">{spot.tags.slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>
        </div>
      </header>

      <div className="detail-layout">
        <div className="detail-main">
          {detailDataLoading && (
            <div className="detail-data-status state-loading" role="status" aria-live="polite">
              <Droplets size={19} aria-hidden="true" />
              <div><strong>{t('spot.data.loading.title')}</strong><span>{t('spot.data.loading.description')}</span></div>
            </div>
          )}
          {spot.apiId !== null && conditionStatus === 'empty' && observationStatus === 'empty' && (
            <div className="detail-data-status state-empty" role="status" aria-live="polite">
              <ShieldAlert size={19} aria-hidden="true" />
              <div><strong>{t('spot.data.empty.title')}</strong><span>{t('spot.data.empty.description')}</span></div>
            </div>
          )}
          {detailDataError && (
            <div className="detail-data-status state-error" role="alert">
              <ShieldAlert size={19} />
              <div><strong>{t('spot.data.error.title')}</strong><span>{t('spot.data.error.description')}</span></div>
              <button type="button" onClick={retryData}>{t('common.retry')}</button>
            </div>
          )}
          <section className={`safety-banner safety-${selectedView.safety.level}`} aria-live={selectedView.safety.level === 'clear' ? 'polite' : 'assertive'}>
            <div className="safety-icon">
              {selectedView.safety.level === 'clear' ? <ShieldCheck size={23} /> : <ShieldAlert size={23} />}
            </div>
            <div><span>SAFETY FIRST · {t(`activity.${selectedActivity}`)}</span><strong>{selectedSafety.label}</strong><p>{selectedSafety.message}</p></div>
            <button type="button" onClick={downloadSafetyCard}><Download size={16} /> {t('spot.safety.offlineCard')}</button>
          </section>

          <section className="detail-panel score-panel">
            <div className="detail-section-heading">
              <div><span>ACTIVITY INDEX</span><h2>{t('spot.index.title')}</h2></div>
              <span className={`freshness-pill state-${selectedView.dataState}`}>{selectedView.provenance.updatedLabel}</span>
            </div>
            <div className="activity-score-grid" role="tablist" aria-label="활동별 Water Index" aria-orientation="horizontal">
              {availableActivities.map((activity, index) => {
                const view = getSpotActivityView(spot, activity.id);
                const isSelected = activity.id === selectedActivity;
                return (
                  <button
                    type="button"
                    role="tab"
                    id={`activity-tab-${activity.id}`}
                    aria-controls="activity-score-panel"
                    aria-selected={isSelected}
                    tabIndex={isSelected ? 0 : -1}
                    className={isSelected ? 'primary-score' : ''}
                    onClick={() => setRequestedActivity(activity.id)}
                    onKeyDown={(event) => moveActivityTab(event, index)}
                    key={activity.id}
                  >
                    <span>{t(`activity.${activity.id}`)}</span>
                    <strong>{scoreLabel(view)}</strong>
                    <small>{view.score === null ? localizedSafety(t, view.safety.level).label : localizedDataState(t, view.dataState)}</small>
                  </button>
                );
              })}
              {availableActivities.length === 0 && (
                <div className="score-empty"><strong>—</strong><span>{t('spot.index.empty')}</span></div>
              )}
            </div>
            <div
              id="activity-score-panel"
              role="tabpanel"
              aria-labelledby={availableActivities.length > 0
                ? `activity-tab-${selectedActivity}`
                : undefined}
              tabIndex={0}
            >
              <div className="score-confidence-row">
                <span>{t('spot.index.confidence')} <strong>{selectedView.confidence === null ? '—' : `${Math.round(selectedView.confidence * 100)}%`}</strong></span>
                <span>coverage <strong>{selectedView.coverage === null ? '—' : `${Math.round(selectedView.coverage * 100)}%`}</strong></span>
                {selectedView.score === null && selectedView.scoreRange.length === 2 && <span>{t('spot.index.range')} <strong>{selectedView.scoreRange.join('–')}</strong></span>}
                <span>{t('spot.index.method')} <strong>{selectedView.methodologyVersion}</strong></span>
              </div>
              <div className="score-reasons">
                <span>{t('spot.index.reasons')}</span>
                {selectedView.reasons.map((reason) => <p key={reason.code}><Check size={14} /><code>{reason.code}</code> {formatGateReason(reason.code, t)}</p>)}
                {selectedView.reasons.length === 0 && selectedView.isDemoFallback
                  ? spot.reasons.map((reason) => <p key={reason}><Check size={14} /> {reason} <em>DEMO</em></p>)
                  : null}
                {selectedView.reasons.length === 0 && !selectedView.isDemoFallback && <p><ShieldAlert size={14} /> {t('spot.index.noReason')}</p>}
              </div>
            </div>
          </section>

          <section className="detail-panel condition-panel">
            <div className="detail-section-heading">
              <div><span>CONDITION</span><h2>{t('spot.conditions.title')}</h2></div>
              <CloudSun size={21} />
            </div>
            <div className="metric-grid">
              <div><ThermometerSun size={21} /><span>{t('metric.waterTemp')}</span><strong>{selectedView.conditions.waterTemp}</strong></div>
              <div><CloudSun size={21} /><span>{t('metric.airTemp')}</span><strong>{selectedView.conditions.airTemp}</strong></div>
              <div><Waves size={21} /><span>{t('metric.waveHeight')}</span><strong>{selectedView.conditions.waveHeight}</strong></div>
              <div><Wind size={21} /><span>{t('metric.wind')}</span><strong>{selectedView.conditions.windSpeed}</strong></div>
              <div><Droplets size={21} /><span>{t('metric.waterQuality')}</span><strong>{selectedView.conditions.waterQuality}</strong></div>
              <div><Accessibility size={21} /><span>{t('metric.crowd')}</span><strong>{selectedView.conditions.crowd}</strong></div>
            </div>
            {spot.type === 'beach' || spot.type === 'mudflat' ? (
              <div className="tide-timeline">
                <div><span>{t('spot.conditions.lowTide')}</span><strong>{selectedView.conditions.tide.low}</strong></div>
                <div className="tide-line"><span className="tide-progress" /></div>
                <div><span>{t('spot.conditions.highTide')}</span><strong>{selectedView.conditions.tide.high}</strong></div>
              </div>
            ) : null}
          </section>

          <section className="detail-panel evidence-panel" aria-labelledby="evidence-title">
            <div className="detail-section-heading">
              <div><span>PROVENANCE & LIMITS</span><h2 id="evidence-title">{t('spot.evidence.title')}</h2></div>
              <span className={`freshness-pill state-${selectedView.dataState}`}>{localizedDataState(t, selectedView.dataState, true)}</span>
            </div>
            <dl className="provenance-grid">
              <div><dt>{t('spot.evidence.provider')}</dt><dd>{selectedView.provenance.provider}</dd></div>
              <div><dt>{t('spot.evidence.scope')}</dt><dd>{selectedView.provenance.spatialScope}</dd></div>
              <div><dt>{t('spot.evidence.observed')}</dt><dd>{formatDateTime(selectedView.provenance.observedAt, intlLocale, t('common.noData'))}</dd></div>
              <div><dt>{t('spot.evidence.fetched')}</dt><dd>{formatDateTime(selectedView.provenance.fetchedAt, intlLocale, t('common.noData'))}</dd></div>
              <div><dt>{t('spot.evidence.validUntil')}</dt><dd>{formatDateTime(selectedView.provenance.validUntil, intlLocale, t('common.noData'))}</dd></div>
              <div><dt>{t('spot.evidence.version')}</dt><dd>{selectedView.methodologyVersion}</dd></div>
            </dl>
            <div className="evidence-lists">
              <div>
                <span>{t('spot.evidence.missing')}</span>
                {selectedView.missingMetrics.length > 0
                  ? selectedView.missingMetrics.map((metric) => <strong key={metric}>{formatMetricName(metric, t)}</strong>)
                  : <small>{t('spot.evidence.noMissing')}</small>}
              </div>
              <div>
                <span>{t('spot.evidence.stale')}</span>
                {selectedView.staleMetrics.length > 0
                  ? selectedView.staleMetrics.map((metric) => <strong key={metric}>{formatMetricName(metric, t)}</strong>)
                  : <small>{t('spot.evidence.noStale')}</small>}
              </div>
              <div>
                <span>{t('spot.evidence.limits')}</span>
                {selectedView.limitations.length > 0
                  ? selectedView.limitations.map((limitation) => <strong key={limitation}>{limitation}</strong>)
                  : <small>{t('spot.evidence.noLimits')}</small>}
              </div>
            </div>
            {selectedView.contributions.length > 0 && (
              <div className="contribution-list">
                <span>{t('spot.evidence.contributions')}</span>
                {selectedView.contributions.slice(0, 6).map((contribution, index) => (
                  <div key={`${contribution.metric_name ?? 'metric'}-${index}`}>
                    <strong>{formatMetricName(contribution.metric_name ?? 'metric', t)}</strong>
                    <span>{contribution.weighted_points == null ? t('spot.evidence.reflected') : `${Number(contribution.weighted_points).toFixed(1)} pt`}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="detail-panel forecast-panel">
            <div className="detail-section-heading">
              <div>
                <span>{t(spot.apiId === null ? 'spot.forecast.eyebrowDemo' : 'spot.forecast.eyebrowApi')}</span>
                <h2>{t('spot.forecast.title')}</h2>
              </div>
              <Link to={spot.apiId === null
                ? '/forecast'
                : `/forecast?spot=${encodeURIComponent(spot.apiId)}&activity=${encodeURIComponent(selectedActivity)}&profile=general`}>
                {t('spot.forecast.all')} <ChevronRight size={16} />
              </Link>
            </div>
            {spot.apiId === null ? (
              <div className="detail-forecast-state is-demo" role="status">
                <ShieldAlert size={19} aria-hidden="true" />
                <div><strong>{t('spot.forecast.demoTitle')}</strong><p>{t('spot.forecast.demoDescription')}</p></div>
              </div>
            ) : null}
            {spot.apiId !== null && dailyForecast.status === 'loading' ? (
              <div className="detail-forecast-state" role="status" aria-live="polite">
                <Droplets size={19} aria-hidden="true" />
                <div><strong>{t('spot.forecast.loading')}</strong><p>{t('spot.forecast.loadingDescription')}</p></div>
              </div>
            ) : null}
            {spot.apiId !== null && dailyForecast.status === 'error' ? (
              <div className="detail-forecast-state is-error" role="alert">
                <ShieldAlert size={19} aria-hidden="true" />
                <div><strong>{t('spot.forecast.errorTitle')}</strong><p>{t(dailyForecast.error?.messageKey || 'forecast.api.error.response')}</p></div>
                <button type="button" onClick={dailyForecast.retry}>{t('common.retry')}</button>
              </div>
            ) : null}
            {spot.apiId !== null && dailyForecast.status === 'ready' ? (
              <>
                <div className="detail-forecast-strip" aria-label={t('spot.forecast.weekAria')}>
                  {forecastRows.map((day) => (
                    <div className={bestForecast?.forecastDate === day.forecastDate ? 'best' : ''} key={day.forecastDate}>
                      <span>{formatForecastDate(day.forecastDate, intlLocale, day.forecastDate)}</span>
                      <strong>{day.score ?? '—'}</strong>
                      <div className="forecast-mini-bar" aria-hidden="true"><span style={{ height: `${day.score ?? 0}%` }} /></div>
                      <small>{t(`forecast.safety.${day.safetyStatus}`)}</small>
                    </div>
                  ))}
                </div>
                {bestForecast ? (
                  <div className="best-day-note"><Sparkles size={18} aria-hidden="true" /><p>{t('spot.forecast.bestCurrent', { date: formatForecastDate(bestForecast.forecastDate, intlLocale, bestForecast.forecastDate) })}</p></div>
                ) : (
                  <div className="best-day-note is-unknown"><ShieldAlert size={18} aria-hidden="true" /><p>{t('spot.forecast.noBest')}</p></div>
                )}
                <dl className="detail-forecast-provenance">
                  <div><dt>{t('forecast.detail.availability')}</dt><dd>{forecastRows[0] ? t(`forecast.availability.${forecastRows[0].availability}`) : t('common.noData')}</dd></div>
                  <div><dt>{t('forecast.detail.providers')}</dt><dd>{forecastRows[0]?.providers.join(' · ') || t('common.noData')}</dd></div>
                  <div><dt>{t('forecast.detail.validUntil')}</dt><dd>{formatDateTime(forecastRows[0]?.validUntil, intlLocale, t('common.noData'))}</dd></div>
                  <div><dt>{t('forecast.detail.current')}</dt><dd>{t(forecastRows[0]?.evidenceCurrent ? 'forecast.current.yes' : 'forecast.current.no')}</dd></div>
                </dl>
                <p className="detail-forecast-policy"><Info size={15} aria-hidden="true" /> {t('spot.forecast.policy')}</p>
              </>
            ) : null}
          </section>

          <section className="detail-panel route-panel">
            <div className="detail-section-heading">
              <div><span>PRE / POST ROUTE · DEMO</span><h2>{spot.typeLabel} 방문 전후 확인할 것</h2></div>
              <Navigation2 size={21} />
            </div>
            <div className="facility-grid">
              {facilities.map(({ icon: Icon, title, meta, tag }) => (
                <article key={title}>
                  <div><Icon size={19} /></div><span>{tag}</span><h3>{title}</h3><p>{meta}</p>
                </article>
              ))}
            </div>
          </section>

          {livecam ? (
            <section className="detail-panel detail-livecam">
              <div className="livecam-poster"><img src={livecam.poster} alt={`${livecam.name} DEMO`} /><span><Radio size={15} /> {t('spot.livecam.demoPreview')}</span></div>
              <div><span>SEE IT YOURSELF</span><h2>{livecam.name}</h2><p>{t('spot.livecam.notLive')}</p><Link to="/livecam">{t('spot.livecam.cta')} <ArrowRight size={16} /></Link></div>
            </section>
          ) : null}

          <TypeSpecificPanel spot={spot} />
        </div>

        <aside className="detail-sidebar">
          <div className={`sidebar-index-card state-${selectedView.dataState}`}>
            <span>SUITABILITY · {t(`activity.${selectedActivity}`)}</span>
            <div className={`sidebar-score score-${selectedView.score === null ? 'unknown' : 'known'}`} style={{ '--score': selectedView.score ?? 0 }}><strong>{scoreLabel(selectedView)}</strong></div>
            <h2>{spot.summary}</h2>
            <p>{spot.description}</p>
            <div><Clock3 size={16} /><span>{isRecommendationEligible(selectedView) ? t('spot.sidebar.recommendable') : t('spot.sidebar.decision')}</span><strong>{selectedView.isDemoFallback ? t('home.hero.demo') : t(`concierge.decision.${selectedView.decision}`)}</strong></div>
          </div>
          <div className={`source-card state-${selectedView.dataState}`}>
            <span>DATA STATUS · {localizedDataState(t, selectedView.dataState, true)}</span>
            <h3>{localizedDataState(t, selectedView.dataState)}</h3>
            <p>{t('spot.sidebar.policy')}</p>
            <ul>
              <li>{selectedView.provenance.provider}</li>
              <li>{selectedView.provenance.spatialScope}</li>
              <li>{selectedView.provenance.updatedLabel}</li>
              <li>{t('spot.sidebar.observations', { count: spot.observations?.length ?? 0 })}</li>
            </ul>
          </div>
        </aside>
      </div>

      <div className="detail-sticky-actions">
        <div><span>{spot.name} · {localizedDataState(t, selectedView.dataState)}</span><strong>{selectedView.isDemoFallback ? `${spot.bestTime} · DEMO` : selectedSafety.label}</strong></div>
        <a
          className="directions"
          href={`https://map.kakao.com/?q=${encodeURIComponent(`${spot.name} ${spot.address}`)}`}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={17} /> {t('spot.sidebar.kakaoMap')}
        </a>
        <Link
          className="plan-link"
          to={`/concierge?activity=${encodeURIComponent(selectedActivity)}&spot=${encodeURIComponent(spot.apiId ?? spot.id)}`}
        >
          <CalendarDays size={17} />
          {t('spot.plan.add')}
        </Link>
      </div>
    </div>
  );
}

export default SpotDetailPage;
