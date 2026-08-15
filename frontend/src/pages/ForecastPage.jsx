import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  Check,
  CloudRain,
  Info,
  MapPin,
  Sparkles,
  TableProperties,
  ThermometerSun,
  Waves,
  Wind,
} from 'lucide-react';
import { spots, weeklyForecast } from '../data/pongdangData';
import { useI18n } from '../i18n';
import './ForecastPage.css';

const ACTIVITY_OPTIONS = [
  'swim', 'surf', 'relax', 'mudflat', 'onsen', 'rafting',
];

const statusLabel = (t, tone) => t(`forecast.status.${tone}`);

const toArray = (value) => (Array.isArray(value) ? value : []);

const toNumber = (value) => {
  const parsed = typeof value === 'string' ? Number.parseFloat(value) : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const clampScore = (value) => {
  const parsed = toNumber(value);
  return parsed === null ? null : Math.min(100, Math.max(0, Math.round(parsed)));
};

const getTone = (score) => {
  if (score === null) return 'unavailable';
  if (score >= 90) return 'excellent';
  if (score >= 80) return 'good';
  if (score >= 65) return 'fair';
  return 'caution';
};

const normalizeFactors = (factors) =>
  toArray(factors)
    .map((factor) => {
      if (typeof factor === 'string') return factor;
      return factor?.label || factor?.reason || factor?.text || '';
    })
    .filter(Boolean);

const getActivityScore = (entry, activity) => {
  const activityScores = entry?.scores || entry?.activityScores;
  if (activityScores && typeof activityScores === 'object') {
    const activityScore = clampScore(activityScores[activity]);
    if (activityScore !== null) return activityScore;
  }
  return clampScore(entry?.score);
};

const normalizeForecastEntry = (entry, index) => ({
  ...entry,
  id: entry?.id ?? `forecast-${index}`,
  region: String(entry?.region || '강릉'),
  date: String(entry?.date || `D+${index + 1}`),
  day: String(entry?.day || `${index + 1}일 후`),
  weather: String(entry?.weather || '예보 준비 중'),
  temperature: toNumber(entry?.temperature),
  waveHeight: toNumber(entry?.waveHeight),
  rainChance: toNumber(entry?.rainChance),
  factors: normalizeFactors(entry?.factors),
  freshness: entry?.freshness,
  best: typeof entry?.best === 'string' ? entry.best : '',
});

const FORECAST_DATA = toArray(weeklyForecast).map(normalizeForecastEntry);
const SPOT_DATA = toArray(spots);

const uniqueForecastRegions = [
  ...new Set(FORECAST_DATA.map((entry) => entry.region).filter(Boolean)),
];

const REGION_OPTIONS = uniqueForecastRegions.length
  ? uniqueForecastRegions
  : ['강릉', '전국'];

const formatMetric = (value, suffix, fallback = '미수집') =>
  value === null || value === undefined ? fallback : `${value}${suffix}`;

const regionMatches = (candidate, selectedRegion) => {
  if (selectedRegion === '전국') return true;
  const value = String(candidate || '');
  return value === selectedRegion || value.includes(selectedRegion) || selectedRegion.includes(value);
};

const getSpotActivityScore = (spot, activity) => {
  if (!spot?.scores || typeof spot.scores !== 'object') return null;
  return clampScore(spot.scores[activity]);
};

const resolveFreshnessLabel = (days, recommendedSpot) => {
  const forecastFreshness = days.find((day) => day.freshness)?.freshness;
  if (typeof forecastFreshness === 'string') return forecastFreshness;
  if (forecastFreshness?.updatedLabel) return forecastFreshness.updatedLabel;
  return recommendedSpot?.freshness?.updatedLabel || '실시간 API 연결 전 고정 예시';
};

function ForecastPage() {
  const { t } = useI18n();
  const [selectedRegion, setSelectedRegion] = useState(REGION_OPTIONS[0]);
  const [selectedActivity, setSelectedActivity] = useState('swim');
  const [selectedDayId, setSelectedDayId] = useState(null);

  const days = useMemo(() => {
    const scopedDays = FORECAST_DATA.filter((entry) => entry.region === selectedRegion);

    return scopedDays.slice(0, 7).map((entry) => {
      const resolvedScore = getActivityScore(entry, selectedActivity);
      return {
        ...entry,
        resolvedScore,
        tone: getTone(resolvedScore),
      };
    });
  }, [selectedActivity, selectedRegion]);

  const bestDay = useMemo(() => {
    if (!days.length) return null;
    const highestScore = Math.max(...days.map((day) => day.resolvedScore ?? -1));
    return days.find((day) => day.best && day.resolvedScore === highestScore)
      || days.find((day) => day.resolvedScore === highestScore)
      || days[0];
  }, [days]);

  const selectedDay = days.find((day) => day.id === selectedDayId) || bestDay || days[0];
  const activityLabel = t(`activity.${selectedActivity}`);

  const recommendedSpot = useMemo(() => {
    const scopedSpots = SPOT_DATA.filter((spot) => regionMatches(spot.region, selectedRegion));
    return scopedSpots
      .map((spot) => ({ ...spot, activityScore: getSpotActivityScore(spot, selectedActivity) }))
      .sort((a, b) => (b.activityScore ?? b.index ?? -1) - (a.activityScore ?? a.index ?? -1))[0] || null;
  }, [selectedActivity, selectedRegion]);

  const updateLabel = resolveFreshnessLabel(days, recommendedSpot);
  const displayRegion = selectedRegion;

  const resetForecast = () => {
    setSelectedRegion(REGION_OPTIONS[0]);
    setSelectedActivity('swim');
    setSelectedDayId(null);
  };

  return (
    <div className="forecast-page">
      <header className="forecast-hero" aria-labelledby="forecast-title">
        <div className="forecast-hero__content">
          <div className="forecast-kicker">
            <span className="forecast-demo-badge">DEMO DATA</span>
            <span>{updateLabel}</span>
          </div>
          <h1 id="forecast-title">{t('forecast.hero.title')}</h1>
          <p>{t('forecast.hero.description')}</p>
        </div>

        <div className="forecast-hero__signal" aria-label={t('forecast.signal.label')}>
          <CalendarDays aria-hidden="true" />
          <div>
            <strong>{t('forecast.signal.title')}</strong>
            <span>{t('forecast.signal.description')}</span>
          </div>
        </div>
      </header>

      <section className="forecast-controls" aria-labelledby="forecast-controls-title">
        <div className="forecast-controls__heading">
          <div>
            <span className="forecast-eyebrow">MY WATER FORECAST</span>
            <h2 id="forecast-controls-title">{t('forecast.controls.title')}</h2>
          </div>
          <p aria-live="polite">
            {t('forecast.controls.viewing', { region: displayRegion, activity: activityLabel })}
          </p>
        </div>

        <div className="forecast-control-groups">
          <fieldset className="forecast-choice-group">
            <legend>{t('forecast.region')}</legend>
            <div className="forecast-choice-list">
              {REGION_OPTIONS.map((region) => (
                <button
                  type="button"
                  key={region}
                  className={selectedRegion === region ? 'is-active' : ''}
                  aria-pressed={selectedRegion === region}
                  onClick={() => {
                    setSelectedRegion(region);
                    setSelectedDayId(null);
                  }}
                >
                  {region}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="forecast-choice-group">
            <legend>{t('forecast.purpose')}</legend>
            <div className="forecast-choice-list forecast-choice-list--activity">
              {ACTIVITY_OPTIONS.map((activityId) => (
                <button
                  type="button"
                  key={activityId}
                  className={selectedActivity === activityId ? 'is-active' : ''}
                  aria-pressed={selectedActivity === activityId}
                  onClick={() => {
                    setSelectedActivity(activityId);
                    setSelectedDayId(null);
                  }}
                >
                  {t(`activity.${activityId}`)}
                </button>
              ))}
            </div>
          </fieldset>
        </div>
      </section>

      {days.length ? (
        <>
          <div className="forecast-dashboard">
            <section className="forecast-week" aria-labelledby="forecast-week-title">
              <div className="forecast-section-heading">
                <div>
                  <span className="forecast-eyebrow">7-DAY WATER INDEX</span>
                  <h2 id="forecast-week-title">{t('forecast.week.title', { region: displayRegion })}</h2>
                </div>
                <div className="forecast-legend" aria-label={t('forecast.legend')}>
                  <span><i className="excellent" />90+ {t('forecast.status.excellent')}</span>
                  <span><i className="good" />80+ {t('forecast.status.good')}</span>
                  <span><i className="fair" />65+ {t('forecast.status.fair')}</span>
                  <span><i className="caution" />{t('forecast.status.caution')}</span>
                </div>
              </div>

              <div className="forecast-score-strip" aria-label="7일 Water Index">
                {days.map((day) => {
                  const isSelected = selectedDay?.id === day.id;
                  const isBest = bestDay?.id === day.id;
                  return (
                    <button
                      type="button"
                      key={day.id}
                      className={`forecast-day forecast-day--${day.tone}${isSelected ? ' is-selected' : ''}`}
                      style={{ '--forecast-score': `${day.resolvedScore ?? 0}%` }}
                      aria-pressed={isSelected}
                      aria-label={`${day.date} ${day.day}, ${activityLabel} Water Index ${day.resolvedScore ?? t('common.noData')}, ${statusLabel(t, day.tone)}${isBest ? `, ${t('forecast.table.recommended')}` : ''}`}
                      onClick={() => setSelectedDayId(day.id)}
                    >
                      <span className="forecast-day__date">
                        <strong>{day.day}</strong>
                        <small>{day.date}</small>
                      </span>
                      <span className="forecast-day__track" aria-hidden="true">
                        <span className="forecast-day__fill" />
                        <span className="forecast-day__score">{day.resolvedScore ?? '—'}</span>
                      </span>
                      <span className="forecast-day__weather">{day.weather}</span>
                      <span className="forecast-day__status">
                        {isBest && <Sparkles size={14} aria-hidden="true" />}
                        {isBest ? 'BEST' : statusLabel(t, day.tone)}
                      </span>
                    </button>
                  );
                })}
              </div>

              <p className="forecast-data-note">
                <Info size={16} aria-hidden="true" />
                {t('forecast.note')}
              </p>
            </section>

            <aside className="forecast-best-card" aria-labelledby="forecast-best-title">
              <span className="forecast-best-card__label">
                <Sparkles size={16} aria-hidden="true" /> {t('forecast.best.label')}
              </span>
              <div className="forecast-best-card__score" aria-hidden="true">
                <span>{bestDay?.resolvedScore ?? '—'}</span>
                <small>/ 100</small>
              </div>
              <h2 id="forecast-best-title">
                {t('forecast.best.title', { day: bestDay?.day, activity: activityLabel })}
              </h2>
              <p>
                {bestDay?.label || t('forecast.best.description', { date: bestDay?.date })}
              </p>

              <ul className="forecast-reason-list">
                {(bestDay?.factors.length
                  ? bestDay.factors
                  : [t('forecast.best.factor'), t('forecast.best.weatherFactor', { weather: bestDay?.weather || t('common.loading') })]
                ).slice(0, 3).map((factor) => (
                  <li key={factor}>
                    <Check size={16} aria-hidden="true" />
                    <span>{factor}</span>
                  </li>
                ))}
              </ul>

              {recommendedSpot && (
                <div className="forecast-spot-pick">
                  <span>{t('forecast.spot.label')}</span>
                  <strong>{recommendedSpot.name}</strong>
                  <small>
                    {recommendedSpot.typeLabel || recommendedSpot.type}
                    {recommendedSpot.activityScore !== null && recommendedSpot.activityScore !== undefined
                      ? ` · ${t('forecast.spot.current', { activity: activityLabel, score: recommendedSpot.activityScore })}`
                      : ''}
                  </small>
                  <Link to={`/spot/${recommendedSpot.id}`}>
                    {t('forecast.spot.cta')} <ArrowUpRight size={15} aria-hidden="true" />
                  </Link>
                </div>
              )}
            </aside>
          </div>

          {selectedDay && (
            <section className="forecast-day-detail" aria-labelledby="forecast-detail-title">
              <div className="forecast-day-detail__intro">
                <span className="forecast-eyebrow">SELECTED DAY</span>
                <h2 id="forecast-detail-title">{selectedDay.date} · {selectedDay.day}요일</h2>
                <p>
                  {selectedDay.label || t('forecast.detail.demo', { weather: selectedDay.weather })}
                </p>
              </div>

              <dl className="forecast-metric-grid">
                <div>
                  <dt><ThermometerSun aria-hidden="true" /> {t('metric.airTemp')}</dt>
                  <dd>{formatMetric(selectedDay.temperature, '°C', t('common.noData'))}</dd>
                </div>
                <div>
                  <dt><Waves aria-hidden="true" /> {t('metric.waveHeight')}</dt>
                  <dd>{formatMetric(selectedDay.waveHeight, 'm', t('common.noData'))}</dd>
                </div>
                <div>
                  <dt><CloudRain aria-hidden="true" /> {t('metric.rainChance')}</dt>
                  <dd>{formatMetric(selectedDay.rainChance, '%', t('common.noData'))}</dd>
                </div>
                <div>
                  <dt><Wind aria-hidden="true" /> {t('metric.status')}</dt>
                  <dd>{statusLabel(t, getTone(selectedDay.resolvedScore))}</dd>
                </div>
              </dl>
            </section>
          )}

          <details className="forecast-table-panel">
            <summary>
              <span>
                <TableProperties aria-hidden="true" /> {t('forecast.table.open')}
              </span>
              <small>{t('forecast.table.description')}</small>
            </summary>
            <div className="forecast-table-wrap">
              <table>
                <caption>{displayRegion} · {activityLabel} · 7-day Water Index</caption>
                <thead>
                  <tr>
                    <th scope="col">{t('forecast.table.date')}</th>
                    <th scope="col">{t('forecast.table.weather')}</th>
                    <th scope="col">{t('metric.airTemp')}</th>
                    <th scope="col">{t('metric.waveHeight')}</th>
                    <th scope="col">{t('forecast.table.rain')}</th>
                    <th scope="col">Water Index</th>
                    <th scope="col">{t('forecast.table.decision')}</th>
                  </tr>
                </thead>
                <tbody>
                  {days.map((day) => (
                    <tr key={`table-${day.id}`}>
                      <th scope="row">{day.date} {day.day}</th>
                      <td>{day.weather}</td>
                      <td>{formatMetric(day.temperature, '°C', t('common.noData'))}</td>
                      <td>{formatMetric(day.waveHeight, 'm', t('common.noData'))}</td>
                      <td>{formatMetric(day.rainChance, '%', t('common.noData'))}</td>
                      <td>{day.resolvedScore ?? t('common.noData')}</td>
                      <td>{statusLabel(t, day.tone)}{bestDay?.id === day.id ? ` · ${t('forecast.table.recommended')}` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <footer className="forecast-source-note">
            <BarChart3 aria-hidden="true" />
            <div>
              <strong>{t('forecast.source.title')}</strong>
              <p>{t('forecast.source.description')}</p>
            </div>
          </footer>
        </>
      ) : (
        <section className="forecast-empty" role="status">
          <MapPin aria-hidden="true" />
          <h2>{t('forecast.empty.title', { region: selectedRegion })}</h2>
          <p>{t('forecast.empty.description')}</p>
          <button type="button" onClick={resetForecast}>{t('forecast.empty.cta')}</button>
        </section>
      )}
    </div>
  );
}

export default ForecastPage;
