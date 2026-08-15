import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Accessibility,
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  Check,
  Clock3,
  Compass,
  Database,
  LoaderCircle,
  MapPin,
  MessageCircleMore,
  PawPrint,
  Send,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Users,
  WandSparkles,
  Waves,
} from 'lucide-react';
import { personas } from '../data/pongdangData';
import { useI18n } from '../i18n';
import {
  buildRecommendationPayload,
  getRecommendationError,
  isRecommendationRequestCanceled,
  requestRecommendations,
  requiresAdultSupervision,
} from '../services/recommendations';
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
  beach: 'map.type.sea',
  valley: 'map.type.valley',
  hotspring: 'map.type.hotspring',
  lake: 'map.type.lake',
  mudflat: 'map.type.tidal_flat',
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
      spotId === null
      || spotId === undefined
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
      id: String(spotId),
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
          <span>FAIL-CLOSED REPORT</span>
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
        <span>LIVE · {item.type}</span>
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
            <strong>CLEAR · {decision}</strong>
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
        <span>DEMO · {locale === 'ko' ? item.type : t('concierge.demo.type')}</span>
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
          <span className="concierge-kicker"><WandSparkles size={15} aria-hidden="true" /> EVIDENCE-FIRST WATER CONCIERGE</span>
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
              <span>STEP 01 · CONDITIONS</span>
              <h2 id="composer-title">{t('concierge.form.title')}</h2>
            </div>
            <span className={`runtime-label is-${requestState.kind}`}>
              {requestState.kind === 'live' && t('concierge.state.live')}
              {requestState.kind === 'loading' && t('concierge.state.loading')}
              {requestState.kind === 'demo' && (requestState.error ? t('concierge.state.demoError') : t('concierge.state.demoEmpty'))}
              {requestState.kind === 'idle' && (persona ? `${t(`persona.${persona.id}.title`)} · preset` : t('concierge.state.idle'))}
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
              <span>READY WHEN YOU ARE</span>
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

                <div className="itinerary-preview">
                  <div className="itinerary-copy">
                    <span>STEP 02 · READY LATER</span>
                    <h2>{t('concierge.itinerary.title')}</h2>
                    <p>{t('concierge.itinerary.description')}</p>
                    <button type="button" disabled title={t('concierge.itinerary.pending')}>
                      <CalendarClock size={18} aria-hidden="true" /> {t('concierge.itinerary.pending')}
                    </button>
                  </div>
                  <div className="itinerary-rules" aria-label={t('concierge.itinerary.rules')}>
                    <div><Clock3 size={18} aria-hidden="true" /><span><strong>{t('concierge.itinerary.hours')}</strong><small>{t('concierge.itinerary.hoursDetail')}</small></span></div>
                    <div><MapPin size={18} aria-hidden="true" /><span><strong>{t('concierge.itinerary.matrix')}</strong><small>{t('concierge.itinerary.matrixDetail')}</small></span></div>
                    <div><ShieldCheck size={18} aria-hidden="true" /><span><strong>{t('concierge.itinerary.weather')}</strong><small>{t('concierge.itinerary.weatherDetail')}</small></span></div>
                  </div>
                </div>
              </>
            ) : null}
          </section>
        )}
      </div>
    </div>
  );
}

export default ConciergePage;
