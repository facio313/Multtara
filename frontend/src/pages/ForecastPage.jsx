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
import './ForecastPage.css';

const ACTIVITY_OPTIONS = [
  { id: 'swim', label: '물놀이' },
  { id: 'surf', label: '서핑' },
  { id: 'relax', label: '물멍' },
  { id: 'mudflat', label: '갯벌' },
  { id: 'onsen', label: '온천' },
  { id: 'rafting', label: '래프팅' },
];

const STATUS_LABELS = {
  excellent: '최적',
  good: '좋음',
  fair: '보통',
  caution: '주의',
  unavailable: '미수집',
};

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
  const activity = ACTIVITY_OPTIONS.find((option) => option.id === selectedActivity);

  const recommendedSpot = useMemo(() => {
    const scopedSpots = SPOT_DATA.filter((spot) => regionMatches(spot.region, selectedRegion));
    return scopedSpots
      .map((spot) => ({ ...spot, activityScore: getSpotActivityScore(spot, selectedActivity) }))
      .sort((a, b) => (b.activityScore ?? b.index ?? -1) - (a.activityScore ?? a.index ?? -1))[0] || null;
  }, [selectedActivity, selectedRegion]);

  const updateLabel = resolveFreshnessLabel(days, recommendedSpot);
  const displayRegion = selectedRegion === '전국' ? '전국 데모 지역' : selectedRegion;

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
          <h1 id="forecast-title">
            가장 좋은 물의 순간을
            <span> 7일 먼저 만나요</span>
          </h1>
          <p>
            기온·파고·강수와 물 상태를 함께 읽어, 막연한 예보 대신
            방문하기 좋은 날을 또렷하게 보여드립니다.
          </p>
        </div>

        <div className="forecast-hero__signal" aria-label="예보 데이터 안내">
          <CalendarDays aria-hidden="true" />
          <div>
            <strong>문서 기반 고정 예보</strong>
            <span>실측 데이터가 연결되면 관측 시각과 출처가 여기에 표시됩니다.</span>
          </div>
        </div>
      </header>

      <section className="forecast-controls" aria-labelledby="forecast-controls-title">
        <div className="forecast-controls__heading">
          <div>
            <span className="forecast-eyebrow">MY WATER FORECAST</span>
            <h2 id="forecast-controls-title">어디서, 무엇을 즐길까요?</h2>
          </div>
          <p aria-live="polite">
            {displayRegion} · {activity?.label} 기준으로 보고 있어요.
          </p>
        </div>

        <div className="forecast-control-groups">
          <fieldset className="forecast-choice-group">
            <legend>지역</legend>
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
            <legend>여행 목적</legend>
            <div className="forecast-choice-list forecast-choice-list--activity">
              {ACTIVITY_OPTIONS.map((option) => (
                <button
                  type="button"
                  key={option.id}
                  className={selectedActivity === option.id ? 'is-active' : ''}
                  aria-pressed={selectedActivity === option.id}
                  onClick={() => {
                    setSelectedActivity(option.id);
                    setSelectedDayId(null);
                  }}
                >
                  {option.label}
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
                  <h2 id="forecast-week-title">{displayRegion} 주간 흐름</h2>
                </div>
                <div className="forecast-legend" aria-label="점수 범례">
                  <span><i className="excellent" />90+ 최적</span>
                  <span><i className="good" />80+ 좋음</span>
                  <span><i className="fair" />65+ 보통</span>
                  <span><i className="caution" />주의</span>
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
                      aria-label={`${day.date} ${day.day}, ${activity?.label} 지수 ${day.resolvedScore ?? '미수집'}점, ${STATUS_LABELS[day.tone]}${isBest ? ', 이번 주 추천일' : ''}`}
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
                        {isBest ? 'BEST' : STATUS_LABELS[day.tone]}
                      </span>
                    </button>
                  );
                })}
              </div>

              <p className="forecast-data-note">
                <Info size={16} aria-hidden="true" />
                활동별 세부 예보가 없는 날은 지역 종합 Water Index를 사용합니다.
                점수는 안전 경보를 대신하지 않습니다.
              </p>
            </section>

            <aside className="forecast-best-card" aria-labelledby="forecast-best-title">
              <span className="forecast-best-card__label">
                <Sparkles size={16} aria-hidden="true" /> 이번 주의 퐁당 타이밍
              </span>
              <div className="forecast-best-card__score" aria-hidden="true">
                <span>{bestDay?.resolvedScore ?? '—'}</span>
                <small>/ 100</small>
              </div>
              <h2 id="forecast-best-title">
                {bestDay?.day}요일, {activity?.label}하기 가장 좋아요
              </h2>
              <p>
                {bestDay?.label || `${bestDay?.date} 예보 가운데 Water Index가 가장 높습니다.`}
              </p>

              <ul className="forecast-reason-list">
                {(bestDay?.factors.length
                  ? bestDay.factors
                  : ['선택한 기간의 최고 Water Index', `${bestDay?.weather || '날씨 정보 확인 중'} 예보 반영`]
                ).slice(0, 3).map((factor) => (
                  <li key={factor}>
                    <Check size={16} aria-hidden="true" />
                    <span>{factor}</span>
                  </li>
                ))}
              </ul>

              {recommendedSpot && (
                <div className="forecast-spot-pick">
                  <span>이 지역 추천 스팟</span>
                  <strong>{recommendedSpot.name}</strong>
                  <small>
                    {recommendedSpot.typeLabel || recommendedSpot.type}
                    {recommendedSpot.activityScore !== null && recommendedSpot.activityScore !== undefined
                      ? ` · 현재 ${activity?.label} ${recommendedSpot.activityScore}점`
                      : ''}
                  </small>
                  <Link to={`/spot/${recommendedSpot.id}`}>
                    스팟 자세히 보기 <ArrowUpRight size={15} aria-hidden="true" />
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
                  {selectedDay.label || `${selectedDay.weather} 예보를 반영한 문서 기반 데모입니다.`}
                </p>
              </div>

              <dl className="forecast-metric-grid">
                <div>
                  <dt><ThermometerSun aria-hidden="true" /> 기온</dt>
                  <dd>{formatMetric(selectedDay.temperature, '°C')}</dd>
                </div>
                <div>
                  <dt><Waves aria-hidden="true" /> 파고</dt>
                  <dd>{formatMetric(selectedDay.waveHeight, 'm')}</dd>
                </div>
                <div>
                  <dt><CloudRain aria-hidden="true" /> 강수 확률</dt>
                  <dd>{formatMetric(selectedDay.rainChance, '%')}</dd>
                </div>
                <div>
                  <dt><Wind aria-hidden="true" /> 상태</dt>
                  <dd>{STATUS_LABELS[getTone(selectedDay.resolvedScore)]}</dd>
                </div>
              </dl>
            </section>
          )}

          <details className="forecast-table-panel">
            <summary>
              <span>
                <TableProperties aria-hidden="true" /> 표로 자세히 보기
              </span>
              <small>차트와 같은 데이터를 읽기 쉬운 표로 제공합니다.</small>
            </summary>
            <div className="forecast-table-wrap">
              <table>
                <caption>{displayRegion} {activity?.label} 7일 예보</caption>
                <thead>
                  <tr>
                    <th scope="col">날짜</th>
                    <th scope="col">날씨</th>
                    <th scope="col">기온</th>
                    <th scope="col">파고</th>
                    <th scope="col">강수</th>
                    <th scope="col">Water Index</th>
                    <th scope="col">판정</th>
                  </tr>
                </thead>
                <tbody>
                  {days.map((day) => (
                    <tr key={`table-${day.id}`}>
                      <th scope="row">{day.date} {day.day}</th>
                      <td>{day.weather}</td>
                      <td>{formatMetric(day.temperature, '°C')}</td>
                      <td>{formatMetric(day.waveHeight, 'm')}</td>
                      <td>{formatMetric(day.rainChance, '%')}</td>
                      <td>{day.resolvedScore ?? '미수집'}</td>
                      <td>{STATUS_LABELS[day.tone]}{bestDay?.id === day.id ? ' · 추천일' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <footer className="forecast-source-note">
            <BarChart3 aria-hidden="true" />
            <div>
              <strong>데이터를 솔직하게 보여드려요</strong>
              <p>
                현재 화면은 고정 데모 데이터입니다. 실제 연동 이후에는 기상청·해양 관측 데이터의
                출처, 관측 시각, 누락 여부를 각 지표에 함께 표시합니다.
              </p>
            </div>
          </footer>
        </>
      ) : (
        <section className="forecast-empty" role="status">
          <MapPin aria-hidden="true" />
          <h2>{selectedRegion} 예보를 준비하고 있어요</h2>
          <p>현재 제공 가능한 지역을 선택하거나 기본 데모 예보로 돌아가세요.</p>
          <button type="button" onClick={resetForecast}>기본 예보 보기</button>
        </section>
      )}
    </div>
  );
}

export default ForecastPage;
