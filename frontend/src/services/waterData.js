import api from './api.js';
import { getSpotTypeMeta } from './spotTypes.js';

const ACTIVITY_IDS = ['swim', 'surf', 'relax', 'mudflat', 'onsen', 'rafting'];
const MAX_PAGES = 20;
const DEFAULT_STALE_AFTER_MS = 6 * 60 * 60 * 1000;

export const dataStateMeta = Object.freeze({
  live: { label: '실데이터', shortLabel: 'LIVE', tone: 'live' },
  stale: { label: '갱신 지연', shortLabel: 'STALE', tone: 'stale' },
  missing: { label: '판단 자료 없음', shortLabel: 'NO DATA', tone: 'missing' },
  demo: { label: '데모 대체값', shortLabel: 'DEMO', tone: 'demo' },
  error: { label: '데이터 연결 오류', shortLabel: 'ERROR', tone: 'error' },
});

const safetyMeta = Object.freeze({
  clear: {
    level: 'clear',
    label: '차단 신호 없음',
    message: '필수 안전 입력에서 활동 중지 신호가 확인되지 않았습니다. 현장 안내를 함께 확인하세요.',
  },
  caution: {
    level: 'caution',
    label: '주의 조건',
    message: '주의 조건이 있습니다. 근거와 현장 안내를 확인한 뒤 활동 범위를 조정하세요.',
  },
  stop: {
    level: 'stop',
    label: '활동 중지',
    message: '공식 통제 또는 중지 조건이 확인되었습니다. 이 활동을 추천하지 않습니다.',
  },
  unknown: {
    level: 'unknown',
    label: '안전 판단 보류',
    message: '필수 안전 자료가 없거나 오래되어 판단할 수 없습니다. 점수로 안전을 추정하지 않습니다.',
  },
});

const reasonLabels = Object.freeze({
  ACCESS_STATUS_MISSING: '공식 출입 상태가 없습니다.',
  ACTIVE_PATROL_UNAVAILABLE: '활동 중인 안전요원을 확인할 수 없습니다.',
  ADULT_ARM_REACH_SUPERVISION_UNAVAILABLE: '보호자 밀착 감독 조건이 충족되지 않았습니다.',
  DESIGNATED_SWIM_ZONE_UNAVAILABLE: '지정 물놀이 구역을 이용할 수 없습니다.',
  LIGHTNING_30_MINUTE_CLEARANCE_NOT_MET: '마지막 번개 후 30분이 지나지 않았습니다.',
  MARINE_HAZARD_ACTIVE: '해상 위험 특보가 발효 중입니다.',
  OFFICIAL_ACCESS_CLOSED: '공식 출입 통제 상태입니다.',
  OFFICIAL_STOP_ACTIVE: '공식 활동 중지 신호가 발효 중입니다.',
  RIP_CURRENT_CAUTION: '이안류 주의 단계입니다.',
  RIP_CURRENT_HIGH: '이안류 위험 단계입니다.',
  SAFETY_VALUE_UNRECOGNIZED: '안전 입력값을 해석할 수 없습니다.',
  SEVERE_WEATHER_ALERT: '기상 경보가 발효 중입니다.',
  WATER_QUALITY_ADVISORY: '물 접촉 자제 권고가 확인되었습니다.',
  WATER_QUALITY_STATUS_MISSING: '최신 수질 상태가 없습니다.',
  WATER_QUALITY_UNSAFE: '수질 부적합 상태입니다.',
  WEATHER_ADVISORY: '기상 주의보가 발효 중입니다.',
});

function collectionFromPayload(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

function publicError(error) {
  return {
    kind: error?.response ? 'response' : 'network',
    status: Number.isInteger(error?.response?.status) ? error.response.status : null,
  };
}

async function fetchAllPages(path, options = {}) {
  const records = [];
  let nextPath = path;
  let pageCount = 0;
  let requestOptions = options;

  while (nextPath && pageCount < MAX_PAGES) {
    // Axios accepts both same-origin paths and the absolute `next` URL emitted
    // by Django REST Framework.
    const response = await api.get(nextPath, requestOptions);
    records.push(...collectionFromPayload(response.data));
    nextPath = typeof response.data?.next === 'string' ? response.data.next : null;
    requestOptions = {};
    pageCount += 1;
  }

  return records;
}

function normalizeName(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('ko-KR')
    .replace(/해수욕장/g, '해변')
    .replace(/[^0-9a-z가-힣]/g, '');
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function stringOr(value, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function stableHash(value) {
  return [...String(value)].reduce(
    (hash, character) => ((hash * 31) + character.codePointAt(0)) >>> 0,
    2166136261,
  );
}

function syntheticVisual(apiSpot) {
  const hash = stableHash(`${apiSpot.id}:${apiSpot.name}`);
  const hue = 164 + (hash % 54);
  const lat = finiteNumber(apiSpot.lat);
  const lng = finiteNumber(apiSpot.lng);
  const x = lng === null ? 50 + (hash % 36) - 18 : 10 + (((lng - 124) / 8) * 80);
  const y = lat === null ? 50 + ((hash >> 8) % 36) - 18 : 88 - (((lat - 33) / 6) * 76);
  const meta = getSpotTypeMeta(apiSpot.type);

  return {
    gradient: `linear-gradient(145deg, hsl(${hue} 58% 34%), hsl(${hue + 22} 63% 66%), #eff2d8)`,
    accent: `hsl(${hue} 58% 34%)`,
    icon: meta.icon,
    mapPosition: {
      x: Math.min(92, Math.max(8, x)),
      y: Math.min(90, Math.max(10, y)),
    },
  };
}

function emptyScores() {
  return Object.fromEntries(ACTIVITY_IDS.map((activity) => [activity, null]));
}

function unknownSafety() {
  return { ...safetyMeta.unknown };
}

function demoFallbackSafety(spot) {
  return {
    level: 'demo',
    label: spot?.safety?.label || '데모 조건',
    message: spot?.safety?.message
      || '실제 안전 관측이 없어 고정 데모 설명을 표시합니다. 공식 특보와 현장 안내를 확인하세요.',
  };
}

function emptyConditions() {
  return {
    waterTemperatureC: null,
    waterTemp: '자료 없음',
    airTemp: '자료 없음',
    waveHeight: '자료 없음',
    windSpeed: '자료 없음',
    waterQuality: '자료 없음',
    crowd: '자료 없음',
    tide: { low: '—', high: '—' },
  };
}

export function apiSpotRouteId(apiId) {
  const normalized = String(apiId ?? '').trim();
  if (!/^[1-9]\d*$/.test(normalized)) return null;
  return `api-${normalized}`;
}

export function findSpotByRouteId(spots, routeId) {
  const normalizedRouteId = String(routeId ?? '');
  if (normalizedRouteId.startsWith('api-')) {
    const apiId = normalizedRouteId.slice(4);
    if (!apiId) return null;
    return spots.find((spot) => String(spot.apiId) === apiId) ?? null;
  }
  return spots.find((spot) => (
    String(spot.id) === normalizedRouteId || spot.slug === normalizedRouteId
  )) ?? null;
}

function normalizeDemoSpot(spot) {
  const meta = getSpotTypeMeta(spot?.type);
  return {
    ...spot,
    type: meta.type,
    typeLabel: meta.label,
    visual: spot?.visual
      ? { ...spot.visual, icon: meta.icon }
      : spot?.visual,
    apiId: null,
    spotSource: 'demo',
    livecamUrl: '',
    livecam_url: '',
    catalogVerification: 'demo',
    catalog_verification: 'demo',
    catalogVerifiedAt: null,
    catalog_verified_at: null,
    dataState: 'demo',
    safety: demoFallbackSafety(spot),
    conditionRecords: {},
    observations: [],
    latestObservation: null,
  };
}

function findDemoMatch(apiSpot, demoSpots, claimedDemoIds) {
  const apiTourId = stringOr(apiSpot.tourapi_id);
  const apiName = normalizeName(apiSpot.name);
  const apiLat = finiteNumber(apiSpot.lat);
  const apiLng = finiteNumber(apiSpot.lng);

  return demoSpots.find((demoSpot) => {
    if (claimedDemoIds.has(demoSpot.id)) return false;
    if (apiTourId && stringOr(demoSpot.tourapi_id) === apiTourId) return true;
    if (apiName && normalizeName(demoSpot.name) === apiName) return true;
    if (apiLat === null || apiLng === null) return false;
    return Math.abs(apiLat - demoSpot.lat) < 0.006
      && Math.abs(apiLng - demoSpot.lng) < 0.006;
  }) ?? null;
}

function mergeOneSpot(apiSpot, demoSpot) {
  const meta = getSpotTypeMeta(apiSpot.type || demoSpot?.type);
  const region = stringOr(apiSpot.region, demoSpot?.region || '지역 정보 없음');
  const tags = Array.isArray(apiSpot.tags) && apiSpot.tags.length > 0
    ? apiSpot.tags.filter((tag) => typeof tag === 'string')
    : (demoSpot?.tags ?? []);
  const visual = demoSpot?.visual ?? syntheticVisual(apiSpot);
  const description = stringOr(apiSpot.description, demoSpot?.description || '관광 상세 설명을 준비하고 있습니다.');
  const livecamUrl = stringOr(apiSpot.livecam_url);
  const catalogVerification = stringOr(apiSpot.catalog_verification, 'unknown').toLowerCase();
  const catalogVerifiedAt = apiSpot.catalog_verified_at ?? null;

  return {
    ...(demoSpot ?? {}),
    id: demoSpot?.id ?? apiSpotRouteId(apiSpot.id),
    apiId: apiSpot.id,
    slug: demoSpot?.slug ?? `api-spot-${apiSpot.id}`,
    name: stringOr(apiSpot.name, demoSpot?.name || '이름 없는 물 여행지'),
    type: meta.type,
    typeLabel: meta.label,
    region,
    regionGroup: stringOr(apiSpot.region, demoSpot?.regionGroup || region),
    address: stringOr(apiSpot.address, demoSpot?.address || '주소 정보 없음'),
    lat: finiteNumber(apiSpot.lat) ?? demoSpot?.lat ?? 37.75,
    lng: finiteNumber(apiSpot.lng) ?? demoSpot?.lng ?? 128.9,
    tourapiId: stringOr(apiSpot.tourapi_id),
    tags,
    imageUrl: stringOr(apiSpot.image_url, demoSpot?.imageUrl || ''),
    image_url: stringOr(apiSpot.image_url, demoSpot?.imageUrl || ''),
    livecamUrl,
    livecam_url: livecamUrl,
    catalogVerification,
    catalog_verification: catalogVerification,
    catalogVerifiedAt,
    catalog_verified_at: catalogVerifiedAt,
    catalogSource: stringOr(apiSpot.catalog_source),
    catalogSourceUrl: stringOr(apiSpot.catalog_source_url),
    description,
    summary: demoSpot?.summary ?? description,
    scores: demoSpot?.scores ? { ...demoSpot.scores } : emptyScores(),
    safety: demoSpot ? demoFallbackSafety(demoSpot) : unknownSafety(),
    conditions: demoSpot?.conditions ? { ...demoSpot.conditions } : emptyConditions(),
    reasons: demoSpot?.reasons ? [...demoSpot.reasons] : ['공식 Water Index 평가를 기다리고 있어요.'],
    bestTime: demoSpot?.bestTime ?? '공식 평가 대기',
    isGangneungMvp: demoSpot?.isGangneungMvp ?? /강릉/.test(region),
    freshness: demoSpot?.freshness
      ? { ...demoSpot.freshness }
      : { isMock: false, observedAt: null, updatedLabel: '관측 자료 없음' },
    visual,
    spotSource: 'api',
    dataState: demoSpot ? 'demo' : 'missing',
    conditionRecords: {},
    observations: [],
    latestObservation: null,
  };
}

export function mergeSpotsWithDemo(apiSpots, demoSpots) {
  if (!Array.isArray(apiSpots) || apiSpots.length === 0) {
    return demoSpots.map(normalizeDemoSpot);
  }

  const claimedDemoIds = new Set();
  const mergedApiSpots = apiSpots.map((apiSpot) => {
    const demoSpot = findDemoMatch(apiSpot, demoSpots, claimedDemoIds);
    if (demoSpot) claimedDemoIds.add(demoSpot.id);
    return mergeOneSpot(apiSpot, demoSpot);
  });
  const demoOnlySpots = demoSpots
    .filter((spot) => !claimedDemoIds.has(spot.id))
    .map(normalizeDemoSpot);

  return [...mergedApiSpots, ...demoOnlySpots];
}

export async function fetchMergedSpots(demoSpots, params = {}) {
  try {
    const apiSpots = await fetchAllPages('spots/', { params });
    if (apiSpots.length === 0) {
      return {
        data: mergeSpotsWithDemo([], demoSpots),
        source: 'demo',
        status: 'empty',
        error: null,
      };
    }
    const data = mergeSpotsWithDemo(apiSpots, demoSpots);
    return {
      data,
      source: data.some((spot) => spot.spotSource === 'demo') ? 'mixed' : 'api',
      status: 'ready',
      error: null,
    };
  } catch (error) {
    return {
      data: mergeSpotsWithDemo([], demoSpots),
      source: 'demo',
      status: 'error',
      error: publicError(error),
    };
  }
}

function normalizeSafetyStatus(value) {
  const normalized = String(value ?? '').trim().toLowerCase();
  return Object.hasOwn(safetyMeta, normalized) ? normalized : 'unknown';
}

function normalizeDecision(value) {
  const normalized = String(value ?? '').trim().toLowerCase();
  return [
    'recommended',
    'consider',
    'caution',
    'not_recommended',
    'blocked',
    'unknown',
  ].includes(normalized) ? normalized : 'unknown';
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function stateFromEvidence(snapshot, evaluatedAt) {
  const providerState = String(snapshot?.state ?? '').trim().toLowerCase();
  if (['demo', 'missing', 'stale', 'error'].includes(providerState)) return providerState;
  if (!snapshot) return 'missing';

  const now = Date.now();
  const validFrom = parseDate(snapshot.valid_from)?.getTime();
  if (validFrom && validFrom > now) return 'missing';
  const validUntil = parseDate(snapshot.valid_until)?.getTime();
  if (validUntil && validUntil < now) return 'stale';
  const reference = parseDate(snapshot.fetched_at ?? snapshot.observed_at ?? evaluatedAt)?.getTime();
  if (!reference) return 'missing';
  return now - reference > DEFAULT_STALE_AFTER_MS ? 'stale' : 'live';
}

function formatTimestamp(value) {
  const date = parseDate(value);
  if (!date) return '시각 정보 없음';
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function normalizeReason(gate) {
  const code = stringOr(gate?.reason_code, 'REASON_NOT_PROVIDED');
  return {
    code,
    label: reasonLabels[code] ?? code.replaceAll('_', ' ').toLocaleLowerCase('ko-KR'),
    severity: stringOr(gate?.severity, 'info'),
    metricName: stringOr(gate?.metric_name),
  };
}

function metricValueLabel(metric) {
  if (metric?.value === null || metric?.value === undefined || metric.state !== 'valid') {
    return '자료 없음';
  }
  const value = metric.value;
  const unit = stringOr(metric.unit);
  if (typeof value === 'number') {
    const formatted = Number.isInteger(value) ? String(value) : value.toFixed(1);
    if (['degC', '°C', 'celsius'].includes(unit)) return `${formatted}°C`;
    if (['m', 'meter'].includes(unit)) return `${formatted}m`;
    if (['m/s', 'mps'].includes(unit)) return `${formatted}m/s`;
    return `${formatted}${unit ? ` ${unit}` : ''}`;
  }
  if (typeof value === 'boolean') return value ? '예' : '아니요';
  return String(value);
}

function conditionsFromMetrics(metrics) {
  const byName = Object.fromEntries(
    (Array.isArray(metrics) ? metrics : []).map((metric) => [metric.name, metric]),
  );
  const read = (names, fallbackValue = '자료 없음') => {
    const metric = names.map((name) => byName[name]).find(Boolean);
    return metric ? metricValueLabel(metric) : fallbackValue;
  };
  const waterTemperatureMetric = ['water_temperature_c', 'water_temp_c']
    .map((name) => byName[name])
    .find(Boolean);
  const waterTemperatureC = waterTemperatureMetric?.state === 'valid'
    ? finiteNumber(waterTemperatureMetric.value)
    : null;

  return {
    waterTemperatureC,
    waterTemp: read(['water_temperature_c', 'water_temp_c']),
    airTemp: read(['air_temperature_c', 'air_temp_c']),
    waveHeight: read(['wave_height_m', 'average_wave_height_m', 'maximum_wave_height_m']),
    windSpeed: read([
      'wind_speed_ms',
      'maximum_wind_speed_ms',
      'wind_speed_m_s',
      'average_wind_speed_m_s',
    ]),
    waterQuality: read(['water_quality_status', 'water_quality_grade']),
    crowd: read(['crowd_level']),
    tide: {
      low: read(['low_tide_time'], '—'),
      high: read(['high_tide_time'], '—'),
    },
  };
}

export function normalizeConditionScore(score) {
  const reportedSafetyStatus = normalizeSafetyStatus(score?.safety_status);
  const decision = normalizeDecision(score?.decision);
  const numericScore = finiteNumber(score?.suitability_score ?? score?.score);
  const scoreRange = Array.isArray(score?.score_range)
    && score.score_range.length === 2
    && score.score_range.every((value) => finiteNumber(value) !== null)
    ? score.score_range.map(Number)
    : [];
  const snapshot = score?.snapshot && typeof score.snapshot === 'object' ? score.snapshot : null;
  const metrics = Array.isArray(snapshot?.metrics) ? snapshot.metrics : [];
  const reasons = (Array.isArray(score?.gates) ? score.gates : []).map(normalizeReason);
  const dataState = stateFromEvidence(snapshot, score?.evaluated_at);
  const evidenceStartsInFuture = (
    parseDate(snapshot?.valid_from)?.getTime() ?? Number.NEGATIVE_INFINITY
  ) > Date.now();
  const unavailableEvidence = ['stale', 'missing', 'error'].includes(dataState);
  const safetyStatus = evidenceStartsInFuture
    ? 'unknown'
    : (
      unavailableEvidence && reportedSafetyStatus !== 'stop'
        ? 'unknown'
        : reportedSafetyStatus
    );
  const mustHideScore = ['stop', 'unknown'].includes(safetyStatus)
    || ['blocked', 'unknown'].includes(decision);
  const evidenceMessage = {
    stale: '평가 근거의 유효 시간이 지났습니다. 현재 안전 상태로 사용하지 않습니다.',
    missing: '평가에 연결된 관측 근거가 없습니다. 점수로 안전을 추정하지 않습니다.',
    error: '관측 연결 오류로 현재 안전 상태를 확인할 수 없습니다.',
  }[dataState];
  const safety = {
    ...safetyMeta[safetyStatus],
    status: safetyStatus,
    message: evidenceStartsInFuture
      ? '아직 유효하지 않은 미래 평가입니다. 현재 안전 상태로 사용하지 않습니다.'
      : (evidenceMessage ?? reasons[0]?.label ?? safetyMeta[safetyStatus].message),
  };
  if (dataState === 'demo') {
    safety.level = 'demo';
    safety.label = '데모 조건';
    safety.message = '고정 데모 평가이며 현재 안전 상태가 아닙니다. 공식 안내를 확인하세요.';
  }
  const observedAt = snapshot?.observed_at ?? metrics[0]?.provenance?.observed_at ?? null;
  const fetchedAt = snapshot?.fetched_at ?? metrics[0]?.provenance?.fetched_at ?? null;
  const provider = stringOr(snapshot?.provider, metrics[0]?.provenance?.provider || '출처 미상');

  return {
    id: score?.id,
    spotApiId: score?.spot,
    activity: stringOr(score?.activity),
    score: mustHideScore ? null : numericScore,
    rawScore: numericScore,
    scoreRange,
    safetyStatus,
    reportedSafetyStatus,
    safety,
    decision,
    confidence: finiteNumber(score?.confidence),
    coverage: finiteNumber(score?.coverage),
    reasons,
    contributions: Array.isArray(score?.contributions) ? score.contributions : [],
    missingMetrics: Array.isArray(score?.missing_metrics) ? score.missing_metrics : [],
    staleMetrics: Array.isArray(score?.stale_or_conflicting_metrics)
      ? score.stale_or_conflicting_metrics
      : [],
    limitations: Array.isArray(score?.limitations) ? score.limitations : [],
    methodologyVersion: stringOr(score?.methodology_version, '버전 정보 없음'),
    evaluatedAt: score?.evaluated_at ?? null,
    snapshot,
    metrics,
    dataState,
    conditions: conditionsFromMetrics(metrics),
    provenance: {
      provider,
      providerRecordId: stringOr(snapshot?.provider_record_id),
      spatialScope: stringOr(snapshot?.spatial_scope, '공간 범위 정보 없음'),
      observedAt,
      fetchedAt,
      validUntil: snapshot?.valid_until ?? null,
      updatedLabel: `${dataStateMeta[dataState].label} · ${formatTimestamp(fetchedAt ?? score?.evaluated_at)}`,
    },
  };
}

export async function fetchLatestConditionScores(params = {}) {
  try {
    const scores = await fetchAllPages('conditions/scores/latest/', { params });
    return {
      data: scores.map(normalizeConditionScore).filter((score) => score.activity),
      status: scores.length > 0 ? 'ready' : 'empty',
      error: null,
    };
  } catch (error) {
    return { data: [], status: 'error', error: publicError(error) };
  }
}

function normalizeObservation(snapshot) {
  const state = stateFromEvidence(snapshot, null);
  const metrics = Array.isArray(snapshot?.metrics) ? snapshot.metrics : [];
  return {
    id: snapshot?.id,
    spotApiId: snapshot?.spot,
    provider: stringOr(snapshot?.provider, '출처 미상'),
    providerRecordId: stringOr(snapshot?.provider_record_id),
    state,
    observedAt: snapshot?.observed_at ?? null,
    fetchedAt: snapshot?.fetched_at ?? null,
    validUntil: snapshot?.valid_until ?? null,
    spatialScope: stringOr(snapshot?.spatial_scope, '공간 범위 정보 없음'),
    ingestionVersion: stringOr(snapshot?.ingestion_version, '버전 정보 없음'),
    metrics,
    conditions: conditionsFromMetrics(metrics),
    updatedLabel: `${dataStateMeta[state].label} · ${formatTimestamp(snapshot?.fetched_at)}`,
  };
}

export async function fetchSpotObservations(spotApiId) {
  if (spotApiId === null || spotApiId === undefined) {
    return { data: [], status: 'empty', error: null };
  }
  try {
    const snapshots = await fetchAllPages('conditions/observations/', {
      params: { spot: spotApiId },
    });
    return {
      data: snapshots.map(normalizeObservation),
      status: snapshots.length > 0 ? 'ready' : 'empty',
      error: null,
    };
  } catch (error) {
    return { data: [], status: 'error', error: publicError(error) };
  }
}

export function applyConditionScores(spots, scores) {
  const recordsBySpot = new Map();
  scores.forEach((record) => {
    const key = String(record.spotApiId);
    const current = recordsBySpot.get(key) ?? [];
    current.push(record);
    recordsBySpot.set(key, current);
  });

  return spots.map((spot) => {
    const records = recordsBySpot.get(String(spot.apiId)) ?? [];
    if (records.length === 0) return spot;
    const conditionRecords = { ...spot.conditionRecords };
    const nextScores = { ...spot.scores };

    records.forEach((record) => {
      conditionRecords[record.activity] = record;
      nextScores[record.activity] = record.score;
    });

    const freshest = [...Object.values(conditionRecords)].sort((left, right) => (
      (parseDate(right.provenance?.fetchedAt)?.getTime() ?? 0)
      - (parseDate(left.provenance?.fetchedAt)?.getTime() ?? 0)
    ))[0];

    return {
      ...spot,
      scores: nextScores,
      conditionRecords,
      dataState: freshest?.dataState ?? spot.dataState,
      freshness: freshest
        ? {
          isMock: freshest.dataState === 'demo',
          observedAt: freshest.provenance.observedAt,
          updatedLabel: freshest.provenance.updatedLabel,
        }
        : spot.freshness,
    };
  });
}

export function applyObservations(spots, spotApiId, observations) {
  return spots.map((spot) => {
    if (String(spot.apiId) !== String(spotApiId) || observations.length === 0) return spot;
    const latest = observations[0];
    return {
      ...spot,
      observations,
      latestObservation: latest,
      dataState: Object.keys(spot.conditionRecords).length > 0 ? spot.dataState : latest.state,
      conditions: conditionsFromMetrics(latest.metrics),
      freshness: Object.keys(spot.conditionRecords).length > 0
        ? spot.freshness
        : {
          isMock: latest.state === 'demo',
          observedAt: latest.observedAt,
          updatedLabel: latest.updatedLabel,
        },
    };
  });
}

export function getSpotActivityView(spot, activity) {
  const record = spot?.conditionRecords?.[activity] ?? null;
  if (record) {
    return {
      activity,
      score: record.score,
      scoreRange: record.scoreRange,
      safety: record.safety,
      safetyStatus: record.safetyStatus,
      decision: record.decision,
      confidence: record.confidence,
      coverage: record.coverage,
      dataState: record.dataState,
      reasons: record.reasons,
      contributions: record.contributions,
      missingMetrics: record.missingMetrics,
      staleMetrics: record.staleMetrics,
      limitations: record.limitations,
      methodologyVersion: record.methodologyVersion,
      conditions: conditionsFromMetrics(record.metrics),
      provenance: record.provenance,
      isDemoFallback: false,
    };
  }

  const observation = spot?.latestObservation ?? null;
  const hasObservation = Boolean(observation);
  const demoScore = hasObservation ? null : (spot?.scores?.[activity] ?? null);
  const isDemo = !hasObservation && (
    spot?.spotSource === 'demo' || Boolean(demoScore !== null && spot?.apiId)
  );
  return {
    activity,
    score: demoScore,
    scoreRange: [],
    safety: isDemo ? demoFallbackSafety(spot) : unknownSafety(),
    safetyStatus: 'unknown',
    decision: 'unknown',
    confidence: null,
    coverage: null,
    dataState: isDemo ? 'demo' : (observation?.state ?? spot?.dataState ?? 'missing'),
    reasons: [],
    contributions: [],
    missingMetrics: [],
    staleMetrics: [],
    limitations: isDemo
      ? ['고정 데모 대체값이며 실시간 안전 판단이 아닙니다.']
      : [hasObservation
        ? '실관측 조건은 있지만 이 활동의 Water Index 평가가 없습니다.'
        : '이 활동의 Water Index 평가가 없습니다.'],
    methodologyVersion: isDemo ? 'demo-fixture' : '평가 없음',
    conditions: observation?.conditions ?? spot?.conditions ?? emptyConditions(),
    provenance: {
      provider: isDemo ? 'PongDang demo fixture' : (observation?.provider ?? '출처 없음'),
      spatialScope: observation?.spatialScope ?? spot?.name ?? '공간 범위 정보 없음',
      observedAt: observation?.observedAt ?? spot?.freshness?.observedAt ?? null,
      fetchedAt: observation?.fetchedAt ?? null,
      validUntil: observation?.validUntil ?? null,
      updatedLabel: isDemo
        ? (spot?.freshness?.updatedLabel ?? '고정 데모')
        : (observation?.updatedLabel ?? '관측 자료 없음'),
    },
    isDemoFallback: isDemo,
  };
}

export function isRecommendationEligible(view) {
  if (view.isDemoFallback) return view.score !== null;
  return view.safetyStatus === 'clear'
    && ['recommended', 'consider'].includes(view.decision)
    && view.score !== null
    && view.dataState === 'live';
}

export function scoreLabel(view) {
  if (view.score !== null) return String(Math.round(view.score));
  return '—';
}

export function formatMetricName(value) {
  const labels = {
    adult_supervision_status: '보호자 밀착 감독',
    designated_swim_zone_status: '지정 물놀이 구역',
    lightning_clearance_minutes: '번개 경과 시간',
    marine_hazard_status: '해상 특보',
    patrol_status: '안전요원',
    rip_current_risk: '이안류',
    water_quality_status: '수질',
    water_temperature_c: '수온',
    weather_alert_level: '기상 특보',
  };
  return labels[value] ?? String(value).replaceAll('_', ' ');
}
