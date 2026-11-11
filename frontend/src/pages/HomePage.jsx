import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  ChevronRight,
  CloudSun,
  Compass,
  Droplets,
  Eye,
  Heart,
  Info,
  LocateFixed,
  MapPin,
  Navigation2,
  Play,
  Radio,
  Search,
  ShieldCheck,
  Sparkles,
  ThermometerSun,
  TrendingUp,
  Waves,
  Wind,
} from 'lucide-react';
import { livecams, personas, weeklyForecast } from '../data/pongdangData';
import { useWaterSpots } from '../hooks/useWaterData';
import { localizedDataState, localizedSafety, useI18n } from '../i18n';
import {
  formatGateReason,
  getSpotActivityView,
  isRecommendationEligible,
  scoreLabel,
} from '../services/waterData';
import './HomePage.css';

const pillars = [
  {
    eyebrow: 'NOW',
    titleKey: 'home.pillar.now.title',
    descriptionKey: 'home.pillar.now.description',
    icon: Droplets,
    tone: 'mint',
    to: '/map',
  },
  {
    eyebrow: 'WHEN',
    titleKey: 'home.pillar.when.title',
    descriptionKey: 'home.pillar.when.description',
    icon: CalendarDays,
    tone: 'blue',
    to: '/forecast',
  },
  {
    eyebrow: 'PREVIEW',
    titleKey: 'home.pillar.preview.title',
    descriptionKey: 'home.pillar.preview.description',
    icon: Radio,
    tone: 'coral',
    to: '/livecam',
  },
];

const activityTabs = ['swim', 'surf', 'relax', 'onsen'];

const personaActivities = {
  active: 'surf',
  family: 'swim',
  wellness: 'onsen',
  local: 'relax',
  indoor: 'onsen',
};

function readPersonaId() {
  try {
    return localStorage.getItem('pongdang:persona-preference');
  } catch {
    return null;
  }
}

function HomeDataStatus({ spotStatus, conditionStatus, onRetry }) {
  const { t } = useI18n();
  const isLoading = ['idle', 'loading'].includes(spotStatus)
    || ['idle', 'loading'].includes(conditionStatus);
  const isError = spotStatus === 'error' || conditionStatus === 'error';
  const isEmpty = spotStatus === 'empty' || conditionStatus === 'empty';
  const Icon = isError ? AlertTriangle : Info;
  let title = t('home.data.ready.title');
  let description = t('home.data.ready.description');

  if (isError) {
    title = t('home.data.error.title');
    description = t('home.data.error.description');
  } else if (isLoading) {
    title = t('home.data.loading.title');
    description = t('home.data.loading.description');
  } else if (isEmpty) {
    title = t('home.data.empty.title');
    description = t('home.data.empty.description');
  }

  return (
    <section
      className={`home-data-note home-data-note-${isError ? 'error' : isLoading ? 'loading' : isEmpty ? 'empty' : 'ready'}`}
      aria-label={t('home.data.label')}
      aria-live="polite"
    >
      <Icon size={18} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
      {isError ? (
        <button type="button" onClick={onRetry}>{t('common.retry')}</button>
      ) : (
        <Link to="/map">{t('home.data.statusCta')} <ArrowRight size={15} /></Link>
      )}
    </section>
  );
}

function HomePage() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [personaId] = useState(readPersonaId);
  const persona = personas.find((item) => item.id === personaId) ?? null;
  const [activity, setActivity] = useState(() => personaActivities[readPersonaId()] ?? 'swim');
  const {
    spots,
    spotStatus,
    conditionStatus,
    retryData,
  } = useWaterSpots(activity);
  const [searchQuery, setSearchQuery] = useState('');
  const [savedSpots, setSavedSpots] = useState(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('pongdang-home-favorites') || '[]'));
    } catch {
      return new Set();
    }
  });

  const dataLoading = ['idle', 'loading'].includes(spotStatus)
    || ['idle', 'loading'].includes(conditionStatus);
  const dataError = spotStatus === 'error' || conditionStatus === 'error';
  const dataEmpty = spotStatus === 'empty' || conditionStatus === 'empty';
  const rankedSpots = useMemo(
    () => [...spots]
      .map((spot) => ({ spot, view: getSpotActivityView(spot, activity) }))
      .filter(({ view }) => isRecommendationEligible(view))
      .sort((a, b) => b.view.score - a.view.score)
      .slice(0, 4),
    [activity, spots],
  );
  const heroResult = rankedSpots[0] ?? null;
  const heroStatus = dataError
    ? t('home.hero.statusError')
    : dataLoading
      ? t('home.hero.statusLoading')
      : heroResult?.view?.isDemoFallback
        ? t('home.hero.statusDemo')
        : !heroResult || dataEmpty
          ? t('home.hero.statusNoLive')
          : persona
            ? t('home.hero.statusPersona', { persona: persona.title })
            : t('home.hero.statusGuest');
  const heroConditions = heroResult ? [
    { label: t('metric.waterTemp'), value: heroResult.view.conditions.waterTemp, icon: ThermometerSun },
    { label: t('metric.waveHeight'), value: heroResult.view.conditions.waveHeight, icon: Waves },
    { label: t('metric.wind'), value: heroResult.view.conditions.windSpeed, icon: Wind },
    { label: t('metric.status'), value: localizedSafety(t, heroResult.view.safety.level).label, icon: ShieldCheck },
  ] : [];
  const gangneungForecast = weeklyForecast.filter((day) => day.region === '강릉').slice(0, 7);
  const bestForecast = gangneungForecast.reduce((best, day) => (day.score > best.score ? day : best));

  const toggleFavorite = (spotId) => {
    const next = new Set(savedSpots);
    if (next.has(spotId)) next.delete(spotId);
    else next.add(spotId);
    setSavedSpots(next);
    try {
      localStorage.setItem('pongdang-home-favorites', JSON.stringify([...next]));
    } catch {
      // Favorites still work for this session when local storage is unavailable.
    }
  };

  const submitSearch = (event) => {
    event.preventDefault();
    const query = searchQuery.trim();
    navigate(query ? `/map?q=${encodeURIComponent(query)}` : '/map');
  };

  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="hero-title">
        <div className="hero-ambient hero-ambient-one" aria-hidden="true" />
        <div className="hero-ambient hero-ambient-two" aria-hidden="true" />

        <div className="hero-copy">
          <div className="hero-status">
            <span className="status-dot" aria-hidden="true" />
            {heroStatus}
          </div>

          <p className="hero-kicker">WATER TRAVEL, CURATED FOR TODAY</p>
          <h1 id="hero-title">
            {t('home.hero.title')}
            <span>PongDang</span>
          </h1>
          <p className="hero-description">
            {t('home.hero.description')}
          </p>

          <form className="hero-search" onSubmit={submitSearch}>
            <label className="sr-only" htmlFor="water-search">
              {t('home.search.label')}
            </label>
            <Search size={19} aria-hidden="true" />
            <input
              id="water-search"
              type="search"
              placeholder={t('home.search.placeholder')}
              autoComplete="off"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <button type="submit" aria-label={t('home.search.submit')}>
              <ArrowUpRight size={19} />
            </button>
          </form>

          <div className="hero-actions">
            <Link className="primary-action" to="/map">
              <Compass size={18} />
              {t('home.cta.find')}
              <ArrowUpRight size={17} />
            </Link>
            <Link className="text-action" to="/onboarding">
              <Sparkles size={17} />
              {t('home.cta.taste')}
            </Link>
          </div>
        </div>

        <aside className="hero-index-card" aria-label={t('home.hero.recommendation')} aria-live="polite">
          {heroResult ? (
            <>
              <div className="index-card-topline">
                <span><MapPin size={15} /> {heroResult.spot.region} · {heroResult.spot.name}</span>
                <span className={`live-pill state-${heroResult.view.dataState}`}>
                  {localizedDataState(t, heroResult.view.dataState, true)}
                </span>
              </div>

              <div className="index-score-area">
                <div className="score-ring" style={{ '--score': heroResult.view.score ?? 0 }}>
                  <div className="score-ring-inner">
                    <span>SUITABILITY</span>
                    <strong>{scoreLabel(heroResult.view)}</strong>
                    <small>{heroResult.view.isDemoFallback ? 'DEMO' : t('home.hero.recommendable')}</small>
                  </div>
                </div>
                <div className="index-summary">
                  <p>{heroResult.view.isDemoFallback ? t('home.hero.demo') : t('home.hero.gatePassed')}</p>
                  <h2>{heroResult.spot.summary}</h2>
                  <span><CloudSun size={17} /> {heroResult.view.provenance.updatedLabel}</span>
                </div>
              </div>

              <div className="condition-grid">
                {heroConditions.map(({ label, value, icon: Icon }) => (
                  <div className="condition-item" key={label}>
                    <Icon size={18} aria-hidden="true" />
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>

              <div className="index-card-footer">
                <div>
                  <span>{heroResult.view.methodologyVersion}</span>
                  <strong>{heroResult.spot.bestTime}</strong>
                </div>
                <Link to={`/spot/${heroResult.spot.id}`} aria-label={`${heroResult.spot.name} ${t('common.details')}`}>
                  <ChevronRight size={20} />
                </Link>
              </div>
            </>
          ) : (
            <div className="hero-index-empty">
              <AlertTriangle size={26} aria-hidden="true" />
              <span>RECOMMENDATION PAUSED</span>
              <h2>{t('home.hero.paused')}</h2>
              <p>{t('home.hero.pausedDescription')}</p>
              <Link to="/map">{t('home.cta.allStatus')} <ArrowRight size={16} /></Link>
            </div>
          )}
        </aside>
      </section>

      <section className="pillar-section" aria-labelledby="pillar-title">
        <div className="section-heading">
          <div>
            <p>{t('home.pillars.eyebrow')}</p>
            <h2 id="pillar-title">{t('home.pillars.title')}</h2>
          </div>
          <span>{t('home.pillars.description')}</span>
        </div>

        <div className="pillar-grid">
          {pillars.map(({ eyebrow, titleKey, descriptionKey, icon: Icon, tone, to }) => (
            <Link className={`pillar-card pillar-${tone}`} to={to} key={eyebrow}>
              <div className="pillar-icon"><Icon size={22} /></div>
              <span className="pillar-eyebrow">{eyebrow}</span>
              <h3>{t(titleKey)}</h3>
              <p>{t(descriptionKey)}</p>
              <ChevronRight className="pillar-arrow" size={20} />
            </Link>
          ))}
        </div>
      </section>

      <HomeDataStatus
        spotStatus={spotStatus}
        conditionStatus={conditionStatus}
        onRetry={retryData}
      />

      <section className="home-section today-section" aria-labelledby="today-title">
        <div className="home-section-heading">
          <div>
            <p>{t('home.today.eyebrow')}</p>
            <h2 id="today-title">{t('home.today.title')}</h2>
          </div>
          <div className="activity-tabs" role="group" aria-label={t('home.today.activityLabel')}>
            {activityTabs.map((activityId) => (
              <button
                key={activityId}
                type="button"
                className={activity === activityId ? 'active' : ''}
                onClick={() => setActivity(activityId)}
                aria-pressed={activity === activityId}
              >
                {t(`activity.${activityId}`)}
              </button>
            ))}
          </div>
        </div>

        <div className="home-spot-grid">
          {rankedSpots.map(({ spot, view }, index) => (
            <article className={`home-spot-card ${index === 0 ? 'featured' : ''}`} key={spot.id}>
              <Link className="home-spot-image" to={`/spot/${spot.id}`}>
                {spot.imageUrl ? <img src={spot.imageUrl} alt={t('common.waterSceneryAlt', { name: spot.name })} /> : <span className="spot-image-placeholder" aria-hidden="true">{spot.visual.icon}</span>}
                <span className="spot-image-shade" />
                <div className="spot-card-badges">
                  <span>{spot.typeLabel}</span>
                  <span className={`data-state-badge state-${view.dataState}`}>{localizedDataState(t, view.dataState)}</span>
                  <span className={`safety-${view.safety.level}`}>{localizedSafety(t, view.safety.level).label}</span>
                </div>
                <div className="spot-image-score">
                  <span>{t(`activity.${activity}`)}</span>
                  <strong>{scoreLabel(view)}</strong>
                </div>
              </Link>
              <div className="home-spot-body">
                <div>
                  <span className="spot-region"><MapPin size={13} /> {spot.region}</span>
                  <button
                    type="button"
                    onClick={() => toggleFavorite(spot.id)}
                    aria-label={`${spot.name} ${savedSpots.has(spot.id) ? t('common.cancelSave') : t('common.save')}`}
                    aria-pressed={savedSpots.has(spot.id)}
                  >
                    <Heart size={17} fill={savedSpots.has(spot.id) ? 'currentColor' : 'none'} />
                  </button>
                </div>
                <h3><Link to={`/spot/${spot.id}`}>{spot.name}</Link></h3>
                <p>{spot.summary}</p>
                <div className="spot-reason-row">
                  {view.reasons.length > 0
                    ? view.reasons.slice(0, 2).map((reason) => (
                      <span title={reason.code} key={reason.code}>
                        {formatGateReason(reason.code, t)}
                      </span>
                    ))
                    : spot.reasons.slice(0, 2).map((reason) => <span key={reason}>{reason}</span>)}
                </div>
                <div className="spot-card-footer">
                  <span><ThermometerSun size={14} /> {view.conditions.waterTemp}</span>
                  <span><Waves size={14} /> {view.conditions.waveHeight}</span>
                  <Link to={`/spot/${spot.id}`} aria-label={`${spot.name} ${t('common.details')}`}><ChevronRight size={17} /></Link>
                </div>
              </div>
            </article>
          ))}
          {rankedSpots.length === 0 && (
            <div className="home-ranked-empty" role="status">
              <AlertTriangle size={24} aria-hidden="true" />
              <h3>{t('home.today.empty', { activity: t(`activity.${activity}`) })}</h3>
              <p>{t('home.today.emptyDescription')}</p>
              <Link to="/map">{t('home.cta.allStatus')} <ArrowRight size={16} /></Link>
            </div>
          )}
        </div>
      </section>

      <section className="home-section forecast-home-section" aria-labelledby="forecast-home-title">
        <div className="forecast-home-copy">
          <span className="home-eyebrow"><TrendingUp size={15} /> WATER FORECAST</span>
          <h2 id="forecast-home-title">{t('home.forecast.title', { day: bestForecast.day })}</h2>
          <p>{t('home.forecast.description', { activity: t('activity.swim'), score: bestForecast.score })}</p>
          <div className="best-time-card">
            <CalendarDays size={20} />
            <div><span>{t('home.forecast.recommendedTime')}</span><strong>{bestForecast.date} · {bestForecast.best}</strong></div>
          </div>
          <Link to="/forecast">{t('home.forecast.cta')} <ArrowRight size={16} /></Link>
        </div>

        <div className="forecast-week-card">
          <div className="forecast-week-head"><span>{t('home.forecast.fixedLabel', { region: '강릉', activity: t('activity.swim') })}</span><span>{t('home.forecast.fixedDemo')}</span></div>
          <div className="forecast-week-grid">
            {gangneungForecast.map((day) => (
              <div className={day.id === bestForecast.id ? 'best' : ''} key={day.id}>
                <span>{day.day}</span>
                <strong>{day.score}</strong>
                <div><span style={{ height: `${day.score}%` }} /></div>
                <small>{day.weather}</small>
                {day.id === bestForecast.id && <em>BEST</em>}
              </div>
            ))}
          </div>
          <div className="forecast-reason-list">
            {bestForecast.factors.map((factor) => <span key={factor}><CheckIcon /> {factor}</span>)}
          </div>
        </div>
      </section>

      <section className="home-section nearby-section" aria-labelledby="nearby-title">
        <div className="nearby-map-card" aria-hidden="true">
          <div className="nearby-map-grid" />
          {spots.filter((spot) => spot.isGangneungMvp).slice(0, 6).map((spot) => {
            const view = getSpotActivityView(spot, activity);
            return (
              <span className={`nearby-marker state-${view.dataState}`} style={{ left: `${spot.visual.mapPosition.x}%`, top: `${spot.visual.mapPosition.y}%` }} key={spot.id}>
                <strong>{scoreLabel(view)}</strong><small>{spot.name}</small>
              </span>
            );
          })}
          <div className="nearby-you"><LocateFixed size={15} /> {t('home.map.stationBasis', { station: '강릉역' })}</div>
        </div>
        <div className="nearby-copy">
          <span className="home-eyebrow"><Navigation2 size={15} /> WATER TWIN</span>
          <h2 id="nearby-title">{t('home.map.title')}</h2>
          <p>{t('home.map.description')}</p>
          <ul>
            <li><span>01</span><div><strong>{t('home.map.layer.title')}</strong><small>{t('home.map.layer.description')}</small></div></li>
            <li><span>02</span><div><strong>{t('home.map.safety.title')}</strong><small>{t('home.map.safety.description')}</small></div></li>
            <li><span>03</span><div><strong>{t('home.map.fallback.title')}</strong><small>{t('home.map.fallback.description')}</small></div></li>
          </ul>
          <Link to="/map">{t('home.map.cta')} <ArrowRight size={16} /></Link>
        </div>
      </section>

      <section className="home-section ai-home-section" aria-labelledby="ai-home-title">
        <div className="ai-home-orbit" aria-hidden="true"><Sparkles size={30} /><span>AI</span></div>
        <div className="ai-home-copy">
          <span>AI WATER CONCIERGE</span>
          <h2 id="ai-home-title">{t('home.concierge.title')}</h2>
          <p>{t('home.concierge.description')}</p>
          <Link to="/concierge"><Sparkles size={17} /> {t('nav.askAi')} <ArrowRight size={16} /></Link>
        </div>
        <div className="ai-result-preview">
          {spots
            .filter((spot) => ['anmok-beach', 'gyeongpo-lake', 'geumjin-hotspring'].includes(spot.slug))
            .map((spot) => {
              const view = getSpotActivityView(
                spot,
                ['hotspring', 'pool', 'waterpark'].includes(spot.type) ? 'onsen' : 'relax',
              );
              return { spot, view };
            })
            .filter(({ view }) => isRecommendationEligible(view))
            .map(({ spot, view }, index) => (
              <Link to={`/spot/${spot.id}`} key={spot.id}>
                <span>0{index + 1}</span><div><strong>{spot.name}</strong><small>{localizedDataState(t, view.dataState)} · {t('common.points', { score: scoreLabel(view) })}</small></div><ChevronRight size={17} />
              </Link>
            ))}
        </div>
      </section>

      <section className="home-section live-home-section" aria-labelledby="live-home-title">
        <div className="home-section-heading">
          <div><p>{t('home.live.eyebrow')}</p><h2 id="live-home-title">{t('home.live.title')}</h2></div>
          <Link to="/livecam">{t('home.live.cta')} <ArrowRight size={16} /></Link>
        </div>
        <div className="live-preview-grid">
          {livecams.slice(0, 3).map((cam, index) => (
            <Link to="/livecam" className={index === 0 ? 'large' : ''} key={cam.id}>
              <img src={cam.poster} alt={t('common.demoPreviewAlt', { name: cam.name })} />
              <span className="live-preview-shade" />
              <div className="live-preview-status"><Eye size={14} /> {t('home.live.notLive')}</div>
              <div className="live-preview-copy"><span>{cam.region}</span><h3>{cam.name}</h3><small>Water Index {cam.waterIndex}</small></div>
              <div className="live-preview-play"><Play size={17} fill="currentColor" /></div>
            </Link>
          ))}
        </div>
      </section>

      <footer className="home-footer">
        <div className="footer-brand"><Droplets size={22} /><div><strong>퐁당 PongDang</strong><span>{t('home.footer.tagline')}</span></div></div>
        <div className="footer-links"><Link to="/map">{t('nav.map')}</Link><Link to="/forecast">{t('nav.forecast')}</Link><Link to="/concierge">{t('nav.concierge')}</Link><Link to="/profile">{t('nav.profile')}</Link></div>
        <p>{t('home.footer.policy')}</p>
      </footer>
    </div>
  );
}

function CheckIcon() {
  return <span aria-hidden="true">✓</span>;
}

export default HomePage;
