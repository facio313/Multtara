import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronUp,
  Clock3,
  Compass,
  Database,
  Droplets,
  Info,
  Layers3,
  Map as MapIcon,
  MapPin,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Waves,
} from 'lucide-react';
import {
  activityOptions,
  dataMeta,
  spots,
  spotTypeOptions,
} from '../data/pongdangData';
import './MapPage.css';

const KAKAO_SDK_ID = 'pongdang-kakao-map-sdk';
const KAKAO_MAP_KEY = import.meta.env.VITE_KAKAO_MAP_KEY?.trim() ?? '';

let kakaoSdkPromise;

function loadKakaoMapsSdk(appKey) {
  if (!appKey) {
    return Promise.reject(new Error('Kakao Maps JavaScript key is missing.'));
  }

  if (window.kakao?.maps) {
    return new Promise((resolve) => {
      window.kakao.maps.load(() => resolve(window.kakao));
    });
  }

  if (kakaoSdkPromise) return kakaoSdkPromise;

  kakaoSdkPromise = new Promise((resolve, reject) => {
    const finishLoading = () => {
      if (!window.kakao?.maps) {
        reject(new Error('Kakao Maps SDK did not initialize.'));
        return;
      }
      window.kakao.maps.load(() => resolve(window.kakao));
    };

    const failLoading = () => reject(new Error('Kakao Maps SDK could not be loaded.'));
    const existingScript = document.getElementById(KAKAO_SDK_ID);

    if (existingScript) {
      existingScript.addEventListener('load', finishLoading, { once: true });
      existingScript.addEventListener('error', failLoading, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.id = KAKAO_SDK_ID;
    script.async = true;
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(appKey)}&autoload=false`;
    script.addEventListener('load', finishLoading, { once: true });
    script.addEventListener('error', failLoading, { once: true });
    document.head.appendChild(script);
  });

  return kakaoSdkPromise;
}

function getActivityScore(spot, activity) {
  return spot.scores[activity] ?? spot.index;
}

function getScoreTone(score) {
  if (score >= 90) return 'excellent';
  if (score >= 84) return 'good';
  if (score >= 76) return 'fair';
  return 'check';
}

function getStatusIcon(level) {
  return level === 'safe' ? CheckCircle2 : AlertTriangle;
}

function MapStatusNotice({ status }) {
  const messages = {
    loading: {
      icon: Compass,
      title: '카카오 지도를 연결하고 있어요',
      description: '로딩 중에도 아래 개념도와 여행지 목록을 탐색할 수 있습니다.',
    },
    'missing-key': {
      icon: Info,
      title: '지금은 Water Twin 개념도로 보여드려요',
      description: 'VITE_KAKAO_MAP_KEY가 설정되면 같은 마커가 실제 카카오 지도 위에 표시됩니다.',
    },
    error: {
      icon: AlertTriangle,
      title: '실제 지도를 불러오지 못했어요',
      description: '네트워크 또는 허용 도메인을 확인해 주세요. 데모 지도와 목록은 계속 사용할 수 있습니다.',
    },
  };

  const message = messages[status];
  if (!message) return null;
  const Icon = message.icon;

  return (
    <div className={`pd-map-status pd-map-status-${status}`} role="status" aria-live="polite">
      <Icon size={17} aria-hidden="true" />
      <div>
        <strong>{message.title}</strong>
        <span>{message.description}</span>
      </div>
    </div>
  );
}

function WaterTwinFallback({ filteredSpots, activity, selectedId, onSelect, dimmed = false }) {
  return (
    <div
      className={`pd-map-fallback${dimmed ? ' is-dimmed' : ''}`}
      aria-label="실제 지도를 대신하는 여행지 위치 개념도"
    >
      <div className="pd-map-fallback-grid" aria-hidden="true" />
      <div className="pd-map-water-shape pd-map-water-east" aria-hidden="true" />
      <div className="pd-map-water-shape pd-map-water-west" aria-hidden="true" />
      <div className="pd-map-region-label pd-map-label-gangneung" aria-hidden="true">
        GANGNEUNG MVP
      </div>
      <div className="pd-map-region-label pd-map-label-korea" aria-hidden="true">
        KOREA EXPANSION
      </div>

      {filteredSpots.map((spot) => {
        const score = getActivityScore(spot, activity);
        const isSelected = selectedId === spot.id;
        return (
          <button
            className={`pd-map-marker pd-map-marker-${getScoreTone(score)} safety-${spot.safety.level}${isSelected ? ' is-selected' : ''}`}
            key={spot.id}
            type="button"
            style={{
              '--marker-x': `${spot.visual.mapPosition.x}%`,
              '--marker-y': `${spot.visual.mapPosition.y}%`,
            }}
            aria-pressed={isSelected}
            aria-label={`${spot.name}, ${score}점, ${spot.safety.label}`}
            onClick={() => onSelect(spot.id)}
          >
            <span className="pd-map-marker-score">{score}</span>
            <span className="pd-map-marker-name">{spot.name}</span>
          </button>
        );
      })}

      {filteredSpots.length === 0 && (
        <div className="pd-map-fallback-empty">
          <MapPin size={24} aria-hidden="true" />
          <span>조건에 맞는 마커가 없습니다.</span>
        </div>
      )}
    </div>
  );
}

function MapPage() {
  const [searchParams] = useSearchParams();
  const [scope, setScope] = useState(() => (searchParams.get('q')?.trim() ? 'nationwide' : 'gangneung'));
  const [activeType, setActiveType] = useState('all');
  const [activeActivity, setActiveActivity] = useState('swim');
  const [query, setQuery] = useState(() => searchParams.get('q')?.trim() ?? '');
  const [selectedSpotId, setSelectedSpotId] = useState(1);
  const [mapStatus, setMapStatus] = useState(KAKAO_MAP_KEY ? 'loading' : 'missing-key');
  const mapCanvasRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const overlaysRef = useRef([]);

  const activeActivityLabel =
    activityOptions.find((activity) => activity.id === activeActivity)?.label ?? '종합';

  const filteredSpots = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR');

    return spots
      .filter((spot) => scope === 'nationwide' || spot.isGangneungMvp)
      .filter((spot) => activeType === 'all' || spot.type === activeType)
      .filter((spot) => {
        if (!normalizedQuery) return true;
        const searchTarget = [spot.name, spot.region, spot.address, ...spot.tags]
          .join(' ')
          .toLocaleLowerCase('ko-KR');
        return searchTarget.includes(normalizedQuery);
      })
      .sort((a, b) => getActivityScore(b, activeActivity) - getActivityScore(a, activeActivity));
  }, [activeActivity, activeType, query, scope]);

  const selectedSpot =
    filteredSpots.find((spot) => spot.id === selectedSpotId) ?? filteredSpots[0] ?? null;

  useEffect(() => {
    if (!KAKAO_MAP_KEY) return undefined;

    let cancelled = false;
    loadKakaoMapsSdk(KAKAO_MAP_KEY)
      .then(() => {
        if (!cancelled) setMapStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setMapStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (mapStatus !== 'ready' || !mapCanvasRef.current || !window.kakao?.maps) {
      return undefined;
    }

    const { maps } = window.kakao;
    const initialCenter = new maps.LatLng(37.77, 128.9);

    if (!mapInstanceRef.current) {
      mapInstanceRef.current = new maps.Map(mapCanvasRef.current, {
        center: initialCenter,
        level: scope === 'gangneung' ? 8 : 13,
      });
      mapInstanceRef.current.addControl(
        new maps.ZoomControl(),
        maps.ControlPosition.RIGHT,
      );
    }

    const map = mapInstanceRef.current;
    overlaysRef.current.forEach(({ overlay, button, clickHandler }) => {
      button.removeEventListener('click', clickHandler);
      overlay.setMap(null);
    });
    overlaysRef.current = [];

    if (filteredSpots.length === 0) return undefined;

    const bounds = new maps.LatLngBounds();

    filteredSpots.forEach((spot) => {
      const position = new maps.LatLng(spot.lat, spot.lng);
      const score = getActivityScore(spot, activeActivity);
      const button = document.createElement('button');
      const scoreElement = document.createElement('strong');
      const nameElement = document.createElement('span');
      const clickHandler = () => setSelectedSpotId(spot.id);

      button.type = 'button';
      button.className = `pd-kakao-marker pd-kakao-marker-${getScoreTone(score)} safety-${spot.safety.level}`;
      button.setAttribute('aria-label', `${spot.name}, ${activeActivityLabel} ${score}점, ${spot.safety.label}`);
      scoreElement.textContent = String(score);
      nameElement.textContent = spot.name;
      button.append(scoreElement, nameElement);
      button.addEventListener('click', clickHandler);

      const overlay = new maps.CustomOverlay({
        position,
        content: button,
        xAnchor: 0.5,
        yAnchor: 1.1,
        zIndex: spot.isGangneungMvp ? 3 : 2,
      });
      overlay.setMap(map);
      overlaysRef.current.push({ overlay, button, clickHandler });
      bounds.extend(position);
    });

    if (filteredSpots.length === 1) {
      map.setCenter(new maps.LatLng(filteredSpots[0].lat, filteredSpots[0].lng));
      map.setLevel(6);
    } else {
      map.setBounds(bounds, 72, 72, 72, 72);
    }

    return () => {
      overlaysRef.current.forEach(({ overlay, button, clickHandler }) => {
        button.removeEventListener('click', clickHandler);
        overlay.setMap(null);
      });
      overlaysRef.current = [];
    };
  }, [activeActivity, activeActivityLabel, filteredSpots, mapStatus, scope]);

  const clearFilters = () => {
    setQuery('');
    setActiveType('all');
    setScope('gangneung');
  };

  return (
    <div className="pd-map-page">
      <header className="pd-map-hero">
        <div className="pd-map-hero-copy">
          <p className="pd-map-eyebrow">
            <Sparkles size={14} aria-hidden="true" />
            WATER TWIN · GANGNEUNG FIRST
          </p>
          <h1>지금 좋은 물을 한눈에.</h1>
          <p>
            수온·파고·혼잡도·안전 정보를 활동별 지수로 번역해, 오늘의 선택을 더 가볍게 만들어요.
          </p>
        </div>

        <div className="pd-map-data-note" role="note">
          <span className="pd-map-demo-badge">
            <Database size={14} aria-hidden="true" /> DEMO DATA
          </span>
          <div>
            <strong>{dataMeta.updatedLabel}</strong>
            <span>실시간 관측값이 아닌 제품 경험용 고정 데이터</span>
          </div>
        </div>
      </header>

      <section className="pd-map-controls" aria-label="지도 필터">
        <div className="pd-map-search">
          <Search size={18} aria-hidden="true" />
          <label className="sr-only" htmlFor="pd-map-search-input">
            여행지, 지역, 태그 검색
          </label>
          <input
            id="pd-map-search-input"
            type="search"
            value={query}
            placeholder="여행지, 지역, 태그 검색"
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <div className="pd-map-scope" aria-label="탐색 범위">
          <button
            type="button"
            className={scope === 'gangneung' ? 'is-active' : ''}
            aria-pressed={scope === 'gangneung'}
            onClick={() => setScope('gangneung')}
          >
            강릉 MVP
          </button>
          <button
            type="button"
            className={scope === 'nationwide' ? 'is-active' : ''}
            aria-pressed={scope === 'nationwide'}
            onClick={() => setScope('nationwide')}
          >
            전국 확장
          </button>
        </div>

        <label className="pd-map-activity-select" htmlFor="pd-map-activity">
          <SlidersHorizontal size={16} aria-hidden="true" />
          <span>활동</span>
          <select
            id="pd-map-activity"
            value={activeActivity}
            onChange={(event) => setActiveActivity(event.target.value)}
          >
            {activityOptions.map((activity) => (
              <option value={activity.id} key={activity.id}>
                {activity.icon} {activity.label}
              </option>
            ))}
          </select>
        </label>

        <div className="pd-map-type-filters" aria-label="물 여행지 유형">
          {spotTypeOptions.map((type) => (
            <button
              type="button"
              key={type.id}
              className={activeType === type.id ? 'is-active' : ''}
              aria-pressed={activeType === type.id}
              onClick={() => setActiveType(type.id)}
            >
              {type.label}
            </button>
          ))}
        </div>
      </section>

      <section className="pd-map-explorer" aria-label="Water Twin 지도와 여행지 목록">
        <div className="pd-map-panel">
          <div className="pd-map-panel-heading">
            <div>
              <span className="pd-map-panel-icon"><Layers3 size={17} aria-hidden="true" /></span>
              <div>
                <strong>{activeActivityLabel} 지수 레이어</strong>
                <span>{scope === 'gangneung' ? '강릉 우선 스팟' : '전국 확장 스팟'} {filteredSpots.length}곳</span>
              </div>
            </div>
            <span className={`pd-map-sdk-state state-${mapStatus}`}>
              <span aria-hidden="true" />
              {mapStatus === 'ready' ? 'KAKAO MAP' : 'CONCEPT MAP'}
            </span>
          </div>

          <div className="pd-map-canvas-wrap">
            <MapStatusNotice status={mapStatus} />

            {mapStatus === 'ready' ? (
              <div
                className="pd-map-kakao-canvas"
                ref={mapCanvasRef}
                aria-label="카카오 지도. 여행지 목록에서도 같은 정보를 탐색할 수 있습니다."
              />
            ) : (
              <WaterTwinFallback
                filteredSpots={filteredSpots}
                activity={activeActivity}
                selectedId={selectedSpot?.id}
                onSelect={setSelectedSpotId}
                dimmed={mapStatus === 'loading'}
              />
            )}

            {mapStatus === 'loading' && (
              <div className="pd-map-loading" aria-hidden="true">
                <span />
              </div>
            )}

            <div className="pd-map-legend" aria-label="지도 범례">
              <span><i className="legend-excellent" /> 90+ 최적</span>
              <span><i className="legend-good" /> 84+ 추천</span>
              <span><i className="legend-fair" /> 확인</span>
              <span><i className="legend-caution" /> 안전 주의</span>
            </div>
          </div>
        </div>

        <aside className="pd-map-sheet" aria-label="필터링된 여행지">
          <div className="pd-map-sheet-handle" aria-hidden="true"><ChevronUp size={18} /></div>
          <div className="pd-map-sheet-header">
            <div>
              <p>CURATED FOR {activeActivityLabel.toUpperCase()}</p>
              <h2>{filteredSpots.length}개의 물을 찾았어요</h2>
            </div>
            <span>{scope === 'gangneung' ? '강릉 우선' : '전국 보기'}</span>
          </div>

          {selectedSpot ? (
            <article className="pd-map-featured" style={{ '--spot-accent': selectedSpot.visual.accent }}>
              <div className="pd-map-featured-top">
                <div>
                  <span className="pd-map-spot-type">{selectedSpot.typeLabel}</span>
                  <span className={`pd-map-safety-chip safety-${selectedSpot.safety.level}`}>
                    {selectedSpot.safety.label}
                  </span>
                </div>
                <div className={`pd-map-big-score score-${getScoreTone(getActivityScore(selectedSpot, activeActivity))}`}>
                  <strong>{getActivityScore(selectedSpot, activeActivity)}</strong>
                  <span>{selectedSpot.scores[activeActivity] == null ? '종합' : activeActivityLabel}</span>
                </div>
              </div>

              <div className="pd-map-featured-title">
                <span className="pd-map-featured-icon" aria-hidden="true">{selectedSpot.visual.icon}</span>
                <div>
                  <h3>{selectedSpot.name}</h3>
                  <p><MapPin size={14} aria-hidden="true" /> {selectedSpot.region}</p>
                </div>
              </div>

              <p className="pd-map-featured-summary">{selectedSpot.summary}</p>

              <dl className="pd-map-condition-row">
                <div>
                  <dt><Droplets size={14} aria-hidden="true" /> 수온</dt>
                  <dd>{selectedSpot.conditions.waterTemp}</dd>
                </div>
                <div>
                  <dt><Waves size={14} aria-hidden="true" /> 파고</dt>
                  <dd>{selectedSpot.conditions.waveHeight}</dd>
                </div>
                <div>
                  <dt><Compass size={14} aria-hidden="true" /> 혼잡</dt>
                  <dd>{selectedSpot.conditions.crowd}</dd>
                </div>
              </dl>

              <div className={`pd-map-safety-message safety-${selectedSpot.safety.level}`}>
                {(() => {
                  const SafetyIcon = getStatusIcon(selectedSpot.safety.level);
                  return <SafetyIcon size={16} aria-hidden="true" />;
                })()}
                <span>{selectedSpot.safety.message}</span>
              </div>

              <div className="pd-map-featured-footer">
                <span><Clock3 size={14} aria-hidden="true" /> {selectedSpot.freshness.updatedLabel}</span>
                <Link to={`/spot/${selectedSpot.id}`}>
                  상세 보기 <ArrowRight size={16} aria-hidden="true" />
                </Link>
              </div>
            </article>
          ) : (
            <div className="pd-map-no-results" role="status">
              <MapIcon size={30} aria-hidden="true" />
              <h3>조건에 맞는 물이 아직 없어요.</h3>
              <p>검색어 또는 장소 유형을 바꾸면 데모 스팟을 다시 볼 수 있습니다.</p>
              <button type="button" onClick={clearFilters}>필터 초기화</button>
            </div>
          )}

          {filteredSpots.length > 0 && (
            <div className="pd-map-result-list" role="list" aria-label="여행지 결과 목록">
              {filteredSpots.map((spot, index) => {
                const score = getActivityScore(spot, activeActivity);
                const isSelected = selectedSpot?.id === spot.id;
                return (
                  <article
                    className={`pd-map-result-card${isSelected ? ' is-selected' : ''}`}
                    key={spot.id}
                    role="listitem"
                  >
                    <button
                      className="pd-map-result-select"
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => setSelectedSpotId(spot.id)}
                    >
                      <span className="pd-map-result-rank">{String(index + 1).padStart(2, '0')}</span>
                      <span className="pd-map-result-copy">
                        <strong>{spot.name}</strong>
                        <small>{spot.region} · {spot.typeLabel}</small>
                      </span>
                      <span className={`pd-map-result-score score-${getScoreTone(score)}`}>
                        <strong>{score}</strong>
                        <small>점</small>
                      </span>
                    </button>
                    <Link to={`/spot/${spot.id}`} aria-label={`${spot.name} 상세 보기`}>
                      <ArrowRight size={16} aria-hidden="true" />
                    </Link>
                  </article>
                );
              })}
            </div>
          )}

          <div className="pd-map-sheet-footnote">
            <ShieldCheck size={16} aria-hidden="true" />
            <span>{dataMeta.disclaimer}</span>
          </div>
        </aside>
      </section>
    </div>
  );
}

export default MapPage;
