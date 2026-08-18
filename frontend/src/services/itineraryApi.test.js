import assert from 'node:assert/strict';
import test from 'node:test';

import {
  allowsItinerarySessionConfirmation,
  buildSavedItineraryUpdatePayload,
  classifyItineraryError,
  hasBlockingItineraryRevalidation,
  ITINERARY_TRANSITIONS,
  minuteToTime,
  normalizeItineraryPlan,
  normalizeSavedItinerary,
  normalizeItineraryStatus,
  requiresItineraryAdultSupervisionConfirmation,
  timeToMinute,
} from './itineraryApi.js';

test('time conversion honors the itinerary API minute boundaries', () => {
  assert.equal(timeToMinute('08:30'), 510);
  assert.equal(timeToMinute('24:00'), 1440);
  assert.equal(timeToMinute('24:01'), null);
  assert.equal(timeToMinute('bad'), null);
  assert.equal(minuteToTime(0), '00:00');
  assert.equal(minuteToTime(1440), '24:00');
  assert.equal(minuteToTime(1441), '--:--');
});

test('saved itinerary transitions mirror the backend state machine', () => {
  assert.deepEqual(ITINERARY_TRANSITIONS.draft, ['draft', 'accepted', 'cancelled']);
  assert.deepEqual(ITINERARY_TRANSITIONS.accepted, ['accepted', 'started', 'cancelled']);
  assert.deepEqual(ITINERARY_TRANSITIONS.started, ['started', 'completed', 'cancelled']);
  assert.deepEqual(ITINERARY_TRANSITIONS.completed, ['completed']);
  assert.deepEqual(ITINERARY_TRANSITIONS.cancelled, ['cancelled']);
  assert.equal(normalizeItineraryStatus('unknown-from-server'), 'draft');
});

test('missing route evidence has a dedicated safe error and hides backend detail', () => {
  const result = classifyItineraryError({
    response: {
      status: 409,
      data: {
        reason_code: 'NO_CURRENT_ROUTE_TO_END',
        detail: 'internal graph node identifiers',
      },
    },
  });

  assert.equal(result.kind, 'route-missing');
  assert.equal(result.messageKey, 'itinerary.error.routeMissing');
  assert.equal(JSON.stringify(result).includes('graph'), false);
});

test('itinerary errors use bounded public categories', () => {
  assert.equal(classifyItineraryError({ response: { status: 400 } }).kind, 'validation');
  assert.equal(classifyItineraryError({
    response: {
      status: 400,
      data: { status: [{ code: 'ITINERARY_REVALIDATION_REQUIRED', detail: 'internal' }] },
    },
  }).kind, 'revalidation');
  assert.equal(classifyItineraryError({ response: { status: 401 } }).kind, 'session');
  assert.equal(classifyItineraryError({ response: { status: 429 } }).kind, 'rate-limit');
  assert.equal(classifyItineraryError(new Error('offline')).kind, 'network');
});

test('a successful draft still requires current persisted route evidence', () => {
  const valid = normalizeItineraryPlan({
    status: 'draft',
    activity: 'relax',
    participant_profile: 'general',
    participant_skill_level: 'unspecified',
    start_spot: { id: 1, name: 'Start' },
    end_spot: { id: 2, name: 'End' },
    plan: {
      visits: [],
      skipped: [],
      total_cost_krw: 0,
      total_travel_minutes: 20,
      total_activity_minutes: 0,
      end_arrival_minute: 540,
    },
    route_evidence: {
      data_state: 'live',
      snapshot_ids: [4],
      valid_until: '2026-08-18T13:00:00Z',
    },
    water_evidence: [],
    safety_revalidation_required_at: '2026-08-18T12:30:00Z',
    execution_notice: 'Revalidate before departure.',
    saved_itinerary_id: null,
  });

  assert.deepEqual(valid.route_evidence.snapshot_ids, [4]);
  assert.throws(() => normalizeItineraryPlan({
    status: 'draft',
    activity: 'relax',
    participant_profile: 'general',
    participant_skill_level: 'unspecified',
    start_spot: { id: 1 },
    end_spot: { id: 2 },
    plan: { visits: [] },
    route_evidence: { data_state: 'missing', snapshot_ids: [] },
    water_evidence: [],
    safety_revalidation_required_at: '2026-08-18T12:30:00Z',
    execution_notice: 'Revalidate before departure.',
  }), TypeError);
});

test('saved itinerary records require a known backend state', () => {
  const record = {
    id: 2,
    status: 'accepted',
    activity: 'relax',
    participant_profile: 'general',
    participant_skill_level: 'unspecified',
    plan_date: '2026-08-18',
    start_minute: 480,
    end_minute: 720,
    start_spot_name: 'Start',
    end_spot_name: 'End',
    route_snapshot_ids: [7],
    route_evidence: {
      data_state: 'live',
      snapshot_ids: [7],
      providers: ['VALHALLA'],
      valid_until: '2026-08-18T13:00:00Z',
      source_urls: ['https://routing.example.org/route?secret=removed'],
      available_pairs: 3,
    },
    water_evidence: [],
    route_revalidation_required_at: '2026-08-18T13:00:00Z',
    safety_revalidation_required_at: '2026-08-18T12:30:00Z',
    evidence_status: {
      state: 'current',
      revalidation_required: false,
      reason_codes: [],
      checked_at: '2026-08-18T12:00:00Z',
    },
    execution_notice: 'Revalidate before departure.',
  };
  const normalized = normalizeSavedItinerary(record);
  assert.equal(normalized.status, 'accepted');
  assert.equal(normalized.evidenceStatus.revalidationRequired, false);
  assert.equal(normalized.routeEvidence.sourceUrls[0], 'https://routing.example.org/route');
  assert.throws(() => normalizeSavedItinerary({ ...record, status: 'invented' }), TypeError);
  assert.throws(() => normalizeSavedItinerary({
    ...record,
    route_evidence: { ...record.route_evidence, snapshot_ids: [8] },
  }), TypeError);
});

test('a current saved itinerary must cover every visit with bounded water evidence', () => {
  const record = {
    id: 8,
    title: 'Current draft',
    status: 'draft',
    activity: 'swim',
    participant_profile: 'general',
    participant_skill_level: 'beginner',
    plan_date: '2026-08-18',
    start_minute: 480,
    end_minute: 720,
    start_spot_name: 'Start',
    end_spot_name: 'End',
    schedule: { visits: [{ candidate_id: '3' }] },
    route_snapshot_ids: [7],
    route_evidence: {
      data_state: 'live', snapshot_ids: [7], valid_until: '2026-08-18T13:00:00Z',
    },
    water_evidence: [{
      spot_id: 3,
      condition_score_id: 9,
      snapshot_id: 10,
      participant_profile: 'general',
      participant_skill_level: 'beginner',
      condition_score_participant_skill_level: 'unspecified',
      safety_status: 'clear',
      decision: 'recommended',
      suitability_score: 82,
      confidence: 0.8,
      valid_until: '2026-08-18T12:30:00Z',
    }],
    route_revalidation_required_at: '2026-08-18T13:00:00Z',
    safety_revalidation_required_at: '2026-08-18T12:30:00Z',
    evidence_status: {
      state: 'current',
      revalidation_required: false,
      reason_codes: [],
      checked_at: '2026-08-18T12:00:00Z',
    },
  };

  assert.equal(normalizeSavedItinerary(record).waterEvidence[0].spotId, 3);
  assert.throws(() => normalizeSavedItinerary({
    ...record,
    water_evidence: [{ ...record.water_evidence[0], participant_profile: 'legacy' }],
  }), TypeError);
  assert.throws(() => normalizeSavedItinerary({
    ...record,
    water_evidence: [{ ...record.water_evidence[0], spot_id: 4 }],
  }), TypeError);
});

test('expired saved itineraries preserve bounded revalidation reasons and water evidence', () => {
  const record = {
    id: 5,
    title: 'Expired draft',
    status: 'draft',
    activity: 'swim',
    participant_profile: 'general',
    participant_skill_level: 'unspecified',
    plan_date: '2026-08-18',
    start_minute: 480,
    end_minute: 720,
    start_spot_name: 'Start',
    end_spot_name: 'End',
    schedule: { visits: [{ candidate_id: '3' }] },
    route_snapshot_ids: [7],
    route_evidence: {
      data_state: 'live', snapshot_ids: [7], providers: ['VALHALLA'], valid_until: '2026-08-18T11:59:00Z',
    },
    water_evidence: [{
      spot_id: 3,
      condition_score_id: 9,
      snapshot_id: 10,
      participant_profile: 'general',
      participant_skill_level: 'unspecified',
      condition_score_participant_skill_level: 'unspecified',
      safety_status: 'clear',
      decision: 'recommended',
      suitability_score: 82,
      confidence: 0.8,
      methodology_version: 'water-index-v1',
      evaluated_at: '2026-08-18T11:40:00Z',
      valid_until: '2026-08-18T11:59:00Z',
      sources: ['KHOA'],
      source_refs: [],
      session_context_reconfirmation_required: false,
    }],
    route_revalidation_required_at: '2026-08-18T11:59:00Z',
    safety_revalidation_required_at: '2026-08-18T11:59:00Z',
    evidence_status: {
      state: 'revalidation_required',
      revalidation_required: true,
      reason_codes: ['ROUTE_EVIDENCE_REVALIDATION_REQUIRED'],
      checked_at: '2026-08-18T12:00:00Z',
    },
    execution_notice: 'Revalidate.',
  };
  const normalized = normalizeSavedItinerary(record);
  assert.equal(normalized.evidenceStatus.revalidationRequired, true);
  assert.deepEqual(normalized.evidenceStatus.reasonCodes, ['ROUTE_EVIDENCE_REVALIDATION_REQUIRED']);
  assert.equal(normalized.waterEvidence[0].suitabilityScore, 82);

  const legacyWaterRow = { ...record.water_evidence[0] };
  delete legacyWaterRow.participant_skill_level;
  delete legacyWaterRow.condition_score_participant_skill_level;
  const legacy = normalizeSavedItinerary({ ...record, water_evidence: [legacyWaterRow] });
  assert.equal(legacy.waterEvidence[0].participantSkillLevel, null);
  assert.equal(legacy.waterEvidence[0].conditionScoreParticipantSkillLevel, null);

  const legacyItinerary = normalizeSavedItinerary({ ...record, activity: '' });
  assert.equal(legacyItinerary.activity, 'legacy');
  assert.equal(legacyItinerary.isLegacyActivity, true);
});

test('family swim session evidence requires a fresh write-only supervision confirmation', () => {
  const record = {
    id: 11,
    title: 'Family swim',
    status: 'draft',
    activity: 'swim',
    participant_profile: 'family',
    participant_skill_level: 'beginner',
    plan_date: '2026-08-18',
    start_minute: 480,
    end_minute: 720,
    start_spot_name: 'Start',
    end_spot_name: 'End',
    schedule: { visits: [{ candidate_id: '3' }] },
    route_snapshot_ids: [7],
    route_evidence: {
      data_state: 'live', snapshot_ids: [7], valid_until: '2026-08-18T13:00:00Z',
    },
    water_evidence: [{
      spot_id: 3,
      condition_score_id: 9,
      snapshot_id: 10,
      participant_profile: 'family',
      participant_skill_level: 'beginner',
      condition_score_participant_skill_level: 'unspecified',
      safety_status: 'clear',
      decision: 'recommended',
      suitability_score: 82,
      confidence: 0.8,
      valid_until: '2026-08-18T11:59:00Z',
      session_context_reconfirmation_required: true,
    }],
    route_revalidation_required_at: '2026-08-18T13:00:00Z',
    safety_revalidation_required_at: '2026-08-18T11:59:00Z',
    evidence_status: {
      state: 'revalidation_required',
      revalidation_required: true,
      reason_codes: [
        'SAFETY_EVIDENCE_REVALIDATION_REQUIRED',
        'ADULT_SUPERVISION_RECONFIRMATION_REQUIRED',
      ],
      checked_at: '2026-08-18T12:00:00Z',
    },
  };
  const item = normalizeSavedItinerary(record);
  assert.equal(requiresItineraryAdultSupervisionConfirmation(item), true);
  assert.equal(allowsItinerarySessionConfirmation(item), true);
  assert.equal(hasBlockingItineraryRevalidation(item), false);
  assert.equal(item.waterEvidence[0].conditionScoreParticipantSkillLevel, 'unspecified');
  assert.throws(() => buildSavedItineraryUpdatePayload(item, {
    title: 'Family swim',
    status: 'accepted',
  }), (error) => error.code === 'ADULT_SUPERVISION_CONFIRMATION_REQUIRED');
  assert.deepEqual(buildSavedItineraryUpdatePayload(item, {
    title: 'Family swim',
    status: 'accepted',
    adultSupervisionConfirmed: true,
  }), {
    title: 'Family swim',
    status: 'accepted',
    adult_supervision_confirmed: true,
  });

  const blocked = normalizeSavedItinerary({
    ...record,
    evidence_status: {
      ...record.evidence_status,
      reason_codes: [
        ...record.evidence_status.reason_codes,
        'ROUTE_EVIDENCE_REVALIDATION_REQUIRED',
      ],
    },
  });
  assert.equal(allowsItinerarySessionConfirmation(blocked), false);
  assert.equal(hasBlockingItineraryRevalidation(blocked), true);
  assert.throws(() => buildSavedItineraryUpdatePayload(blocked, {
    title: 'Blocked',
    status: 'accepted',
    adultSupervisionConfirmed: true,
  }), (error) => error.code === 'ITINERARY_REVALIDATION_REQUIRED');
});
