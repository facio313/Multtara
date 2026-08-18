import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Accessibility,
  AlertTriangle,
  ArrowRight,
  Banknote,
  CalendarClock,
  Car,
  Check,
  Clock3,
  Compass,
  Database,
  Footprints,
  LoaderCircle,
  MapPin,
  MessageCircleMore,
  PawPrint,
  Send,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Users,
  WandSparkles,
  Waves,
} from 'lucide-react';
import { personas, spotTypeOptions } from '../data/pongdangData';
import { useWaterSpots } from '../hooks/useWaterData';
import { useI18n } from '../i18n';
import {
  allowsItinerarySessionConfirmation,
  buildSavedItineraryUpdatePayload,
  classifyItineraryError,
  deleteSavedItinerary,
  hasBlockingItineraryRevalidation,
  ITINERARY_TRANSITIONS,
  listSavedItineraries,
  minuteToTime,
  normalizeItineraryStatus,
  requestItineraryPlan,
  requiresItineraryAdultSupervisionConfirmation,
  timeToMinute,
  updateSavedItinerary,
} from '../services/itineraryApi';
import {
  buildRecommendationPayload,
  getRecommendationError,
  isRecommendationRequestCanceled,
  requestRecommendations,
  requiresAdultSupervision,
} from '../services/recommendations';
import { apiSpotRouteId } from '../services/waterData';
import { spotTypeSupportsActivity } from '../services/spotTypes';
import useSessionStore from '../store/useSessionStore';
import './ConciergePage.css';

const MAX_EVIDENCE_AGE_MS = 15 * 60 * 1000;
const SKILL_LEVELS = ['unspecified', 'beginner', 'intermediate', 'advanced'];

const activityOptions = [
  { value: 'swim', icon: '🏊' },
  { value: 'surf', icon: '🏄' },
  { value: 'relax', icon: '🌊' },
  { value: 'mudflat', icon: '🦀' },
  { value: 'onsen', icon: '♨️' },
  { value: 'rafting', icon: '🛶' },
];

const promptSuggestions = [
  { key: 'concierge.suggestion.drive', preset: { activity: 'relax', quiet: 86, activityLevel: 20, ages: '30, 30' } },
  { key: 'concierge.suggestion.family', preset: { activity: 'swim', quiet: 64, activityLevel: 30, ages: '8, 38', participantSkillLevel: 'beginner' } },
  { key: 'concierge.suggestion.onsen', preset: { activity: 'onsen', quiet: 86, activityLevel: 12 } },
  { key: 'concierge.suggestion.surf', preset: { activity: 'surf', quiet: 84, activityLevel: 92 } },
];

const personaPresets = {
  active: { activity: 'surf', quiet: 25, activityLevel: 90, ages: '30' },
  family: { activity: 'swim', quiet: 62, activityLevel: 32, ages: '8, 38', participantSkillLevel: 'beginner' },
  wellness: { activity: 'onsen', quiet: 88, activityLevel: 12, ages: '35' },
  local: { activity: 'relax', quiet: 78, activityLevel: 28, ages: '30' },
  indoor: { activity: 'onsen', quiet: 72, activityLevel: 18, ages: '30' },
  stay: { activity: 'onsen', quiet: 72, activityLevel: 18, ages: '30' },
};

const defaultForm = {
  activity: 'relax',
  region: '강릉 · 강원',
  spotType: '',
  quiet: 72,
  activityLevel: 28,
  ages: '30',
  requiresAccessibility: false,
  bringingPet: false,
  adultSupervisionConfirmed: null,
  participantSkillLevel: 'unspecified',
};

const demoRecommendations = {
  family: [
    { id: 'demo-gyeongpo', name: '경포해변', region: '강원 강릉', type: '가족형 해변', reason: '얕은 물과 편의시설을 먼저 살펴보는 화면 구성 예시예요.' },
    { id: 'demo-yeongok', name: '연곡해변', region: '강원 강릉', type: '한적한 해변', reason: '한적함과 짧은 이동 부담을 반영하는 고정 예시예요.' },
    { id: 'demo-geumjin', name: '금진 온수 자원', region: '강원 강릉', type: '실내 대안', reason: '날씨가 나쁠 때 검증된 실내 대안을 찾는 경험 예시예요.' },
  ],
  wellness: [
    { id: 'demo-geumjin', name: '금진 온수 자원', region: '강원 강릉', type: '웰니스', reason: '조용함과 실내 체류를 우선하는 화면 구성 예시예요.' },
    { id: 'demo-anmok', name: '안목해변', region: '강원 강릉', type: '물멍', reason: '바다 산책과 주변 체류를 연결하는 고정 예시예요.' },
    { id: 'demo-gyeongpo-lake', name: '경포호', region: '강원 강릉', type: '호수 산책', reason: '낮은 활동 강도와 긴 체류를 반영하는 경험 예시예요.' },
  ],
  active: [
    { id: 'demo-sacheonjin', name: '사천진해변', region: '강원 강릉', type: '서핑', reason: '높은 활동 강도와 장비 접근성을 비교하는 화면 예시예요.' },
    { id: 'demo-jeongdongjin', name: '정동진해변', region: '강원 강릉', type: '해안 활동', reason: '활동 시간과 바람 근거가 연결될 때의 카드 예시예요.' },
    { id: 'demo-yeongok', name: '연곡해변', region: '강원 강릉', type: '해안 탐험', reason: '혼잡을 피한 활동형 장소 탐색의 고정 예시예요.' },
  ],
};

const spotTypeMessageKeys = {
  beach: 'map.type.beach',
  river: 'map.type.river',
  valley: 'map.type.valley',
  hotspring: 'map.type.hotspring',
  pool: 'map.type.pool',
  waterpark: 'map.type.waterpark',
  lake: 'map.type.lake',
  waterfall: 'map.type.waterfall',
  riverside: 'map.type.riverside',
  reservoir: 'map.type.reservoir',
  mudflat: 'map.type.mudflat',
  coastal_road: 'map.type.coastal_road',
};

function readPersonaId() {
  try {
    return window.localStorage.getItem('pongdang:persona-preference');
  } catch {
    return null;
  }
}

function buildInitialForm(personaId) {
  const preset = personaPresets[personaId] || {};
  return { ...defaultForm, ...preset };
}

function inferFormFromQuery(text, currentForm, { suggestion = false } = {}) {
  const next = { ...currentForm };

  if (/서핑|파도/.test(text)) {
    next.activity = 'surf';
    next.activityLevel = 92;
    next.quiet = /사람 적|한적/.test(text) ? 84 : 34;
  } else if (/온천|스파|따뜻|실내|비 오는|비가/.test(text)) {
    next.activity = 'onsen';
    next.activityLevel = 12;
    next.quiet = 86;
  } else if (/아이|가족|얕|물놀이|수영/.test(text)) {
    next.activity = 'swim';
    next.activityLevel = 30;
    next.quiet = 64;
  } else if (/물멍|산책|드라이브|조용|힐링/.test(text)) {
    next.activity = 'relax';
    next.activityLevel = 20;
    next.quiet = 86;
  } else if (/갯벌/.test(text)) {
    next.activity = 'mudflat';
    next.activityLevel = 55;
  } else if (/래프팅|급류/.test(text)) {
    next.activity = 'rafting';
    next.activityLevel = 95;
    next.quiet = 18;
  }

  if (/아이/.test(text) && (suggestion || currentForm.ages.trim() === '30')) {
    next.ages = '8, 38';
  } else if (/연인/.test(text) && suggestion) {
    next.ages = '30, 30';
  }

  if (
    next.activity !== currentForm.activity
    || next.ages !== currentForm.ages
    || next.participantSkillLevel !== currentForm.participantSkillLevel
  ) {
    next.adultSupervisionConfirmed = null;
  }

  return next;
}

function parseAges(value) {
  const tokens = String(value)
    .split(/[\s,/]+/)
    .map((token) => token.trim())
    .filter(Boolean);

  if (tokens.length === 0 || tokens.length > 12) {
    return { ages: null, errorKey: 'concierge.age.count' };
  }

  const ages = tokens.map(Number);
  if (ages.some((age) => !Number.isInteger(age) || age < 0 || age > 120)) {
    return { ages: null, errorKey: 'concierge.age.range' };
  }

  return { ages, errorKey: null };
}

function toFiniteNumber(value) {
  if (
    value === null
    || value === undefined
    || typeof value === 'boolean'
    || (typeof value === 'string' && value.trim() === '')
  ) {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function evidenceFreshness(evaluatedAt, generatedAt, t) {
  const evaluatedTime = Date.parse(evaluatedAt);
  const generatedTime = Date.parse(generatedAt);
  if (!Number.isFinite(evaluatedTime) || !Number.isFinite(generatedTime)) {
    return { isCurrent: false, label: t('concierge.freshness.unknown') };
  }

  const age = generatedTime - evaluatedTime;
  if (age < -2 * 60 * 1000 || age > MAX_EVIDENCE_AGE_MS) {
    return { isCurrent: false, label: age > 0 ? t('concierge.freshness.stale') : t('concierge.freshness.conflict') };
  }

  const minutes = Math.max(0, Math.floor(age / 60000));
  return { isCurrent: true, label: minutes < 1 ? t('concierge.freshness.now') : t('concierge.freshness.minutes', { minutes }) };
}

function normalizeExcludedSummary(summary) {
  if (!summary || typeof summary !== 'object' || Array.isArray(summary)) return {};
  return Object.fromEntries(
    Object.entries(summary)
      .map(([code, value]) => [String(code), Math.max(0, Math.floor(Number(value)))])
      .filter(([, value]) => Number.isFinite(value) && value > 0),
  );
}

function normalizeLiveResponse(payload, t) {
  const recommendations = Array.isArray(payload?.recommendations) ? payload.recommendations : [];
  const accepted = [];
  const clientExcluded = {};
  const backendExcluded = normalizeExcludedSummary(payload?.excluded_summary);
  const exclude = (code) => {
    clientExcluded[code] = (clientExcluded[code] || 0) + 1;
  };

  recommendations.forEach((item) => {
    const waterIndex = item?.water_index || {};
    const safetyStatus = String(waterIndex.safety_status || 'unknown').toLowerCase();
    const spotId = item?.spot?.id;
    const spotRouteId = apiSpotRouteId(spotId);
    const spotName = typeof item?.spot?.name === 'string' ? item.spot.name.trim() : '';
    const fitScore = toFiniteNumber(item?.score);
    const suitabilityScore = toFiniteNumber(waterIndex.suitability_score);
    const waterConfidence = toFiniteNumber(waterIndex.confidence);
    const evidenceConfidence = toFiniteNumber(item?.evidence_confidence);
    const decision = String(waterIndex.decision || 'unknown').toLowerCase();
    const methodologyVersion = String(waterIndex.methodology_version || '').trim();
    const sources = Array.isArray(waterIndex.sources)
      ? [...new Set(waterIndex.sources.filter((source) => typeof source === 'string' && source.trim()).map((source) => source.trim()))]
      : [];
    const freshness = evidenceFreshness(waterIndex.evaluated_at, payload?.generated_at, t);

    if (safetyStatus !== 'clear') {
      exclude('CLIENT_SAFETY_REJECTED');
      return;
    }
    if (!freshness.isCurrent) {
      exclude('CLIENT_FRESHNESS_REJECTED');
      return;
    }
    if (sources.length === 0) {
      exclude('CLIENT_PROVENANCE_REJECTED');
      return;
    }
    if (
      spotRouteId === null
      || !spotName
      || fitScore === null
      || fitScore < 0
      || fitScore > 100
      || suitabilityScore === null
      || suitabilityScore < 0
      || suitabilityScore > 100
      || waterConfidence === null
      || waterConfidence < 0
      || waterConfidence > 1
      || evidenceConfidence === null
      || evidenceConfidence < 0
      || evidenceConfidence > 1
      || !['recommended', 'consider', 'not_recommended'].includes(decision)
      || !methodologyVersion.startsWith('water-index-v')
    ) {
      exclude('CLIENT_PAYLOAD_REJECTED');
      return;
    }

    const contributions = Array.isArray(item?.contributions) ? item.contributions : [];
    accepted.push({
      id: spotRouteId,
      apiId: Number(spotId),
      rank: Number.isInteger(item?.rank) ? item.rank : accepted.length + 1,
      name: spotName,
      type: spotTypeMessageKeys[item?.spot?.type]
        ? t(spotTypeMessageKeys[item.spot.type])
        : String(item?.spot?.type || t('concierge.card.destination')),
      region: String(item?.spot?.region || item?.spot?.address || t('concierge.card.regionUnknown')),
      address: String(item?.spot?.address || ''),
      fitScore,
      safetyStatus,
      suitabilityScore,
      decision,
      confidence: waterConfidence,
      methodologyVersion,
      freshness: freshness.label,
      evaluatedAt: waterIndex.evaluated_at,
      sources,
      reasonCodes: Array.isArray(item?.reason_codes) ? item.reason_codes.map(String) : [],
      contributions: contributions
        .filter((contribution) => contribution && typeof contribution.feature === 'string')
        .map((contribution) => ({
          feature: contribution.feature,
          candidateValue: toFiniteNumber(contribution.candidate_value),
          similarity: toFiniteNumber(contribution.similarity),
          weightedPoints: toFiniteNumber(contribution.weighted_points),
        })),
      evidenceConfidence,
    });
  });

  return {
    recommendations: accepted,
    excluded: {
      ...backendExcluded,
      ...Object.fromEntries(
        Object.entries(clientExcluded).map(([code, count]) => [
          code,
          count + (backendExcluded[code] || 0),
        ]),
      ),
    },
    meta: {
      generatedAt: payload?.generated_at || null,
      candidateCount: toFiniteNumber(payload?.candidate_count) ?? 0,
      evaluatedCount: toFiniteNumber(payload?.candidate_pool_evaluated) ?? 0,
      truncated: Boolean(payload?.candidate_pool_truncated),
      method: String(payload?.method || t('concierge.method.unknown')),
    },
  };
}

function getDemoIntent(form) {
  if (form.activity === 'swim' && /(^|[\s,])(?:[0-9]|1[0-2])(?:$|[\s,])/.test(form.ages)) return 'family';
  if (form.activity === 'onsen' || form.activity === 'relax' || form.quiet >= 70) return 'wellness';
  return 'active';
}

function contributionReason(item, t) {
  const strongest = [...item.contributions]
    .filter((contribution) => contribution.weightedPoints !== null)
    .sort((left, right) => right.weightedPoints - left.weightedPoints)
    .slice(0, 2)
    .map((contribution) => {
      const label = t(`concierge.feature.${contribution.feature}`);
      const match = Math.round((contribution.similarity ?? 0) * 100);
      return t('concierge.feature.match', { label, match });
    });

  return strongest.length > 0
    ? strongest.join(' · ')
    : t('concierge.feature.default');
}

function formatGeneratedAt(value, locale, fallback) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function ResultStatus({ requestState, intlLocale, t }) {
  if (requestState.kind === 'loading') {
    return (
      <div className="concierge-state-card is-loading" role="status">
        <LoaderCircle size={21} aria-hidden="true" />
        <div>
          <strong>{t('concierge.loading.title')}</strong>
          <span>{t('concierge.loading.description')}</span>
        </div>
      </div>
    );
  }

  if (requestState.kind === 'demo' && requestState.error) {
    return (
      <div className="concierge-state-card is-error" role="alert">
        <AlertTriangle size={21} aria-hidden="true" />
        <div>
          <strong>{t('concierge.error.title')}</strong>
          <span>{t('concierge.error.description', { error: t(requestState.error.messageKey) })}</span>
        </div>
      </div>
    );
  }

  if (requestState.kind === 'demo') {
    return (
      <div className="concierge-state-card is-empty" role="status">
        <ShieldAlert size={21} aria-hidden="true" />
        <div>
          <strong>{t('concierge.noEligible.title')}</strong>
          <span>{t('concierge.noEligible.description')}</span>
        </div>
      </div>
    );
  }

  if (requestState.kind === 'live') {
    return (
      <div className="concierge-state-card is-live" role="status">
        <ShieldCheck size={21} aria-hidden="true" />
        <div>
          <strong>{t('concierge.live.title')}</strong>
          <span>{t('concierge.live.description', { time: formatGeneratedAt(requestState.meta.generatedAt, intlLocale, t('concierge.freshness.unknown')) })}</span>
        </div>
      </div>
    );
  }

  return null;
}

function ExclusionSummary({ excluded, meta, t }) {
  const entries = Object.entries(excluded || {}).filter(([, count]) => count > 0);
  if (entries.length === 0 && !meta) return null;

  return (
    <aside className="exclusion-summary" aria-labelledby="exclusion-title">
      <div className="exclusion-heading">
        <div>
          <span>{t('concierge.eyebrow.report')}</span>
          <h3 id="exclusion-title">{t('concierge.excluded.title')}</h3>
        </div>
        {meta ? <small>{t('concierge.excluded.count', { candidates: Math.round(meta.candidateCount), evaluated: Math.round(meta.evaluatedCount) })}</small> : null}
      </div>
      {entries.length > 0 ? (
        <ul>
          {entries.map(([code, count]) => (
            <li key={code}>
              <span>{t(`concierge.exclusion.${code}`) === `concierge.exclusion.${code}` ? code : t(`concierge.exclusion.${code}`)}</span>
              <strong>{count}</strong>
            </li>
          ))}
        </ul>
      ) : (
        <p>{t('concierge.excluded.none')}</p>
      )}
      {meta?.truncated ? <p className="exclusion-note">{t('concierge.excluded.truncated')}</p> : null}
    </aside>
  );
}

function LiveRecommendationCard({ item, index, t }) {
  const displayedRank = Number.isFinite(item.rank) ? item.rank : index + 1;
  const decision = t(`concierge.decision.${item.decision}`);

  return (
    <article className={`recommendation-card rank-${Math.min(index + 1, 3)} is-live`}>
      <div className="recommendation-rank">
        <span>{String(displayedRank).padStart(2, '0')}</span>
        <span>{t('dataState.live.short')} · {item.type}</span>
      </div>

      <div className="recommendation-score" aria-label={`${t('concierge.card.fit')} ${Math.round(item.fitScore)}`}>
        <strong>{Math.round(item.fitScore)}</strong>
        <small>{t('concierge.card.fit')}</small>
      </div>

      <h3>{item.name}</h3>
      <p className="recommendation-region"><MapPin size={14} aria-hidden="true" /> {item.region}</p>
      <p className="recommendation-reason">{contributionReason(item, t)}</p>

      <div className="water-index-panel">
        <div className="water-index-heading">
          <ShieldCheck size={17} aria-hidden="true" />
          <div>
            <span>Water Index {Math.round(item.suitabilityScore)}</span>
            <strong>{t('safety.clear.label')} · {decision}</strong>
          </div>
        </div>
        <dl>
          <div>
            <dt>{t('concierge.card.source')}</dt>
            <dd>{item.sources.slice(0, 3).join(' · ')}</dd>
          </div>
          <div>
            <dt>{t('concierge.card.freshness')}</dt>
            <dd>{item.freshness}</dd>
          </div>
          <div>
            <dt>{t('concierge.card.wiConfidence')}</dt>
            <dd>{Math.round(item.confidence * 100)}%</dd>
          </div>
          <div>
            <dt>{t('concierge.card.evidence')}</dt>
            <dd>{Math.round(item.evidenceConfidence * 100)}%</dd>
          </div>
        </dl>
        <small>{item.methodologyVersion} · {t('concierge.card.scoreDisclaimer')}</small>
      </div>

      <Link to={`/spot/${encodeURIComponent(item.id)}`}>
        {t('concierge.card.details')} <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </article>
  );
}

function DemoRecommendationCard({ item, index, locale, t }) {
  return (
    <article className="recommendation-card is-demo">
      <div className="recommendation-rank">
        <span>{String(index + 1).padStart(2, '0')}</span>
        <span>{t('dataState.demo.short')} · {locale === 'ko' ? item.type : t('concierge.demo.type')}</span>
      </div>

      <div className="recommendation-score is-unavailable" aria-label={t('concierge.card.noLiveScore')}>
        <strong>--</strong>
        <small>{t('concierge.card.noLiveScore')}</small>
      </div>

      <h3>{item.name}</h3>
      <p className="recommendation-region"><MapPin size={14} aria-hidden="true" /> {item.region}</p>
      <p className="recommendation-reason">{locale === 'ko' ? item.reason : t('concierge.demo.reason')}</p>

      <div className="water-index-panel is-unknown">
        <div className="water-index-heading">
          <ShieldAlert size={17} aria-hidden="true" />
          <div>
            <span>{t('concierge.card.demoUnlinked')}</span>
            <strong>{t('concierge.card.unknown')}</strong>
          </div>
        </div>
        <p>{t('concierge.card.demoDescription')}</p>
      </div>

      <button type="button" className="demo-detail-button" disabled>
        {t('concierge.card.demoDisabled')}
      </button>
    </article>
  );
}

function itineraryDateValue(offsetDays = 0) {
  const now = new Date();
  now.setDate(now.getDate() + offsetDays);
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function refreshItinerarySession(error) {
  if ([401, 403].includes(error?.response?.status)) {
    void useSessionStore.getState().ensureSession({ force: true });
  }
}

function formatPlanDate(value, locale, fallback) {
  const date = new Date(`${value}T12:00:00`);
  if (!Number.isFinite(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

function formatKrw(value, locale) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return '—';
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'KRW',
    maximumFractionDigits: 0,
  }).format(amount);
}

function SavedItineraryCard({ item, intlLocale, onDeleted, onUpdated, t }) {
  const currentStatus = normalizeItineraryStatus(item.status);
  const revalidationRequired = item.evidenceStatus?.revalidationRequired === true;
  const sessionConfirmationAllowed = allowsItinerarySessionConfirmation(item);
  const blockingRevalidation = hasBlockingItineraryRevalidation(item);
  const adultSupervisionRequired = requiresItineraryAdultSupervisionConfirmation(item);
  const [title, setTitle] = useState(item.title || '');
  const [status, setStatus] = useState(currentStatus);
  const [adultSupervisionConfirmed, setAdultSupervisionConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const transitions = (ITINERARY_TRANSITIONS[currentStatus] || [currentStatus]).filter((next) => (
    !blockingRevalidation
    || !['accepted', 'started'].includes(next)
    || next === currentStatus
  ));
  const enteringExecutionState = status !== currentStatus
    && ['accepted', 'started'].includes(status);
  const adultConfirmationMissing = enteringExecutionState
    && adultSupervisionRequired
    && !adultSupervisionConfirmed;

  const submitUpdate = async (event) => {
    event.preventDefault();
    if (blockingRevalidation
      && status !== currentStatus
      && ['accepted', 'started'].includes(status)) {
      setFeedback({ type: 'error', messageKey: 'itinerary.error.revalidation' });
      return;
    }
    if (adultConfirmationMissing) {
      setFeedback({ type: 'error', messageKey: 'itinerary.error.adultSupervision' });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const payload = buildSavedItineraryUpdatePayload(item, {
        title,
        status,
        adultSupervisionConfirmed,
      });
      const updated = await updateSavedItinerary(item.id, payload);
      onUpdated(updated);
      setAdultSupervisionConfirmed(false);
      setFeedback({ type: 'success', messageKey: 'itinerary.saved.updated' });
    } catch (error) {
      refreshItinerarySession(error);
      setFeedback({ type: 'error', ...classifyItineraryError(error) });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setFeedback(null);
    try {
      await deleteSavedItinerary(item.id);
      onDeleted(item.id);
    } catch (error) {
      refreshItinerarySession(error);
      setFeedback({ type: 'error', ...classifyItineraryError(error) });
      setConfirmingDelete(false);
      setBusy(false);
    }
  };

  return (
    <li className="saved-itinerary-card">
      <div className="saved-itinerary-meta">
        <span className={`saved-itinerary-status is-${currentStatus}`}>{t(`itinerary.status.${currentStatus}`)}</span>
        <span>{t('itinerary.saved.date', {
          date: formatPlanDate(item.plan_date, intlLocale, t('common.noData')),
          start: minuteToTime(item.start_minute),
          end: minuteToTime(item.end_minute),
        })}</span>
      </div>
      <strong>{item.title || t('itinerary.status.draft')}</strong>
      <p>{item.start_spot_name || t('account.spot.unknown')} → {item.end_spot_name || t('account.spot.unknown')}</p>
      <p className="saved-itinerary-participant">
        {t(`activity.${item.activity}`)} · {t(`forecast.profile.${item.participantProfile}`)} · {t(`concierge.skill.${item.participantSkillLevel}`)}
      </p>
      <div className={`saved-itinerary-evidence-state is-${revalidationRequired ? 'required' : 'current'}`}>
        {revalidationRequired ? <ShieldAlert size={15} aria-hidden="true" /> : <ShieldCheck size={15} aria-hidden="true" />}
        <strong>{t(sessionConfirmationAllowed
          ? 'itinerary.evidence.supervisionRequired'
          : (revalidationRequired ? 'itinerary.evidence.revalidationRequired' : 'itinerary.evidence.current'))}</strong>
      </div>
      {blockingRevalidation ? (
        <div id={`saved-evidence-warning-${item.id}`} className="saved-itinerary-evidence-warning" role="alert">
          <p>{t('itinerary.evidence.replan')}</p>
          <ul>
            {item.evidenceStatus.reasonCodes.map((code) => {
              const key = `itinerary.evidence.reason.${code}`;
              const label = t(key);
              return <li key={code}>{label === key ? t('itinerary.evidence.reason.unknown') : label}</li>;
            })}
          </ul>
          <a href="#composer-title">{t('itinerary.evidence.replanCta')}</a>
        </div>
      ) : sessionConfirmationAllowed ? (
        <div id={`saved-evidence-warning-${item.id}`} className="saved-itinerary-evidence-warning is-supervision" role="status">
          <p>{t('itinerary.evidence.supervisionDescription')}</p>
          <small>{t('itinerary.evidence.supervisionNotStored')}</small>
        </div>
      ) : (
        <p className="saved-itinerary-execution-notice"><ShieldAlert size={14} aria-hidden="true" /> {t('itinerary.evidence.executionNotice')}</p>
      )}

      <details className="saved-itinerary-evidence-details">
        <summary><Database size={15} aria-hidden="true" /> {t('itinerary.evidence.details')}</summary>
        <dl>
          <div><dt>{t('itinerary.evidence.checked')}</dt><dd>{formatGeneratedAt(item.evidenceStatus.checkedAt, intlLocale, t('common.noData'))}</dd></div>
          <div><dt>{t('itinerary.evidence.routeUntil')}</dt><dd>{formatGeneratedAt(item.routeRevalidationRequiredAt, intlLocale, t('common.noData'))}</dd></div>
          <div><dt>{t('itinerary.evidence.waterUntil')}</dt><dd>{formatGeneratedAt(item.safetyRevalidationRequiredAt, intlLocale, t('common.noData'))}</dd></div>
          <div><dt>{t('itinerary.evidence.routeState')}</dt><dd>{t(`itinerary.evidence.route.${item.routeEvidence.dataState}`)}</dd></div>
          <div><dt>{t('itinerary.evidence.routeProviders')}</dt><dd>{item.routeEvidence.providers.join(' · ') || t('common.noData')}</dd></div>
          <div><dt>{t('itinerary.evidence.snapshots')}</dt><dd>{item.routeEvidence.snapshotIds.length}</dd></div>
        </dl>
        {item.routeEvidence.sourceUrls.length > 0 ? (
          <div className="saved-itinerary-source-links">
            {item.routeEvidence.sourceUrls.map((url, index) => <a href={url} key={url} target="_blank" rel="noreferrer">{t('itinerary.evidence.routeSource', { count: index + 1 })}</a>)}
          </div>
        ) : null}
        <div className="saved-itinerary-water-evidence">
          <strong>{t('itinerary.evidence.waterRows', { count: item.waterEvidence.length })}</strong>
          {item.waterEvidence.length > 0 ? (
            <ul>
              {item.waterEvidence.map((evidence) => (
                <li key={`${evidence.spotId}-${evidence.conditionScoreId ?? 'unknown'}`}>
                  <span>{t('itinerary.evidence.spotId', { id: evidence.spotId })}</span>
                  <strong>{t(`forecast.safety.${evidence.safetyStatus}`)} · {t(`forecast.decision.${evidence.decision}`)}</strong>
                  <small>{evidence.suitabilityScore ?? t('common.scoreMissing')} · {evidence.sources.join(' · ') || t('common.noData')}</small>
                  <small>{t('itinerary.evidence.skillProvenance', {
                    requested: evidence.participantSkillLevel
                      ? t(`concierge.skill.${evidence.participantSkillLevel}`)
                      : t('common.noData'),
                    condition: evidence.conditionScoreParticipantSkillLevel
                      ? t(`concierge.skill.${evidence.conditionScoreParticipantSkillLevel}`)
                      : t('common.noData'),
                  })}</small>
                  {evidence.sessionContextReconfirmationRequired ? <em>{t('itinerary.evidence.sessionReconfirm')}</em> : null}
                </li>
              ))}
            </ul>
          ) : <p>{t('itinerary.evidence.waterMissing')}</p>}
        </div>
      </details>

      <form className="saved-itinerary-form" onSubmit={submitUpdate}>
        <label htmlFor={`saved-title-${item.id}`}>
          <span>{t('itinerary.field.title')}</span>
          <input
            id={`saved-title-${item.id}`}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength="120"
            disabled={busy}
          />
        </label>
        <label htmlFor={`saved-status-${item.id}`}>
          <span>{t('itinerary.saved.status')}</span>
          <select
            id={`saved-status-${item.id}`}
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            disabled={busy}
            aria-describedby={revalidationRequired ? `saved-evidence-warning-${item.id}` : undefined}
          >
            {transitions.map((nextStatus) => (
              <option key={nextStatus} value={nextStatus}>{t(`itinerary.status.${nextStatus}`)}</option>
            ))}
          </select>
        </label>
        {adultSupervisionRequired ? (
          <label className="saved-itinerary-supervision-check" htmlFor={`saved-supervision-${item.id}`}>
            <input
              id={`saved-supervision-${item.id}`}
              type="checkbox"
              checked={adultSupervisionConfirmed}
              onChange={(event) => setAdultSupervisionConfirmed(event.target.checked)}
              disabled={busy || blockingRevalidation}
              aria-describedby={`saved-supervision-help-${item.id}`}
            />
            <span>{t('itinerary.evidence.supervisionConfirm')}</span>
            <small id={`saved-supervision-help-${item.id}`}>{t('itinerary.evidence.supervisionConfirmHelp')}</small>
          </label>
        ) : null}
        {adultConfirmationMissing ? (
          <p className="itinerary-feedback is-error" role="status">{t('itinerary.error.adultSupervision')}</p>
        ) : null}
        {feedback ? (
          <p className={`itinerary-feedback is-${feedback.type}`} role={feedback.type === 'error' ? 'alert' : 'status'}>
            {t(feedback.messageKey)}
          </p>
        ) : null}
        <div className="saved-itinerary-actions">
          <button type="submit" disabled={busy || adultConfirmationMissing}>{t('itinerary.saved.update')}</button>
          {!confirmingDelete ? (
            <button type="button" className="is-delete" onClick={() => setConfirmingDelete(true)} disabled={busy}>
              <Trash2 size={14} aria-hidden="true" /> {t('itinerary.saved.delete')}
            </button>
          ) : (
            <>
              <button type="button" className="is-delete" onClick={remove} disabled={busy}>
                {t('itinerary.saved.confirmDelete')}
              </button>
              <button type="button" onClick={() => setConfirmingDelete(false)} disabled={busy}>
                {t('itinerary.saved.cancelDelete')}
              </button>
            </>
          )}
        </div>
      </form>
    </li>
  );
}

function ItineraryWorkspace({ requestState, intlLocale, t }) {
  const session = useSessionStore();
  const hasLiveRequest = requestState?.kind === 'live'
    && Array.isArray(requestState.recommendations)
    && requestState.requestPayload;
  const itineraryRequestKey = hasLiveRequest
    ? `${requestState.meta?.generatedAt || ''}|${requestState.requestPayload.activity}|${requestState.recommendations.map((item) => item.apiId).join(',')}`
    : 'none';
  const { spots, spotStatus } = useWaterSpots(null, { loadConditions: false });
  const apiSpots = useMemo(() => spots.filter((spot) => (
    Number.isInteger(Number(spot.apiId))
    && Number(spot.apiId) > 0
    && spot.catalogVerification !== 'unknown'
  )), [spots]);
  const [form, setForm] = useState({
    startSpot: '',
    endSpot: '',
    planDate: itineraryDateValue(),
    startTime: '08:00',
    endTime: '18:00',
    transport: 'drive',
    budget: '100000',
    badWeather: false,
    save: false,
    title: '',
  });
  const [planState, setPlanState] = useState({ kind: 'idle', data: null, error: null });
  const [savedState, setSavedState] = useState({ kind: 'idle', items: [], error: null });

  useEffect(() => {
    void session.ensureSession();
  }, [session]);

  const loadSaved = useCallback(async () => {
    setSavedState((current) => ({ ...current, kind: 'loading', error: null }));
    try {
      const items = await listSavedItineraries();
      setSavedState({ kind: 'ready', items, error: null });
    } catch (error) {
      refreshItinerarySession(error);
      setSavedState((current) => ({
        ...current,
        kind: 'error',
        error: classifyItineraryError(error),
      }));
    }
  }, []);

  useEffect(() => {
    if (session.status === 'authenticated') void loadSaved();
  }, [loadSaved, session.status]);

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    setPlanState({ kind: 'idle', data: null, error: null, requestKey: itineraryRequestKey });
  };

  const submitPlan = async (event) => {
    event.preventDefault();
    if (!hasLiveRequest) return;
    const startSpot = Number(form.startSpot);
    const endSpot = Number(form.endSpot);
    const startMinute = timeToMinute(form.startTime);
    const endMinute = timeToMinute(form.endTime);
    if (!startSpot || !endSpot || startSpot === endSpot) {
      setPlanState({ kind: 'error', data: null, error: { messageKey: 'itinerary.error.selectStops' }, requestKey: itineraryRequestKey });
      return;
    }
    if (startMinute === null || endMinute === null || startMinute >= endMinute) {
      setPlanState({ kind: 'error', data: null, error: { messageKey: 'itinerary.error.time' }, requestKey: itineraryRequestKey });
      return;
    }

    const candidateIds = [...new Set(
      requestState.recommendations
        .map((item) => Number(item.apiId))
        .filter((id) => Number.isInteger(id) && id > 0),
    )];
    setPlanState({ kind: 'loading', data: null, error: null, requestKey: itineraryRequestKey });
    try {
      const save = session.status === 'authenticated' && form.save;
      const payload = {
        recommendation: requestState.requestPayload,
        candidate_ids: candidateIds,
        start_spot: startSpot,
        end_spot: endSpot,
        transport: form.transport,
        plan_date: form.planDate,
        start_minute: startMinute,
        end_minute: endMinute,
        budget_krw: Math.max(0, Math.floor(Number(form.budget) || 0)),
        bad_weather: form.badWeather,
        save,
        title: save ? form.title.trim() : '',
      };
      const data = await requestItineraryPlan(payload);
      setPlanState({ kind: 'ready', data, error: null, requestKey: itineraryRequestKey });
      if (data?.saved_itinerary_id) await loadSaved();
    } catch (error) {
      refreshItinerarySession(error);
      setPlanState({ kind: 'error', data: null, error: classifyItineraryError(error), requestKey: itineraryRequestKey });
    }
  };

  const activePlanState = planState.requestKey === itineraryRequestKey
    ? planState
    : { kind: 'idle', data: null, error: null };
  const plan = activePlanState.data?.plan;
  const visits = Array.isArray(plan?.visits) ? plan.visits : [];
  const routeSnapshotCount = Array.isArray(activePlanState.data?.route_evidence?.snapshot_ids)
    ? activePlanState.data.route_evidence.snapshot_ids.length
    : 0;

  if (!hasLiveRequest && session.status !== 'authenticated') return null;

  return (
    <div className="itinerary-workspace">
      {hasLiveRequest ? <section className="itinerary-builder" aria-labelledby="itinerary-builder-title">
        <div className="itinerary-builder-heading">
          <div>
            <span>{t('itinerary.eyebrow.builder')}</span>
            <h2 id="itinerary-builder-title">{t('itinerary.builder.title')}</h2>
            <p>{t('itinerary.builder.description')}</p>
          </div>
          <CalendarClock size={27} aria-hidden="true" />
        </div>

        <form className="itinerary-builder-form" onSubmit={submitPlan}>
          <label htmlFor="itinerary-start">
            <span>{t('itinerary.field.start')}</span>
            <select id="itinerary-start" value={form.startSpot} onChange={(event) => updateForm('startSpot', event.target.value)} disabled={activePlanState.kind === 'loading'} required>
              <option value="">{t('itinerary.choose')}</option>
              {apiSpots.map((spot) => <option key={spot.apiId} value={spot.apiId}>{spot.name} · {spot.region}</option>)}
            </select>
          </label>
          <label htmlFor="itinerary-end">
            <span>{t('itinerary.field.end')}</span>
            <select id="itinerary-end" value={form.endSpot} onChange={(event) => updateForm('endSpot', event.target.value)} disabled={activePlanState.kind === 'loading'} required>
              <option value="">{t('itinerary.choose')}</option>
              {apiSpots.map((spot) => <option key={spot.apiId} value={spot.apiId}>{spot.name} · {spot.region}</option>)}
            </select>
          </label>
          <label htmlFor="itinerary-date">
            <span>{t('itinerary.field.date')}</span>
            <input id="itinerary-date" type="date" min={itineraryDateValue()} max={itineraryDateValue(7)} value={form.planDate} onChange={(event) => updateForm('planDate', event.target.value)} disabled={activePlanState.kind === 'loading'} required />
          </label>
          <label htmlFor="itinerary-transport">
            <span>{t('itinerary.field.transport')}</span>
            <select id="itinerary-transport" value={form.transport} onChange={(event) => updateForm('transport', event.target.value)} disabled={activePlanState.kind === 'loading'}>
              <option value="drive">{t('itinerary.transport.drive')}</option>
              <option value="walk">{t('itinerary.transport.walk')}</option>
              <option value="bicycle">{t('itinerary.transport.bicycle')}</option>
            </select>
          </label>
          <label htmlFor="itinerary-start-time">
            <span>{t('itinerary.field.startTime')}</span>
            <input id="itinerary-start-time" type="time" value={form.startTime} onChange={(event) => updateForm('startTime', event.target.value)} disabled={activePlanState.kind === 'loading'} required />
          </label>
          <label htmlFor="itinerary-end-time">
            <span>{t('itinerary.field.endTime')}</span>
            <input id="itinerary-end-time" type="time" value={form.endTime} onChange={(event) => updateForm('endTime', event.target.value)} disabled={activePlanState.kind === 'loading'} required />
          </label>
          <label htmlFor="itinerary-budget">
            <span>{t('itinerary.field.budget')}</span>
            <input id="itinerary-budget" type="number" min="0" max="100000000" step="1000" inputMode="numeric" value={form.budget} onChange={(event) => updateForm('budget', event.target.value)} disabled={activePlanState.kind === 'loading'} required />
          </label>
          <label className="itinerary-check" htmlFor="itinerary-bad-weather">
            <input id="itinerary-bad-weather" type="checkbox" checked={form.badWeather} onChange={(event) => updateForm('badWeather', event.target.checked)} disabled={activePlanState.kind === 'loading'} />
            <span>{t('itinerary.field.badWeather')}</span>
          </label>

          {session.status === 'authenticated' ? (
            <>
              <label className="itinerary-check" htmlFor="itinerary-save">
                <input id="itinerary-save" type="checkbox" checked={form.save} onChange={(event) => updateForm('save', event.target.checked)} disabled={activePlanState.kind === 'loading'} />
                <span>{t('itinerary.field.save')}</span>
              </label>
              {form.save ? (
                <label className="is-wide" htmlFor="itinerary-title">
                  <span>{t('itinerary.field.title')}</span>
                  <input id="itinerary-title" value={form.title} onChange={(event) => updateForm('title', event.target.value)} maxLength="120" disabled={activePlanState.kind === 'loading'} />
                </label>
              ) : null}
            </>
          ) : (
            <p className="itinerary-auth-note">
              {t('itinerary.anonymous')} <Link to="/profile">{t('itinerary.signInToSave')}</Link>
            </p>
          )}

          {apiSpots.length === 0 ? (
            <p className="itinerary-feedback" role="status">
              {['idle', 'loading'].includes(spotStatus) ? t('itinerary.catalog.loading') : t('itinerary.catalog.unavailable')}
            </p>
          ) : null}
          {activePlanState.kind === 'error' ? (
            <p className="itinerary-feedback is-error" role="alert">{t(activePlanState.error?.messageKey || 'itinerary.error.response')}</p>
          ) : null}
          <button type="submit" className="itinerary-submit" disabled={activePlanState.kind === 'loading' || apiSpots.length === 0}>
            {activePlanState.kind === 'loading' ? <LoaderCircle className="button-spinner" size={17} aria-hidden="true" /> : <CalendarClock size={17} aria-hidden="true" />}
            {activePlanState.kind === 'loading' ? t('itinerary.generating') : t('itinerary.submit')}
          </button>
        </form>
      </section> : null}

      {hasLiveRequest && activePlanState.kind === 'ready' ? (
        <section className="itinerary-result" aria-labelledby="itinerary-result-title" aria-live="polite">
          <div className="itinerary-result-heading">
            <div>
              <span>{t('itinerary.result.badge')}</span>
              <h2 id="itinerary-result-title">{t('itinerary.result.title')}</h2>
              <p>{t('itinerary.result.notice')}</p>
            </div>
            <ShieldAlert size={27} aria-hidden="true" />
          </div>
          <p className="itinerary-safety-notice"><ShieldAlert size={17} aria-hidden="true" /> {t('itinerary.result.safetyNotice')}</p>
          {activePlanState.data.saved_itinerary_id ? <p className="itinerary-saved-notice"><Check size={16} aria-hidden="true" /> {t('itinerary.result.saved')}</p> : null}
          <dl className="itinerary-summary-grid">
            <div><dt><MapPin size={15} aria-hidden="true" /> {t('itinerary.summary.route')}</dt><dd>{activePlanState.data.start_spot?.name || '—'} → {activePlanState.data.end_spot?.name || '—'}</dd></div>
            <div><dt><Banknote size={15} aria-hidden="true" /> {t('itinerary.summary.cost')}</dt><dd>{formatKrw(plan?.total_cost_krw, intlLocale)}</dd></div>
            <div><dt><Car size={15} aria-hidden="true" /> {t('itinerary.summary.travel')}</dt><dd>{t('itinerary.unit.minutes', { count: Math.max(0, Number(plan?.total_travel_minutes) || 0) })}</dd></div>
            <div><dt><Footprints size={15} aria-hidden="true" /> {t('itinerary.summary.activity')}</dt><dd>{t('itinerary.unit.minutes', { count: Math.max(0, Number(plan?.total_activity_minutes) || 0) })}</dd></div>
            <div><dt><Clock3 size={15} aria-hidden="true" /> {t('itinerary.summary.end')}</dt><dd>{minuteToTime(plan?.end_arrival_minute)}</dd></div>
          </dl>
          <div className="itinerary-visits">
            <h3>{t('itinerary.visits.title')}</h3>
            {visits.length === 0 ? <p>{t('itinerary.visits.empty')}</p> : (
              <ol>
                {visits.map((visit) => (
                  <li key={`${visit.candidate_id}-${visit.start_minute}`}>
                    <span>{minuteToTime(visit.start_minute)}</span>
                    <div>
                      <strong>{visit.candidate_name || t('account.spot.unknown')}</strong>
                      <small>{t('itinerary.visits.window', {
                        arrival: minuteToTime(visit.arrival_minute),
                        start: minuteToTime(visit.start_minute),
                        end: minuteToTime(visit.end_minute),
                      })}</small>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <p className="itinerary-route-evidence"><Database size={15} aria-hidden="true" /> {t('itinerary.routeEvidence', { count: routeSnapshotCount })}</p>
        </section>
      ) : null}

      {session.status === 'authenticated' ? (
        <section className="saved-itinerary-section" aria-labelledby="saved-itinerary-title">
          <div className="itinerary-builder-heading">
            <div>
              <span>{t('itinerary.eyebrow.saved')}</span>
              <h2 id="saved-itinerary-title">{t('itinerary.saved.title')}</h2>
              <p>{t('itinerary.saved.description')}</p>
            </div>
            <Database size={26} aria-hidden="true" />
          </div>
          {savedState.kind === 'loading' ? <p className="itinerary-feedback" role="status"><LoaderCircle className="button-spinner" size={16} aria-hidden="true" /> {t('itinerary.saved.loading')}</p> : null}
          {savedState.kind === 'error' ? (
            <div className="itinerary-feedback is-error" role="alert">
              <span>{t(savedState.error?.messageKey || 'itinerary.error.response')}</span>
              <button type="button" onClick={loadSaved}>{t('common.retry')}</button>
            </div>
          ) : null}
          {savedState.kind === 'ready' && savedState.items.length === 0 ? (
            <div className="saved-itinerary-empty"><strong>{t('itinerary.saved.empty')}</strong><p>{t('itinerary.saved.emptyDescription')}</p></div>
          ) : null}
          {savedState.items.length > 0 ? (
            <ul className="saved-itinerary-list">
              {savedState.items.map((item) => (
                <SavedItineraryCard
                  key={item.id}
                  item={item}
                  intlLocale={intlLocale}
                  t={t}
                  onUpdated={(updated) => setSavedState((current) => ({
                    ...current,
                    items: current.items.map((entry) => (entry.id === updated.id ? updated : entry)),
                  }))}
                  onDeleted={(id) => setSavedState((current) => ({
                    ...current,
                    items: current.items.filter((entry) => entry.id !== id),
                  }))}
                />
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function ConciergePage() {
  const location = useLocation();
  const { intlLocale, locale, t } = useI18n();
  const locationPersonaId = typeof location.state?.personaId === 'string'
    ? location.state.personaId
    : null;
  const [storedPersonaId] = useState(readPersonaId);
  const personaId = locationPersonaId || storedPersonaId;
  const persona = personas.find((item) => item.id === personaId) ?? null;
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [form, setForm] = useState(() => buildInitialForm(personaId));
  const [ageError, setAgeError] = useState('');
  const [requestState, setRequestState] = useState({ kind: 'idle' });
  const activeRequest = useRef(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const activity = activityOptions.find((item) => item.value === form.activity) || activityOptions[0];
  const demoResults = useMemo(() => demoRecommendations[getDemoIntent(form)], [form]);
  const isLoading = requestState.kind === 'loading';
  const controlAges = parseAges(form.ages).ages || [];
  const supervisionRequired = requiresAdultSupervision(form, controlAges);
  const compatibleSpotTypes = spotTypeOptions.filter((option) => (
    option.id !== 'all' && spotTypeSupportsActivity(option.id, form.activity)
  ));

  const runRecommendation = async (nextForm, nextQuery) => {
    const parsed = parseAges(nextForm.ages);
    if (parsed.errorKey) {
      setAgeError(parsed.errorKey);
      return;
    }

    setAgeError('');
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setRequestState({ kind: 'loading' });

    try {
      const payload = buildRecommendationPayload(nextForm, parsed.ages, persona?.title || '');
      const response = await requestRecommendations(payload, { signal: controller.signal });
      if (activeRequest.current !== controller) return;
      const normalized = normalizeLiveResponse(response, t);

      setSubmittedQuery(nextQuery);
      if (normalized.recommendations.length > 0) {
        setRequestState({
          kind: 'live',
          recommendations: normalized.recommendations,
          excluded: normalized.excluded,
          meta: normalized.meta,
          requestPayload: payload,
        });
      } else {
        setRequestState({
          kind: 'demo',
          reason: 'empty',
          excluded: normalized.excluded,
          meta: normalized.meta,
        });
      }
    } catch (error) {
      if (isRecommendationRequestCanceled(error)) return;
      if (activeRequest.current !== controller) return;
      setSubmittedQuery(nextQuery);
      setRequestState({
        kind: 'demo',
        reason: 'error',
        error: getRecommendationError(error),
        excluded: {},
        meta: null,
      });
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  };

  const submitQuery = (event) => {
    event.preventDefault();
    const trimmed = query.trim();
    const inferred = inferFormFromQuery(trimmed, form);
    setForm(inferred);
    void runRecommendation(inferred, trimmed);
  };

  const chooseSuggestion = (suggestion) => {
    const suggestionText = t(suggestion.key);
    const inferred = {
      ...form,
      ...suggestion.preset,
      adultSupervisionConfirmed: null,
    };
    setQuery(suggestionText);
    setForm(inferred);
    void runRecommendation(inferred, suggestionText);
  };

  const updateForm = (field, value) => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setForm((current) => {
      const next = { ...current, [field]: value };
      if (
        field !== 'adultSupervisionConfirmed'
        && ['activity', 'participantSkillLevel', 'ages'].includes(field)
        && current[field] !== value
      ) {
        next.adultSupervisionConfirmed = null;
      }
      if (
        field === 'activity'
        && next.spotType
        && !spotTypeSupportsActivity(next.spotType, value)
      ) {
        next.spotType = '';
      }
      return next;
    });
    setRequestState({ kind: 'idle' });
    setSubmittedQuery('');
    if (field === 'ages') setAgeError('');
  };

  const resultTitle = submittedQuery
    ? `“${submittedQuery}”`
    : t('concierge.results.defaultTitle', { activity: t(`activity.${activity.value}`) });
  const visibleResults = requestState.kind === 'live'
    ? requestState.recommendations
    : demoResults;

  return (
    <div className="concierge-page">
      <header className="concierge-hero">
        <div className="concierge-heading">
          <span className="concierge-kicker"><WandSparkles size={15} aria-hidden="true" /> {t('concierge.eyebrow.hero')}</span>
          <h1>{t('concierge.hero.title')}</h1>
          <p>{t('concierge.hero.description')}</p>
          <div className="concierge-proof">
            <span><ShieldCheck size={14} aria-hidden="true" /> {t('concierge.hero.proofGate')}</span>
            <span><Database size={14} aria-hidden="true" /> {t('concierge.hero.proofSource')}</span>
            <span><Check size={14} aria-hidden="true" /> {t('concierge.hero.proofUnknown')}</span>
          </div>
        </div>

        <div className="concierge-orb" aria-hidden="true">
          <Sparkles size={34} />
          <span>{t('concierge.hero.orb')}</span>
        </div>
      </header>

      <div className="concierge-workspace">
        <section className="concierge-composer" aria-labelledby="composer-title">
          <div className="composer-title-row">
            <div>
              <span>{t('concierge.eyebrow.conditions')}</span>
              <h2 id="composer-title">{t('concierge.form.title')}</h2>
            </div>
            <span className={`runtime-label is-${requestState.kind}`}>
              {requestState.kind === 'live' && t('concierge.state.live')}
              {requestState.kind === 'loading' && t('concierge.state.loading')}
              {requestState.kind === 'demo' && (requestState.error ? t('concierge.state.demoError') : t('concierge.state.demoEmpty'))}
              {requestState.kind === 'idle' && (persona
                ? t('concierge.state.preset', { persona: t(`persona.${persona.id}.title`) })
                : t('concierge.state.idle'))}
            </span>
          </div>

          <form onSubmit={submitQuery} noValidate>
            <div className="concierge-input-wrap">
              <MessageCircleMore size={22} aria-hidden="true" />
              <label className="sr-only" htmlFor="concierge-query">{t('concierge.query.label')}</label>
              <textarea
                id="concierge-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t('concierge.query.placeholder')}
                rows="3"
                maxLength="300"
              />
              <button type="submit" disabled={isLoading}>
                {isLoading ? <LoaderCircle className="button-spinner" size={18} aria-hidden="true" /> : <Send size={18} aria-hidden="true" />}
                {isLoading ? t('common.loading') : t('concierge.query.submit')}
              </button>
            </div>

            <div className="prompt-suggestions" aria-label={t('concierge.query.suggestions')}>
              {promptSuggestions.map((suggestion) => (
                <button key={suggestion.key} type="button" onClick={() => chooseSuggestion(suggestion)} disabled={isLoading}>
                  {t(suggestion.key)}
                  <ArrowRight size={14} aria-hidden="true" />
                </button>
              ))}
            </div>

            <div className="condition-panel">
              <div className="condition-panel-heading">
                <SlidersHorizontal size={18} aria-hidden="true" />
                <div>
                  <h3>{t('concierge.controls.title')}</h3>
                  <p>{t('concierge.controls.description')}</p>
                </div>
              </div>

              <div className="condition-grid">
                <label className="condition-field">
                  <span><Waves size={16} aria-hidden="true" /> {t('concierge.controls.activity')}</span>
                  <select value={form.activity} onChange={(event) => updateForm('activity', event.target.value)}>
                    {activityOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.icon} {t(`activity.${option.value}`)}</option>
                    ))}
                  </select>
                </label>

                <label className="condition-field">
                  <span><MapPin size={16} aria-hidden="true" /> {t('concierge.controls.region')}</span>
                  <input
                    type="text"
                    value={form.region}
                    onChange={(event) => updateForm('region', event.target.value)}
                    placeholder={t('concierge.controls.regionPlaceholder')}
                    maxLength="100"
                    autoComplete="address-level1"
                  />
                  <small>{form.region.trim()
                    ? t('concierge.controls.regionHelp')
                    : t('concierge.controls.regionNationwideHelp')}</small>
                </label>

                <label className="condition-field">
                  <span><Compass size={16} aria-hidden="true" /> {t('concierge.controls.spotType')}</span>
                  <select
                    value={form.spotType}
                    onChange={(event) => updateForm('spotType', event.target.value)}
                  >
                    <option value="">{t('concierge.controls.allCompatibleTypes')}</option>
                    {compatibleSpotTypes.map((option) => (
                      <option key={option.id} value={option.id}>{t(`map.type.${option.id}`)}</option>
                    ))}
                  </select>
                  <small>{t('concierge.controls.spotTypeHelp')}</small>
                </label>

                {['surf', 'swim'].includes(form.activity) && (
                  <label className="condition-field">
                    <span><ShieldCheck size={16} aria-hidden="true" /> {t('concierge.controls.skill')}</span>
                    <select
                      value={form.participantSkillLevel}
                      onChange={(event) => updateForm('participantSkillLevel', event.target.value)}
                    >
                      {SKILL_LEVELS.map((level) => (
                        <option key={level} value={level}>{t(`concierge.skill.${level}`)}</option>
                      ))}
                    </select>
                    <small>{t(form.activity === 'surf' ? 'concierge.skill.surfHelp' : 'concierge.skill.swimHelp')}</small>
                  </label>
                )}

                <label className="condition-field">
                  <span><Users size={16} aria-hidden="true" /> {t('concierge.controls.ages')}</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={form.ages}
                    onChange={(event) => updateForm('ages', event.target.value)}
                    placeholder={t('concierge.controls.agesPlaceholder')}
                    aria-describedby={ageError ? 'ages-help ages-error' : 'ages-help'}
                    aria-invalid={Boolean(ageError)}
                  />
                  <small id="ages-help">{t('concierge.controls.agesHelp')}</small>
                  {ageError ? <strong id="ages-error" className="field-error" role="alert">{t(ageError)}</strong> : null}
                </label>

                {supervisionRequired && (
                  <label className="condition-field">
                    <span><ShieldAlert size={16} aria-hidden="true" /> {t('concierge.controls.supervision')}</span>
                    <select
                      value={typeof form.adultSupervisionConfirmed === 'boolean'
                        ? String(form.adultSupervisionConfirmed)
                        : ''}
                      onChange={(event) => updateForm(
                        'adultSupervisionConfirmed',
                        event.target.value === '' ? null : event.target.value === 'true',
                      )}
                    >
                      <option value="">{t('concierge.supervision.unselected')}</option>
                      <option value="true">{t('concierge.supervision.yes')}</option>
                      <option value="false">{t('concierge.supervision.no')}</option>
                    </select>
                    <small>{t('concierge.supervision.help')}</small>
                  </label>
                )}

                <label className="range-field">
                  <span>{t('concierge.controls.quiet')} <output>{form.quiet}%</output></span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    value={form.quiet}
                    onChange={(event) => updateForm('quiet', Number(event.target.value))}
                    aria-label={t('concierge.controls.quiet')}
                  />
                  <small><span>{t('concierge.controls.quietLow')}</span><span>{t('concierge.controls.quietHigh')}</span></small>
                </label>

                <label className="range-field">
                  <span>{t('concierge.controls.intensity')} <output>{form.activityLevel}%</output></span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    value={form.activityLevel}
                    onChange={(event) => updateForm('activityLevel', Number(event.target.value))}
                    aria-label={t('concierge.controls.intensity')}
                  />
                  <small><span>{t('concierge.controls.intensityLow')}</span><span>{t('concierge.controls.intensityHigh')}</span></small>
                </label>
              </div>

              <fieldset className="party-options">
                <legend>{t('concierge.controls.party')}</legend>
                <label>
                  <input
                    type="checkbox"
                    checked={form.requiresAccessibility}
                    onChange={(event) => updateForm('requiresAccessibility', event.target.checked)}
                  />
                  <span className="option-icon"><Accessibility size={18} aria-hidden="true" /></span>
                  <span><strong>{t('concierge.controls.accessibility')}</strong><small>{t('concierge.controls.accessibilityHelp')}</small></span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={form.bringingPet}
                    onChange={(event) => updateForm('bringingPet', event.target.checked)}
                  />
                  <span className="option-icon"><PawPrint size={18} aria-hidden="true" /></span>
                  <span><strong>{t('concierge.controls.pet')}</strong><small>{t('concierge.controls.petHelp')}</small></span>
                </label>
              </fieldset>
            </div>
          </form>
        </section>

        {requestState.kind === 'idle' ? (
          <section className="concierge-empty" aria-labelledby="empty-title">
            <div className="empty-graphic"><Compass size={24} aria-hidden="true" /></div>
            <div>
              <span>{t('concierge.eyebrow.ready')}</span>
              <h2 id="empty-title">{t('concierge.empty.title')}</h2>
              <p>{t('concierge.empty.description')}</p>
            </div>
          </section>
        ) : (
          <section className="concierge-results" aria-live="polite" aria-busy={isLoading}>
            <ResultStatus requestState={requestState} intlLocale={intlLocale} t={t} />

            {requestState.kind !== 'loading' ? (
              <>
                <div className="result-context">
                  <span><Sparkles size={16} aria-hidden="true" /> {t('concierge.results.label')}</span>
                  <h2>{resultTitle}</h2>
                  <p>
                    {requestState.kind === 'live'
                      ? t('concierge.results.liveDescription', { activity: t(`activity.${activity.value}`) })
                      : t('concierge.results.demoDescription')}
                  </p>
                </div>

                <div className="recommendation-grid">
                  {visibleResults.map((item, index) => (
                    requestState.kind === 'live'
                      ? <LiveRecommendationCard key={item.id} item={item} index={index} t={t} />
                      : <DemoRecommendationCard key={item.id} item={item} index={index} locale={locale} t={t} />
                  ))}
                </div>

                <ExclusionSummary excluded={requestState.excluded} meta={requestState.meta} t={t} />

              </>
            ) : null}
          </section>
        )}
        <ItineraryWorkspace requestState={requestState} intlLocale={intlLocale} t={t} />
      </div>
    </div>
  );
}

export default ConciergePage;
