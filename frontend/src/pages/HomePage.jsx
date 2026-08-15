import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
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
import { dataMeta, livecams, personas, spots, weeklyForecast } from '../data/pongdangData';
import './HomePage.css';

const pillars = [
  {
    eyebrow: 'NOW',
    title: '지금 좋은 물',
    description: '수온·파고·수질·혼잡도를 하나의 지수로 확인해요.',
    icon: Droplets,
    tone: 'mint',
    to: '/map',
  },
  {
    eyebrow: 'WHEN',
    title: '가장 좋은 때',
    description: '7일 예보에서 떠나기 좋은 하루를 미리 골라드려요.',
    icon: CalendarDays,
    tone: 'blue',
    to: '/forecast',
  },
  {
    eyebrow: 'PREVIEW',
    title: '직접 보는 물',
    description: '영상 연결 상태와 데모 미리보기를 구분해 출발 전 풍경을 확인해요.',
    icon: Radio,
    tone: 'coral',
    to: '/livecam',
  },
];

const conditions = [
  { label: '수온', value: '24.2°', icon: ThermometerSun },
  { label: '파고', value: '0.5m', icon: Waves },
  { label: '바람', value: '2.8m/s', icon: Wind },
  { label: '안전', value: '좋음', icon: ShieldCheck },
];

const activityTabs = [
  { id: 'swim', label: '물놀이' },
  { id: 'surf', label: '서핑' },
  { id: 'relax', label: '물멍' },
  { id: 'onsen', label: '온천' },
];

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

function HomePage() {
  const navigate = useNavigate();
  const [personaId] = useState(readPersonaId);
  const persona = personas.find((item) => item.id === personaId) ?? null;
  const [activity, setActivity] = useState(() => personaActivities[readPersonaId()] ?? 'swim');
  const [searchQuery, setSearchQuery] = useState('');
  const [savedSpots, setSavedSpots] = useState(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('pongdang-home-favorites') || '[]'));
    } catch {
      return new Set();
    }
  });

  const rankedSpots = useMemo(
    () => [...spots]
      .filter((spot) => spot.scores[activity] !== null)
      .sort((a, b) => b.scores[activity] - a.scores[activity])
      .slice(0, 4),
    [activity],
  );
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
            8월 15일 · 강릉 우선 · {persona ? `${persona.title} 맞춤` : '게스트 탐색'} · 데모
          </div>

          <p className="hero-kicker">WATER TRAVEL, CURATED FOR TODAY</p>
          <h1 id="hero-title">
            오늘, 물이 좋은 곳으로.
            <span>퐁당</span>
          </h1>
          <p className="hero-description">
            바다부터 계곡, 온천과 호수까지. 흩어진 물 정보를 한데 모아
            지금 떠나기 좋은 장소와 가장 좋은 순간을 알려드려요.
          </p>

          <form className="hero-search" onSubmit={submitSearch}>
            <label className="sr-only" htmlFor="water-search">
              물 여행지 검색
            </label>
            <Search size={19} aria-hidden="true" />
            <input
              id="water-search"
              type="search"
              placeholder="어떤 물을 만나고 싶나요?"
              autoComplete="off"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <button type="submit" aria-label="검색하기">
              <ArrowUpRight size={19} />
            </button>
          </form>

          <div className="hero-actions">
            <Link className="primary-action" to="/map">
              <Compass size={18} />
              지금 좋은 물 찾기
              <ArrowUpRight size={17} />
            </Link>
            <Link className="text-action" to="/onboarding">
              <Sparkles size={17} />
              내 취향으로 추천받기
            </Link>
          </div>
        </div>

        <aside className="hero-index-card" aria-label="오늘의 추천 물 여행지">
          <div className="index-card-topline">
            <span><MapPin size={15} /> 강릉 안목해변</span>
            <span className="live-pill">DEMO</span>
          </div>

          <div className="index-score-area">
            <div className="score-ring" style={{ '--score': 94 }}>
              <div className="score-ring-inner">
                <span>WATER INDEX</span>
                <strong>94</strong>
                <small>최적</small>
              </div>
            </div>
            <div className="index-summary">
              <p>오늘의 첫 번째 추천</p>
              <h2>파도는 잔잔하고<br />물은 기분 좋게 따뜻해요.</h2>
              <span><CloudSun size={17} /> 맑음 · 체감 27°</span>
            </div>
          </div>

          <div className="condition-grid">
            {conditions.map(({ label, value, icon: Icon }) => (
              <div className="condition-item" key={label}>
                <Icon size={18} aria-hidden="true" />
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>

          <div className="index-card-footer">
            <div>
              <span>BEST TIME</span>
              <strong>오늘 16:30 — 18:10</strong>
            </div>
            <Link to="/spot/1" aria-label="안목해변 상세 보기">
              <ChevronRight size={20} />
            </Link>
          </div>
        </aside>
      </section>

      <section className="pillar-section" aria-labelledby="pillar-title">
        <div className="section-heading">
          <div>
            <p>퐁당이 답하는 세 가지</p>
            <h2 id="pillar-title">지금, 언제, 어떻게.</h2>
          </div>
          <span>여행 전 확인하던 여러 정보를 한 흐름으로 연결했어요.</span>
        </div>

        <div className="pillar-grid">
          {pillars.map(({ eyebrow, title, description, icon: Icon, tone, to }) => (
            <Link className={`pillar-card pillar-${tone}`} to={to} key={eyebrow}>
              <div className="pillar-icon"><Icon size={22} /></div>
              <span className="pillar-eyebrow">{eyebrow}</span>
              <h3>{title}</h3>
              <p>{description}</p>
              <ChevronRight className="pillar-arrow" size={20} />
            </Link>
          ))}
        </div>
      </section>

      <section className="home-data-note" aria-label="데이터 안내">
        <Info size={18} />
        <div>
          <strong>제품 경험을 위한 고정 데모 값이에요.</strong>
          <span>{dataMeta.updatedLabel} · 실제 방문 전 공식 특보와 현장 안내를 확인하세요.</span>
        </div>
        <Link to="/map">데이터 상태 보기 <ArrowRight size={15} /></Link>
      </section>

      <section className="home-section today-section" aria-labelledby="today-title">
        <div className="home-section-heading">
          <div>
            <p>오늘의 Water Index</p>
            <h2 id="today-title">지금 좋은 물부터 볼까요?</h2>
          </div>
          <div className="activity-tabs" role="group" aria-label="활동 선택">
            {activityTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={activity === tab.id ? 'active' : ''}
                onClick={() => setActivity(tab.id)}
                aria-pressed={activity === tab.id}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="home-spot-grid">
          {rankedSpots.map((spot, index) => (
            <article className={`home-spot-card ${index === 0 ? 'featured' : ''}`} key={spot.id}>
              <Link className="home-spot-image" to={`/spot/${spot.id}`}>
                <img src={spot.imageUrl} alt={`${spot.name} 데모 풍경`} />
                <span className="spot-image-shade" />
                <div className="spot-card-badges">
                  <span>{spot.typeLabel}</span>
                  <span>{spot.safety.label}</span>
                </div>
                <div className="spot-image-score">
                  <span>{activityTabs.find((tab) => tab.id === activity)?.label}</span>
                  <strong>{spot.scores[activity]}</strong>
                </div>
              </Link>
              <div className="home-spot-body">
                <div>
                  <span className="spot-region"><MapPin size={13} /> {spot.region}</span>
                  <button
                    type="button"
                    onClick={() => toggleFavorite(spot.id)}
                    aria-label={`${spot.name} ${savedSpots.has(spot.id) ? '저장 취소' : '저장'}`}
                    aria-pressed={savedSpots.has(spot.id)}
                  >
                    <Heart size={17} fill={savedSpots.has(spot.id) ? 'currentColor' : 'none'} />
                  </button>
                </div>
                <h3><Link to={`/spot/${spot.id}`}>{spot.name}</Link></h3>
                <p>{spot.summary}</p>
                <div className="spot-reason-row">
                  {spot.reasons.slice(0, 2).map((reason) => <span key={reason}>{reason}</span>)}
                </div>
                <div className="spot-card-footer">
                  <span><ThermometerSun size={14} /> {spot.conditions.waterTemp}</span>
                  <span><Waves size={14} /> {spot.conditions.waveHeight}</span>
                  <Link to={`/spot/${spot.id}`} aria-label={`${spot.name} 상세 보기`}><ChevronRight size={17} /></Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section forecast-home-section" aria-labelledby="forecast-home-title">
        <div className="forecast-home-copy">
          <span className="home-eyebrow"><TrendingUp size={15} /> WATER FORECAST</span>
          <h2 id="forecast-home-title">오늘보다<br /><em>{bestForecast.day}요일</em>이 더 좋아요.</h2>
          <p>파고가 안정되고 비 올 확률이 낮아져 물놀이 지수가 {bestForecast.score}점까지 올라가는 데모 예보예요.</p>
          <div className="best-time-card">
            <CalendarDays size={20} />
            <div><span>이번 주 추천 시간</span><strong>{bestForecast.date.slice(5).replace('-', '월 ')}일 · {bestForecast.best}</strong></div>
          </div>
          <Link to="/forecast">7일 예보 자세히 보기 <ArrowRight size={16} /></Link>
        </div>

        <div className="forecast-week-card">
          <div className="forecast-week-head"><span>강릉 · 물놀이</span><span>고정 데모 예보</span></div>
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
          {spots.filter((spot) => spot.isGangneungMvp).slice(0, 6).map((spot) => (
            <span className="nearby-marker" style={{ left: `${spot.visual.mapPosition.x}%`, top: `${spot.visual.mapPosition.y}%` }} key={spot.id}>
              <strong>{spot.index}</strong><small>{spot.name}</small>
            </span>
          ))}
          <div className="nearby-you"><LocateFixed size={15} /> 강릉역 기준</div>
        </div>
        <div className="nearby-copy">
          <span className="home-eyebrow"><Navigation2 size={15} /> WATER TWIN</span>
          <h2 id="nearby-title">지도에서<br />좋은 물이 먼저 보여요.</h2>
          <p>장소가 아니라 상태를 탐색하세요. 물놀이·서핑·물멍처럼 활동을 고르면 점수, 수온, 안전 정보가 같은 화면에서 바뀝니다.</p>
          <ul>
            <li><span>01</span><div><strong>수온·점수 레이어</strong><small>지금 따뜻하고 적합한 물 찾기</small></div></li>
            <li><span>02</span><div><strong>안전 우선 표시</strong><small>경보가 점수보다 먼저 보이도록</small></div></li>
            <li><span>03</span><div><strong>목록 대체 보기</strong><small>지도 키가 없어도 동일하게 탐색</small></div></li>
          </ul>
          <Link to="/map">워터 트윈 열기 <ArrowRight size={16} /></Link>
        </div>
      </section>

      <section className="home-section ai-home-section" aria-labelledby="ai-home-title">
        <div className="ai-home-orbit" aria-hidden="true"><Sparkles size={30} /><span>AI</span></div>
        <div className="ai-home-copy">
          <span>AI WATER CONCIERGE</span>
          <h2 id="ai-home-title">“이번 주말 연인과<br />드라이브하며 물을 보고 싶어요.”</h2>
          <p>완벽한 검색어를 몰라도 괜찮아요. 기분과 동행, 이동수단을 말하면 물 상태와 동선을 함께 보고 추천해요.</p>
          <Link to="/concierge"><Sparkles size={17} /> AI에게 물어보기 <ArrowRight size={16} /></Link>
        </div>
        <div className="ai-result-preview">
          {spots.filter((spot) => ['anmok-beach', 'gyeongpo-lake', 'geumjin-hotspring'].includes(spot.slug)).map((spot, index) => (
            <Link to={`/spot/${spot.id}`} key={spot.id}>
              <span>0{index + 1}</span><div><strong>{spot.name}</strong><small>{spot.reasons[0]} · {spot.index}점</small></div><ChevronRight size={17} />
            </Link>
          ))}
        </div>
      </section>

      <section className="home-section live-home-section" aria-labelledby="live-home-title">
        <div className="home-section-heading">
          <div><p>직접 눈으로</p><h2 id="live-home-title">가기 전, 물의 표정을 봐요.</h2></div>
          <Link to="/livecam">라이브캠 허브 <ArrowRight size={16} /></Link>
        </div>
        <div className="live-preview-grid">
          {livecams.slice(0, 3).map((cam, index) => (
            <Link to="/livecam" className={index === 0 ? 'large' : ''} key={cam.id}>
              <img src={cam.poster} alt={`${cam.name} 데모 미리보기`} />
              <span className="live-preview-shade" />
              <div className="live-preview-status"><Eye size={14} /> 실시간 아님 · DEMO</div>
              <div className="live-preview-copy"><span>{cam.region}</span><h3>{cam.name}</h3><small>Water Index {cam.waterIndex}</small></div>
              <div className="live-preview-play"><Play size={17} fill="currentColor" /></div>
            </Link>
          ))}
        </div>
      </section>

      <footer className="home-footer">
        <div className="footer-brand"><Droplets size={22} /><div><strong>퐁당 PongDang</strong><span>오늘 가장 좋은 물을 찾는 여행 플랫폼</span></div></div>
        <div className="footer-links"><Link to="/map">워터맵</Link><Link to="/forecast">7일 예보</Link><Link to="/concierge">AI 추천</Link><Link to="/profile">MY 퐁당</Link></div>
        <p>현재 화면은 문서 기반 제품 데모입니다. 안전 정보는 공식 발표와 현장 안내를 우선하세요.</p>
      </footer>
    </div>
  );
}

function CheckIcon() {
  return <span aria-hidden="true">✓</span>;
}

export default HomePage;
