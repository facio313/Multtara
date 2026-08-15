import { useState } from 'react';
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
import { activityOptions, livecams, weeklyForecast } from '../data/pongdangData';
import { useWaterSpot } from '../hooks/useWaterData';
import { localizedDataState, localizedSafety, useI18n } from '../i18n';
import {
  formatMetricName,
  getSpotActivityView,
  isRecommendationEligible,
  scoreLabel,
} from '../services/waterData';
import './SpotDetailPage.css';

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

function defaultActivityForSpot(spot) {
  if (!spot) return 'swim';
  const preferred = {
    hotspring: 'onsen',
    tidal_flat: 'mudflat',
    valley: 'rafting',
  }[spot.type] ?? 'swim';
  if (spot.conditionRecords?.[preferred] || spot.scores?.[preferred] !== null) return preferred;
  return activityOptions.find((activity) => (
    spot.conditionRecords?.[activity.id] || spot.scores?.[activity.id] !== null
  ))?.id ?? preferred;
}

function formatDateTime(value, locale, fallback) {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function TypeSpecificPanel({ spot }) {
  const { t } = useI18n();
  if (spot.type === 'hotspring') {
    return (
      <section className="detail-panel type-panel type-hotspring">
        <div className="detail-section-heading">
          <div><span>FACILITY FIT</span><h2>온천 시설 특성과 이용 팁</h2></div>
          <Sparkles size={21} />
        </div>
        <div className="benefit-grid">
          <div><span>대표 성분</span><strong>해수 · 나트륨</strong><p>실제 시설 성분표 연결 전 데모 분류</p></div>
          <div><span>WELLNESS</span><strong>REST · WARM WATER</strong><p>{t('spot.type.hotspringDisclaimer')}</p></div>
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
        <p>{t('spot.type.valleyDisclaimer')}</p>
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
  const { intlLocale, t } = useI18n();
  const {
    spot,
    spotStatus,
    conditionStatus,
    observationStatus,
    retryData,
  } = useWaterSpot(id);
  const [requestedActivity, setRequestedActivity] = useState(null);
  const [saved, setSaved] = useState(() => readFavorite(id));
  const [planned, setPlanned] = useState(false);

  if (!spot) {
    if (spotStatus === 'idle' || spotStatus === 'loading') {
      return (
        <div className="detail-not-found detail-loading" role="status" aria-live="polite">
          <Droplets size={34} />
          <h1>{t('spot.loading.title')}</h1>
          <p>{t('spot.loading.description')}</p>
        </div>
      );
    }
    return (
      <div className="detail-not-found">
        <Droplets size={34} />
        <h1>{t('spot.notFound.title')}</h1>
        <p>{t('spot.notFound.description')}</p>
        <Link to="/map">{t('spot.notFound.cta')} <ArrowRight size={16} /></Link>
      </div>
    );
  }

  const selectedActivity = requestedActivity ?? defaultActivityForSpot(spot);
  const selectedView = getSpotActivityView(spot, selectedActivity);
  const selectedSafety = localizedSafety(t, selectedView.safety.level);
  const forecastRegion = resolveForecastRegion(spot.region);
  const forecast = weeklyForecast.filter((day) => day.region === forecastRegion).slice(0, 7);
  const bestForecast = forecast.reduce((best, day) => (day.score > best.score ? day : best));
  const facilities = facilitySets[spot.type] ?? facilitySets.default;
  const availableActivities = activityOptions.filter((activity) => (
    spot.conditionRecords?.[activity.id] || spot.scores?.[activity.id] !== null
  ));
  const livecam = livecams.find((cam) => cam.id === spot.livecamId);
  const detailDataError = spotStatus === 'error'
    || conditionStatus === 'error'
    || observationStatus === 'error';
  const detailDataLoading = !detailDataError && (['idle', 'loading'].includes(spotStatus)
    || (
      spot.apiId !== null
      && (
        ['idle', 'loading'].includes(conditionStatus)
        || ['idle', 'loading'].includes(observationStatus)
      )
    ));

  const toggleSaved = () => {
    const next = !saved;
    setSaved(next);
    writeFavorite(id, next);
  };

  const downloadSafetyCard = () => {
    const content = [
      `${t('spot.card.title')} — ${spot.name}`,
      `${t('spot.card.address')}: ${spot.address}`,
      `${t('spot.card.activity')}: ${t(`activity.${selectedActivity}`)}`,
      `${t('spot.card.safety')}: ${selectedSafety.label}`,
      `${t('spot.card.score')}: ${selectedView.score === null ? t('common.scoreMissing') : selectedView.score}`,
      `${t('spot.card.data')}: ${localizedDataState(t, selectedView.dataState)}`,
      selectedSafety.message,
      ...selectedView.reasons.map((reason) => `${t('spot.card.reason')}: ${reason.code} — ${reason.label}`),
      `${t('spot.evidence.provider')}: ${selectedView.provenance.provider}`,
      `${t('spot.evidence.scope')}: ${selectedView.provenance.spatialScope}`,
      `${t('spot.card.updated')}: ${selectedView.provenance.updatedLabel}`,
      t('common.scoreNotSafety'),
      t('common.officialFirst'),
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
        {spot.imageUrl
          ? <img src={spot.imageUrl} alt={`${spot.name}의 물 풍경`} />
          : <div className="detail-image-placeholder" aria-hidden="true">{spot.visual.icon}</div>}
        <div className="detail-visual-shade" />
        <div className="detail-top-actions">
          <button type="button" onClick={() => navigate(-1)} aria-label={t('spot.back')}><ArrowLeft size={20} /></button>
          <button type="button" className={saved ? 'saved' : ''} onClick={toggleSaved} aria-pressed={saved}>
            <Heart size={19} fill={saved ? 'currentColor' : 'none'} />
            {saved ? t('common.saved') : t('common.save')}
          </button>
        </div>

        <div className="detail-title-block">
          <div className="detail-badges">
            <span>{spot.typeLabel}</span>
            {spot.isGangneungMvp && <span>강릉 MVP</span>}
            <span className={`demo state-${selectedView.dataState}`}>
              {localizedDataState(t, selectedView.dataState)}
            </span>
          </div>
          <h1>{spot.name}</h1>
          <p><MapPin size={16} /> {spot.address}</p>
          <div className="detail-tags">{spot.tags.slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>
        </div>
      </header>

      <div className="detail-layout">
        <div className="detail-main">
          {detailDataLoading && (
            <div className="detail-data-status state-loading" role="status" aria-live="polite">
              <Droplets size={19} aria-hidden="true" />
              <div><strong>{t('spot.data.loading.title')}</strong><span>{t('spot.data.loading.description')}</span></div>
            </div>
          )}
          {spot.apiId !== null && conditionStatus === 'empty' && observationStatus === 'empty' && (
            <div className="detail-data-status state-empty" role="status" aria-live="polite">
              <ShieldAlert size={19} aria-hidden="true" />
              <div><strong>{t('spot.data.empty.title')}</strong><span>{t('spot.data.empty.description')}</span></div>
            </div>
          )}
          {detailDataError && (
            <div className="detail-data-status state-error" role="alert">
              <ShieldAlert size={19} />
              <div><strong>{t('spot.data.error.title')}</strong><span>{t('spot.data.error.description')}</span></div>
              <button type="button" onClick={retryData}>{t('common.retry')}</button>
            </div>
          )}
          <section className={`safety-banner safety-${selectedView.safety.level}`} aria-live={selectedView.safety.level === 'clear' ? 'polite' : 'assertive'}>
            <div className="safety-icon">
              {selectedView.safety.level === 'clear' ? <ShieldCheck size={23} /> : <ShieldAlert size={23} />}
            </div>
            <div><span>SAFETY FIRST · {t(`activity.${selectedActivity}`)}</span><strong>{selectedSafety.label}</strong><p>{selectedSafety.message}</p></div>
            <button type="button" onClick={downloadSafetyCard}><Download size={16} /> {t('spot.safety.offlineCard')}</button>
          </section>

          <section className="detail-panel score-panel">
            <div className="detail-section-heading">
              <div><span>ACTIVITY INDEX</span><h2>{t('spot.index.title')}</h2></div>
              <span className={`freshness-pill state-${selectedView.dataState}`}>{selectedView.provenance.updatedLabel}</span>
            </div>
            <div className="activity-score-grid" role="tablist" aria-label="활동별 Water Index">
              {availableActivities.map((activity) => {
                const view = getSpotActivityView(spot, activity.id);
                const isSelected = activity.id === selectedActivity;
                return (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={isSelected}
                    className={isSelected ? 'primary-score' : ''}
                    onClick={() => setRequestedActivity(activity.id)}
                    key={activity.id}
                  >
                    <span>{t(`activity.${activity.id}`)}</span>
                    <strong>{scoreLabel(view)}</strong>
                    <small>{view.score === null ? localizedSafety(t, view.safety.level).label : localizedDataState(t, view.dataState)}</small>
                  </button>
                );
              })}
              {availableActivities.length === 0 && (
                <div className="score-empty"><strong>—</strong><span>{t('spot.index.empty')}</span></div>
              )}
            </div>
            <div className="score-confidence-row">
              <span>{t('spot.index.confidence')} <strong>{selectedView.confidence === null ? '—' : `${Math.round(selectedView.confidence * 100)}%`}</strong></span>
              <span>coverage <strong>{selectedView.coverage === null ? '—' : `${Math.round(selectedView.coverage * 100)}%`}</strong></span>
              {selectedView.score === null && selectedView.scoreRange.length === 2 && <span>{t('spot.index.range')} <strong>{selectedView.scoreRange.join('–')}</strong></span>}
              <span>{t('spot.index.method')} <strong>{selectedView.methodologyVersion}</strong></span>
            </div>
            <div className="score-reasons">
              <span>{t('spot.index.reasons')}</span>
              {selectedView.reasons.map((reason) => <p key={reason.code}><Check size={14} /><code>{reason.code}</code> {reason.label}</p>)}
              {selectedView.reasons.length === 0 && selectedView.isDemoFallback
                ? spot.reasons.map((reason) => <p key={reason}><Check size={14} /> {reason} <em>DEMO</em></p>)
                : null}
              {selectedView.reasons.length === 0 && !selectedView.isDemoFallback && <p><ShieldAlert size={14} /> {t('spot.index.noReason')}</p>}
            </div>
          </section>

          <section className="detail-panel condition-panel">
            <div className="detail-section-heading">
              <div><span>CONDITION</span><h2>{t('spot.conditions.title')}</h2></div>
              <CloudSun size={21} />
            </div>
            <div className="metric-grid">
              <div><ThermometerSun size={21} /><span>{t('metric.waterTemp')}</span><strong>{selectedView.conditions.waterTemp}</strong></div>
              <div><CloudSun size={21} /><span>{t('metric.airTemp')}</span><strong>{selectedView.conditions.airTemp}</strong></div>
              <div><Waves size={21} /><span>{t('metric.waveHeight')}</span><strong>{selectedView.conditions.waveHeight}</strong></div>
              <div><Wind size={21} /><span>{t('metric.wind')}</span><strong>{selectedView.conditions.windSpeed}</strong></div>
              <div><Droplets size={21} /><span>{t('metric.waterQuality')}</span><strong>{selectedView.conditions.waterQuality}</strong></div>
              <div><Accessibility size={21} /><span>{t('metric.crowd')}</span><strong>{selectedView.conditions.crowd}</strong></div>
            </div>
            {spot.type === 'sea' || spot.type === 'tidal_flat' ? (
              <div className="tide-timeline">
                <div><span>{t('spot.conditions.lowTide')}</span><strong>{selectedView.conditions.tide.low}</strong></div>
                <div className="tide-line"><span className="tide-progress" /></div>
                <div><span>{t('spot.conditions.highTide')}</span><strong>{selectedView.conditions.tide.high}</strong></div>
              </div>
            ) : null}
          </section>

          <section className="detail-panel evidence-panel" aria-labelledby="evidence-title">
            <div className="detail-section-heading">
              <div><span>PROVENANCE & LIMITS</span><h2 id="evidence-title">{t('spot.evidence.title')}</h2></div>
              <span className={`freshness-pill state-${selectedView.dataState}`}>{localizedDataState(t, selectedView.dataState, true)}</span>
            </div>
            <dl className="provenance-grid">
              <div><dt>{t('spot.evidence.provider')}</dt><dd>{selectedView.provenance.provider}</dd></div>
              <div><dt>{t('spot.evidence.scope')}</dt><dd>{selectedView.provenance.spatialScope}</dd></div>
              <div><dt>{t('spot.evidence.observed')}</dt><dd>{formatDateTime(selectedView.provenance.observedAt, intlLocale, t('common.noData'))}</dd></div>
              <div><dt>{t('spot.evidence.fetched')}</dt><dd>{formatDateTime(selectedView.provenance.fetchedAt, intlLocale, t('common.noData'))}</dd></div>
              <div><dt>{t('spot.evidence.validUntil')}</dt><dd>{formatDateTime(selectedView.provenance.validUntil, intlLocale, t('common.noData'))}</dd></div>
              <div><dt>{t('spot.evidence.version')}</dt><dd>{selectedView.methodologyVersion}</dd></div>
            </dl>
            <div className="evidence-lists">
              <div>
                <span>{t('spot.evidence.missing')}</span>
                {selectedView.missingMetrics.length > 0
                  ? selectedView.missingMetrics.map((metric) => <strong key={metric}>{formatMetricName(metric)}</strong>)
                  : <small>{t('spot.evidence.noMissing')}</small>}
              </div>
              <div>
                <span>{t('spot.evidence.stale')}</span>
                {selectedView.staleMetrics.length > 0
                  ? selectedView.staleMetrics.map((metric) => <strong key={metric}>{formatMetricName(metric)}</strong>)
                  : <small>{t('spot.evidence.noStale')}</small>}
              </div>
              <div>
                <span>{t('spot.evidence.limits')}</span>
                {selectedView.limitations.length > 0
                  ? selectedView.limitations.map((limitation) => <strong key={limitation}>{limitation}</strong>)
                  : <small>{t('spot.evidence.noLimits')}</small>}
              </div>
            </div>
            {selectedView.contributions.length > 0 && (
              <div className="contribution-list">
                <span>{t('spot.evidence.contributions')}</span>
                {selectedView.contributions.slice(0, 6).map((contribution, index) => (
                  <div key={`${contribution.metric_name ?? 'metric'}-${index}`}>
                    <strong>{formatMetricName(contribution.metric_name ?? 'metric')}</strong>
                    <span>{contribution.weighted_points == null ? t('spot.evidence.reflected') : `${Number(contribution.weighted_points).toFixed(1)} pt`}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="detail-panel forecast-panel">
            <div className="detail-section-heading">
              <div><span>WATER FORECAST</span><h2>{t('spot.forecast.title')}</h2></div>
              <Link to="/forecast">{t('spot.forecast.all')} <ChevronRight size={16} /></Link>
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
            <div className="best-day-note"><Sparkles size={18} /><p>{t('spot.forecast.bestNote', { region: forecastRegion, day: bestForecast.day, time: bestForecast.best })}</p></div>
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
              <div className="livecam-poster"><img src={livecam.poster} alt={`${livecam.name} DEMO`} /><span><Radio size={15} /> {t('spot.livecam.demoPreview')}</span></div>
              <div><span>SEE IT YOURSELF</span><h2>{livecam.name}</h2><p>{t('spot.livecam.notLive')}</p><Link to="/livecam">{t('spot.livecam.cta')} <ArrowRight size={16} /></Link></div>
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
          <div className={`sidebar-index-card state-${selectedView.dataState}`}>
            <span>SUITABILITY · {t(`activity.${selectedActivity}`)}</span>
            <div className={`sidebar-score score-${selectedView.score === null ? 'unknown' : 'known'}`} style={{ '--score': selectedView.score ?? 0 }}><strong>{scoreLabel(selectedView)}</strong></div>
            <h2>{spot.summary}</h2>
            <p>{spot.description}</p>
            <div><Clock3 size={16} /><span>{isRecommendationEligible(selectedView) ? 'RECOMMENDABLE' : 'DECISION'}</span><strong>{selectedView.isDemoFallback ? t('home.hero.demo') : t(`concierge.decision.${selectedView.decision}`)}</strong></div>
          </div>
          <div className={`source-card state-${selectedView.dataState}`}>
            <span>DATA STATUS · {localizedDataState(t, selectedView.dataState, true)}</span>
            <h3>{localizedDataState(t, selectedView.dataState)}</h3>
            <p>{t('spot.sidebar.policy')}</p>
            <ul>
              <li>{selectedView.provenance.provider}</li>
              <li>{selectedView.provenance.spatialScope}</li>
              <li>{selectedView.provenance.updatedLabel}</li>
              <li>정규화 관측 스냅샷 {spot.observations?.length ?? 0}건 연결</li>
            </ul>
          </div>
        </aside>
      </div>

      <div className="detail-sticky-actions">
        <div><span>{spot.name} · {localizedDataState(t, selectedView.dataState)}</span><strong>{planned ? t('spot.plan.added') : selectedView.isDemoFallback ? `${spot.bestTime} · DEMO` : selectedSafety.label}</strong></div>
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
          {planned ? t('spot.plan.added') : t('spot.plan.add')}
        </button>
      </div>
    </div>
  );
}

export default SpotDetailPage;
