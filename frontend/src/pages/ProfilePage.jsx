import { useMemo, useState } from 'react';
import {
  Accessibility,
  ArrowRight,
  BadgeCheck,
  CalendarDays,
  Check,
  ChevronRight,
  Compass,
  Database,
  Droplets,
  Leaf,
  LockKeyhole,
  MapPin,
  Route,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { passportCollections, personas, spots } from '../data/pongdangData';
import { useI18n } from '../i18n';
import './ProfilePage.css';

const PREFERENCE_STORAGE_KEY = 'pongdang:persona-preference';

const demoSavedTrips = [
  {
    id: 'east-coast-wave-day',
    eyebrow: '8월 22일 · 당일',
    title: '강릉, 파도와 커피 사이',
    route: '안목해변 → 초당동 → 경포호',
    condition: '예상 지수 91',
    href: '/forecast',
    tone: 'mint',
  },
  {
    id: 'forest-valley-rest',
    eyebrow: '저장한 초안 · 1박 2일',
    title: '숲 깊은 계곡에서 한 박자 쉬기',
    route: '인제 계곡 → 로컬 식당 → 숲 스테이',
    condition: '일정 다듬기',
    href: '/concierge',
    tone: 'blue',
  },
];

const ecoMilestones = [
  { id: 'bottle', label: '다회용 물병 챙기기', complete: true },
  { id: 'cleanup', label: '해변 정화 20분 인증', complete: true },
  { id: 'local', label: '로컬 상점 이용하기', complete: true },
  { id: 'transit', label: '대중교통 물 여행', complete: false },
  { id: 'share', label: '안전한 스팟 정보 나누기', complete: false },
];

function readLocalPreference() {
  if (typeof window === 'undefined') {
    return { id: null, status: 'unavailable' };
  }

  try {
    return {
      id: window.localStorage.getItem(PREFERENCE_STORAGE_KEY),
      status: 'available',
    };
  } catch {
    return { id: null, status: 'unavailable' };
  }
}

function readDemoItinerary() {
  if (typeof window === 'undefined') return null;

  try {
    const value = JSON.parse(window.localStorage.getItem('pongdang:demo-itinerary') || 'null');
    return value && typeof value.spotId === 'string' ? value : null;
  } catch {
    return null;
  }
}

function getPersonaById(personaId) {
  if (!personaId || !Array.isArray(personas)) return null;
  return personas.find((persona) => String(persona?.id) === String(personaId)) || null;
}

function normalizeCollections(collections) {
  if (!Array.isArray(collections)) return [];

  return collections.map((collection, index) => {
    const total = Math.max(0, Number(collection?.total) || 0);
    const current = Math.min(total || Infinity, Math.max(0, Number(collection?.current) || 0));

    return {
      id: collection?.id || `collection-${index}`,
      title: collection?.title || '이름 없는 컬렉션',
      current: Number.isFinite(current) ? current : 0,
      total,
      unit: collection?.unit || '곳',
      icon: typeof collection?.icon === 'string' ? collection.icon : '💧',
      color: collection?.color || '#0b987a',
    };
  });
}

function EmptyPanel({ icon: Icon, title, description, actionLabel, to }) {
  return (
    <div className="profile-empty-state">
      <span><Icon size={21} aria-hidden="true" /></span>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      {actionLabel && to ? (
        <Link to={to}>
          {actionLabel}
          <ArrowRight size={15} aria-hidden="true" />
        </Link>
      ) : null}
    </div>
  );
}

function ProfilePage() {
  const { t } = useI18n();
  const [localPreference, setLocalPreference] = useState(readLocalPreference);
  const [localItinerary] = useState(readDemoItinerary);
  const [storageMessage, setStorageMessage] = useState('');

  const currentPersona = useMemo(
    () => getPersonaById(localPreference.id),
    [localPreference.id],
  );
  const collections = useMemo(() => normalizeCollections(passportCollections), []);
  const savedTrips = useMemo(() => {
    if (!localItinerary) return demoSavedTrips;
    const firstSpot = spots.find((spot) => spot.slug === localItinerary.spotId);
    if (!firstSpot) return demoSavedTrips;

    return [
      {
        id: 'local-persona-itinerary',
        eyebrow: '이 기기에 저장한 데모 일정',
        title: `${firstSpot.name}에서 시작하는 물 여행`,
        route: `${firstSpot.name} → 로컬 한 끼 → 실내 대안`,
        condition: '컨시어지 데모',
        href: `/spot/${firstSpot.slug}`,
        tone: 'mint',
      },
      ...demoSavedTrips,
    ];
  }, [localItinerary]);

  const collectionTotals = collections.reduce(
    (totals, collection) => ({
      current: totals.current + collection.current,
      total: totals.total + collection.total,
    }),
    { current: 0, total: 0 },
  );
  const passportProgress = collectionTotals.total
    ? Math.round((collectionTotals.current / collectionTotals.total) * 100)
    : 0;
  const ecoCompleted = ecoMilestones.filter((milestone) => milestone.complete).length;

  const clearPreference = () => {
    try {
      window.localStorage.removeItem(PREFERENCE_STORAGE_KEY);
      setLocalPreference({ id: null, status: 'available' });
      setStorageMessage('profile.storage.cleared');
    } catch {
      setLocalPreference((current) => ({ ...current, status: 'unavailable' }));
      setStorageMessage('profile.storage.clearFailed');
    }
  };

  return (
    <div className="profile-page">
      <section className="profile-hero" aria-labelledby="profile-title">
        <div className="profile-hero-glow" aria-hidden="true" />

        <div className="profile-identity">
          <div className="profile-avatar" aria-hidden="true">
            <Droplets size={27} />
          </div>
          <div className="profile-identity-copy">
            <span className="profile-demo-label"><UserRound size={13} /> GUEST · DEMO</span>
            <h1 id="profile-title">{t('profile.hero.title')}</h1>
            <p>{t('profile.hero.description')}</p>
          </div>
        </div>

        <div className="profile-hero-actions">
          <Link className="profile-hero-primary" to="/onboarding">
            <Sparkles size={17} aria-hidden="true" />
            {currentPersona ? t('profile.cta.refindTaste') : t('profile.cta.findTaste')}
          </Link>
          <Link className="profile-hero-secondary" to="/concierge">
            {t('profile.cta.aiTrip')}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className="profile-overview" aria-label={t('profile.summary')}>
        <article className="profile-persona-card">
          <div className="profile-card-eyebrow">
            <Sparkles size={14} aria-hidden="true" />
            MY WATER TASTE
          </div>

          {currentPersona ? (
            <div className="profile-persona-content">
              <span className="profile-persona-icon" aria-hidden="true">
                {typeof currentPersona.icon === 'string' ? currentPersona.icon : '💧'}
              </span>
              <div>
                <p>{t(`persona.${currentPersona.id}.subtitle`)}</p>
                <h2>{t(`persona.${currentPersona.id}.title`)}</h2>
                <div className="profile-persona-tags">
                  {(Array.isArray(currentPersona.tags) ? currentPersona.tags : []).slice(0, 3).map((tag) => (
                    <span key={tag}>#{tag}</span>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <EmptyPanel
              icon={Compass}
              title={localPreference.id ? t('profile.persona.invalid') : t('profile.persona.empty')}
              description={localPreference.id
                ? t('profile.persona.invalidDescription')
                : t('profile.persona.emptyDescription')}
              actionLabel={t('profile.cta.taste')}
              to="/onboarding"
            />
          )}
        </article>

        <div className="profile-stats" aria-label={t('profile.stats.label')}>
          <article>
            <span>{t('profile.stats.progress')}</span>
            <strong>{passportProgress}<small>%</small></strong>
            <p>{t('profile.stats.spots', { current: collectionTotals.current, total: collectionTotals.total || '—' })}</p>
          </article>
          <article>
            <span>{t('profile.stats.saved')}</span>
            <strong>{savedTrips.length}<small>{t('profile.stats.countUnit')}</small></strong>
            <p>{t('profile.stats.includesDemo')}</p>
          </article>
          <article>
            <span>{t('profile.stats.eco')}</span>
            <strong>{ecoCompleted}<small>{t('profile.stats.actionUnit')}</small></strong>
            <p>{t('profile.stats.nextBadge', { count: ecoMilestones.length - ecoCompleted })}</p>
          </article>
        </div>
      </section>

      <div className="profile-dashboard-grid">
        <section className="profile-section profile-passport-section" aria-labelledby="passport-title">
          <div className="profile-section-heading">
            <div>
              <p>WATER PASSPORT</p>
              <h2 id="passport-title">{t('profile.passport.title')}</h2>
            </div>
            <span className="profile-section-note">{t('profile.passport.demo')}</span>
          </div>

          {collections.length ? (
            <div className="profile-collection-grid">
              {collections.map((collection) => {
                const progress = collection.total
                  ? Math.round((collection.current / collection.total) * 100)
                  : 0;

                return (
                  <article
                    className="profile-collection-card"
                    key={collection.id}
                    style={{ '--collection-color': collection.color }}
                  >
                    <div className="profile-collection-topline">
                      <span className="profile-collection-icon" aria-hidden="true">{collection.icon}</span>
                      <span>{progress}%</span>
                    </div>
                    <h3>{collection.title}</h3>
                    <p>
                      <strong>{collection.current}</strong>{collection.unit}
                      <span> / {collection.total}{collection.unit}</span>
                    </p>
                    <div
                      className="profile-collection-progress"
                      role="progressbar"
                      aria-label={`${collection.title} 수집 진행률`}
                      aria-valuemin="0"
                      aria-valuemax={collection.total || 100}
                      aria-valuenow={collection.current}
                    >
                      <span style={{ width: `${progress}%` }} />
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyPanel
              icon={Droplets}
              title={t('profile.passport.empty')}
              description={t('profile.passport.emptyDescription')}
              actionLabel={t('profile.passport.emptyCta')}
              to="/map"
            />
          )}
        </section>

        <section className="profile-section profile-eco-section" aria-labelledby="eco-title">
          <div className="profile-eco-badge">
            <div className="profile-eco-icon"><Leaf size={25} aria-hidden="true" /></div>
            <div>
              <p>NEXT BADGE</p>
              <h2 id="eco-title">{t('profile.eco.title')}</h2>
              <span>{t('profile.eco.progress', { current: ecoCompleted, total: ecoMilestones.length })}</span>
            </div>
          </div>

          <div className="profile-eco-progress" aria-hidden="true">
            <span style={{ width: `${(ecoCompleted / ecoMilestones.length) * 100}%` }} />
          </div>

          <ul className="profile-eco-list">
            {ecoMilestones.map((milestone) => (
              <li className={milestone.complete ? 'is-complete' : ''} key={milestone.id}>
                <span><Check size={14} aria-hidden="true" /></span>
                {milestone.label}
              </li>
            ))}
          </ul>

          <Link className="profile-inline-link" to="/map">
            {t('profile.eco.cta')}
            <ChevronRight size={16} aria-hidden="true" />
          </Link>
        </section>
      </div>

      <section className="profile-section profile-trips-section" aria-labelledby="saved-trips-title">
        <div className="profile-section-heading">
          <div>
            <p>SAVED JOURNEYS</p>
            <h2 id="saved-trips-title">{t('profile.trips.title')}</h2>
          </div>
          <Link to="/concierge">
            {t('profile.trips.new')}
            <ArrowRight size={15} aria-hidden="true" />
          </Link>
        </div>

        {savedTrips.length ? (
          <div className="profile-trip-list">
            {savedTrips.map((trip) => (
              <Link className={`profile-trip-card is-${trip.tone}`} to={trip.href} key={trip.id}>
                <div className="profile-trip-date"><CalendarDays size={20} aria-hidden="true" /></div>
                <div className="profile-trip-copy">
                  <span>{trip.eyebrow}</span>
                  <h3>{trip.title}</h3>
                  <p><MapPin size={14} aria-hidden="true" /> {trip.route}</p>
                </div>
                <div className="profile-trip-status">
                  <span>{trip.condition}</span>
                  <ChevronRight size={18} aria-hidden="true" />
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyPanel
            icon={Route}
            title={t('profile.trips.empty')}
            description={t('profile.trips.emptyDescription')}
            actionLabel={t('profile.trips.emptyCta')}
            to="/concierge"
          />
        )}
      </section>

      <section className="profile-settings" aria-labelledby="settings-title">
        <div className="profile-settings-heading">
          <div className="profile-settings-icon"><ShieldCheck size={22} aria-hidden="true" /></div>
          <div>
            <p>PRIVACY & ACCESS</p>
            <h2 id="settings-title">{t('profile.settings.title')}</h2>
          </div>
        </div>

        <div className="profile-settings-grid">
          <article>
            <span className="profile-setting-icon"><Database size={19} aria-hidden="true" /></span>
            <div>
              <strong>{t('profile.settings.local.title')}</strong>
              <p>
                {localPreference.status === 'available'
                  ? t('profile.settings.local.available')
                  : t('profile.settings.local.unavailable')}
              </p>
            </div>
            <span className={`profile-setting-state is-${localPreference.status}`}>
              {localPreference.status === 'available' ? t('profile.settings.available') : t('profile.settings.unavailable')}
            </span>
          </article>

          <article>
            <span className="profile-setting-icon"><Accessibility size={19} aria-hidden="true" /></span>
            <div>
              <strong>{t('profile.settings.a11y.title')}</strong>
              <p>{t('profile.settings.a11y.description')}</p>
            </div>
            <span className="profile-setting-state is-ready">{t('profile.settings.supported')}</span>
          </article>

          <article>
            <span className="profile-setting-icon"><LockKeyhole size={19} aria-hidden="true" /></span>
            <div>
              <strong>{t('profile.settings.privacy.title')}</strong>
              <p>{t('profile.settings.privacy.description')}</p>
            </div>
            <span className="profile-setting-state is-ready">{t('profile.settings.private')}</span>
          </article>
        </div>

        <div className="profile-storage-footer">
          <p role="status">{t(storageMessage || 'profile.storage.default')}</p>
          <button type="button" onClick={clearPreference} disabled={!localPreference.id || localPreference.status !== 'available'}>
            <BadgeCheck size={15} aria-hidden="true" />
            {t('profile.storage.clear')}
          </button>
        </div>
      </section>
    </div>
  );
}

export default ProfilePage;
