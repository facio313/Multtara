import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronUp,
  Clock3,
  Compass,
  Database,
  Droplets,
  Info,
  Layers3,
  LocateFixed,
  Map as MapIcon,
  MapPin,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Thermometer,
  Waves,
  X,
} from 'lucide-react';
import {
  activityOptions,
  spotTypeOptions,
} from '../data/pongdangData';
import { useWaterSpots } from '../hooks/useWaterData';
import { localizedDataState, localizedSafety, useI18n } from '../i18n';
import {
  getSpotActivityView,
  scoreLabel,
} from '../services/waterData';
import {
  distanceKm,
  geolocationFailureKind,
  liveWaterTemperatureC,
  normalizeCoordinates,
  sortSpotsByDistance,
  waterTemperatureTone,
} from '../services/mapData';
import './MapPage.css';

const KAKAO_SDK_ID = 'pongdang-kakao-map-sdk';
const KAKAO_MAP_KEY = import.meta.env.VITE_KAKAO_MAP_KEY?.trim() ?? '';

let kakaoSdkPromise;

function loadKakaoMapsSdk(appKey) {
  if (!appKey) {
    return Promise.reject(new Error('Kakao Maps JavaScript key is missing.'));
  }

  if (window.kakao?.maps) {
    return new Promise((resolve) => {
      window.kakao.maps.load(() => resolve(window.kakao));
    });
  }

  if (kakaoSdkPromise) return kakaoSdkPromise;

  kakaoSdkPromise = new Promise((resolve, reject) => {
    const finishLoading = () => {
      if (!window.kakao?.maps) {
        reject(new Error('Kakao Maps SDK did not initialize.'));
        return;
      }
      window.kakao.maps.load(() => resolve(window.kakao));
    };

    const failLoading = () => reject(new Error('Kakao Maps SDK could not be loaded.'));
    const existingScript = document.getElementById(KAKAO_SDK_ID);

    if (existingScript) {
      existingScript.addEventListener('load', finishLoading, { once: true });
      existingScript.addEventListener('error', failLoading, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.id = KAKAO_SDK_ID;
    script.async = true;
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(appKey)}&autoload=false`;
    script.addEventListener('load', finishLoading, { once: true });
    script.addEventListener('error', failLoading, { once: true });
    document.head.appendChild(script);
  });

  return kakaoSdkPromise;
}

function getScoreTone(score) {
  if (score === null) return 'unknown';
  if (score >= 90) return 'excellent';
  if (score >= 84) return 'good';
  if (score >= 76) return 'fair';
  return 'check';
}

function getStatusIcon(level) {
  return level === 'clear' ? CheckCircle2 : AlertTriangle;
}

function MapStatusNotice({ status }) {
  const { t } = useI18n();
  const messages = {
    loading: {
      icon: Compass,
      title: t('map.status.loading.title'),
      description: t('map.status.loading.description'),
    },
    'missing-key': {
      icon: Info,
      title: t('map.status.missing.title'),
      description: t('map.status.missing.description'),
    },
    error: {
      icon: AlertTriangle,
      title: t('map.status.error.title'),
      description: t('map.status.error.description'),
    },
  };

  const message = messages[status];
  if (!message) return null;
  const Icon = message.icon;

  return (
    <div className={`pd-map-status pd-map-status-${status}`} role="status" aria-live="polite">
      <Icon size={17} aria-hidden="true" />
      <div>
        <strong>{message.title}</strong>
        <span>{message.description}</span>
      </div>
    </div>
  );
}

function WaterTwinFallback({
  filteredSpots,
  activity,
  layerMode,
  selectedId,
  onSelect,
  dimmed = false,
}) {
  const { t } = useI18n();
  return (
    <div
      className={`pd-map-fallback${dimmed ? ' is-dimmed' : ''}`}
      role="region"
      aria-label={t('map.explorer')}
    >
      <div className="pd-map-fallback-grid" aria-hidden="true" />
      <div className="pd-map-water-shape pd-map-water-east" aria-hidden="true" />
      <div className="pd-map-water-shape pd-map-water-west" aria-hidden="true" />
      <div className="pd-map-region-label pd-map-label-gangneung" aria-hidden="true">
        {t('map.fallback.gangneung')}
      </div>
      <div className="pd-map-region-label pd-map-label-korea" aria-hidden="true">
        {t('map.fallback.korea')}
      </div>

      {filteredSpots.map((spot) => {
        const view = getSpotActivityView(spot, activity);
        const isSelected = selectedId === spot.id;
        const waterTemperature = liveWaterTemperatureC(view);
        const markerTone = layerMode === 'temperature'
          ? `temperature-${waterTemperatureTone(waterTemperature)}`
          : getScoreTone(view.score);
        const markerValue = layerMode === 'temperature'
          ? (waterTemperature === null ? '—' : `${Math.round(waterTemperature)}°`)
          : scoreLabel(view);
        const markerLabel = layerMode === 'temperature'
          ? t('map.marker.temperature', {
            name: spot.name,
            temperature: waterTemperature === null
              ? t('common.noData')
              : t('map.temperature.value', { temperature: waterTemperature.toFixed(1) }),
          })
          : `${spot.name}, ${view.score === null ? t('common.scoreMissing') : t('common.points', { score: view.score })}, ${localizedSafety(t, view.safety.level).label}, ${localizedDataState(t, view.dataState)}`;
        return (
          <Link
            className={`pd-map-marker pd-map-marker-${markerTone}${layerMode === 'score' ? ` safety-${view.safety.level}` : ''}${isSelected ? ' is-selected' : ''}`}
            key={spot.id}
            to={`/spot/${spot.id}`}
            style={{
              '--marker-x': `${spot.visual.mapPosition.x}%`,
              '--marker-y': `${spot.visual.mapPosition.y}%`,
            }}
            aria-current={isSelected ? 'location' : undefined}
            aria-label={`${markerLabel}. ${t('map.marker.openDetail')}`}
            onClick={() => onSelect(spot.id)}
            onFocus={() => onSelect(spot.id)}
          >
            <span className="pd-map-marker-score">{markerValue}</span>
            <span className="pd-map-marker-name">{spot.name}</span>
          </Link>
        );
      })}

      {filteredSpots.length === 0 && (
        <div className="pd-map-fallback-empty">
          <MapPin size={24} aria-hidden="true" />
          <span>{t('map.empty.title')}</span>
        </div>
      )}
    </div>
  );
}

function MapPage() {
  const { intlLocale, t } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [scope, setScope] = useState(() => (searchParams.get('q')?.trim() ? 'nationwide' : 'gangneung'));
  const [activeType, setActiveType] = useState('all');
  const [activeActivity, setActiveActivity] = useState('swim');
  const [layerMode, setLayerMode] = useState('score');
  const [query, setQuery] = useState(() => searchParams.get('q')?.trim() ?? '');
  const [selectedSpotId, setSelectedSpotId] = useState(1);
  const [mapStatus, setMapStatus] = useState(KAKAO_MAP_KEY ? 'loading' : 'missing-key');
  const [locationState, setLocationState] = useState('idle');
  const [userLocation, setUserLocation] = useState(null);
  const {
    spots,
    spotStatus,
    conditionStatus,
    retryData,
  } = useWaterSpots(activeActivity);
  const mapCanvasRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const overlaysRef = useRef([]);

  const activeActivityLabel = t(`activity.${activeActivity}`);

  const filteredSpots = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR');
    const candidates = spots
      .filter((spot) => scope === 'nationwide' || spot.isGangneungMvp)
      .filter((spot) => activeType === 'all' || spot.type === activeType)
      .filter((spot) => {
        if (!normalizedQuery) return true;
        const searchTarget = [spot.name, spot.region, spot.address, ...spot.tags]
          .join(' ')
          .toLocaleLowerCase('ko-KR');
        return searchTarget.includes(normalizedQuery);
      });

    if (locationState === 'ready' && userLocation) {
      return sortSpotsByDistance(candidates, userLocation);
    }

    return candidates.sort((a, b) => {
        const aScore = getSpotActivityView(a, activeActivity).score;
        const bScore = getSpotActivityView(b, activeActivity).score;
        if (aScore === null && bScore === null) return a.name.localeCompare(b.name, 'ko-KR');
        if (aScore === null) return 1;
        if (bScore === null) return -1;
        return bScore - aScore;
      });
  }, [activeActivity, activeType, locationState, query, scope, spots, userLocation]);

  const selectedSpot =
    filteredSpots.find((spot) => spot.id === selectedSpotId) ?? filteredSpots[0] ?? null;
  const selectedView = selectedSpot
    ? getSpotActivityView(selectedSpot, activeActivity)
    : null;
  const selectedDistance = selectedSpot && userLocation
    ? distanceKm(userLocation, selectedSpot)
    : null;

  const formatDistance = (distance) => {
    if (!Number.isFinite(distance)) return '';
    const digits = distance < 10 ? 1 : 0;
    return t('map.nearby.distance', {
      distance: new Intl.NumberFormat(intlLocale, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(distance),
    });
  };

  const requestNearby = () => {
    if (!navigator.geolocation) {
      setUserLocation(null);
      setLocationState('unsupported');
      return;
    }

    setLocationState('requesting');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coordinates = normalizeCoordinates(position?.coords);
        if (!coordinates) {
          setUserLocation(null);
          setLocationState('error');
          return;
        }
        setUserLocation(coordinates);
        setLocationState('ready');
        setScope('nationwide');
      },
      (error) => {
        setUserLocation(null);
        setLocationState(geolocationFailureKind(error));
      },
      { enableHighAccuracy: false, maximumAge: 300_000, timeout: 10_000 },
    );
  };

  const clearNearby = () => {
    setUserLocation(null);
    setLocationState('idle');
  };

  useEffect(() => {
    if (!KAKAO_MAP_KEY) return undefined;

    let cancelled = false;
    loadKakaoMapsSdk(KAKAO_MAP_KEY)
      .then(() => {
        if (!cancelled) setMapStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setMapStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (mapStatus !== 'ready' || !mapCanvasRef.current || !window.kakao?.maps) {
      return undefined;
    }

    const { maps } = window.kakao;
    const initialCenter = new maps.LatLng(37.77, 128.9);

    if (!mapInstanceRef.current) {
      mapInstanceRef.current = new maps.Map(mapCanvasRef.current, {
        center: initialCenter,
        level: scope === 'gangneung' ? 8 : 13,
      });
      mapInstanceRef.current.addControl(
        new maps.ZoomControl(),
        maps.ControlPosition.RIGHT,
      );
    }

    const map = mapInstanceRef.current;
    overlaysRef.current.forEach(({ overlay, button, clickHandler }) => {
      button.removeEventListener('click', clickHandler);
      overlay.setMap(null);
    });
    overlaysRef.current = [];

    if (filteredSpots.length === 0) return undefined;

    const bounds = new maps.LatLngBounds();

    filteredSpots.forEach((spot) => {
      const position = new maps.LatLng(spot.lat, spot.lng);
      const view = getSpotActivityView(spot, activeActivity);
      const waterTemperature = liveWaterTemperatureC(view);
      const markerTone = layerMode === 'temperature'
        ? `temperature-${waterTemperatureTone(waterTemperature)}`
        : getScoreTone(view.score);
      const markerValue = layerMode === 'temperature'
        ? (waterTemperature === null ? '—' : `${Math.round(waterTemperature)}°`)
        : scoreLabel(view);
      const button = document.createElement('button');
      const scoreElement = document.createElement('strong');
      const nameElement = document.createElement('span');
      const clickHandler = () => {
        setSelectedSpotId(spot.id);
        navigate(`/spot/${spot.id}`);
      };

      button.type = 'button';
      button.className = `pd-kakao-marker pd-kakao-marker-${markerTone}${layerMode === 'score' ? ` safety-${view.safety.level}` : ''}`;
      button.setAttribute(
        'aria-label',
        layerMode === 'temperature'
          ? `${t('map.marker.temperature', {
            name: spot.name,
            temperature: waterTemperature === null
              ? t('common.noData')
              : t('map.temperature.value', { temperature: waterTemperature.toFixed(1) }),
          })}. ${t('map.marker.openDetail')}`
          : `${spot.name}, ${activeActivityLabel} ${view.score === null ? t('common.scoreMissing') : t('common.points', { score: view.score })}, ${localizedSafety(t, view.safety.level).label}. ${t('map.marker.openDetail')}`,
      );
      scoreElement.textContent = markerValue;
      nameElement.textContent = spot.name;
      button.append(scoreElement, nameElement);
      button.addEventListener('click', clickHandler);

      const overlay = new maps.CustomOverlay({
        position,
        content: button,
        xAnchor: 0.5,
        yAnchor: 1.1,
        zIndex: spot.isGangneungMvp ? 3 : 2,
      });
      overlay.setMap(map);
      overlaysRef.current.push({ overlay, button, clickHandler });
      bounds.extend(position);
    });

    if (filteredSpots.length === 1) {
      map.setCenter(new maps.LatLng(filteredSpots[0].lat, filteredSpots[0].lng));
      map.setLevel(6);
    } else {
      map.setBounds(bounds, 72, 72, 72, 72);
    }

    return () => {
      overlaysRef.current.forEach(({ overlay, button, clickHandler }) => {
        button.removeEventListener('click', clickHandler);
        overlay.setMap(null);
      });
      overlaysRef.current = [];
    };
  }, [activeActivity, activeActivityLabel, filteredSpots, layerMode, mapStatus, navigate, scope, t]);

  const clearFilters = () => {
    setQuery('');
    setActiveType('all');
    setScope('gangneung');
  };
  const dataLoading = ['idle', 'loading'].includes(spotStatus)
    || ['idle', 'loading'].includes(conditionStatus);
  const dataError = spotStatus === 'error' || conditionStatus === 'error';
  const dataEmpty = spotStatus === 'empty' || conditionStatus === 'empty';
  const dataBadge = dataError
    ? t('map.data.badge.error')
    : dataLoading
      ? t('map.data.badge.loading')
      : dataEmpty
        ? t('map.data.badge.empty')
        : t('map.data.badge.ready');

  return (
    <div className="pd-map-page">
      <header className="pd-map-hero">
        <div className="pd-map-hero-copy">
          <p className="pd-map-eyebrow">
            <Sparkles size={14} aria-hidden="true" />
            {t('map.eyebrow')}
          </p>
          <h1>{t('map.hero.title')}</h1>
          <p>{t('map.hero.description')}</p>
        </div>

        <div className={`pd-map-data-note state-${dataError ? 'error' : dataLoading ? 'loading' : dataEmpty ? 'demo' : 'live'}`} role="status" aria-live="polite">
          <span className="pd-map-demo-badge">
            <Database size={14} aria-hidden="true" />
            {dataBadge}
          </span>
          <div>
            <strong>{dataError
              ? t('map.data.error')
              : dataLoading
                ? t('map.data.loading')
                : dataEmpty
                  ? t('map.data.empty')
                  : t('map.data.ready')}</strong>
            <span>{t('common.unknownStopPolicy')}</span>
          </div>
          {dataError && <button type="button" onClick={retryData}>{t('common.retry')}</button>}
        </div>
      </header>

      <section className="pd-map-controls" aria-label={t('map.filters.label')}>
        <div className="pd-map-search">
          <Search size={18} aria-hidden="true" />
          <label className="sr-only" htmlFor="pd-map-search-input">
            {t('map.search.label')}
          </label>
          <input
            id="pd-map-search-input"
            type="search"
            value={query}
            placeholder={t('map.search.label')}
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <div className="pd-map-scope" role="group" aria-label={t('map.scope.label')}>
          <button
            type="button"
            className={scope === 'gangneung' ? 'is-active' : ''}
            aria-pressed={scope === 'gangneung'}
            onClick={() => setScope('gangneung')}
          >
            {t('map.scope.gangneung')}
          </button>
          <button
            type="button"
            className={scope === 'nationwide' ? 'is-active' : ''}
            aria-pressed={scope === 'nationwide'}
            onClick={() => setScope('nationwide')}
          >
            {t('map.scope.nationwide')}
          </button>
        </div>

        <label className="pd-map-activity-select" htmlFor="pd-map-activity">
          <SlidersHorizontal size={16} aria-hidden="true" />
          <span>{t('map.activity')}</span>
          <select
            id="pd-map-activity"
            value={activeActivity}
            onChange={(event) => setActiveActivity(event.target.value)}
          >
            {activityOptions.map((activity) => (
              <option value={activity.id} key={activity.id}>
                {activity.icon} {t(`activity.${activity.id}`)}
              </option>
            ))}
          </select>
        </label>

        <div className={`pd-map-nearby state-${locationState}`}>
          <button
            type="button"
            onClick={requestNearby}
            disabled={locationState === 'requesting'}
            aria-describedby="pd-map-nearby-status pd-map-nearby-privacy"
          >
            <LocateFixed size={16} aria-hidden="true" />
            {locationState === 'requesting'
              ? t('map.nearby.requesting')
              : locationState === 'ready'
                ? t('map.nearby.refresh')
                : t('map.nearby.use')}
          </button>
          {locationState === 'ready' && (
            <button
              type="button"
              className="pd-map-nearby-clear"
              onClick={clearNearby}
              aria-label={t('map.nearby.clear')}
            >
              <X size={14} aria-hidden="true" />
            </button>
          )}
          <span id="pd-map-nearby-status" className="pd-map-nearby-status" aria-live="polite">
            {locationState === 'idle'
              ? t('map.nearby.idle')
              : t(`map.nearby.${locationState}`)}
          </span>
          <small id="pd-map-nearby-privacy">{t('map.nearby.privacy')}</small>
        </div>

        <div className="pd-map-type-filters" role="group" aria-label={t('map.types')}>
          {spotTypeOptions.map((type) => (
            <button
              type="button"
              key={type.id}
              className={activeType === type.id ? 'is-active' : ''}
              aria-pressed={activeType === type.id}
              onClick={() => setActiveType(type.id)}
            >
              {t(`map.type.${type.id}`)}
            </button>
          ))}
        </div>
      </section>

      <section className="pd-map-explorer" aria-label={t('map.explorer')}>
        <div className="pd-map-panel">
          <div className="pd-map-panel-heading">
            <div>
              <span className="pd-map-panel-icon"><Layers3 size={17} aria-hidden="true" /></span>
              <div>
                <strong>{layerMode === 'temperature'
                  ? t('map.layer.temperature')
                  : t('map.layer.score', { activity: activeActivityLabel })}</strong>
                <span>{scope === 'gangneung' ? t('map.spots.gangneung') : t('map.spots.nationwide')} · {t('common.countPlaces', { count: filteredSpots.length })}</span>
              </div>
            </div>
            <div className="pd-map-layer-actions">
              <div className="pd-map-layer-switch" role="group" aria-label={t('map.layer.switch')}>
                <button
                  type="button"
                  className={layerMode === 'score' ? 'is-active' : ''}
                  aria-pressed={layerMode === 'score'}
                  onClick={() => setLayerMode('score')}
                >
                  <ShieldCheck size={14} aria-hidden="true" /> {t('map.layer.scoreButton')}
                </button>
                <button
                  type="button"
                  className={layerMode === 'temperature' ? 'is-active' : ''}
                  aria-pressed={layerMode === 'temperature'}
                  onClick={() => setLayerMode('temperature')}
                >
                  <Thermometer size={14} aria-hidden="true" /> {t('map.layer.temperatureButton')}
                </button>
              </div>
              <span className={`pd-map-sdk-state state-${mapStatus}`}>
                <span aria-hidden="true" />
                {mapStatus === 'ready' ? t('map.sdk.kakao') : t('map.sdk.concept')}
              </span>
            </div>
          </div>

          <div className="pd-map-canvas-wrap">
            <MapStatusNotice status={mapStatus} />

            {mapStatus === 'ready' ? (
              <div
                className="pd-map-kakao-canvas"
                ref={mapCanvasRef}
                role="region"
                aria-label={t('map.explorer')}
              />
            ) : (
              <WaterTwinFallback
                filteredSpots={filteredSpots}
                activity={activeActivity}
                layerMode={layerMode}
                selectedId={selectedSpot?.id}
                onSelect={setSelectedSpotId}
                dimmed={mapStatus === 'loading'}
              />
            )}

            {mapStatus === 'loading' && (
              <div className="pd-map-loading" aria-hidden="true">
                <span />
              </div>
            )}

            <div className="pd-map-legend" aria-label={t('map.legend')}>
              {layerMode === 'temperature' ? (
                <>
                  <span><i className="legend-temperature-very-cold" /> {t('map.temperature.veryCold')}</span>
                  <span><i className="legend-temperature-cold" /> {t('map.temperature.cold')}</span>
                  <span><i className="legend-temperature-cool" /> {t('map.temperature.cool')}</span>
                  <span><i className="legend-temperature-mild" /> {t('map.temperature.mild')}</span>
                  <span><i className="legend-temperature-warm" /> {t('map.temperature.warm')}</span>
                  <span><i className="legend-unknown" /> {t('map.temperature.missing')}</span>
                </>
              ) : (
                <>
                  <span><i className="legend-excellent" /> {t('map.legend.excellent')}</span>
                  <span><i className="legend-good" /> {t('map.legend.good')}</span>
                  <span><i className="legend-fair" /> {t('map.legend.check')}</span>
                  <span><i className="legend-caution" /> {t('map.legend.stop')}</span>
                  <span><i className="legend-unknown" /> {t('map.legend.unknown')}</span>
                </>
              )}
            </div>
          </div>
        </div>

        <aside className="pd-map-sheet" aria-label={t('map.results.label')}>
          <div className="pd-map-sheet-handle" aria-hidden="true"><ChevronUp size={18} /></div>
          <div className="pd-map-sheet-header">
            <div>
              <p>{locationState === 'ready'
                ? t('map.results.nearbyFirst')
                : t('map.results.curatedFor', { activity: activeActivityLabel })}</p>
              <h2>{t('map.results.title', { count: filteredSpots.length })}</h2>
            </div>
            <span>{scope === 'gangneung' ? t('map.results.gangneung') : t('map.results.nationwide')}</span>
          </div>

          {selectedSpot && selectedView ? (
            <article className="pd-map-featured" style={{ '--spot-accent': selectedSpot.visual.accent }}>
              <div className="pd-map-featured-top">
                <div>
                  <span className="pd-map-spot-type">{selectedSpot.typeLabel}</span>
                  <span className={`pd-map-safety-chip safety-${selectedView.safety.level}`}>
                    {localizedSafety(t, selectedView.safety.level).label}
                  </span>
                  <span className={`pd-map-data-chip state-${selectedView.dataState}`}>
                    {localizedDataState(t, selectedView.dataState)}
                  </span>
                </div>
                <div className={`pd-map-big-score score-${getScoreTone(selectedView.score)}`}>
                  <strong>{scoreLabel(selectedView)}</strong>
                  <span>{selectedView.score === null && selectedView.scoreRange.length === 2 ? t('map.scoreRange') : activeActivityLabel}</span>
                </div>
              </div>

              <div className="pd-map-featured-title">
                <span className="pd-map-featured-icon" aria-hidden="true">{selectedSpot.visual.icon}</span>
                <div>
                  <h3>{selectedSpot.name}</h3>
                  <p>
                    <MapPin size={14} aria-hidden="true" /> {selectedSpot.region}
                    {selectedDistance !== null ? ` · ${formatDistance(selectedDistance)}` : ''}
                  </p>
                </div>
              </div>

              <p className="pd-map-featured-summary">{selectedSpot.summary}</p>

              <dl className="pd-map-condition-row">
                <div>
                  <dt><Droplets size={14} aria-hidden="true" /> {t('metric.waterTemp')}</dt>
                  <dd>{selectedView.conditions.waterTemp}</dd>
                </div>
                <div>
                  <dt><Waves size={14} aria-hidden="true" /> {t('metric.waveHeight')}</dt>
                  <dd>{selectedView.conditions.waveHeight}</dd>
                </div>
                <div>
                  <dt><Compass size={14} aria-hidden="true" /> {t('metric.crowd')}</dt>
                  <dd>{selectedView.conditions.crowd}</dd>
                </div>
              </dl>

              <div className={`pd-map-safety-message safety-${selectedView.safety.level}`}>
                {(() => {
                  const SafetyIcon = getStatusIcon(selectedView.safety.level);
                  return <SafetyIcon size={16} aria-hidden="true" />;
                })()}
                <span>{localizedSafety(t, selectedView.safety.level).message}</span>
              </div>

              {selectedView.reasons.length > 0 && (
                <div className="pd-map-reason-codes" aria-label={t('map.reasons')}>
                  {selectedView.reasons.slice(0, 3).map((reason) => (
                    <span title={reason.label} key={reason.code}>{reason.code}</span>
                  ))}
                </div>
              )}

              <div className="pd-map-featured-footer">
                <span><Clock3 size={14} aria-hidden="true" /> {selectedView.provenance.updatedLabel}</span>
                <Link to={`/spot/${selectedSpot.id}`}>
                  {t('common.details')} <ArrowRight size={16} aria-hidden="true" />
                </Link>
              </div>
            </article>
          ) : (
            <div className="pd-map-no-results" role="status">
              <MapIcon size={30} aria-hidden="true" />
              <h3>{t('map.empty.title')}</h3>
              <p>{t('map.empty.description')}</p>
              <button type="button" onClick={clearFilters}>{t('common.resetFilters')}</button>
            </div>
          )}

          {filteredSpots.length > 0 && (
            <div className="pd-map-result-list" role="list" aria-label={t('map.results.label')}>
              {filteredSpots.map((spot, index) => {
                const view = getSpotActivityView(spot, activeActivity);
                const isSelected = selectedSpot?.id === spot.id;
                const spotDistance = userLocation ? distanceKm(userLocation, spot) : null;
                return (
                  <article
                    className={`pd-map-result-card${isSelected ? ' is-selected' : ''}`}
                    key={spot.id}
                    role="listitem"
                  >
                    <button
                      className="pd-map-result-select"
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => setSelectedSpotId(spot.id)}
                    >
                      <span className="pd-map-result-rank">{String(index + 1).padStart(2, '0')}</span>
                      <span className="pd-map-result-copy">
                        <strong>{spot.name}</strong>
                        <small>
                          {spot.region} · {spot.typeLabel} · {localizedDataState(t, view.dataState)}
                          {spotDistance !== null ? ` · ${formatDistance(spotDistance)}` : ''}
                        </small>
                      </span>
                      <span className={`pd-map-result-score score-${getScoreTone(view.score)} safety-${view.safety.level}`}>
                        <strong>{scoreLabel(view)}</strong>
                        <small>{view.score === null ? localizedSafety(t, view.safety.level).label : t('common.points', { score: '' }).trim()}</small>
                      </span>
                    </button>
                    <Link to={`/spot/${spot.id}`} aria-label={`${spot.name} ${t('common.details')}`}>
                      <ArrowRight size={16} aria-hidden="true" />
                    </Link>
                  </article>
                );
              })}
            </div>
          )}

          <div className="pd-map-sheet-footnote">
            <ShieldCheck size={16} aria-hidden="true" />
            <span>{t('map.policy')}</span>
          </div>
        </aside>
      </section>
    </div>
  );
}

export default MapPage;
