import assert from 'node:assert/strict';
import test from 'node:test';

import {
  bestEligibleForecast,
  classifyDailyForecastError,
  normalizeDailyForecastResponse,
} from './dailyForecastApi.js';

const NOW = '2026-08-18T00:00:00Z';

function row(overrides = {}) {
  return {
    id: 9,
    spot: 3,
    spot_name: 'API Beach',
    forecast_date: '2026-08-18',
    activity: 'swim',
    participant_profile: 'general',
    participant_skill_level: 'unspecified',
    target_at: '2026-08-18T12:00:00+09:00',
    score: 87,
    suitability_score: 87,
    safety_status: 'clear',
    decision: 'recommended',
    confidence: 0.8,
    coverage: 0.9,
    score_range: [82, 90],
    gates: [],
    contributions: [],
    missing_metrics: [],
    stale_or_conflicting_metrics: [],
    limitations: [],
    availability: 'available',
    unavailable_reason: '',
    providers: ['KMA', 'KHOA'],
    evidence_issued_at: '2026-08-17T22:00:00Z',
    evidence_fetched_at: '2026-08-17T23:00:00Z',
    valid_from: '2026-08-17T23:00:00Z',
    valid_until: '2026-08-18T03:00:00Z',
    methodology_version: 'water-index-v1',
    projection_methodology_version: 'daily-v1',
    evaluated_at: '2026-08-17T23:10:00Z',
    computed_at: '2026-08-17T23:11:00Z',
    updated_at: '2026-08-17T23:11:00Z',
    evidence: [{
      metric_id: 11,
      name: 'air_temperature_c',
      provider: 'KMA',
      source: 'KMA',
      spatial_scope: 'kma-grid:92,132',
      source_url: 'https://weather.example.org/item?serviceKey=secret',
      fetched_at: '2026-08-17T23:00:00Z',
      valid_until: '2026-08-18T03:00:00Z',
    }],
    ...overrides,
  };
}

function response(rows = [row()]) {
  return {
    count: rows.length,
    spot: 3,
    spot_name: 'API Beach',
    activity: 'swim',
    participant_profile: 'general',
    participant_skill_level: 'unspecified',
    start_date: '2026-08-18',
    days: rows.length,
    reference_time: '12:00:00',
    methodology_version: 'water-index-v1',
    projection_methodology_version: 'daily-v1',
    results: rows,
  };
}

const request = {
  spot: 3,
  activity: 'swim',
  participantProfile: 'general',
  participantSkillLevel: 'unspecified',
  startDate: '2026-08-18',
  days: 1,
};

test('daily forecast normalization preserves exact provenance and current availability', () => {
  const normalized = normalizeDailyForecastResponse(response(), request, { now: NOW });
  const item = normalized.results[0];

  assert.equal(item.availability, 'available');
  assert.equal(item.evidenceCurrent, true);
  assert.equal(item.recommendationEligible, true);
  assert.deepEqual(item.providers, ['KMA', 'KHOA']);
  assert.equal(item.evidence[0].spatialScope, 'kma-grid:92,132');
  assert.equal(item.evidence[0].sourceUrl, 'https://weather.example.org/item');
});

test('UNKNOWN and null forecasts can never become a best day', () => {
  const unknown = row({
    id: null,
    score: null,
    suitability_score: null,
    score_range: [],
    safety_status: 'unknown',
    decision: 'unknown',
    confidence: 0,
    coverage: 0,
    availability: 'unavailable',
    unavailable_reason: 'PROVIDER_HORIZON_UNAVAILABLE',
    evidence_fetched_at: null,
    valid_until: '2026-08-18T03:00:00Z',
    evidence: [],
    providers: [],
  });
  const normalized = normalizeDailyForecastResponse(response([unknown]), request, { now: NOW });

  assert.equal(normalized.results[0].recommendationEligible, false);
  assert.equal(bestEligibleForecast(normalized.results), null);
});

test('SURF without an explicit skill is fail-closed even when a payload attempts a score', () => {
  const surfRequest = {
    ...request,
    activity: 'surf',
    participantSkillLevel: 'unspecified',
  };
  const surfUnknown = response([row({
    activity: 'surf',
    score: null,
    suitability_score: null,
    score_range: [],
    safety_status: 'unknown',
    decision: 'unknown',
    confidence: 0,
    coverage: 0,
    availability: 'unavailable',
    unavailable_reason: 'SURF_SKILL_LEVEL_REQUIRED',
    evidence_fetched_at: null,
    evidence: [],
    providers: [],
  })]);
  surfUnknown.activity = 'surf';
  const normalized = normalizeDailyForecastResponse(surfUnknown, surfRequest, { now: NOW });
  assert.equal(bestEligibleForecast(normalized.results), null);

  const unsafeAttempt = structuredClone(surfUnknown);
  Object.assign(unsafeAttempt.results[0], {
    score: 90,
    suitability_score: 90,
    safety_status: 'clear',
    decision: 'recommended',
  });
  assert.throws(() => normalizeDailyForecastResponse(unsafeAttempt, surfRequest, { now: NOW }), TypeError);

  const authoritativeStop = structuredClone(surfUnknown);
  Object.assign(authoritativeStop.results[0], {
    safety_status: 'stop',
    decision: 'blocked',
    availability: 'available',
    unavailable_reason: '',
    evidence_fetched_at: '2026-08-17T23:00:00Z',
    providers: ['KHOA'],
  });
  const stopped = normalizeDailyForecastResponse(authoritativeStop, surfRequest, { now: NOW });
  assert.equal(stopped.results[0].safetyStatus, 'stop');
  assert.equal(stopped.results[0].score, null);
  assert.equal(bestEligibleForecast(stopped.results), null);
});

test('expired provenance is not treated as current or recommendation eligible', () => {
  const normalized = normalizeDailyForecastResponse(
    response([row({ valid_until: '2026-08-17T23:59:59Z' })]),
    request,
    { now: NOW },
  );
  assert.equal(normalized.results[0].evidenceCurrent, false);
  assert.equal(bestEligibleForecast(normalized.results), null);
});

test('SURF skill mismatch suppresses suitability without erasing an authoritative hazard', () => {
  const surfRequest = {
    ...request,
    activity: 'surf',
    participantSkillLevel: 'beginner',
  };
  const hazard = response([row({
    activity: 'surf',
    participant_skill_level: 'beginner',
    score: null,
    suitability_score: null,
    score_range: [],
    safety_status: 'caution',
    decision: 'caution',
    availability: 'available',
    unavailable_reason: 'SURF_GRADE_SKILL_MISMATCH',
  })]);
  hazard.activity = 'surf';
  hazard.participant_skill_level = 'beginner';

  const normalized = normalizeDailyForecastResponse(hazard, surfRequest, { now: NOW });
  assert.equal(normalized.results[0].safetyStatus, 'caution');
  assert.equal(normalized.results[0].score, null);
  assert.equal(bestEligibleForecast(normalized.results), null);
});

test('daily response rows must match the requested spot, activity, profile, and date sequence', () => {
  assert.throws(() => normalizeDailyForecastResponse(
    response([row({ spot: 4 })]),
    request,
    { now: NOW },
  ), TypeError);
  assert.throws(() => normalizeDailyForecastResponse(
    response([
      row(),
      row({ id: 10, forecast_date: '2026-08-20' }),
    ]),
    { ...request, days: 2 },
    { now: NOW },
  ), TypeError);
  assert.throws(() => normalizeDailyForecastResponse(
    response([row({ safety_status: 'unknown' })]),
    request,
    { now: NOW },
  ), TypeError);
});

test('daily forecast errors are bounded and never expose backend details', () => {
  const classified = classifyDailyForecastError({
    response: { status: 500, data: { detail: 'secret provider response' } },
  });
  assert.equal(classified.messageKey, 'forecast.api.error.response');
  assert.equal(JSON.stringify(classified).includes('secret'), false);
});

test('family profile is bounded to SWIM requests', () => {
  const nonSwimFamily = response([row({ activity: 'relax', participant_profile: 'family' })]);
  nonSwimFamily.activity = 'relax';
  nonSwimFamily.participant_profile = 'family';
  assert.throws(() => normalizeDailyForecastResponse(nonSwimFamily, {
    ...request,
    activity: 'relax',
    participantProfile: 'family',
  }, { now: NOW }), TypeError);
});
