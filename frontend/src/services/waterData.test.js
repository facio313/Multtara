import assert from 'node:assert/strict';
import test from 'node:test';

import { mergeSpotsWithDemo, normalizeConditionScore } from './waterData.js';

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
