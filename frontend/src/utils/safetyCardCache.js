const PREFIX = 'pongdang.safety-cards.';

function keyFor(userId) {
  return `${PREFIX}${userId}`;
}

export function readSafetyCards(userId) {
  if (!userId) return [];
  try {
    const raw = window.localStorage.getItem(keyFor(userId));
    const rows = raw ? JSON.parse(raw) : [];
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

export function writeSafetyCards(userId, cards) {
  if (!userId) return;
  window.localStorage.setItem(keyFor(userId), JSON.stringify(cards || []));
}

export function upsertSafetyCard(userId, card) {
  if (!userId || !card) return [];
  const rest = readSafetyCards(userId).filter((row) => row.id !== card.id);
  const next = [card, ...rest];
  writeSafetyCards(userId, next);
  return next;
}

export function findSafetyCard(userId, cardId) {
  return readSafetyCards(userId).find((row) => String(row.id) === String(cardId)) || null;
}
