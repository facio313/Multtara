import api from './api.js';
import { normalizePublicHttpsUrl } from './livecamData.js';

const UI_TO_API_LOCALE = Object.freeze({
  ko: 'ko',
  en: 'en',
  ja: 'ja',
  zh: 'zh-hans',
});

const API_TO_UI_LOCALE = Object.freeze({
  ko: 'ko',
  en: 'en',
  ja: 'ja',
  'zh-hans': 'zh',
});

let csrfToken = '';

const PERSONA_TYPES = new Set(['', 'active', 'family', 'wellness', 'local', 'stay']);
const ACTIVITY_TYPES = new Set(['click', 'save', 'unsave', 'dismiss', 'visit', 'review', 'report']);
const PASSPORT_METHODS = new Set(['operator', 'qr', 'partner']);
const ECO_ACTION_TYPES = new Set(['cleanup', 'reusable', 'local', 'transit', 'safety_share']);
const VERIFICATION_STATES = new Set(['pending', 'verified', 'rejected']);

function invalidResponse(message) {
  const error = new TypeError(message);
  error.code = 'INVALID_API_RESPONSE';
  return error;
}

function validDateString(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function normalizeSpotReference(payload, { optional = false } = {}) {
  if (optional && (payload === null || payload === undefined)) return null;
  const id = Number(payload?.id);
  const name = typeof payload?.name === 'string' ? payload.name.trim() : '';
  if (!Number.isInteger(id) || id < 1 || !name) throw invalidResponse('Invalid spot reference');
  return {
    id,
    name,
    type: typeof payload.type === 'string' ? payload.type : '',
    region: typeof payload.region === 'string' ? payload.region : '',
  };
}

export function normalizeAccountUser(payload) {
  const id = Number(payload?.id);
  const username = typeof payload?.username === 'string' ? payload.username.trim() : '';
  if (!Number.isInteger(id) || id < 1 || !username) {
    throw invalidResponse('Invalid account response');
  }
  const stringField = (name) => (typeof payload[name] === 'string' ? payload[name] : '');
  const personaType = stringField('persona_type').toLowerCase();
  const preferredLocale = stringField('preferred_locale').toLowerCase();
  return {
    id,
    username,
    email: stringField('email'),
    first_name: stringField('first_name'),
    last_name: stringField('last_name'),
    persona_type: PERSONA_TYPES.has(personaType) ? personaType : '',
    mood_state: stringField('mood_state'),
    home_region: stringField('home_region'),
    preferred_locale: Object.hasOwn(API_TO_UI_LOCALE, preferredLocale) ? preferredLocale : 'ko',
    date_joined: typeof payload?.date_joined === 'string' ? payload.date_joined : null,
  };
}

export function normalizeActivity(payload, { allowLegacyAction = false } = {}) {
  const id = Number(payload?.id);
  const spotId = Number(payload?.spot);
  const spotDetail = normalizeSpotReference(payload?.spot_detail);
  const action = typeof payload?.action === 'string'
    ? payload.action.trim().toLowerCase()
    : '';
  const isLegacyAction = action.length > 0
    && action.length <= 100
    && ![...action].some((character) => character.codePointAt(0) < 32)
    && !ACTIVITY_TYPES.has(action);
  const rating = payload?.rating === null || payload?.rating === undefined
    ? null
    : Number(payload.rating);
  const reviewText = typeof payload?.review_text === 'string' ? payload.review_text : '';
  const validRating = rating === null || (Number.isInteger(rating) && rating >= 1 && rating <= 5);
  if (
    !Number.isInteger(id)
    || id < 1
    || !Number.isInteger(spotId)
    || spotId < 1
    || spotDetail.id !== spotId
    || (!ACTIVITY_TYPES.has(action) && !(allowLegacyAction && isLegacyAction))
    || (!isLegacyAction && !validRating)
    || !validDateString(payload?.created_at)
    || (!isLegacyAction && action === 'review' && rating === null && !reviewText.trim())
    || (!isLegacyAction && action !== 'review' && (rating !== null || reviewText))
  ) throw invalidResponse('Invalid activity response');
  return {
    id,
    spot: spotId,
    spot_detail: spotDetail,
    action: isLegacyAction ? 'legacy' : action,
    rating: isLegacyAction ? null : rating,
    review_text: isLegacyAction ? '' : reviewText,
    created_at: payload.created_at,
    is_legacy: isLegacyAction,
  };
}

export function normalizePassport(payload) {
  const id = Number(payload?.id);
  const method = String(payload?.verification_method || '').toLowerCase();
  if (
    !Number.isInteger(id)
    || id < 1
    || !PASSPORT_METHODS.has(method)
    || !validDateString(payload?.verified_at)
  ) throw invalidResponse('Invalid passport response');
  return {
    id,
    spot: normalizeSpotReference(payload.spot),
    verified_at: payload.verified_at,
    verification_method: method,
    verification_source: typeof payload.verification_source === 'string'
      ? payload.verification_source
      : '',
    evidence_url: normalizePublicHttpsUrl(payload.evidence_url) || '',
    badge_earned: payload.badge_earned && typeof payload.badge_earned === 'object'
      && !Array.isArray(payload.badge_earned)
      ? payload.badge_earned
      : {},
    eco_action: typeof payload.eco_action === 'string' ? payload.eco_action : '',
  };
}

export function normalizeEcoAction(payload) {
  const id = Number(payload?.id);
  const spotId = payload?.spot === null || payload?.spot === undefined
    ? null
    : Number(payload.spot);
  const spotDetail = normalizeSpotReference(payload?.spot_detail, { optional: true });
  const actionType = String(payload?.action_type || '').toLowerCase();
  const state = String(payload?.state || '').toLowerCase();
  if (
    !Number.isInteger(id)
    || id < 1
    || (spotId !== null && (!Number.isInteger(spotId) || spotId < 1))
    || (spotId === null) !== (spotDetail === null)
    || (spotId !== null && spotDetail?.id !== spotId)
    || !ECO_ACTION_TYPES.has(actionType)
    || !VERIFICATION_STATES.has(state)
    || !validDateString(payload?.occurred_on)
    || !validDateString(payload?.submitted_at)
    || (state === 'verified' && !validDateString(payload?.verified_at))
  ) throw invalidResponse('Invalid eco action response');
  return {
    id,
    spot: spotId,
    spot_detail: spotDetail,
    action_type: actionType,
    state,
    note: typeof payload.note === 'string' ? payload.note : '',
    evidence_url: normalizePublicHttpsUrl(payload.evidence_url) || '',
    occurred_on: payload.occurred_on,
    submitted_at: payload.submitted_at,
    verified_at: validDateString(payload.verified_at) ? payload.verified_at : null,
    verified_by: typeof payload.verified_by === 'string' ? payload.verified_by : null,
  };
}

export function uiLocaleToAccountLocale(locale) {
  return UI_TO_API_LOCALE[String(locale || '').toLowerCase()] || 'ko';
}

export function accountLocaleToUiLocale(locale) {
  return API_TO_UI_LOCALE[String(locale || '').toLowerCase()] || 'ko';
}

export function invalidateCsrfToken() {
  csrfToken = '';
}

export function isMissingSession(error) {
  return [401, 403].includes(error?.response?.status);
}

export function classifyAccountError(error, operation = 'account') {
  const status = Number.isInteger(error?.response?.status)
    ? error.response.status
    : null;
  const fields = error?.response?.data && typeof error.response.data === 'object'
    ? Object.keys(error.response.data)
    : [];

  if (error?.code === 'INVALID_API_RESPONSE') {
    return { kind: 'response', status: null, messageKey: 'account.error.response' };
  }

  if (status === 429) {
    return { kind: 'rate-limit', status, messageKey: 'account.error.rateLimit' };
  }
  if (operation === 'login' && [400, 401, 403].includes(status)) {
    return { kind: 'credentials', status, messageKey: 'account.error.credentials' };
  }
  if (operation === 'register' && fields.includes('username')) {
    return { kind: 'username', status, messageKey: 'account.error.username' };
  }
  if (['register', 'password'].includes(operation)
    && (fields.includes('password') || fields.includes('new_password'))) {
    return { kind: 'password-policy', status, messageKey: 'account.error.passwordPolicy' };
  }
  if (['password', 'delete'].includes(operation) && fields.includes('current_password')) {
    return { kind: 'current-password', status, messageKey: 'account.error.currentPassword' };
  }
  if (status === 400) {
    return { kind: 'validation', status, messageKey: 'account.error.validation' };
  }
  if ([401, 403].includes(status)) {
    return { kind: 'session', status, messageKey: 'account.error.session' };
  }
  if (status !== null) {
    return { kind: 'response', status, messageKey: 'account.error.response' };
  }
  return { kind: 'network', status: null, messageKey: 'account.error.network' };
}

export async function ensureCsrfToken({ force = false } = {}) {
  if (csrfToken && !force) return csrfToken;
  const response = await api.get('users/csrf/');
  const token = typeof response.data?.csrf_token === 'string'
    ? response.data.csrf_token.trim()
    : '';
  if (!token || token.length > 256) throw invalidResponse('CSRF token unavailable');
  csrfToken = token;
  return csrfToken;
}

export async function csrfRequest(method, url, data, options = {}) {
  const request = async (force = false) => {
    const token = await ensureCsrfToken({ force });
    return api.request({
      ...options,
      method,
      url,
      data,
      headers: {
        ...options.headers,
        'X-CSRFToken': token,
      },
    });
  };

  try {
    return await request(false);
  } catch (error) {
    if (error?.response?.status !== 403) throw error;
    return request(true);
  }
}

function collectionItems(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

export async function fetchApiCollection(path, { maxPages = 20 } = {}) {
  const items = [];
  let next = path;
  let pages = 0;

  while (next && pages < maxPages) {
    const response = await api.get(next);
    items.push(...collectionItems(response.data));
    next = typeof response.data?.next === 'string' && response.data.next.trim()
      ? response.data.next
      : null;
    pages += 1;
  }
  if (next) throw invalidResponse('Collection page limit exceeded');
  return items;
}

export async function getCurrentUser() {
  const response = await api.get('users/me/');
  return normalizeAccountUser(response.data);
}

export async function registerAccount(payload) {
  const response = await csrfRequest('post', 'users/register/', payload);
  invalidateCsrfToken();
  return normalizeAccountUser(response.data);
}

export async function loginAccount(payload) {
  const response = await csrfRequest('post', 'users/login/', payload);
  invalidateCsrfToken();
  return normalizeAccountUser(response.data);
}

export async function logoutAccount() {
  await csrfRequest('post', 'users/logout/');
  invalidateCsrfToken();
}

export async function updateAccount(payload) {
  const response = await csrfRequest('patch', 'users/me/', payload);
  return normalizeAccountUser(response.data);
}

export async function changeAccountPassword(payload) {
  await csrfRequest('post', 'users/password/', payload);
  invalidateCsrfToken();
}

export async function deleteAccount(payload) {
  await csrfRequest('delete', 'users/me/', payload);
  invalidateCsrfToken();
}

export async function listActivities() {
  const items = await fetchApiCollection('users/activities/');
  return items.map((item) => normalizeActivity(item, { allowLegacyAction: true }));
}

export async function createActivity(payload) {
  const response = await csrfRequest('post', 'users/activities/', payload);
  return normalizeActivity(response.data);
}

export async function listPassports() {
  const items = await fetchApiCollection('users/passports/');
  return items.map(normalizePassport);
}

export async function listEcoActions() {
  const items = await fetchApiCollection('users/eco-actions/');
  return items.map(normalizeEcoAction);
}

export async function createEcoAction(payload) {
  const response = await csrfRequest('post', 'users/eco-actions/', payload);
  return normalizeEcoAction(response.data);
}
