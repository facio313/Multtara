import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  Check,
  Clock3,
  Database,
  Info,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TableProperties,
} from 'lucide-react';
import { useDailyForecast } from '../hooks/useDailyForecast';
import { useWaterSpots } from '../hooks/useWaterData';
import { useI18n } from '../i18n';
import {
  bestEligibleForecast,
  DAILY_FORECAST_ACTIVITIES,
  DAILY_FORECAST_SKILL_LEVELS,
} from '../services/dailyForecastApi';
import './ForecastPage.css';

function formatDate(value, locale, fallback) {
  const date = new Date(`${value}T12:00:00`);
  if (!Number.isFinite(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

function formatDateTime(value, locale, fallback) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function toneForForecast(item) {
  if (!item.evidenceCurrent) return 'unavailable';
  if (['caution', 'stop'].includes(item.safetyStatus)) return 'caution';
  if (item.score === null || item.safetyStatus === 'unknown') {
    return 'unavailable';
  }
  if (item.score >= 90) return 'excellent';
  if (item.score >= 80) return 'good';
  if (item.score >= 65) return 'fair';
  return 'caution';
}

function localizedReason(t, reason) {
  const key = `forecast.reason.${reason}`;
  const translated = t(key);
  return translated === key ? reason : translated;
}

function ForecastPage() {
  const { intlLocale, t } = useI18n();
  const [searchParams] = useSearchParams();
  const { spots, spotStatus, retryData } = useWaterSpots(null, { loadConditions: false });
  const apiSpots = useMemo(() => spots.filter((spot) => (
    Number.isInteger(Number(spot.apiId)) && Number(spot.apiId) > 0
  )), [spots]);
  const requestedSpot = searchParams.get('spot');
  const requestedActivity = searchParams.get('activity');
  const requestedProfile = searchParams.get('profile');
  const requestedSkill = searchParams.get('skill');
  const initialActivity = DAILY_FORECAST_ACTIVITIES.includes(requestedActivity)
    ? requestedActivity
    : 'swim';
  const [selectedSpotId, setSelectedSpotId] = useState('');
  const [selectedActivity, setSelectedActivity] = useState(initialActivity);
  const [participantProfile, setParticipantProfile] = useState(
    initialActivity === 'swim' && requestedProfile === 'family' ? 'family' : 'general',
  );
  const [participantSkillLevel, setParticipantSkillLevel] = useState(
    DAILY_FORECAST_SKILL_LEVELS.includes(requestedSkill) ? requestedSkill : 'unspecified',
  );
  const [selectedDate, setSelectedDate] = useState('');

  const defaultSpotId = String(
    apiSpots.find((spot) => String(spot.apiId) === requestedSpot)?.apiId
    ?? apiSpots[0]?.apiId
    ?? '',
  );
  const effectiveSpotId = apiSpots.some((spot) => String(spot.apiId) === selectedSpotId)
    ? selectedSpotId
    : defaultSpotId;
  const selectedSpot = apiSpots.find((spot) => String(spot.apiId) === effectiveSpotId) ?? null;
  const forecast = useDailyForecast({
    spot: Number(effectiveSpotId) || null,
    activity: selectedActivity,
    participantProfile,
    participantSkillLevel: selectedActivity === 'surf' ? participantSkillLevel : 'unspecified',
    days: 7,
    enabled: Boolean(effectiveSpotId),
  });
  const rows = useMemo(() => forecast.data?.results ?? [], [forecast.data]);
  const bestDay = useMemo(() => bestEligibleForecast(rows), [rows]);
  const selectedDay = rows.find((row) => row.forecastDate === selectedDate)
    ?? bestDay
    ?? rows[0]
    ?? null;
  const activityLabel = t(`activity.${selectedActivity}`);
  const profileLabel = t(`forecast.profile.${participantProfile}`);
  const skillLabel = t(`concierge.skill.${participantSkillLevel}`);

  const selectFilter = (setter, value) => {
    setter(value);
    setSelectedDate('');
  };

  return (
    <div className="forecast-page">
      <header className="forecast-hero" aria-labelledby="forecast-title">
        <div className="forecast-hero__content">
          <div className="forecast-kicker">
            <span className="forecast-api-badge"><Database size={13} aria-hidden="true" /> API</span>
            <span>{t('forecast.api.exactQuery')}</span>
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
            <span className="forecast-eyebrow">{t('forecast.api.eyebrow')}</span>
            <h2 id="forecast-controls-title">{t('forecast.controls.title')}</h2>
          </div>
          <p aria-live="polite">
            {selectedSpot
              ? t('forecast.controls.viewingExact', {
                spot: selectedSpot.name,
                activity: activityLabel,
                profile: profileLabel,
              })
              : t('forecast.controls.waitingSpot')}
          </p>
        </div>

        <div className="forecast-api-controls">
          <label htmlFor="forecast-spot">
            <span>{t('forecast.spot.field')}</span>
            <select
              id="forecast-spot"
              value={effectiveSpotId}
              onChange={(event) => selectFilter(setSelectedSpotId, event.target.value)}
              disabled={['idle', 'loading'].includes(spotStatus) || apiSpots.length === 0}
            >
              <option value="">{t('forecast.spot.choose')}</option>
              {apiSpots.map((spot) => (
                <option key={spot.apiId} value={spot.apiId}>{spot.name} · {spot.region}</option>
              ))}
            </select>
          </label>
          <label htmlFor="forecast-activity">
            <span>{t('forecast.purpose')}</span>
            <select
              id="forecast-activity"
              value={selectedActivity}
              onChange={(event) => {
                const nextActivity = event.target.value;
                selectFilter(setSelectedActivity, nextActivity);
                if (nextActivity !== 'surf') setParticipantSkillLevel('unspecified');
                if (nextActivity !== 'swim') setParticipantProfile('general');
              }}
            >
              {DAILY_FORECAST_ACTIVITIES.map((activity) => (
                <option key={activity} value={activity}>{t(`activity.${activity}`)}</option>
              ))}
            </select>
          </label>
          {selectedActivity === 'swim' ? (
            <label htmlFor="forecast-profile">
              <span>{t('forecast.profile.field')}</span>
              <select
                id="forecast-profile"
                value={participantProfile}
                onChange={(event) => selectFilter(setParticipantProfile, event.target.value)}
              >
                <option value="general">{t('forecast.profile.general')}</option>
                <option value="family">{t('forecast.profile.family')}</option>
              </select>
            </label>
          ) : null}
          {selectedActivity === 'surf' ? (
            <label htmlFor="forecast-skill">
              <span>{t('forecast.skill.field')}</span>
              <select
                id="forecast-skill"
                value={participantSkillLevel}
                onChange={(event) => selectFilter(setParticipantSkillLevel, event.target.value)}
                aria-describedby="forecast-skill-help"
              >
                {DAILY_FORECAST_SKILL_LEVELS.map((skill) => (
                  <option key={skill} value={skill}>{t(`concierge.skill.${skill}`)}</option>
                ))}
              </select>
              <small id="forecast-skill-help">{t('forecast.skill.help')}</small>
            </label>
          ) : null}
        </div>
      </section>

      {['idle', 'loading'].includes(spotStatus) ? (
        <section className="forecast-empty" role="status" aria-live="polite">
          <LoaderCircle className="forecast-spinner" aria-hidden="true" />
          <h2>{t('forecast.spot.loading')}</h2>
          <p>{t('forecast.spot.loadingDescription')}</p>
        </section>
      ) : null}

      {!['idle', 'loading'].includes(spotStatus) && apiSpots.length === 0 ? (
        <section className="forecast-empty" role="alert">
          <ShieldAlert aria-hidden="true" />
          <h2>{t('forecast.spot.unavailable')}</h2>
          <p>{t('forecast.spot.unavailableDescription')}</p>
          <button type="button" onClick={retryData}><RefreshCw size={16} aria-hidden="true" /> {t('common.retry')}</button>
        </section>
      ) : null}

      {forecast.status === 'loading' ? (
        <section className="forecast-empty" role="status" aria-live="polite">
          <LoaderCircle className="forecast-spinner" aria-hidden="true" />
          <h2>{t('forecast.api.loading')}</h2>
          <p>{t('forecast.api.loadingDescription')}</p>
        </section>
      ) : null}

      {forecast.status === 'error' ? (
        <section className="forecast-empty is-error" role="alert">
          <ShieldAlert aria-hidden="true" />
          <h2>{t('forecast.api.errorTitle')}</h2>
          <p>{t(forecast.error?.messageKey || 'forecast.api.error.response')}</p>
          <button type="button" onClick={forecast.retry}><RefreshCw size={16} aria-hidden="true" /> {t('common.retry')}</button>
        </section>
      ) : null}

      {forecast.status === 'ready' ? (
        <>
          <div className="forecast-dashboard">
            <section className="forecast-week" aria-labelledby="forecast-week-title">
              <div className="forecast-section-heading">
                <div>
                  <span className="forecast-eyebrow">{t('forecast.week.eyebrow')}</span>
                  <h2 id="forecast-week-title">{t('forecast.week.titleExact', { spot: forecast.data.spotName })}</h2>
                </div>
                <div className="forecast-query-badge">
                  {activityLabel} · {profileLabel}{selectedActivity === 'surf' ? ` · ${skillLabel}` : ''} · {forecast.data.referenceTime}
                </div>
              </div>

              <div className="forecast-score-strip" aria-label={t('forecast.week.aria')}>
                {rows.map((day) => {
                  const isSelected = selectedDay?.forecastDate === day.forecastDate;
                  const isBest = bestDay?.forecastDate === day.forecastDate;
                  const tone = toneForForecast(day);
                  return (
                    <button
                      type="button"
                      key={day.forecastDate}
                      className={`forecast-day forecast-day--${tone}${isSelected ? ' is-selected' : ''}`}
                      style={{ '--forecast-score': `${day.score ?? 0}%` }}
                      aria-pressed={isSelected}
                      aria-label={t('forecast.day.aria', {
                        date: formatDate(day.forecastDate, intlLocale, day.forecastDate),
                        score: day.score ?? t('common.scoreMissing'),
                        safety: t(`forecast.safety.${day.safetyStatus}`),
                        availability: t(`forecast.availability.${day.availability}`),
                      })}
                      onClick={() => setSelectedDate(day.forecastDate)}
                    >
                      <span className="forecast-day__date">
                        <strong>{formatDate(day.forecastDate, intlLocale, day.forecastDate)}</strong>
                        <small>{day.forecastDate}</small>
                      </span>
                      <span className="forecast-day__track" aria-hidden="true">
                        <span className="forecast-day__fill" />
                        <span className="forecast-day__score">{day.score ?? '—'}</span>
                      </span>
                      <span className="forecast-day__weather">{t(`forecast.availability.${day.availability}`)}</span>
                      <span className="forecast-day__status">
                        {isBest ? <Sparkles size={14} aria-hidden="true" /> : null}
                        {isBest ? t('forecast.best.short') : t(`forecast.safety.${day.safetyStatus}`)}
                      </span>
                    </button>
                  );
                })}
              </div>

              <p className="forecast-data-note">
                <Info size={16} aria-hidden="true" />
                {t('forecast.note.evidence')}
              </p>
            </section>

            <aside className={`forecast-best-card${bestDay ? '' : ' is-unavailable'}`} aria-labelledby="forecast-best-title">
              {bestDay ? (
                <>
                  <span className="forecast-best-card__label"><Sparkles size={16} aria-hidden="true" /> {t('forecast.best.label')}</span>
                  <div className="forecast-best-card__score" aria-hidden="true"><span>{bestDay.score}</span><small>/ 100</small></div>
                  <h2 id="forecast-best-title">{t('forecast.best.titleExact', { date: formatDate(bestDay.forecastDate, intlLocale, bestDay.forecastDate), activity: activityLabel })}</h2>
                  <p>{t('forecast.best.descriptionExact')}</p>
                  <ul className="forecast-reason-list">
                    <li><Check size={16} aria-hidden="true" /><span>{t('forecast.best.reasonDecision')}</span></li>
                    <li><Check size={16} aria-hidden="true" /><span>{t('forecast.best.reasonCurrent')}</span></li>
                    <li><Check size={16} aria-hidden="true" /><span>{t('forecast.best.reasonAvailable')}</span></li>
                  </ul>
                </>
              ) : (
                <>
                  <span className="forecast-best-card__label"><ShieldAlert size={16} aria-hidden="true" /> {t('forecast.safety.unknown')}</span>
                  <div className="forecast-best-card__score" aria-hidden="true"><span>—</span></div>
                  <h2 id="forecast-best-title">{t('forecast.best.noneTitle')}</h2>
                  <p>{t('forecast.best.noneDescription')}</p>
                </>
              )}

              {selectedSpot ? (
                <div className="forecast-spot-pick">
                  <span>{t('forecast.spot.selected')}</span>
                  <strong>{selectedSpot.name}</strong>
                  <small>{selectedSpot.typeLabel} · {selectedSpot.region}</small>
                  <Link to={`/spot/${encodeURIComponent(selectedSpot.id)}`}>
                    {t('forecast.spot.cta')} <ArrowUpRight size={15} aria-hidden="true" />
                  </Link>
                </div>
              ) : null}
            </aside>
          </div>

          {selectedDay ? (
            <section className="forecast-day-detail" aria-labelledby="forecast-detail-title">
              <div className="forecast-day-detail__intro">
                <span className="forecast-eyebrow">{t('forecast.detail.provenance')} · {t(selectedDay.evidenceCurrent ? 'forecast.current.yes' : 'forecast.current.no')}</span>
                <h2 id="forecast-detail-title">{formatDate(selectedDay.forecastDate, intlLocale, selectedDay.forecastDate)}</h2>
                <p>{selectedDay.unavailableReason
                  ? localizedReason(t, selectedDay.unavailableReason)
                  : t(`forecast.decision.${selectedDay.decision}`)}</p>
              </div>

              <dl className="forecast-provenance-grid">
                <div><dt>{t('forecast.detail.score')}</dt><dd>{selectedDay.score ?? t('common.scoreMissing')}</dd></div>
                <div><dt>{t('forecast.detail.safety')}</dt><dd>{t(`forecast.safety.${selectedDay.safetyStatus}`)}</dd></div>
                <div><dt>{t('forecast.detail.decision')}</dt><dd>{t(`forecast.decision.${selectedDay.decision}`)}</dd></div>
                <div><dt>{t('forecast.detail.availability')}</dt><dd>{t(`forecast.availability.${selectedDay.availability}`)}</dd></div>
                <div><dt>{t('forecast.detail.confidence')}</dt><dd>{Math.round(selectedDay.confidence * 100)}%</dd></div>
                <div><dt>{t('forecast.detail.coverage')}</dt><dd>{Math.round(selectedDay.coverage * 100)}%</dd></div>
                <div><dt>{t('forecast.detail.providers')}</dt><dd>{selectedDay.providers.join(' · ') || t('common.noData')}</dd></div>
                <div><dt>{t('forecast.detail.fetched')}</dt><dd>{formatDateTime(selectedDay.evidenceFetchedAt, intlLocale, t('common.noData'))}</dd></div>
                <div><dt>{t('forecast.detail.validUntil')}</dt><dd>{formatDateTime(selectedDay.validUntil, intlLocale, t('common.noData'))}</dd></div>
                <div><dt>{t('forecast.detail.current')}</dt><dd>{t(selectedDay.evidenceCurrent ? 'forecast.current.yes' : 'forecast.current.no')}</dd></div>
              </dl>

              <div className="forecast-evidence-lists">
                <div>
                  <strong>{t('forecast.detail.missing')}</strong>
                  <p>{selectedDay.missingMetrics.join(' · ') || t('forecast.detail.none')}</p>
                </div>
                <div>
                  <strong>{t('forecast.detail.stale')}</strong>
                  <p>{selectedDay.staleOrConflictingMetrics.join(' · ') || t('forecast.detail.none')}</p>
                </div>
                <div>
                  <strong>{t('forecast.detail.method')}</strong>
                  <p>{selectedDay.methodologyVersion || forecast.data.methodologyVersion} · {selectedDay.projectionMethodologyVersion || forecast.data.projectionMethodologyVersion}</p>
                </div>
              </div>

              {selectedDay.evidence.length > 0 ? (
                <details className="forecast-evidence-details">
                  <summary><Database size={16} aria-hidden="true" /> {t('forecast.detail.evidenceOpen', { count: selectedDay.evidence.length })}</summary>
                  <ul>
                    {selectedDay.evidence.map((item, index) => (
                      <li key={`${item.metricId ?? item.name}-${index}`}>
                        <strong>{item.name || t('common.noData')}</strong>
                        <span>{item.provider || item.source || t('common.noData')} · {item.spatialScope || t('common.noData')}</span>
                        {item.sourceUrl ? <a href={item.sourceUrl} target="_blank" rel="noreferrer">{t('forecast.detail.sourceOpen')}</a> : null}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </section>
          ) : null}

          <details className="forecast-table-panel">
            <summary>
              <span><TableProperties aria-hidden="true" /> {t('forecast.table.open')}</span>
              <small>{t('forecast.table.descriptionExact')}</small>
            </summary>
            <div className="forecast-table-wrap">
              <table>
                <caption>{t('forecast.table.caption', { spot: forecast.data.spotName, activity: activityLabel, profile: profileLabel })}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t('forecast.table.date')}</th>
                    <th scope="col">Water Index</th>
                    <th scope="col">{t('forecast.detail.safety')}</th>
                    <th scope="col">{t('forecast.table.decision')}</th>
                    <th scope="col">{t('forecast.detail.availability')}</th>
                    <th scope="col">{t('forecast.detail.providers')}</th>
                    <th scope="col">{t('forecast.detail.current')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((day) => (
                    <tr key={`table-${day.forecastDate}`}>
                      <th scope="row">{formatDate(day.forecastDate, intlLocale, day.forecastDate)}</th>
                      <td>{day.score ?? t('common.scoreMissing')}</td>
                      <td>{t(`forecast.safety.${day.safetyStatus}`)}</td>
                      <td>{t(`forecast.decision.${day.decision}`)}{bestDay?.forecastDate === day.forecastDate ? ` · ${t('forecast.best.short')}` : ''}</td>
                      <td>{t(`forecast.availability.${day.availability}`)}</td>
                      <td>{day.providers.join(' · ') || t('common.noData')}</td>
                      <td>{t(day.evidenceCurrent ? 'forecast.current.yes' : 'forecast.current.no')}</td>
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
              <p>{t('forecast.source.descriptionExact')}</p>
            </div>
            <span><Clock3 size={14} aria-hidden="true" /> {forecast.data.startDate} · {forecast.data.days}</span>
          </footer>
        </>
      ) : null}
    </div>
  );
}

export default ForecastPage;
