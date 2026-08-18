import api from './api.js';
import { csrfRequest, fetchApiCollection } from './accountApi.js';
import { normalizePublicHttpsUrl } from './livecamData.js';

const ITINERARY_STATUSES = new Set([
  'draft',
  'accepted',
  'started',
  'completed',
  'cancelled',
]);
const SAFETY_STATUSES = new Set(['clear', 'caution', 'stop', 'unknown']);
const DECISIONS = new Set([
  'recommended', 'consider', 'caution', 'not_recommended', 'blocked', 'unknown',
]);
const EVIDENCE_STATES = new Set(['current', 'revalidation_required']);
const PARTICIPANT_PROFILES = new Set(['general', 'family']);
const PARTICIPANT_SKILL_LEVELS = new Set([
  'unspecified', 'beginner', 'intermediate', 'advanced',
]);
const ITINERARY_ACTIVITIES = new Set([
  'swim', 'surf', 'relax', 'mudflat', 'onsen', 'rafting',
]);
const SESSION_CONFIRMATION_REASONS = new Set([
  'ADULT_SUPERVISION_RECONFIRMATION_REQUIRED',
  'SAFETY_EVIDENCE_REVALIDATION_REQUIRED',
]);

function invalidResponse(message) {
  const error = new TypeError(message);
  error.code = 'INVALID_API_RESPONSE';
  return error;
}

function validTimestamp(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function nullableTimestamp(value) {
  return validTimestamp(value) ? value : null;
}

function boundedString(value, maxLength = 200) {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
}

function stringList(value, maxItems = 50) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => boundedString(item)).filter(Boolean).slice(0, maxItems);
}

function positiveIds(value) {
  if (!Array.isArray(value)) return [];
  return value.map(Number).filter((id) => Number.isInteger(id) && id > 0);
}

function normalizeRouteEvidence(value) {
  const payload = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const snapshotIds = positiveIds(payload.snapshot_ids);
  const dataState = payload.data_state === 'live' && snapshotIds.length > 0 ? 'live' : 'missing';
  return {
    snapshotIds,
    providers: stringList(payload.providers, 20),
    validUntil: nullableTimestamp(payload.valid_until),
    sourceUrls: Array.isArray(payload.source_urls)
      ? payload.source_urls.map(normalizePublicHttpsUrl).filter(Boolean).slice(0, 20)
      : [],
    availablePairs: Number.isInteger(Number(payload.available_pairs))
      && Number(payload.available_pairs) >= 0
      ? Number(payload.available_pairs)
      : 0,
    dataState,
  };
}

function normalizeWaterSourceReference(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return {
    metricId: Number.isInteger(Number(value.metric_id)) && Number(value.metric_id) > 0
      ? Number(value.metric_id)
      : null,
    metricName: boundedString(value.metric_name),
    source: boundedString(value.source),
    sourceUrl: normalizePublicHttpsUrl(value.source_url) || '',
    spatialScope: boundedString(value.spatial_scope),
    observedAt: nullableTimestamp(value.observed_at),
    fetchedAt: nullableTimestamp(value.fetched_at),
    validUntil: nullableTimestamp(value.valid_until),
    persisted: value.persisted === true,
  };
}

function normalizeWaterEvidence(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 50).map((payload) => {
    const spotId = Number(payload?.spot_id);
    const safetyStatus = boundedString(payload?.safety_status).toLowerCase();
    const decision = boundedString(payload?.decision).toLowerCase();
    const score = payload?.suitability_score === null || payload?.suitability_score === undefined
      ? null
      : Number(payload.suitability_score);
    const confidence = Number(payload?.confidence);
    const participantProfile = boundedString(payload?.participant_profile).toLowerCase();
    const rawParticipantSkillLevel = payload?.participant_skill_level;
    const participantSkillLevel = rawParticipantSkillLevel === null
      || rawParticipantSkillLevel === undefined
      ? null
      : boundedString(rawParticipantSkillLevel).toLowerCase();
    const rawConditionSkillLevel = payload?.condition_score_participant_skill_level;
    const conditionScoreParticipantSkillLevel = rawConditionSkillLevel === null
      || rawConditionSkillLevel === undefined
      ? null
      : boundedString(rawConditionSkillLevel).toLowerCase();
    if (
      !Number.isInteger(spotId)
      || spotId < 1
      || !PARTICIPANT_PROFILES.has(participantProfile)
      || (participantSkillLevel !== null
        && !PARTICIPANT_SKILL_LEVELS.has(participantSkillLevel))
      || (conditionScoreParticipantSkillLevel !== null
        && !PARTICIPANT_SKILL_LEVELS.has(conditionScoreParticipantSkillLevel))
      || !SAFETY_STATUSES.has(safetyStatus)
      || !DECISIONS.has(decision)
      || (score !== null && (!Number.isFinite(score) || score < 0 || score > 100))
      || (['stop', 'unknown'].includes(safetyStatus) && score !== null)
      || !Number.isFinite(confidence)
      || confidence < 0
      || confidence > 1
    ) throw invalidResponse('Invalid saved itinerary water evidence');
    return {
      spotId,
      conditionScoreId: Number.isInteger(Number(payload.condition_score_id))
        && Number(payload.condition_score_id) > 0 ? Number(payload.condition_score_id) : null,
      snapshotId: Number.isInteger(Number(payload.snapshot_id))
        && Number(payload.snapshot_id) > 0 ? Number(payload.snapshot_id) : null,
      participantProfile,
      participantSkillLevel,
      conditionScoreParticipantSkillLevel,
      safetyStatus,
      decision,
      suitabilityScore: score,
      confidence,
      methodologyVersion: boundedString(payload.methodology_version),
      evaluatedAt: nullableTimestamp(payload.evaluated_at),
      validUntil: nullableTimestamp(payload.valid_until),
      sources: stringList(payload.sources, 20),
      sourceRefs: Array.isArray(payload.source_refs)
        ? payload.source_refs.map(normalizeWaterSourceReference).filter(Boolean).slice(0, 100)
        : [],
      sessionContextReconfirmationRequired: payload.session_context_reconfirmation_required === true,
    };
  });
}

function normalizeEvidenceStatus(value) {
  const state = boundedString(value?.state).toLowerCase();
  const revalidationRequired = value?.revalidation_required;
  const checkedAt = nullableTimestamp(value?.checked_at);
  const reasonCodes = stringList(value?.reason_codes, 20);
  if (
    !EVIDENCE_STATES.has(state)
    || typeof revalidationRequired !== 'boolean'
    || revalidationRequired !== (state === 'revalidation_required')
    || !checkedAt
    || (revalidationRequired && reasonCodes.length === 0)
    || (!revalidationRequired && reasonCodes.length > 0)
  ) throw invalidResponse('Invalid saved itinerary evidence status');
  return { state, revalidationRequired, reasonCodes, checkedAt };
}

export const ITINERARY_TRANSITIONS = Object.freeze({
  draft: Object.freeze(['draft', 'accepted', 'cancelled']),
  accepted: Object.freeze(['accepted', 'started', 'cancelled']),
  started: Object.freeze(['started', 'completed', 'cancelled']),
  completed: Object.freeze(['completed']),
  cancelled: Object.freeze(['cancelled']),
});

export function timeToMinute(value) {
  const match = /^(\d{2}):(\d{2})$/.exec(String(value || ''));
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 24 || minute > 59 || (hour === 24 && minute !== 0)) return null;
  return hour * 60 + minute;
}

export function minuteToTime(value) {
  const minute = Number(value);
  if (!Number.isInteger(minute) || minute < 0 || minute > 1440) return '--:--';
  const hours = Math.floor(minute / 60);
  const minutes = minute % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

export function normalizeItineraryStatus(value) {
  const status = String(value || '').toLowerCase();
  return ITINERARY_STATUSES.has(status) ? status : 'draft';
}

export function requiresItineraryAdultSupervisionConfirmation(item) {
  return item?.activity === 'swim'
    && item?.participantProfile === 'family'
    && Array.isArray(item?.waterEvidence)
    && item.waterEvidence.some((evidence) => (
      evidence?.sessionContextReconfirmationRequired === true
    ));
}

export function allowsItinerarySessionConfirmation(item) {
  const reasons = item?.evidenceStatus?.reasonCodes;
  return item?.evidenceStatus?.revalidationRequired === true
    && requiresItineraryAdultSupervisionConfirmation(item)
    && Array.isArray(reasons)
    && reasons.includes('ADULT_SUPERVISION_RECONFIRMATION_REQUIRED')
    && reasons.every((reason) => SESSION_CONFIRMATION_REASONS.has(reason));
}

export function hasBlockingItineraryRevalidation(item) {
  return item?.evidenceStatus?.revalidationRequired === true
    && !allowsItinerarySessionConfirmation(item);
}

export function buildSavedItineraryUpdatePayload(
  item,
  { title = '', status, adultSupervisionConfirmed = false } = {},
) {
  const currentStatus = normalizeItineraryStatus(item?.status);
  const nextStatus = boundedString(status || currentStatus).toLowerCase();
  const allowed = ITINERARY_TRANSITIONS[currentStatus] || [currentStatus];
  if (!allowed.includes(nextStatus)) throw new TypeError('Invalid itinerary status transition');

  const payload = { title: boundedString(title, 120) };
  if (nextStatus === currentStatus) return payload;

  const enteringExecutionState = ['accepted', 'started'].includes(nextStatus);
  if (enteringExecutionState && hasBlockingItineraryRevalidation(item)) {
    const error = new TypeError('Itinerary evidence requires revalidation');
    error.code = 'ITINERARY_REVALIDATION_REQUIRED';
    throw error;
  }
  if (enteringExecutionState && requiresItineraryAdultSupervisionConfirmation(item)) {
    if (adultSupervisionConfirmed !== true) {
      const error = new TypeError('Adult supervision must be confirmed');
      error.code = 'ADULT_SUPERVISION_CONFIRMATION_REQUIRED';
      throw error;
    }
    payload.adult_supervision_confirmed = true;
  }
  payload.status = nextStatus;
  return payload;
}

export function classifyItineraryError(error) {
  const status = Number.isInteger(error?.response?.status)
    ? error.response.status
    : null;
  const reasonCode = error?.response?.data?.reason_code;
  const responseText = (() => {
    try {
      return JSON.stringify(error?.response?.data ?? {});
    } catch {
      return '';
    }
  })();

  if (error?.code === 'ADULT_SUPERVISION_CONFIRMATION_REQUIRED') {
    return { kind: 'adult-supervision', status: null, messageKey: 'itinerary.error.adultSupervision' };
  }
  if (error?.code === 'ITINERARY_REVALIDATION_REQUIRED') {
    return { kind: 'revalidation', status: null, messageKey: 'itinerary.error.revalidation' };
  }
  if (error?.code === 'INVALID_API_RESPONSE') {
    return { kind: 'response', status: null, messageKey: 'itinerary.error.response' };
  }

  if (status === 409 && reasonCode === 'NO_CURRENT_ROUTE_TO_END') {
    return { kind: 'route-missing', status, messageKey: 'itinerary.error.routeMissing' };
  }
  if (status === 401 || status === 403) {
    return { kind: 'session', status, messageKey: 'itinerary.error.session' };
  }
  if (status === 400 && responseText.includes('ITINERARY_REVALIDATION_REQUIRED')) {
    return { kind: 'revalidation', status, messageKey: 'itinerary.error.revalidation' };
  }
  if (status === 400) {
    return { kind: 'validation', status, messageKey: 'itinerary.error.validation' };
  }
  if (status === 404) {
    return { kind: 'not-found', status, messageKey: 'itinerary.error.notFound' };
  }
  if (status === 429) {
    return { kind: 'rate-limit', status, messageKey: 'itinerary.error.rateLimit' };
  }
  if (status !== null) {
    return { kind: 'response', status, messageKey: 'itinerary.error.response' };
  }
  return { kind: 'network', status: null, messageKey: 'itinerary.error.network' };
}

export function normalizeItineraryPlan(payload) {
  const rawSnapshotIds = Array.isArray(payload?.route_evidence?.snapshot_ids)
    ? payload.route_evidence.snapshot_ids
    : [];
  const snapshotIds = rawSnapshotIds.map(Number)
    .filter((id) => Number.isInteger(id) && id > 0);
  const visits = Array.isArray(payload?.plan?.visits) ? payload.plan.visits : null;
  const activity = boundedString(payload?.activity).toLowerCase();
  const participantProfile = boundedString(payload?.participant_profile).toLowerCase();
  const participantSkillLevel = boundedString(payload?.participant_skill_level).toLowerCase();
  const routeEvidence = normalizeRouteEvidence(payload?.route_evidence);
  const waterEvidence = normalizeWaterEvidence(payload?.water_evidence);
  const safetyRevalidationRequiredAt = nullableTimestamp(
    payload?.safety_revalidation_required_at,
  );
  const executionNotice = boundedString(payload?.execution_notice, 1000);
  const validVisits = visits?.filter((visit) => {
    const arrival = Number(visit?.arrival_minute);
    const start = Number(visit?.start_minute);
    const end = Number(visit?.end_minute);
    return visit
      && typeof visit.candidate_id === 'string'
      && typeof visit.candidate_name === 'string'
      && visit.candidate_name.trim()
      && Number.isInteger(arrival)
      && Number.isInteger(start)
      && Number.isInteger(end)
      && arrival >= 0
      && arrival <= start
      && start < end
      && end <= 1440;
  }) ?? [];
  const startId = Number(payload?.start_spot?.id);
  const endId = Number(payload?.end_spot?.id);
  const totalCost = Number(payload?.plan?.total_cost_krw);
  const totalTravel = Number(payload?.plan?.total_travel_minutes);
  const totalActivity = Number(payload?.plan?.total_activity_minutes);
  const endArrival = Number(payload?.plan?.end_arrival_minute);
  const visitIds = new Set(validVisits.map((visit) => String(visit.candidate_id)));
  const waterEvidenceCoversVisits = visitIds.size === 0 || [...visitIds].every((visitId) => (
    waterEvidence.some((evidence) => String(evidence.spotId) === visitId)
  ));
  if (
    payload?.status !== 'draft'
    || !ITINERARY_ACTIVITIES.has(activity)
    || !PARTICIPANT_PROFILES.has(participantProfile)
    || !PARTICIPANT_SKILL_LEVELS.has(participantSkillLevel)
    || (participantProfile === 'family' && activity !== 'swim')
    || (!['swim', 'surf'].includes(activity) && participantSkillLevel !== 'unspecified')
    || routeEvidence.dataState !== 'live'
    || !routeEvidence.validUntil
    || snapshotIds.length === 0
    || snapshotIds.length !== rawSnapshotIds.length
    || !visits
    || validVisits.length !== visits.length
    || !Number.isInteger(startId)
    || startId < 1
    || !Number.isInteger(endId)
    || endId < 1
    || typeof payload?.start_spot?.name !== 'string'
    || !payload.start_spot.name.trim()
    || typeof payload?.end_spot?.name !== 'string'
    || !payload.end_spot.name.trim()
    || !Number.isFinite(totalCost)
    || totalCost < 0
    || !Number.isFinite(totalTravel)
    || totalTravel < 0
    || !Number.isFinite(totalActivity)
    || totalActivity < 0
    || !Number.isInteger(endArrival)
    || endArrival < 0
    || endArrival > 1440
    || !safetyRevalidationRequiredAt
    || !executionNotice
    || !waterEvidenceCoversVisits
    || waterEvidence.some((evidence) => (
      evidence.participantProfile !== participantProfile
      || evidence.participantSkillLevel !== participantSkillLevel
    ))
  ) {
    throw invalidResponse('Invalid itinerary plan response');
  }

  return {
    ...payload,
    activity,
    participant_profile: participantProfile,
    participant_skill_level: participantSkillLevel,
    start_spot: { ...payload.start_spot, id: startId },
    end_spot: { ...payload.end_spot, id: endId },
    plan: {
      ...payload.plan,
      visits: validVisits,
      skipped: Array.isArray(payload.plan.skipped) ? payload.plan.skipped : [],
    },
    route_evidence: {
      ...payload.route_evidence,
      snapshot_ids: snapshotIds,
      data_state: 'live',
    },
    routeEvidence,
    waterEvidence,
    safetyRevalidationRequiredAt,
    executionNotice,
    saved_itinerary_id: Number.isInteger(Number(payload.saved_itinerary_id))
      && Number(payload.saved_itinerary_id) > 0
      ? Number(payload.saved_itinerary_id)
      : null,
  };
}

export function normalizeSavedItinerary(payload) {
  const id = Number(payload?.id);
  const status = String(payload?.status || '').toLowerCase();
  const startMinute = Number(payload?.start_minute);
  const endMinute = Number(payload?.end_minute);
  const startName = typeof payload?.start_spot_name === 'string'
    ? payload.start_spot_name.trim()
    : '';
  const endName = typeof payload?.end_spot_name === 'string'
    ? payload.end_spot_name.trim()
    : '';
  const routeSnapshotIds = positiveIds(payload?.route_snapshot_ids);
  const activity = boundedString(payload?.activity).toLowerCase();
  const isLegacyActivity = activity === '';
  const participantProfile = boundedString(payload?.participant_profile).toLowerCase();
  const participantSkillLevel = boundedString(payload?.participant_skill_level).toLowerCase();
  const routeEvidence = normalizeRouteEvidence(payload?.route_evidence);
  const waterEvidence = normalizeWaterEvidence(payload?.water_evidence);
  const evidenceStatus = normalizeEvidenceStatus(payload?.evidence_status);
  const routeRevalidationRequiredAt = nullableTimestamp(payload?.route_revalidation_required_at);
  const safetyRevalidationRequiredAt = nullableTimestamp(payload?.safety_revalidation_required_at);
  const checkedAtMs = Date.parse(evidenceStatus.checkedAt);
  const visits = Array.isArray(payload?.schedule?.visits) ? payload.schedule.visits : [];
  const visitIds = new Set(visits.flatMap((visit) => {
    if (!visit || typeof visit !== 'object' || Array.isArray(visit)) return [];
    const candidateId = boundedString(visit.candidate_id, 80);
    return candidateId ? [candidateId] : [];
  }));
  const hasVisits = visits.length > 0;
  const routeIdsMatch = routeEvidence.snapshotIds.length === routeSnapshotIds.length
    && routeEvidence.snapshotIds.every((routeId, index) => routeId === routeSnapshotIds[index]);
  const currentWaterEvidenceCoversVisits = !hasVisits || (
    visitIds.size === visits.length
    && [...visitIds].every((visitId) => waterEvidence.some((evidence) => (
      String(evidence.spotId) === visitId
      && evidence.safetyStatus === 'clear'
      && evidence.conditionScoreId !== null
      && evidence.snapshotId !== null
    )))
  );
  if (
    !Number.isInteger(id)
    || id < 1
    || !ITINERARY_STATUSES.has(status)
    || (!ITINERARY_ACTIVITIES.has(activity) && !isLegacyActivity)
    || !PARTICIPANT_PROFILES.has(participantProfile)
    || !PARTICIPANT_SKILL_LEVELS.has(participantSkillLevel)
    || (participantProfile === 'family' && activity !== 'swim')
    || (!['swim', 'surf'].includes(activity) && participantSkillLevel !== 'unspecified')
    || !/^\d{4}-\d{2}-\d{2}$/.test(String(payload?.plan_date || ''))
    || !Number.isInteger(startMinute)
    || !Number.isInteger(endMinute)
    || startMinute < 0
    || startMinute >= endMinute
    || endMinute > 1440
    || routeSnapshotIds.length !== (Array.isArray(payload?.route_snapshot_ids)
      ? payload.route_snapshot_ids.length : 0)
    || (routeEvidence.dataState === 'live' && !routeIdsMatch)
    || (!evidenceStatus.revalidationRequired && (
      routeEvidence.dataState !== 'live'
      || !routeEvidence.validUntil
      || !routeRevalidationRequiredAt
      || Date.parse(routeRevalidationRequiredAt) <= checkedAtMs
      || !safetyRevalidationRequiredAt
      || Date.parse(safetyRevalidationRequiredAt) <= checkedAtMs
      || !currentWaterEvidenceCoversVisits
      || waterEvidence.some((evidence) => (
        evidence.participantProfile !== participantProfile
        || evidence.participantSkillLevel !== participantSkillLevel
      ))
    ))
  ) {
    throw invalidResponse('Invalid saved itinerary response');
  }
  return {
    ...payload,
    id,
    title: typeof payload.title === 'string' ? payload.title : '',
    status,
    activity: isLegacyActivity ? 'legacy' : activity,
    isLegacyActivity,
    participantProfile,
    participantSkillLevel,
    start_spot_name: startName,
    end_spot_name: endName,
    start_minute: startMinute,
    end_minute: endMinute,
    route_snapshot_ids: routeSnapshotIds,
    routeEvidence,
    waterEvidence,
    evidenceStatus,
    routeRevalidationRequiredAt,
    safetyRevalidationRequiredAt,
    executionNotice: boundedString(payload.execution_notice, 1000),
  };
}

export async function requestItineraryPlan(payload) {
  const response = await csrfRequest('post', 'trips/itineraries/plan/', payload);
  return normalizeItineraryPlan(response.data);
}

export async function listSavedItineraries() {
  const items = await fetchApiCollection('trips/itineraries/');
  return items.map(normalizeSavedItinerary);
}

export async function getSavedItinerary(id) {
  const response = await api.get(`trips/itineraries/${encodeURIComponent(id)}/`);
  return normalizeSavedItinerary(response.data);
}

export async function updateSavedItinerary(id, payload) {
  const response = await csrfRequest(
    'patch',
    `trips/itineraries/${encodeURIComponent(id)}/`,
    payload,
  );
  return normalizeSavedItinerary(response.data);
}

export async function deleteSavedItinerary(id) {
  await csrfRequest('delete', `trips/itineraries/${encodeURIComponent(id)}/`);
}
