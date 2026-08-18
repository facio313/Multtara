import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildRecommendationPayload,
  getRecommendationError,
  isRecommendationRequestCanceled,
  requiresAdultSupervision,
} from './recommendations.js';

test('recommendation errors never expose backend response text', () => {
  const error = {
    response: {
      status: 500,
      data: { detail: 'private database hostname' },
    },
  };

  const result = getRecommendationError(error);

  assert.equal(result.kind, 'response');
  assert.equal(result.status, 500);
  assert.doesNotMatch(result.message, /private|database|hostname/i);
});

test('validation and rate-limit failures use bounded public messages', () => {
  assert.equal(
    getRecommendationError({ response: { status: 400 } }).kind,
    'validation',
  );
  assert.equal(
    getRecommendationError({ response: { status: 429 } }).kind,
    'rate-limit',
  );
});

test('request cancellation is distinguished from an availability failure', () => {
  assert.equal(isRecommendationRequestCanceled({ code: 'ERR_CANCELED' }), true);
  assert.equal(isRecommendationRequestCanceled({ name: 'CanceledError' }), true);
  assert.equal(isRecommendationRequestCanceled(new Error('network')), false);
});

test('recommendation payload forwards explicit participant skill for surf and swim only', () => {
  const baseForm = {
    activity: 'surf',
    quiet: 50,
    activityLevel: 70,
    requiresAccessibility: false,
    bringingPet: false,
    adultSupervisionConfirmed: null,
    participantSkillLevel: 'intermediate',
  };

  assert.equal(
    buildRecommendationPayload(baseForm, [28], 'Active Wave').party.participant_skill_level,
    'intermediate',
  );
  assert.equal(
    buildRecommendationPayload({ ...baseForm, activity: 'swim', participantSkillLevel: 'beginner' }, [8, 38]).party.participant_skill_level,
    'beginner',
  );
  assert.equal(
    buildRecommendationPayload({ ...baseForm, activity: 'onsen', participantSkillLevel: 'advanced' }, [28]).party.participant_skill_level,
    'unspecified',
  );
  assert.equal(
    buildRecommendationPayload({ ...baseForm, participantSkillLevel: 'expert' }, [28]).party.participant_skill_level,
    'unspecified',
  );
});

test('adult supervision is requested for minors or beginner swimmers', () => {
  const baseForm = {
    activity: 'relax',
    participantSkillLevel: 'unspecified',
  };

  assert.equal(requiresAdultSupervision(baseForm, [17, 40]), true);
  assert.equal(
    requiresAdultSupervision({ ...baseForm, activity: 'swim', participantSkillLevel: 'beginner' }, [30]),
    true,
  );
  assert.equal(
    requiresAdultSupervision({ ...baseForm, activity: 'swim', participantSkillLevel: 'intermediate' }, [30]),
    false,
  );
});

test('recommendation payload preserves explicit supervision yes/no and unresolved null', () => {
  const baseForm = {
    activity: 'swim',
    quiet: 50,
    activityLevel: 40,
    requiresAccessibility: false,
    bringingPet: false,
    participantSkillLevel: 'beginner',
    adultSupervisionConfirmed: null,
  };

  assert.equal(
    buildRecommendationPayload(baseForm, [30]).party.adult_supervision_confirmed,
    null,
  );
  assert.equal(
    buildRecommendationPayload({ ...baseForm, adultSupervisionConfirmed: true }, [30]).party.adult_supervision_confirmed,
    true,
  );
  assert.equal(
    buildRecommendationPayload({ ...baseForm, adultSupervisionConfirmed: false }, [30]).party.adult_supervision_confirmed,
    false,
  );
  assert.equal(
    buildRecommendationPayload({ ...baseForm, activity: 'relax', adultSupervisionConfirmed: true }, [30]).party.adult_supervision_confirmed,
    null,
  );
});

test('recommendation payload sends a trimmed bounded region and canonical spot type', () => {
  const form = {
    activity: 'surf',
    region: '  강원  ',
    spotType: 'sea',
    quiet: 50,
    activityLevel: 70,
    requiresAccessibility: false,
    bringingPet: false,
    adultSupervisionConfirmed: null,
    participantSkillLevel: 'intermediate',
  };

  const payload = buildRecommendationPayload(form, [28]);

  assert.equal(payload.region, '강원');
  assert.equal(payload.spot_type, 'beach');
});

test('empty region and activity-incompatible spot type are not sent', () => {
  const form = {
    activity: 'onsen',
    region: '   ',
    spotType: 'beach',
    quiet: 80,
    activityLevel: 10,
    requiresAccessibility: false,
    bringingPet: false,
    adultSupervisionConfirmed: null,
    participantSkillLevel: 'unspecified',
  };

  const payload = buildRecommendationPayload(form, [40]);

  assert.equal(Object.hasOwn(payload, 'region'), false);
  assert.equal(Object.hasOwn(payload, 'spot_type'), false);
});
