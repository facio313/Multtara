import assert from 'node:assert/strict';
import test from 'node:test';

import {
  apiSpotRouteId,
  applyConditionScores,
  applyObservations,
  catalogMix,
  findSpotByRouteId,
  getSpotActivityView,
  isRecommendationEligible,
  mergeSpotsWithDemo,
  normalizeConditionScore,
} from './waterData.js';
import { API_SPOT_TYPES } from './spotTypes.js';

const now = Date.now();

function iso(offsetMilliseconds) {
  return new Date(now + offsetMilliseconds).toISOString();
}

function score(overrides = {}) {
  return {
    id: 1,
    spot: 4,
    activity: 'swim',
    suitability_score: 86,
    score_range: [80, 90],
    safety_status: 'clear',
    decision: 'recommended',
    confidence: 0.9,
    coverage: 0.95,
    methodology_version: 'water-index-v1.0.0',
    evaluated_at: iso(-30_000),
    gates: [],
    snapshot: {
      provider: 'PONGDANG_FUSION',
      state: 'live',
      observed_at: iso(-60_000),
      fetched_at: iso(-30_000),
      valid_from: iso(-60_000),
      valid_until: iso(60_000),
      metrics: [],
    },
    ...overrides,
  };
}

test('fresh clear evidence keeps a public suitability score', () => {
  const normalized = normalizeConditionScore(score());

  assert.equal(normalized.dataState, 'live');
  assert.equal(normalized.safetyStatus, 'clear');
  assert.equal(normalized.score, 86);
});

test('STOP always hides a conflicting numeric score', () => {
  const normalized = normalizeConditionScore(score({
    safety_status: 'stop',
    decision: 'blocked',
    suitability_score: 99,
  }));

  assert.equal(normalized.safetyStatus, 'stop');
  assert.equal(normalized.score, null);
});

test('UNKNOWN always hides a conflicting numeric score', () => {
  const normalized = normalizeConditionScore(score({
    safety_status: 'unknown',
    decision: 'unknown',
    suitability_score: 70,
  }));

  assert.equal(normalized.safetyStatus, 'unknown');
  assert.equal(normalized.score, null);
});

test('expired clear evidence becomes stale UNKNOWN', () => {
  const normalized = normalizeConditionScore(score({
    snapshot: {
      ...score().snapshot,
      valid_until: iso(-1_000),
    },
  }));

  assert.equal(normalized.dataState, 'stale');
  assert.equal(normalized.safetyStatus, 'unknown');
  assert.equal(normalized.score, null);
});

test('future evidence never becomes a current STOP or score', () => {
  const normalized = normalizeConditionScore(score({
    safety_status: 'stop',
    decision: 'blocked',
    snapshot: {
      ...score().snapshot,
      valid_from: iso(60_000),
      valid_until: iso(120_000),
    },
  }));

  assert.equal(normalized.dataState, 'missing');
  assert.equal(normalized.safetyStatus, 'unknown');
  assert.equal(normalized.score, null);
});

test('an empty API collection preserves explicitly labeled demo content', () => {
  const demo = [{
    id: 'demo-1',
    name: '데모 해변',
    type: 'sea',
    safety: { label: '데모 조건' },
  }];

  const [merged] = mergeSpotsWithDemo([], demo);

  assert.equal(merged.id, 'demo-1');
  assert.equal(merged.spotSource, 'demo');
  assert.equal(merged.dataState, 'demo');
  assert.equal(merged.safety.level, 'demo');
});

test('every backend WaterSpot type keeps its canonical frontend identity', () => {
  const apiSpots = API_SPOT_TYPES.map((type, index) => ({
    id: index + 1,
    type,
    name: `${type} destination`,
    region: 'Test region',
    address: 'Test address',
    lat: 37 + (index / 100),
    lng: 128 + (index / 100),
  }));

  const merged = mergeSpotsWithDemo(apiSpots, []);

  assert.deepEqual(merged.map((spot) => spot.type), API_SPOT_TYPES);
  assert.ok(merged.every((spot) => spot.typeLabel && spot.visual.icon));
  assert.deepEqual(
    merged.map((spot) => spot.id),
    apiSpots.map((spot) => apiSpotRouteId(spot.id)),
  );
});

test('API livecam verification fields are preserved without trusting DEMO URLs', () => {
  const [apiSpot] = mergeSpotsWithDemo([{
    id: 44,
    type: 'beach',
    name: '검증 해변',
    region: '강릉 · 강원',
    address: '강릉시',
    lat: 37.8,
    lng: 128.9,
    livecam_url: 'https://camera.example.com/live',
    catalog_verification: 'verified',
    catalog_verified_at: '2026-08-18T00:00:00Z',
  }], [{
    id: 4,
    type: 'beach',
    name: '검증 해변',
    officialUrl: 'https://fixture.example.com/not-trusted',
  }]);
  const [demoSpot] = mergeSpotsWithDemo([], [{
    id: 5,
    type: 'beach',
    name: '데모 해변',
    livecamUrl: 'https://fixture.example.com/not-trusted',
  }]);

  assert.equal(apiSpot.livecamUrl, 'https://camera.example.com/live');
  assert.equal(apiSpot.catalogVerification, 'verified');
  assert.equal(apiSpot.catalogVerifiedAt, '2026-08-18T00:00:00Z');
  assert.equal(demoSpot.livecamUrl, '');
  assert.equal(demoSpot.catalogVerification, 'demo');
});

test('legacy demo type aliases normalize to the backend beach and mudflat contract', () => {
  const merged = mergeSpotsWithDemo([], [
    { id: 1, type: 'sea', name: '해변 데모' },
    { id: 2, type: 'tidal_flat', name: '갯벌 데모' },
  ]);

  assert.deepEqual(merged.map((spot) => spot.type), ['beach', 'mudflat']);
  assert.deepEqual(merged.map((spot) => spot.typeLabel), ['해변', '갯벌']);
});

test('a partial live condition score never inherits missing fields or tide from DEMO', () => {
  const demo = [{
    id: 7,
    type: 'sea',
    name: '테스트해변',
    scores: { swim: 91 },
    conditions: {
      waterTemp: '24.2°C',
      airTemp: '28°C',
      waveHeight: '0.5m',
      windSpeed: '2.8m/s',
      waterQuality: '데모 1등급',
      crowd: '보통',
      tide: { low: '14:20', high: '20:35' },
    },
  }];
  const [merged] = mergeSpotsWithDemo([{
    id: 91,
    type: 'beach',
    name: '테스트해변',
    region: '강원',
    address: '강릉시',
    lat: 37.8,
    lng: 128.9,
  }], demo);
  const record = normalizeConditionScore(score({
    spot: 91,
    snapshot: {
      ...score().snapshot,
      provider: 'PONGDANG_FUSION',
      metrics: [{
        name: 'water_temperature_c',
        value: 20,
        unit: 'degC',
        state: 'valid',
      }],
    },
  }));

  const [withScore] = applyConditionScores([merged], [record]);
  const view = getSpotActivityView(withScore, 'swim');

  assert.equal(view.dataState, 'live');
  assert.equal(view.conditions.waterTemperatureC, 20);
  assert.equal(view.conditions.waterTemp, '20°C');
  assert.equal(view.conditions.airTemp, '자료 없음');
  assert.equal(view.conditions.waveHeight, '자료 없음');
  assert.equal(view.conditions.windSpeed, '자료 없음');
  assert.equal(view.conditions.waterQuality, '자료 없음');
  assert.equal(view.conditions.crowd, '자료 없음');
  assert.deepEqual(view.conditions.tide, { low: '—', high: '—' });
});

test('a live observation without an activity evaluation hides the DEMO score', () => {
  const [merged] = mergeSpotsWithDemo([{
    id: 92,
    type: 'beach',
    name: '관측해변',
    region: '강원',
    address: '강릉시',
    lat: 37.81,
    lng: 128.91,
  }], [{
    id: 8,
    type: 'sea',
    name: '관측해변',
    scores: { swim: 88 },
    conditions: {
      waterTemp: '25°C',
      airTemp: '29°C',
      waveHeight: '0.4m',
      windSpeed: '2m/s',
      waterQuality: '데모',
      crowd: '데모',
      tide: { low: '12:00', high: '18:00' },
    },
  }]);
  const observation = {
    state: 'live',
    provider: 'KMA',
    observedAt: iso(-60_000),
    fetchedAt: iso(-30_000),
    validUntil: iso(60_000),
    spatialScope: 'station:TEST',
    updatedLabel: '실데이터 · 방금',
    metrics: [{
      name: 'air_temperature_c',
      value: 21,
      unit: 'degC',
      state: 'valid',
    }],
  };

  const [withObservation] = applyObservations([merged], 92, [observation]);
  const view = getSpotActivityView(withObservation, 'swim');

  assert.equal(view.isDemoFallback, false);
  assert.equal(view.score, null);
  assert.equal(view.safetyStatus, 'unknown');
  assert.equal(view.dataState, 'live');
  assert.equal(view.provenance.provider, 'KMA');
  assert.equal(view.conditions.airTemp, '21°C');
  assert.equal(view.conditions.waterTemp, '자료 없음');
  assert.deepEqual(view.conditions.tide, { low: '—', high: '—' });
});

test('API-prefixed routes cannot collide with a numeric DEMO id', () => {
  const demo = { id: 2, slug: 'demo-two', apiId: null };
  const live = { id: 'api-2', slug: 'api-spot-2', apiId: 2 };
  const spots = [demo, live];

  assert.equal(findSpotByRouteId(spots, '2'), demo);
  assert.equal(findSpotByRouteId(spots, 'demo-two'), demo);
  assert.equal(findSpotByRouteId(spots, 'api-2'), live);
  assert.equal(findSpotByRouteId(spots, 'api-'), null);
  assert.equal(apiSpotRouteId(0), null);
  assert.equal(apiSpotRouteId('not-an-id'), null);
});

test('demo fallback scores are never recommendation-eligible', () => {
  assert.equal(isRecommendationEligible({
    isDemoFallback: true,
    score: 94,
    safetyStatus: 'clear',
    decision: 'recommended',
    dataState: 'demo',
  }), false);
});

test('live clear recommended scores remain eligible', () => {
  assert.equal(isRecommendationEligible({
    isDemoFallback: false,
    score: 88,
    safetyStatus: 'clear',
    decision: 'recommended',
    dataState: 'live',
  }), true);
  assert.equal(isRecommendationEligible({
    isDemoFallback: false,
    score: 88,
    safetyStatus: 'clear',
    decision: 'recommended',
    dataState: 'stale',
  }), false);
});

test('catalog mix labels demo-only, live-only, and mixed catalogs', () => {
  const demoSpot = {
    spotSource: 'demo',
    scores: { swim: 91 },
  };
  const liveSpot = {
    spotSource: 'api',
    apiId: 4,
    conditionRecords: {
      swim: {
        score: 80,
        scoreRange: [70, 90],
        safety: { level: 'clear' },
        safetyStatus: 'clear',
        decision: 'recommended',
        confidence: 0.9,
        coverage: 0.9,
        dataState: 'live',
        reasons: [],
        contributions: [],
        missingMetrics: [],
        staleMetrics: [],
        limitations: [],
        methodologyVersion: 'water-index-v1.0.0',
        metrics: [],
        provenance: {},
      },
    },
  };

  assert.equal(catalogMix([], 'swim'), 'ready');
  assert.equal(catalogMix([demoSpot], 'swim'), 'demo');
  assert.equal(catalogMix([liveSpot], 'swim'), 'live');
  assert.equal(catalogMix([demoSpot, liveSpot], 'swim'), 'mixed');
});
