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
      setStorageMessage('이 기기에 저장된 물 여행 취향을 지웠어요.');
    } catch {
      setLocalPreference((current) => ({ ...current, status: 'unavailable' }));
      setStorageMessage('브라우저 저장소에 접근할 수 없어 취향을 지우지 못했어요.');
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
            <h1 id="profile-title">오늘도 물 좋은 곳을 찾는 여행자</h1>
            <p>로그인 없이도 퐁당의 컬렉션과 일정 흐름을 미리 둘러볼 수 있어요.</p>
          </div>
        </div>

        <div className="profile-hero-actions">
          <Link className="profile-hero-primary" to="/onboarding">
            <Sparkles size={17} aria-hidden="true" />
            {currentPersona ? '물 취향 다시 찾기' : '내 물 취향 찾기'}
          </Link>
          <Link className="profile-hero-secondary" to="/concierge">
            AI 여행 만들기
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className="profile-overview" aria-label="나의 퐁당 요약">
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
                <p>{currentPersona.subtitle}</p>
                <h2>{currentPersona.title}</h2>
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
              title={localPreference.id ? '저장된 취향을 불러오지 못했어요' : '아직 물 여행 취향이 없어요'}
              description={localPreference.id
                ? '공유 데이터가 바뀌었거나 저장된 값이 오래되었을 수 있어요.'
                : '다섯 번의 선택으로 나에게 맞는 물 여행 리듬을 찾아보세요.'}
              actionLabel="취향 찾기"
              to="/onboarding"
            />
          )}
        </article>

        <div className="profile-stats" aria-label="데모 활동 통계">
          <article>
            <span>도감 진행률</span>
            <strong>{passportProgress}<small>%</small></strong>
            <p>{collectionTotals.current} / {collectionTotals.total || '—'} 스팟</p>
          </article>
          <article>
            <span>저장한 일정</span>
            <strong>{savedTrips.length}<small>개</small></strong>
            <p>데모 일정 포함</p>
          </article>
          <article>
            <span>에코 액션</span>
            <strong>{ecoCompleted}<small>회</small></strong>
            <p>다음 배지까지 {ecoMilestones.length - ecoCompleted}회</p>
          </article>
        </div>
      </section>

      <div className="profile-dashboard-grid">
        <section className="profile-section profile-passport-section" aria-labelledby="passport-title">
          <div className="profile-section-heading">
            <div>
              <p>WATER PASSPORT</p>
              <h2 id="passport-title">대한민국의 물을 한 칸씩</h2>
            </div>
            <span className="profile-section-note">데모 컬렉션</span>
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
              title="아직 열린 컬렉션이 없어요"
              description="첫 방문을 인증하면 이곳에 나만의 물 도감이 시작돼요."
              actionLabel="워터맵 둘러보기"
              to="/map"
            />
          )}
        </section>

        <section className="profile-section profile-eco-section" aria-labelledby="eco-title">
          <div className="profile-eco-badge">
            <div className="profile-eco-icon"><Leaf size={25} aria-hidden="true" /></div>
            <div>
              <p>NEXT BADGE</p>
              <h2 id="eco-title">워터 키퍼</h2>
              <span>{ecoCompleted} / {ecoMilestones.length} 에코 액션</span>
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
            비치코밍 스팟 찾기
            <ChevronRight size={16} aria-hidden="true" />
          </Link>
        </section>
      </div>

      <section className="profile-section profile-trips-section" aria-labelledby="saved-trips-title">
        <div className="profile-section-heading">
          <div>
            <p>SAVED JOURNEYS</p>
            <h2 id="saved-trips-title">다음 물 여행</h2>
          </div>
          <Link to="/concierge">
            새 일정 만들기
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
            title="저장한 일정이 아직 없어요"
            description="가고 싶은 물과 동행을 말하면 AI 컨시어지가 첫 일정을 만들어드려요."
            actionLabel="첫 일정 만들기"
            to="/concierge"
          />
        )}
      </section>

      <section className="profile-settings" aria-labelledby="settings-title">
        <div className="profile-settings-heading">
          <div className="profile-settings-icon"><ShieldCheck size={22} aria-hidden="true" /></div>
          <div>
            <p>PRIVACY & ACCESS</p>
            <h2 id="settings-title">가볍고 안전한 게스트 모드</h2>
          </div>
        </div>

        <div className="profile-settings-grid">
          <article>
            <span className="profile-setting-icon"><Database size={19} aria-hidden="true" /></span>
            <div>
              <strong>이 기기에만 저장</strong>
              <p>
                {localPreference.status === 'available'
                  ? '취향 ID, 즐겨찾기와 데모 일정의 장소 ID만 이 브라우저에 보관합니다.'
                  : '현재 브라우저에서는 로컬 저장소를 사용할 수 없습니다.'}
              </p>
            </div>
            <span className={`profile-setting-state is-${localPreference.status}`}>
              {localPreference.status === 'available' ? '사용 가능' : '사용 불가'}
            </span>
          </article>

          <article>
            <span className="profile-setting-icon"><Accessibility size={19} aria-hidden="true" /></span>
            <div>
              <strong>누구나 탐색 가능</strong>
              <p>키보드 포커스, 스크린리더 레이블, 모션 감소 설정을 존중해요.</p>
            </div>
            <span className="profile-setting-state is-ready">지원됨</span>
          </article>

          <article>
            <span className="profile-setting-icon"><LockKeyhole size={19} aria-hidden="true" /></span>
            <div>
              <strong>개인정보 입력 없음</strong>
              <p>데모 모드에서는 이름, 연락처, 위치 기록을 요구하지 않아요.</p>
            </div>
            <span className="profile-setting-state is-ready">비공개</span>
          </article>
        </div>

        <div className="profile-storage-footer">
          <p role="status">{storageMessage || '저장된 취향은 언제든 직접 삭제할 수 있어요.'}</p>
          <button type="button" onClick={clearPreference} disabled={!localPreference.id || localPreference.status !== 'available'}>
            <BadgeCheck size={15} aria-hidden="true" />
            저장된 취향 지우기
          </button>
        </div>
      </section>
    </div>
  );
}

export default ProfilePage;
