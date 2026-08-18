import { csrfRequest, fetchApiCollection } from './accountApi.js';
import { normalizePublicHttpsUrl } from './livecamData.js';

function invalidResponse(message) {
  const error = new TypeError(message);
  error.code = 'INVALID_API_RESPONSE';
  return error;
}

function normalizeSpot(payload) {
  const id = Number(payload?.id);
  const name = typeof payload?.name === 'string' ? payload.name.trim() : '';
  if (!Number.isInteger(id) || id < 1 || !name) throw invalidResponse('Invalid memory spot');
  return {
    id,
    name,
    type: typeof payload.type === 'string' ? payload.type : '',
    region: typeof payload.region === 'string' ? payload.region : '',
  };
}

export function normalizeTripMemory(payload, { now = Date.now() } = {}) {
  const id = Number(payload?.id);
  const spotId = Number(payload?.spot);
  const spotDetail = normalizeSpot(payload?.spot_detail);
  const takenAt = typeof payload?.taken_at === 'string' && Number.isFinite(Date.parse(payload.taken_at))
    ? payload.taken_at
    : null;
  const location = typeof payload?.estimated_location === 'string'
    ? payload.estimated_location.trim()
    : '';
  const rawPhoto = typeof payload?.photo_url === 'string' ? payload.photo_url.trim() : '';
  const photoUrl = rawPhoto ? normalizePublicHttpsUrl(rawPhoto) : '';
  const nowMs = now instanceof Date
    ? now.getTime()
    : (typeof now === 'string' ? Date.parse(now) : Number(now));

  if (
    !Number.isInteger(id)
    || id < 1
    || !Number.isInteger(spotId)
    || spotId < 1
    || spotDetail.id !== spotId
    || !takenAt
    || !Number.isFinite(nowMs)
    || Date.parse(takenAt) > nowMs + 60_000
    || location.length > 200
    || [...location].some((character) => character.codePointAt(0) < 32)
    || (rawPhoto && !photoUrl)
  ) throw invalidResponse('Invalid trip memory response');

  return {
    id,
    spot: spotId,
    spot_detail: spotDetail,
    photo_url: photoUrl,
    taken_at: takenAt,
    estimated_location: location,
  };
}

export async function listTripMemories() {
  const items = await fetchApiCollection('content/memories/');
  return items.map((item) => normalizeTripMemory(item));
}

export async function createTripMemory(payload) {
  const response = await csrfRequest('post', 'content/memories/', payload);
  return normalizeTripMemory(response.data);
}

export async function updateTripMemory(id, payload) {
  const response = await csrfRequest(
    'patch',
    `content/memories/${encodeURIComponent(id)}/`,
    payload,
  );
  return normalizeTripMemory(response.data);
}

export async function deleteTripMemory(id) {
  await csrfRequest('delete', `content/memories/${encodeURIComponent(id)}/`);
}
