import api from './api.js';
import { normalizePublicHttpsUrl } from './livecamData.js';

export const DAILY_FORECAST_ACTIVITIES = Object.freeze([
  'swim', 'surf', 'relax', 'mudflat', 'onsen', 'rafting',
]);
export const DAILY_FORECAST_PROFILES = Object.freeze(['general', 'family']);
export const DAILY_FORECAST_SKILL_LEVELS = Object.freeze([
  'unspecified', 'beginner', 'intermediate', 'advanced',
]);

const ACTIVITY_SET = new Set(DAILY_FORECAST_ACTIVITIES);
const PROFILE_SET = new Set(DAILY_FORECAST_PROFILES);
const SKILL_LEVEL_SET = new Set(DAILY_FORECAST_SKILL_LEVELS);
const SAFETY_SET = new Set(['clear', 'caution', 'stop', 'unknown']);
const DECISION_SET = new Set([
  'recommended', 'consider', 'caution', 'not_recommended', 'blocked', 'unknown',
]);
const AVAILABILITY_SET = new Set(['available', 'partial', 'unavailable']);
const SURF_SUITABILITY_REASONS = new Set([
  'SURF_SKILL_LEVEL_REQUIRED',
  'SURF_OFFICIAL_GRADE_MISSING',
  'SURF_GRADE_DETAIL_MISSING',
  'SURF_GRADE_EVIDENCE_NOT_AUTHORITATIVE',
  'SURF_GRADE_EVIDENCE_SCOPE_MISMATCH',
  'SURF_GRADE_DETAIL_UNSUPPORTED',
  'SURF_GRADE_SKILL_MISMATCH',
]);

function invalidResponse(message) {
  const error = new TypeError(message);
  error.code = 'INVALID_API_RESPONSE';
  return error;
}

function integer(value, { nullable = false } = {}) {
  if (nullable && (value === null || value === undefined)) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}

function numberInRange(value, minimum, maximum) {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum
    ? parsed
    : null;
}

function boundedString(value, maximum = 200) {
  return typeof value === 'string' ? value.trim().slice(0, maximum) : '';
}

function stringList(value, maximumItems = 50) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => boundedString(item))
    .filter(Boolean)
    .slice(0, maximumItems);
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return false;
  const timestamp = Date.parse(`${value}T12:00:00Z`);
  return Number.isFinite(timestamp)
    && new Date(timestamp).toISOString().slice(0, 10) === value;
}

function dateOffset(value, offset) {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

function validTimestamp(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function nullableTimestamp(value) {
  return validTimestamp(value) ? value : null;
}

function normalizeEvidence(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 100).flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    return [{
      metricId: integer(item.metric_id, { nullable: true }),
      name: boundedString(item.name),
      provider: boundedString(item.provider),
      source: boundedString(item.source),
      providerRecordId: boundedString(item.provider_record_id),
      ingestionVersion: boundedString(item.ingestion_version),
      spatialScope: boundedString(item.spatial_scope),
      sourceUrl: normalizePublicHttpsUrl(item.source_url) || '',
      issuedAt: nullableTimestamp(item.issued_at),
      fetchedAt: nullableTimestamp(item.fetched_at),
      validFrom: nullableTimestamp(item.valid_from),
      validUntil: nullableTimestamp(item.valid_until),
    }];
  });
}

function normalizeReasons(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 100).flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    const reasonCode = boundedString(item.reason_code);
    const metricName = boundedString(item.metric_name);
    if (!reasonCode && !metricName) return [];
    return [{
      reasonCode,
      metricName,
      severity: boundedString(item.severity),
      ruleId: boundedString(item.rule_id),
    }];
  });
}

function normalizeForecastRow(payload, expected, nowMs) {
  const id = integer(payload?.id, { nullable: true });
  const spot = integer(payload?.spot);
  const score = numberInRange(payload?.score, 0, 100, { nullable: true });
  const suitabilityScore = numberInRange(
    payload?.suitability_score,
    0,
    100,
    { nullable: true },
  );
  const confidence = numberInRange(payload?.confidence, 0, 1);
  const coverage = numberInRange(payload?.coverage, 0, 1);
  const safetyStatus = boundedString(payload?.safety_status).toLowerCase();
  const decision = boundedString(payload?.decision).toLowerCase();
  const availability = boundedString(payload?.availability).toLowerCase();
  const unavailableReason = boundedString(payload?.unavailable_reason);
  const surfSuitabilityUnresolved = expected.activity === 'surf'
    && SURF_SUITABILITY_REASONS.has(unavailableReason);
  const targetAt = nullableTimestamp(payload?.target_at);
  const contributionCount = Array.isArray(payload?.contributions)
    ? payload.contributions.length
    : null;
  const scoreRange = Array.isArray(payload?.score_range)
    && payload.score_range.every((value) => typeof value === 'number' && Number.isFinite(value))
    ? payload.score_range.slice(0, 3)
    : null;

  if (
    (id !== null && id < 1)
    || spot !== expected.spot
    || payload?.forecast_date !== expected.forecastDate
    || payload?.activity !== expected.activity
    || payload?.participant_profile !== expected.participantProfile
    || payload?.participant_skill_level !== expected.participantSkillLevel
    || !targetAt
    || score !== suitabilityScore
    || !SAFETY_SET.has(safetyStatus)
    || !DECISION_SET.has(decision)
    || !AVAILABILITY_SET.has(availability)
    || confidence === null
    || coverage === null
    || scoreRange === null
    || contributionCount === null
    || (score === null && scoreRange.length > 0)
    || (score !== null && (
      scoreRange.length !== 2
      || scoreRange[0] < 0
      || scoreRange[0] > score
      || scoreRange[1] < score
      || scoreRange[1] > 100
    ))
    || (['unknown', 'stop'].includes(safetyStatus) && score !== null)
    || (['recommended', 'consider', 'not_recommended'].includes(decision)
      && (safetyStatus !== 'clear' || score === null))
    || (decision === 'blocked' && safetyStatus !== 'stop')
    || (decision === 'unknown' && score !== null)
    || (availability !== 'available' && (
      safetyStatus !== 'unknown'
      || decision !== 'unknown'
      || score !== null
    ))
    || (surfSuitabilityUnresolved && (
      score !== null
      || scoreRange.length > 0
      || contributionCount > 0
      || !(
        (['clear', 'unknown'].includes(safetyStatus) && decision === 'unknown')
        || (safetyStatus === 'caution' && decision === 'caution')
        || (safetyStatus === 'stop' && decision === 'blocked')
      )
    ))
    || (expected.activity === 'surf'
      && expected.participantSkillLevel === 'unspecified'
      && (
        score !== null
        || !(
          (['clear', 'unknown'].includes(safetyStatus) && decision === 'unknown')
          || (safetyStatus === 'caution' && decision === 'caution')
          || (safetyStatus === 'stop' && decision === 'blocked')
        )
        || scoreRange.length > 0
      ))
  ) {
    throw invalidResponse('Invalid daily forecast row');
  }

  const evidenceFetchedAt = nullableTimestamp(payload?.evidence_fetched_at);
  const validUntil = nullableTimestamp(payload?.valid_until);
  const fetchedMs = evidenceFetchedAt ? Date.parse(evidenceFetchedAt) : null;
  const validUntilMs = validUntil ? Date.parse(validUntil) : null;
  const providers = stringList(payload?.providers, 20);
  const evidence = normalizeEvidence(payload?.evidence);
  const evidenceCurrent = availability !== 'unavailable'
    && fetchedMs !== null
    && validUntilMs !== null
    && fetchedMs <= nowMs
    && nowMs <= validUntilMs
    && providers.length > 0
    && evidence.length > 0;

  if (
    (availability === 'available' && unavailableReason && !(
      surfSuitabilityUnresolved && ['caution', 'stop'].includes(safetyStatus)
    ))
    || availability !== 'available' && !unavailableReason
    || availability !== 'available' && contributionCount > 0
  ) {
    throw invalidResponse('Invalid daily forecast availability');
  }

  return {
    id,
    spot,
    spotName: boundedString(payload?.spot_name) || expected.spotName,
    forecastDate: payload.forecast_date,
    activity: payload.activity,
    participantProfile: payload.participant_profile,
    participantSkillLevel: payload.participant_skill_level,
    targetAt,
    score,
    safetyStatus,
    decision,
    confidence,
    coverage,
    scoreRange,
    gates: normalizeReasons(payload?.gates),
    missingMetrics: stringList(payload?.missing_metrics),
    staleOrConflictingMetrics: stringList(payload?.stale_or_conflicting_metrics),
    limitations: stringList(payload?.limitations),
    availability,
    unavailableReason,
    providers,
    evidenceIssuedAt: nullableTimestamp(payload?.evidence_issued_at),
    evidenceFetchedAt,
    validFrom: nullableTimestamp(payload?.valid_from),
    validUntil,
    methodologyVersion: boundedString(payload?.methodology_version),
    projectionMethodologyVersion: boundedString(payload?.projection_methodology_version),
    evaluatedAt: nullableTimestamp(payload?.evaluated_at),
    computedAt: nullableTimestamp(payload?.computed_at),
    updatedAt: nullableTimestamp(payload?.updated_at),
    evidence,
    evidenceCurrent,
    recommendationEligible: evidenceCurrent
      && availability === 'available'
      && safetyStatus === 'clear'
      && decision === 'recommended'
      && score !== null,
  };
}

export function normalizeDailyForecastResponse(payload, request, { now = Date.now() } = {}) {
  const spot = integer(payload?.spot);
  const requestSpot = integer(request?.spot);
  const days = integer(payload?.days);
  const requestDays = integer(request?.days ?? 7);
  const count = integer(payload?.count);
  const activity = boundedString(payload?.activity).toLowerCase();
  const participantProfile = boundedString(payload?.participant_profile).toLowerCase();
  const participantSkillLevel = boundedString(payload?.participant_skill_level).toLowerCase();
  const startDate = String(payload?.start_date || '');
  const spotName = boundedString(payload?.spot_name);
  const results = Array.isArray(payload?.results) ? payload.results : null;

  if (
    requestSpot === null
    || requestSpot < 1
    || spot !== requestSpot
    || !ACTIVITY_SET.has(activity)
    || activity !== request?.activity
    || !PROFILE_SET.has(participantProfile)
    || participantProfile !== (request?.participantProfile ?? 'general')
    || (activity !== 'swim' && participantProfile !== 'general')
    || !SKILL_LEVEL_SET.has(participantSkillLevel)
    || participantSkillLevel !== (request?.participantSkillLevel ?? 'unspecified')
    || !validDate(startDate)
    || (request?.startDate && startDate !== request.startDate)
    || days === null
    || days < 1
    || days > 7
    || days !== requestDays
    || count !== days
    || !spotName
    || !results
    || results.length !== days
    || !/^\d{2}:\d{2}:\d{2}$/.test(String(payload?.reference_time || ''))
  ) {
    throw invalidResponse('Invalid daily forecast response');
  }

  const nowMs = now instanceof Date
    ? now.getTime()
    : (typeof now === 'string' ? Date.parse(now) : Number(now));
  if (!Number.isFinite(nowMs)) throw invalidResponse('Invalid forecast comparison time');

  const normalizedRows = results.map((row, index) => normalizeForecastRow(row, {
    spot,
    spotName,
    forecastDate: dateOffset(startDate, index),
    activity,
    participantProfile,
    participantSkillLevel,
  }, nowMs));

  return {
    spot,
    spotName,
    activity,
    participantProfile,
    participantSkillLevel,
    startDate,
    days,
    referenceTime: payload.reference_time,
    methodologyVersion: boundedString(payload?.methodology_version),
    projectionMethodologyVersion: boundedString(payload?.projection_methodology_version),
    results: normalizedRows,
  };
}

export function bestEligibleForecast(rows) {
  if (!Array.isArray(rows)) return null;
  return rows
    .filter((row) => row?.recommendationEligible && Number.isFinite(row.score))
    .sort((left, right) => right.score - left.score || left.forecastDate.localeCompare(right.forecastDate))[0]
    ?? null;
}

export function classifyDailyForecastError(error) {
  const status = Number.isInteger(error?.response?.status) ? error.response.status : null;
  if (error?.code === 'INVALID_API_RESPONSE') {
    return { kind: 'response', status: null, messageKey: 'forecast.api.error.response' };
  }
  if (status === 400) {
    return { kind: 'validation', status, messageKey: 'forecast.api.error.validation' };
  }
  if (status === 404) {
    return { kind: 'not-found', status, messageKey: 'forecast.api.error.notFound' };
  }
  if (status === 429) {
    return { kind: 'rate-limit', status, messageKey: 'forecast.api.error.rateLimit' };
  }
  if (status !== null) {
    return { kind: 'response', status, messageKey: 'forecast.api.error.response' };
  }
  return { kind: 'network', status: null, messageKey: 'forecast.api.error.network' };
}

export function isDailyForecastRequestCanceled(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError';
}

export async function getDailyForecast(request, options = {}) {
  const spot = integer(request?.spot);
  const activity = boundedString(request?.activity).toLowerCase();
  const participantProfile = boundedString(request?.participantProfile || 'general').toLowerCase();
  const participantSkillLevel = boundedString(
    request?.participantSkillLevel || 'unspecified',
  ).toLowerCase();
  const days = integer(request?.days ?? 7);
  if (
    spot === null
    || spot < 1
    || !ACTIVITY_SET.has(activity)
    || !PROFILE_SET.has(participantProfile)
    || (activity !== 'swim' && participantProfile !== 'general')
    || !SKILL_LEVEL_SET.has(participantSkillLevel)
    || (activity !== 'surf' && participantSkillLevel !== 'unspecified')
    || days === null
    || days < 1
    || days > 7
    || (request?.startDate && !validDate(request.startDate))
  ) throw new TypeError('Invalid daily forecast request');

  const normalizedRequest = {
    spot,
    activity,
    participantProfile,
    participantSkillLevel,
    days,
    ...(request.startDate ? { startDate: request.startDate } : {}),
  };
  const response = await api.get('forecasts/daily/', {
    ...options,
    params: {
      ...options.params,
      spot,
      activity,
      participant_profile: participantProfile,
      participant_skill_level: participantSkillLevel,
      days,
      ...(request.startDate ? { start_date: request.startDate } : {}),
    },
  });
  return normalizeDailyForecastResponse(response.data, normalizedRequest);
}
