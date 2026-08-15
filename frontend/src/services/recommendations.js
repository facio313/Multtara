import api from './api.js';

const PARTICIPANT_SKILL_LEVELS = new Set(['beginner', 'intermediate', 'advanced', 'unspecified']);

export function requiresAdultSupervision(form, ages) {
  const hasMinor = Array.isArray(ages)
    && ages.some((age) => Number.isInteger(age) && age >= 0 && age < 18);
  const isBeginnerSwim = form?.activity === 'swim'
    && form?.participantSkillLevel === 'beginner';

  return hasMinor || isBeginnerSwim;
}

export function buildRecommendationPayload(form, ages, personaLabel = '') {
  const participantSkillLevel = ['surf', 'swim'].includes(form.activity)
    && PARTICIPANT_SKILL_LEVELS.has(form.participantSkillLevel)
    ? form.participantSkillLevel
    : 'unspecified';
  const adultSupervisionConfirmed = requiresAdultSupervision(form, ages)
    && typeof form.adultSupervisionConfirmed === 'boolean'
    ? form.adultSupervisionConfirmed
    : null;

  return {
    activity: form.activity,
    preferences: [
      { feature: 'quiet', target: form.quiet / 100, weight: 0.45 },
      { feature: 'activity_level', target: form.activityLevel / 100, weight: 0.35 },
      { feature: 'water_suitability', target: 1, weight: 0.2 },
    ],
    party: {
      ages,
      requires_accessibility: form.requiresAccessibility,
      bringing_pet: form.bringingPet,
      adult_supervision_confirmed: adultSupervisionConfirmed,
      participant_skill_level: participantSkillLevel,
    },
    persona_label: personaLabel,
    limit: 6,
  };
}

export async function requestRecommendations(payload, { signal } = {}) {
  const response = await api.post('trips/recommendations/', payload, { signal });
  return response.data;
}

export function isRecommendationRequestCanceled(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError';
}

export function getRecommendationError(error) {
  const status = Number.isInteger(error?.response?.status)
    ? error.response.status
    : null;

  if (status === 400) {
    return {
      kind: 'validation',
      status,
      messageKey: 'concierge.error.validation',
      message: '추천 조건을 처리하지 못했어요. 입력값을 확인한 뒤 다시 시도해 주세요.',
    };
  }

  if (status === 429) {
    return {
      kind: 'rate-limit',
      status,
      messageKey: 'concierge.error.rateLimit',
      message: '요청이 잠시 몰렸어요. 잠깐 뒤 다시 시도해 주세요.',
    };
  }

  if (status !== null) {
    return {
      kind: 'response',
      status,
      messageKey: 'concierge.error.response',
      message: '실시간 추천 서버가 응답하지 못했어요. 잠시 뒤 다시 확인해 주세요.',
    };
  }

  return {
    kind: 'network',
    status: null,
    messageKey: 'concierge.error.network',
    message: '실시간 추천 서버에 연결할 수 없어요. 네트워크 상태를 확인해 주세요.',
  };
}
