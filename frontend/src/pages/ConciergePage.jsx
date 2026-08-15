import { useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  ArrowRight,
  CalendarPlus,
  Car,
  Check,
  Clock3,
  Compass,
  MapPin,
  MessageCircleMore,
  Send,
  ShieldCheck,
  Sparkles,
  WandSparkles,
} from 'lucide-react';
import { personas } from '../data/pongdangData';
import './ConciergePage.css';

const promptSuggestions = [
  '이번 주말 연인과 드라이브하며 물을 보고 싶어요',
  '아이와 안전하게 놀 수 있는 얕은 바다를 찾아줘',
  '비 오는 날에도 좋은 따뜻한 온천 코스가 필요해',
  '사람 적고 파도 좋은 서핑 스팟을 추천해줘',
];

const recommendationSets = {
  family: [
    { id: 'gyeongpo-beach', name: '경포해변', region: '강원 강릉', score: 91, type: '패밀리', reason: '얕은 수심 · 안전요원 · 샤워장 가까움', safety: '데모 안전 정보' },
    { id: 'yeongok-beach', name: '연곡해변', region: '강원 강릉', score: 88, type: '한적한 바다', reason: '완만한 모래사장 · 비교적 여유로운 혼잡도', safety: '데모 안전 정보' },
    { id: 'geumjin-hotspring', name: '금진온천', region: '강원 강릉', score: 84, type: '실내 대안', reason: '날씨 영향이 적고 휴식 동선으로 전환하기 쉬움', safety: '운영 전 재확인' },
  ],
  wellness: [
    { id: 'geumjin-hotspring', name: '금진온천', region: '강원 강릉', score: 93, type: '웰니스', reason: '해수 온천 · 조용한 시간대 · 바다 전망 동선', safety: '운영 전 재확인' },
    { id: 'anmok-beach', name: '안목해변', region: '강원 강릉', score: 90, type: '물멍', reason: '잔잔한 파도 · 카페거리 · 일몰 전 산책', safety: '데모 해안 정보' },
    { id: 'gyeongpo-lake', name: '경포호수', region: '강원 강릉', score: 87, type: '호수 산책', reason: '고요한 수면 · 무장애 산책로 · 낮은 혼잡도', safety: '산책로 정보' },
  ],
  active: [
    { id: 'sacheonjin-beach', name: '사천진해변', region: '강원 강릉', score: 92, type: '서핑', reason: '데모 기준의 파도 · 풍속 · 장비 접근성을 반영', safety: '현장 파고 재확인' },
    { id: 'jeongdongjin-beach', name: '정동진해변', region: '강원 강릉', score: 89, type: '패들보드', reason: '오전 바람과 입수 동선을 기준으로 추천', safety: '공식 특보 재확인' },
    { id: 'yeongok-beach', name: '연곡해변', region: '강원 강릉', score: 86, type: '카약', reason: '차량 접근과 활동 가능 시간대를 기준으로 추천', safety: '주의 구간 재확인' },
  ],
};

const itinerary = [
  { time: '09:30', title: '강릉역에서 출발', meta: '차량 18분', icon: Car },
  { time: '10:00', title: '첫 번째 추천 스팟', meta: '물 컨디션 확인 후 2시간', icon: Compass },
  { time: '12:20', title: '물놀이 후 로컬 한 끼', meta: '젖은 상태 이동 7분', icon: MapPin },
  { time: '14:10', title: '오션뷰 카페와 산책', meta: '실내 대체 가능', icon: Clock3 },
];

function getIntent(query) {
  if (/아이|가족|얕|안전/.test(query)) return 'family';
  if (/온천|힐링|지친|조용|비 |비가|실내|물멍/.test(query)) return 'wellness';
  return 'active';
}

function readPersonaId() {
  try {
    return localStorage.getItem('pongdang:persona-preference');
  } catch {
    return null;
  }
}

function getPersonaIntent(personaId) {
  if (personaId === 'family') return 'family';
  if (['wellness', 'local', 'indoor'].includes(personaId)) return 'wellness';
  return 'active';
}

function ConciergePage() {
  const location = useLocation();
  const personaId = location.state?.personaId || readPersonaId();
  const persona = personas.find((item) => item.id === personaId) ?? null;
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [itinerarySaved, setItinerarySaved] = useState(false);
  const intent = useMemo(
    () => (submittedQuery ? getIntent(submittedQuery) : getPersonaIntent(persona?.id)),
    [persona?.id, submittedQuery],
  );
  const results = recommendationSets[intent];

  const submitQuery = (event) => {
    event?.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      setSubmittedQuery(trimmed);
      setItinerarySaved(false);
    }
  };

  const chooseSuggestion = (suggestion) => {
    setQuery(suggestion);
    setSubmittedQuery(suggestion);
    setItinerarySaved(false);
  };

  const saveItinerary = () => {
    try {
      localStorage.setItem('pongdang:demo-itinerary', JSON.stringify({ intent, spotId: results[0].id }));
    } catch {
      // The confirmation remains useful for this session if storage is blocked.
    }
    setItinerarySaved(true);
  };

  return (
    <div className="concierge-page">
      <header className="concierge-hero">
        <div className="concierge-heading">
          <span className="concierge-kicker"><WandSparkles size={15} /> AI WATER CONCIERGE</span>
          <h1>가고 싶은 기분만<br />말해 주세요.</h1>
          <p>
            물 상태 데모, 이동 시간, 혼잡도와 안전 항목을 엮어
            취향에 맞는 강릉 물 여행의 구조를 미리 보여드려요.
          </p>
          <div className="concierge-proof">
            <span><Check size={14} /> 데모 컨디션 반영</span>
            <span><Check size={14} /> 악천후 실내 대안</span>
            <span><Check size={14} /> 물놀이 전후 동선</span>
          </div>
        </div>

        <div className="concierge-orb" aria-hidden="true">
          <Sparkles size={34} />
          <span>오늘의 물을<br />읽는 중</span>
        </div>
      </header>

      <div className="concierge-workspace">
        <section className="concierge-composer" aria-labelledby="composer-title">
          <div className="composer-title-row">
            <div>
              <span>STEP 01</span>
              <h2 id="composer-title">어떤 하루를 원하세요?</h2>
            </div>
            <span className="demo-label">{persona ? `${persona.title} 맞춤` : '데모 추천'}</span>
          </div>

          <form onSubmit={submitQuery} className="concierge-input-wrap">
            <MessageCircleMore size={22} aria-hidden="true" />
            <label className="sr-only" htmlFor="concierge-query">여행 요청 입력</label>
            <textarea
              id="concierge-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="예: 이번 주말 연인과 드라이브하며 조용히 물을 보고 싶어요"
              rows="3"
            />
            <button type="submit" disabled={!query.trim()}>
              <Send size={18} />
              추천받기
            </button>
          </form>

          <div className="prompt-suggestions" aria-label="추천 질문">
            {promptSuggestions.map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => chooseSuggestion(suggestion)}>
                {suggestion}
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
        </section>

        {submittedQuery || persona ? (
          <section className="concierge-results" aria-live="polite">
            <div className="result-context">
              <span><Sparkles size={16} /> 퐁당의 답변</span>
              <h2>{submittedQuery ? `“${submittedQuery}”` : `${persona.title} 취향으로 골랐어요.`}</h2>
              <p>
                {intent === 'family' && '안전과 편의시설을 가장 먼저 보고, 이동 부담이 적은 순서로 골랐어요.'}
                {intent === 'wellness' && '고요한 분위기와 실내 대안, 물멍 동선을 중심으로 골랐어요.'}
                {intent === 'active' && '파도와 바람이 안정적인 시간, 장비 접근성을 중심으로 골랐어요.'}
              </p>
            </div>

            <div className="recommendation-grid">
              {results.map((spot, index) => (
                <article className={`recommendation-card rank-${index + 1}`} key={spot.id}>
                  <div className="recommendation-rank">
                    <span>0{index + 1}</span>
                    <span>{spot.type}</span>
                  </div>
                  <div className="recommendation-score" aria-label={`워터 인덱스 ${spot.score}점`}>
                    <strong>{spot.score}</strong>
                    <small>INDEX</small>
                  </div>
                  <h3>{spot.name}</h3>
                  <p className="recommendation-region"><MapPin size={14} /> {spot.region}</p>
                  <p className="recommendation-reason">{spot.reason}</p>
                  <div className="recommendation-safety"><ShieldCheck size={15} /> {spot.safety}</div>
                  <Link to={`/spot/${spot.id}`}>
                    상세 보기 <ArrowRight size={16} />
                  </Link>
                </article>
              ))}
            </div>

            <div className="itinerary-preview">
              <div className="itinerary-copy">
                <span>STEP 02</span>
                <h2>이대로 하루 코스를 만들까요?</h2>
                <p>추천 장소와 젖은 상태의 이동 반경, 식사와 실내 대안까지 이어드려요.</p>
                <button
                  className={itinerarySaved ? 'is-saved' : ''}
                  type="button"
                  onClick={saveItinerary}
                  aria-pressed={itinerarySaved}
                >
                  {itinerarySaved ? <Check size={18} /> : <CalendarPlus size={18} />}
                  {itinerarySaved ? '이 기기에 저장됨' : '데모 일정 저장하기'}
                </button>
              </div>
              <ol className="itinerary-timeline">
                {itinerary.map(({ time, title, meta, icon: Icon }, index) => (
                  <li key={time}>
                    <div className="timeline-icon"><Icon size={17} /></div>
                    <div>
                      <span>{time}</span>
                      <strong>{index === 1 ? results[0].name : title}</strong>
                      <small>{meta}</small>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </section>
        ) : (
          <section className="concierge-empty">
            <Sparkles size={20} />
            <p>한 문장만 들려주면 추천 이유와 반나절 동선을 함께 보여드릴게요.</p>
          </section>
        )}
      </div>
    </div>
  );
}

export default ConciergePage;
