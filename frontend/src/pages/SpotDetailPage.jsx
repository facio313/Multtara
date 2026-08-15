import { useMemo, useState } from 'react';
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
import { activityOptions, dataMeta, livecams, spots, weeklyForecast } from '../data/pongdangData';
import './SpotDetailPage.css';

const activityLabels = Object.fromEntries(activityOptions.map((activity) => [activity.id, activity.label]));

const facilitySets = {
  beach: [
    { icon: ShowerHead, title: '샤워·세족 공간', meta: '운영 여부 방문 전 확인', tag: '해변 편의' },
    { icon: Bath, title: '탈의 공간', meta: '개장 기간과 이용시간 확인', tag: '물놀이 후' },
    { icon: ParkingCircle, title: '인근 주차', meta: '현장 혼잡도에 따라 변동', tag: '이동' },
    { icon: Utensils, title: '로컬 한 끼', meta: '현재 위치 기반 연결 예정', tag: '미식' },
  ],
  hotspring: [
    { icon: Bath, title: '온천 운영시간', meta: '휴무·입장 마감 방문 전 확인', tag: '입욕' },
    { icon: Accessibility, title: '무장애 동선', meta: '시설별 지원 범위 확인', tag: '접근성' },
    { icon: ParkingCircle, title: '주차·진입', meta: '혼잡 시간대 방문 전 확인', tag: '이동' },
    { icon: Utensils, title: '회복 한 끼', meta: '주변 식당 연결 예정', tag: '미식' },
  ],
  valley: [
    { icon: ShieldAlert, title: '대피 지점', meta: '현장 안내판을 가장 먼저 확인', tag: '안전' },
    { icon: ParkingCircle, title: '진입·주차', meta: '통제와 입산 가능 여부 확인', tag: '이동' },
    { icon: ShowerHead, title: '세족·정비', meta: '인근 편의시설 연결 예정', tag: '물놀이 후' },
    { icon: Utensils, title: '지역 한 끼', meta: '현재 위치 기반 연결 예정', tag: '미식' },
  ],
  tidal_flat: [
    { icon: Clock3, title: '복귀 시각', meta: '조석과 현장 통제 우선 확인', tag: '안전' },
    { icon: ShowerHead, title: '세척 공간', meta: '운영 여부 방문 전 확인', tag: '체험 후' },
    { icon: ParkingCircle, title: '주차·진입', meta: '체험장별 이용 안내 확인', tag: '이동' },
    { icon: Utensils, title: '지역 한 끼', meta: '현재 위치 기반 연결 예정', tag: '미식' },
  ],
  default: [
    { icon: Accessibility, title: '접근 가능한 동선', meta: '현장 시설 정보 연결 예정', tag: '접근성' },
    { icon: ParkingCircle, title: '주차·진입', meta: '방문 전 운영 정보 확인', tag: '이동' },
    { icon: ShieldCheck, title: '안전 안내 지점', meta: '공식 안내와 현장 표지 우선', tag: '안전' },
    { icon: Utensils, title: '지역 한 끼', meta: '현재 위치 기반 연결 예정', tag: '미식' },
  ],
};

const analytics = [86, 82, 88, 90, 94];

function resolveForecastRegion(region) {
  if (region.includes('강릉')) return '강릉';
  if (region.includes('강원')) return '강원';
  if (/서울|경기|인천|수도권/.test(region)) return '수도권';
  if (/충청|대전|세종/.test(region)) return '충청';
  if (/전라|광주/.test(region)) return '전라';
  if (/경상|부산|대구|울산/.test(region)) return '경상';
  if (region.includes('제주')) return '제주';
  return '전국';
}

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

function TypeSpecificPanel({ spot }) {
  if (spot.type === 'hotspring') {
    return (
      <section className="detail-panel type-panel type-hotspring">
        <div className="detail-section-heading">
          <div><span>WELLNESS</span><h2>온천 효능과 이용 팁</h2></div>
          <Sparkles size={21} />
        </div>
        <div className="benefit-grid">
          <div><span>대표 성분</span><strong>해수 · 나트륨</strong><p>실제 성분표 연결 전 데모 분류</p></div>
          <div><span>추천 경험</span><strong>피로 회복 · 휴식</strong><p>장시간 입욕보다 충분한 수분 보충</p></div>
          <div><span>악천후 대안</span><strong>실내 스테이</strong><p>야외 일정에서 한 번에 전환 가능</p></div>
        </div>
      </section>
    );
  }

  if (spot.type === 'tidal_flat') {
    return (
      <section className="detail-panel type-panel type-tidal">
        <div className="detail-section-heading">
          <div><span>CATCH GUIDE</span><h2>갯벌 체험 도감</h2></div>
          <Clock3 size={21} />
        </div>
        <div className="catch-grid">
          <div><span>지금 볼 수 있어요</span><strong>바지락 · 칠게 · 갯고둥</strong></div>
          <div className="catch-warning"><span>반드시 확인해요</span><strong>금어기 · 포획금지 체장 · 복귀 시각</strong></div>
        </div>
      </section>
    );
  }

  if (spot.type === 'valley') {
    return (
      <section className="detail-panel type-panel type-valley">
        <div className="detail-section-heading">
          <div><span>VALLEY RADAR</span><h2>계곡 안전 레이더</h2></div>
          <ShieldAlert size={21} />
        </div>
        <div className="radar-track" aria-label="데모 위험도: 주의">
          <span className="radar-fill" />
          <span className="radar-marker" />
        </div>
        <div className="radar-labels"><span>안전</span><strong>주의 · 현장 재확인</strong><span>위험</span></div>
        <p>계곡은 국지성 강우 직후 급격히 달라집니다. 데모 점수가 아니라 공식 호우특보와 현장 통제가 최우선입니다.</p>
      </section>
    );
  }

  return (
    <section className="detail-panel type-panel type-sea">
      <div className="detail-section-heading">
        <div><span>GOLDEN MOMENT</span><h2>오늘의 물멍 & 인생샷</h2></div>
        <Camera size={21} />
      </div>
      <div className="golden-grid">
        <div><span>일몰 × 잔잔한 파도</span><strong>18:47</strong><p>해 질 녘 25분 전부터 추천</p></div>
        <div><span>ASMR 지수</span><strong>91</strong><p>잔잔한 백색소음 데모</p></div>
        <div><span>수질 신뢰도</span><strong>확인 중</strong><p>공식 데이터와 리뷰 연결 예정</p></div>
      </div>
    </section>
  );
}

function SpotDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const spot = useMemo(
    () => spots.find((item) => String(item.id) === id || item.slug === id),
    [id],
  );
  const [saved, setSaved] = useState(() => readFavorite(id));
  const [planned, setPlanned] = useState(false);

  if (!spot) {
    return (
      <div className="detail-not-found">
        <Droplets size={34} />
        <h1>이 물 여행지를 찾지 못했어요.</h1>
        <p>데모 데이터에 포함된 장소인지 확인하거나 워터맵에서 다시 골라보세요.</p>
        <Link to="/map">워터맵으로 이동 <ArrowRight size={16} /></Link>
      </div>
    );
  }

  const forecastRegion = resolveForecastRegion(spot.region);
  const forecast = weeklyForecast.filter((day) => day.region === forecastRegion).slice(0, 7);
  const bestForecast = forecast.reduce((best, day) => (day.score > best.score ? day : best));
  const facilities = facilitySets[spot.type] ?? facilitySets.default;
  const availableScores = Object.entries(spot.scores).filter(([, score]) => score !== null);
  const livecam = livecams.find((cam) => cam.id === spot.livecamId);

  const toggleSaved = () => {
    const next = !saved;
    setSaved(next);
    writeFavorite(id, next);
  };

  const downloadSafetyCard = () => {
    const content = [
      `퐁당 오프라인 안전 카드 — ${spot.name}`,
      `주소: ${spot.address}`,
      `상태: ${spot.safety.label}`,
      spot.safety.message,
      `데이터: ${spot.freshness.updatedLabel}`,
      '이 카드는 데모입니다. 실제 방문 전 공식 특보와 현장 안내를 확인하세요.',
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
        <img src={spot.imageUrl} alt={`${spot.name}의 물 풍경 데모 이미지`} />
        <div className="detail-visual-shade" />
        <div className="detail-top-actions">
          <button type="button" onClick={() => navigate(-1)} aria-label="뒤로 가기"><ArrowLeft size={20} /></button>
          <button type="button" className={saved ? 'saved' : ''} onClick={toggleSaved} aria-pressed={saved}>
            <Heart size={19} fill={saved ? 'currentColor' : 'none'} />
            {saved ? '저장됨' : '저장'}
          </button>
        </div>

        <div className="detail-title-block">
          <div className="detail-badges">
            <span>{spot.typeLabel}</span>
            {spot.isGangneungMvp && <span>강릉 MVP</span>}
            <span className="demo">데모 데이터</span>
          </div>
          <h1>{spot.name}</h1>
          <p><MapPin size={16} /> {spot.address}</p>
          <div className="detail-tags">{spot.tags.slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>
        </div>
      </header>

      <div className="detail-layout">
        <div className="detail-main">
          <section className={`safety-banner safety-${spot.safety.level}`} aria-live={spot.safety.level === 'safe' ? 'polite' : 'assertive'}>
            <div className="safety-icon">
              {spot.safety.level === 'safe' ? <ShieldCheck size={23} /> : <ShieldAlert size={23} />}
            </div>
            <div><span>SAFETY FIRST</span><strong>{spot.safety.label}</strong><p>{spot.safety.message}</p></div>
            <button type="button" onClick={downloadSafetyCard}><Download size={16} /> 오프라인 카드</button>
          </section>

          <section className="detail-panel score-panel">
            <div className="detail-section-heading">
              <div><span>ACTIVITY INDEX</span><h2>오늘, 이렇게 즐기기 좋아요.</h2></div>
              <span className="freshness-pill">{spot.freshness.updatedLabel}</span>
            </div>
            <div className="activity-score-grid">
              {availableScores.map(([activity, score], index) => (
                <div className={index === 0 ? 'primary-score' : ''} key={activity}>
                  <span>{activityLabels[activity]}</span>
                  <strong>{score}</strong>
                  <small>{score >= 90 ? '매우 좋음' : score >= 80 ? '좋음' : '조건 확인'}</small>
                </div>
              ))}
            </div>
            <div className="score-reasons">
              <span>점수 근거</span>
              {spot.reasons.map((reason) => <p key={reason}><Check size={14} /> {reason}</p>)}
            </div>
          </section>

          <section className="detail-panel condition-panel">
            <div className="detail-section-heading">
              <div><span>CONDITION</span><h2>지금 물의 표정</h2></div>
              <CloudSun size={21} />
            </div>
            <div className="metric-grid">
              <div><ThermometerSun size={21} /><span>수온</span><strong>{spot.conditions.waterTemp}</strong></div>
              <div><CloudSun size={21} /><span>기온</span><strong>{spot.conditions.airTemp}</strong></div>
              <div><Waves size={21} /><span>파고</span><strong>{spot.conditions.waveHeight}</strong></div>
              <div><Wind size={21} /><span>바람</span><strong>{spot.conditions.windSpeed}</strong></div>
              <div><Droplets size={21} /><span>수질</span><strong>{spot.conditions.waterQuality}</strong></div>
              <div><Accessibility size={21} /><span>혼잡</span><strong>{spot.conditions.crowd}</strong></div>
            </div>
            {spot.type === 'sea' || spot.type === 'tidal_flat' ? (
              <div className="tide-timeline">
                <div><span>간조</span><strong>{spot.conditions.tide.low}</strong></div>
                <div className="tide-line"><span className="tide-progress" /></div>
                <div><span>만조</span><strong>{spot.conditions.tide.high}</strong></div>
              </div>
            ) : null}
          </section>

          <section className="detail-panel forecast-panel">
            <div className="detail-section-heading">
              <div><span>WATER FORECAST</span><h2>이번 주, 더 좋은 날</h2></div>
              <Link to="/forecast">전체 예보 <ChevronRight size={16} /></Link>
            </div>
            <div className="detail-forecast-strip">
              {forecast.map((day) => (
                <div className={day.score >= 90 ? 'best' : ''} key={day.id}>
                  <span>{day.day}</span>
                  <strong>{day.score}</strong>
                  <div className="forecast-mini-bar"><span style={{ height: `${day.score}%` }} /></div>
                  <small>{day.date.slice(5).replace('-', '.')}</small>
                </div>
              ))}
            </div>
            <div className="best-day-note"><Sparkles size={18} /><p><strong>{forecastRegion}은 {bestForecast.day}요일이 가장 좋아요.</strong> {bestForecast.best} 시간대의 고정 데모 예보이며, 방문 전 공식 예보를 확인하세요.</p></div>
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
              <div className="livecam-poster"><img src={livecam.poster} alt={`${livecam.name} 데모 미리보기`} /><span><Radio size={15} /> 데모 미리보기</span></div>
              <div><span>SEE IT YOURSELF</span><h2>{livecam.name}</h2><p>현재 이미지는 실시간 영상이 아닙니다. 공식 스트림이 연결되면 방문 전 파도와 인파를 직접 확인할 수 있어요.</p><Link to="/livecam">라이브캠 허브 <ArrowRight size={16} /></Link></div>
            </section>
          ) : null}

          <TypeSpecificPanel spot={spot} />

          <section className="detail-panel analytics-panel">
            <div className="detail-section-heading">
              <div><span>WATER LIFE</span><h2>최근 5년과 비교하면</h2></div>
              <span className="demo-label">설명용 데모</span>
            </div>
            <div className="analytics-layout">
              <div className="analytics-copy"><strong>상위 12%</strong><p>올해 같은 계절의 평년 조건보다 좋은 상태를 가정했어요.</p></div>
              <div className="analytics-bars" aria-label="5년 비교 데모 차트">
                {analytics.map((value, index) => <div key={value}><span style={{ height: `${value}%` }} /><small>{2022 + index}</small></div>)}
              </div>
            </div>
          </section>
        </div>

        <aside className="detail-sidebar">
          <div className="sidebar-index-card">
            <span>WATER INDEX</span>
            <div className="sidebar-score" style={{ '--score': spot.index }}><strong>{spot.index}</strong></div>
            <h2>{spot.summary}</h2>
            <p>{spot.description}</p>
            <div><Clock3 size={16} /><span>BEST TIME</span><strong>{spot.bestTime}</strong></div>
          </div>
          <div className="source-card">
            <span>DATA STATUS</span><h3>현재는 고정 데모예요.</h3><p>{dataMeta.disclaimer}</p>
            <ul>{dataMeta.plannedSources.slice(0, 4).map((source) => <li key={source}>{source}</li>)}</ul>
          </div>
        </aside>
      </div>

      <div className="detail-sticky-actions">
        <div><span>{spot.name}</span><strong>{planned ? '일정에 담았어요' : spot.bestTime}</strong></div>
        <a
          className="directions"
          href={`https://map.kakao.com/?q=${encodeURIComponent(`${spot.name} ${spot.address}`)}`}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={17} /> 카카오맵
        </a>
        <button type="button" className={planned ? 'planned' : ''} onClick={() => setPlanned(true)}>
          {planned ? <Check size={17} /> : <CalendarDays size={17} />}
          {planned ? '추가됨' : '일정에 추가'}
        </button>
      </div>
    </div>
  );
}

export default SpotDetailPage;
