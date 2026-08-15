import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  BadgeCheck,
  Camera,
  CircleOff,
  Clock3,
  ExternalLink,
  Info,
  MapPin,
  Maximize2,
  Radio,
  RotateCcw,
  Search,
  ShieldCheck,
  Waves,
  X,
} from 'lucide-react';
import { livecams, spots } from '../data/pongdangData';
import './LivecamPage.css';

const STATUS_FILTERS = [
  { id: 'all', label: '전체' },
  { id: 'official', label: '공식 라이브' },
  { id: 'poster', label: '정적·데모' },
];

const toArray = (value) => (Array.isArray(value) ? value : []);

const toScore = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(100, Math.max(0, Math.round(parsed))) : null;
};

const safeOfficialUrl = (value) => {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const parsed = new URL(value);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
};

const getIndexTone = (score) => {
  if (score === null) return 'unknown';
  if (score >= 90) return 'excellent';
  if (score >= 80) return 'good';
  if (score >= 65) return 'fair';
  return 'caution';
};

const getIndexLabel = (score) => {
  const tone = getIndexTone(score);
  return {
    excellent: '최적',
    good: '좋음',
    fair: '보통',
    caution: '주의',
    unknown: '미수집',
  }[tone];
};

const getStatusMeta = (cam) => {
  const status = String(cam.status || '').toLowerCase();
  if (cam.isLive) {
    return {
      tone: 'official',
      label: '공식 라이브 링크',
      description: '페이지에서는 소리 없는 포스터로 미리 보고, 공식 제공처에서 영상을 엽니다.',
    };
  }
  if (status.includes('offline') || status.includes('중단') || status.includes('오프라인')) {
    return {
      tone: 'offline',
      label: '현재 오프라인',
      description: '현재 영상 상태를 확인할 수 없어 마지막 정적 포스터를 보여드립니다.',
    };
  }
  return {
    tone: 'demo',
    label: '데모 포스터',
    description: '실시간 스트림이 아닌 문서 기반 고정 이미지입니다.',
  };
};

const formatCondition = (value, suffix = '') => {
  if (value === null || value === undefined || value === '') return null;
  return typeof value === 'number' ? `${value}${suffix}` : String(value);
};

const SPOT_BY_ID = new Map(toArray(spots).map((spot) => [String(spot.id), spot]));

const CAM_DATA = toArray(livecams).map((cam, index) => {
  const spot = SPOT_BY_ID.get(String(cam?.spotId)) || null;
  const waterIndex = toScore(cam?.waterIndex ?? spot?.index);
  return {
    ...cam,
    id: cam?.id ?? `livecam-${index}`,
    name: String(cam?.name || spot?.name || `물멍 카메라 ${index + 1}`),
    region: String(cam?.region || spot?.region || '지역 미정'),
    status: cam?.status || 'demo',
    isLive: Boolean(cam?.isLive),
    waterIndex,
    poster: typeof cam?.poster === 'string' ? cam.poster : '',
    tags: toArray(cam?.tags),
    updatedLabel: String(cam?.updatedLabel || spot?.freshness?.updatedLabel || '고정 데모'),
    officialUrl: safeOfficialUrl(cam?.officialUrl),
    spot,
    statusMeta: getStatusMeta(cam || {}),
  };
});

const REGION_OPTIONS = ['전체 지역', ...new Set(CAM_DATA.map((cam) => cam.region).filter(Boolean))];

function LivecamPage() {
  const [statusFilter, setStatusFilter] = useState('all');
  const [regionFilter, setRegionFilter] = useState('전체 지역');
  const [query, setQuery] = useState('');
  const [focusedId, setFocusedId] = useState(null);
  const [failedPosters, setFailedPosters] = useState([]);
  const focusPanelRef = useRef(null);
  const closeButtonRef = useRef(null);
  const lastTriggerRef = useRef(null);

  const filteredCams = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR');
    return CAM_DATA.filter((cam) => {
      const statusMatches = statusFilter === 'all'
        || (statusFilter === 'official' && cam.isLive)
        || (statusFilter === 'poster' && !cam.isLive);
      const regionMatches = regionFilter === '전체 지역' || cam.region === regionFilter;
      const searchableText = [cam.name, cam.region, cam.spot?.typeLabel, ...cam.tags]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase('ko-KR');
      const queryMatches = !normalizedQuery || searchableText.includes(normalizedQuery);
      return statusMatches && regionMatches && queryMatches;
    });
  }, [query, regionFilter, statusFilter]);

  const focusedCam = CAM_DATA.find((cam) => cam.id === focusedId) || null;
  const officialCount = CAM_DATA.filter((cam) => cam.isLive).length;

  const closeFocusMode = useCallback(() => {
    setFocusedId(null);
    window.requestAnimationFrame(() => lastTriggerRef.current?.focus());
  }, []);

  const openFocusMode = (camId, trigger) => {
    lastTriggerRef.current = trigger;
    setFocusedId(camId);
  };

  useEffect(() => {
    if (!focusedCam) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeFocusMode();
        return;
      }

      if (event.key !== 'Tab' || !focusPanelRef.current) return;
      const focusable = [...focusPanelRef.current.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [closeFocusMode, focusedCam]);

  const markPosterFailed = (camId) => {
    setFailedPosters((current) => current.includes(camId) ? current : [...current, camId]);
  };

  const resetFilters = () => {
    setStatusFilter('all');
    setRegionFilter('전체 지역');
    setQuery('');
  };

  return (
    <div className="livecam-page">
      <header className="livecam-hero" aria-labelledby="livecam-title">
        <div className="livecam-hero__copy">
          <span className="livecam-eyebrow">WATER WINDOW</span>
          <h1 id="livecam-title">
            떠나기 전,
            <span> 물의 표정을 먼저 보세요</span>
          </h1>
          <p>
            공개 제공처가 있는 장소는 공식 링크로 연결하고, 그렇지 않은 곳은
            정적 데모 포스터임을 분명히 표시합니다. 이 페이지에서 영상이나 소리는 자동 재생되지 않습니다.
          </p>
        </div>

        <dl className="livecam-hero__stats" aria-label="라이브캠 현황">
          <div>
            <dt>등록 뷰</dt>
            <dd>{CAM_DATA.length}</dd>
          </div>
          <div>
            <dt>공식 링크</dt>
            <dd>{officialCount}</dd>
          </div>
          <div>
            <dt>자동 재생</dt>
            <dd>OFF</dd>
          </div>
        </dl>
      </header>

      <section className="livecam-toolbar" aria-labelledby="livecam-filter-title">
        <div className="livecam-toolbar__heading">
          <div>
            <span className="livecam-eyebrow">LIVE &amp; POSTER VIEW</span>
            <h2 id="livecam-filter-title">보고 싶은 물을 골라보세요</h2>
          </div>
          <span className="livecam-result-count" aria-live="polite">
            {filteredCams.length}개의 뷰
          </span>
        </div>

        <div className="livecam-filter-row">
          <fieldset className="livecam-status-filter">
            <legend>제공 상태</legend>
            <div>
              {STATUS_FILTERS.map((filter) => (
                <button
                  type="button"
                  key={filter.id}
                  className={statusFilter === filter.id ? 'is-active' : ''}
                  aria-pressed={statusFilter === filter.id}
                  onClick={() => setStatusFilter(filter.id)}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </fieldset>

          <label className="livecam-region-filter">
            <span>지역</span>
            <select value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)}>
              {REGION_OPTIONS.map((region) => (
                <option key={region} value={region}>{region}</option>
              ))}
            </select>
          </label>

          <label className="livecam-search">
            <span className="sr-only">라이브캠 검색</span>
            <Search aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="장소, 지역, 태그 검색"
              autoComplete="off"
            />
          </label>
        </div>
      </section>

      <section className="livecam-results" aria-labelledby="livecam-results-title">
        <div className="livecam-results__heading">
          <div>
            <span className="livecam-eyebrow">CURATED WATER VIEWS</span>
            <h2 id="livecam-results-title">지금 열어볼 물 풍경</h2>
          </div>
          <p>
            <Info aria-hidden="true" />
            빨간 LIVE 배지를 흉내 내지 않습니다. 제공 상태와 갱신 기준을 카드마다 확인하세요.
          </p>
        </div>

        {filteredCams.length ? (
          <div className="livecam-grid">
            {filteredCams.map((cam) => {
              const posterFailed = failedPosters.includes(cam.id);
              const safety = cam.spot?.safety;
              const conditions = cam.spot?.conditions || {};
              const waterTemp = formatCondition(conditions.waterTemp, '°C');
              const waveHeight = formatCondition(conditions.waveHeight, 'm');
              const crowd = formatCondition(conditions.crowd);
              const indexTone = getIndexTone(cam.waterIndex);

              return (
                <article
                  className="livecam-card"
                  key={cam.id}
                  style={{ '--livecam-visual': cam.spot?.visual?.gradient || 'linear-gradient(145deg, #0b4f58, #69cbb7)' }}
                >
                  <div className="livecam-card__poster">
                    {cam.poster && !posterFailed ? (
                      <img
                        src={cam.poster}
                        alt={`${cam.name} 정적 미리보기`}
                        loading="lazy"
                        onError={() => markPosterFailed(cam.id)}
                      />
                    ) : (
                      <div className="livecam-poster-fallback" role="img" aria-label={`${cam.name} 포스터 준비 중`}>
                        <Waves aria-hidden="true" />
                        <span>포스터 준비 중</span>
                      </div>
                    )}

                    <div className="livecam-card__overlay">
                      <span className={`livecam-state-badge livecam-state-badge--${cam.statusMeta.tone}`}>
                        {cam.isLive ? <Radio aria-hidden="true" /> : <Camera aria-hidden="true" />}
                        {cam.statusMeta.label}
                      </span>
                      <span className={`livecam-index-badge livecam-index-badge--${indexTone}`}>
                        <small>INDEX</small>
                        <strong>{cam.waterIndex ?? '—'}</strong>
                      </span>
                    </div>

                    <button
                      type="button"
                      className="livecam-focus-button"
                      aria-label={`${cam.name} 집중 보기 열기`}
                      aria-haspopup="dialog"
                      aria-expanded={focusedId === cam.id}
                      onClick={(event) => openFocusMode(cam.id, event.currentTarget)}
                    >
                      <Maximize2 aria-hidden="true" />
                      <span>집중 보기</span>
                    </button>
                  </div>

                  <div className="livecam-card__body">
                    <div className="livecam-card__title-row">
                      <div>
                        <p><MapPin aria-hidden="true" /> {cam.region}</p>
                        <h3>{cam.name}</h3>
                      </div>
                      <span className={`livecam-index-label livecam-index-label--${indexTone}`}>
                        {getIndexLabel(cam.waterIndex)}
                      </span>
                    </div>

                    <p className="livecam-status-description">{cam.statusMeta.description}</p>

                    <dl className="livecam-condition-list">
                      <div>
                        <dt>수온</dt>
                        <dd>{waterTemp || '미수집'}</dd>
                      </div>
                      <div>
                        <dt>파고</dt>
                        <dd>{waveHeight || '미수집'}</dd>
                      </div>
                      <div>
                        <dt>혼잡</dt>
                        <dd>{crowd || '미수집'}</dd>
                      </div>
                    </dl>

                    <div className="livecam-safety-row">
                      <ShieldCheck aria-hidden="true" />
                      <span>{safety?.label || '안전 데이터 미수집'}</span>
                    </div>

                    {cam.tags.length > 0 && (
                      <ul className="livecam-tags" aria-label="장소 태그">
                        {cam.tags.slice(0, 4).map((tag) => <li key={tag}>#{tag}</li>)}
                      </ul>
                    )}

                    <div className="livecam-card__footer">
                      <span><Clock3 aria-hidden="true" /> {cam.updatedLabel}</span>
                      <div>
                        {cam.spot?.id && (
                          <Link to={`/spot/${cam.spot.id}`}>
                            상세 <ArrowUpRight aria-hidden="true" />
                          </Link>
                        )}
                        {cam.officialUrl ? (
                          <a href={cam.officialUrl} target="_blank" rel="noreferrer">
                            공식 링크 <ExternalLink aria-hidden="true" />
                          </a>
                        ) : (
                          <span className="livecam-link-unavailable">공식 링크 준비 중</span>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="livecam-empty" role="status">
            <CircleOff aria-hidden="true" />
            <h3>조건에 맞는 물 풍경이 없어요</h3>
            <p>검색어를 지우거나 제공 상태와 지역 필터를 초기화해 보세요.</p>
            <button type="button" onClick={resetFilters}>
              <RotateCcw aria-hidden="true" /> 필터 초기화
            </button>
          </div>
        )}
      </section>

      <aside className="livecam-integrity-note" aria-label="라이브캠 데이터 원칙">
        <BadgeCheck aria-hidden="true" />
        <div>
          <strong>있는 그대로 보여드리는 라이브캠</strong>
          <p>
            공식 스트림 여부, 포스터 상태, 갱신 기준을 분리해 표시합니다.
            연결되지 않은 영상을 재생 중인 것처럼 보이게 하거나 소리를 자동으로 틀지 않습니다.
          </p>
        </div>
      </aside>

      {focusedCam && (
        <div
          className="livecam-focus-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeFocusMode();
          }}
        >
          <section
            id="livecam-focus-dialog"
            ref={focusPanelRef}
            className="livecam-focus-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="livecam-focus-title"
            aria-describedby="livecam-focus-description"
          >
            <button
              type="button"
              ref={closeButtonRef}
              className="livecam-focus-close"
              onClick={closeFocusMode}
            >
              <X aria-hidden="true" />
              <span>닫기</span>
            </button>

            <div
              className="livecam-focus-media"
              style={{ '--livecam-visual': focusedCam.spot?.visual?.gradient || 'linear-gradient(145deg, #0b4f58, #69cbb7)' }}
            >
              {focusedCam.poster && !failedPosters.includes(focusedCam.id) ? (
                <img
                  src={focusedCam.poster}
                  alt={`${focusedCam.name} 집중 보기 정적 포스터`}
                  onError={() => markPosterFailed(focusedCam.id)}
                />
              ) : (
                <div className="livecam-poster-fallback" role="img" aria-label={`${focusedCam.name} 포스터 준비 중`}>
                  <Waves aria-hidden="true" />
                  <span>포스터 준비 중</span>
                </div>
              )}
              <div className="livecam-focus-media__status">
                <span className={`livecam-state-badge livecam-state-badge--${focusedCam.statusMeta.tone}`}>
                  {focusedCam.isLive ? <Radio aria-hidden="true" /> : <Camera aria-hidden="true" />}
                  {focusedCam.statusMeta.label}
                </span>
                <span>소리·영상 자동 재생 없음</span>
              </div>
            </div>

            <div className="livecam-focus-copy">
              <span className="livecam-eyebrow">FOCUS WATER VIEW</span>
              <h2 id="livecam-focus-title">{focusedCam.name}</h2>
              <p id="livecam-focus-description">{focusedCam.statusMeta.description}</p>

              <div className="livecam-focus-summary">
                <div>
                  <span>Water Index</span>
                  <strong>{focusedCam.waterIndex ?? '—'}</strong>
                  <small>{getIndexLabel(focusedCam.waterIndex)}</small>
                </div>
                <div>
                  <span>지역</span>
                  <strong>{focusedCam.region}</strong>
                  <small>{focusedCam.updatedLabel}</small>
                </div>
              </div>

              <div className="livecam-focus-actions">
                {focusedCam.spot?.id && (
                  <Link to={`/spot/${focusedCam.spot.id}`} onClick={closeFocusMode}>
                    장소 상세 보기 <ArrowUpRight aria-hidden="true" />
                  </Link>
                )}
                {focusedCam.officialUrl ? (
                  <a href={focusedCam.officialUrl} target="_blank" rel="noreferrer">
                    공식 제공처 열기 <ExternalLink aria-hidden="true" />
                  </a>
                ) : (
                  <span>공식 영상 링크가 아직 연결되지 않았습니다.</span>
                )}
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default LivecamPage;
