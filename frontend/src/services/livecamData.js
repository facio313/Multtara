const DEMO_AVAILABILITY = 'demo';
const OFFICIAL_AVAILABILITY = 'official';
const UNKNOWN_AVAILABILITY = 'unknown';

const asArray = (value) => (Array.isArray(value) ? value : []);

function isNonPublicIpv4(hostname) {
  if (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(hostname)) return false;
  const parts = hostname.split('.').map(Number);
  if (parts.some((part) => part < 0 || part > 255)) return true;
  const [first, second, third] = parts;
  return first === 0
    || first === 10
    || first === 127
    || first >= 224
    || (first === 100 && second >= 64 && second <= 127)
    || (first === 169 && second === 254)
    || (first === 172 && second >= 16 && second <= 31)
    || (first === 192 && second === 0)
    || (first === 192 && second === 168)
    || (first === 198 && [18, 19].includes(second))
    || (first === 198 && second === 51 && third === 100)
    || (first === 203 && second === 0 && third === 113);
}

function isNonPublicIpv6(hostname) {
  const canonical = hostname.replace(/^\[|\]$/g, '').toLowerCase();
  if (!canonical.includes(':')) return false;
  if (canonical === '::' || canonical === '::1') return true;
  if (/^(?:fc|fd|fe[89ab]|ff)/.test(canonical)) return true;
  const mappedIpv4 = canonical.match(/(?:^|:)ffff:(\d+(?:\.\d+){3})$/)?.[1];
  return mappedIpv4 ? isNonPublicIpv4(mappedIpv4) : false;
}

function isPublicHostname(hostname) {
  const canonical = hostname.replace(/^\[|\]$/g, '').replace(/\.$/, '').toLowerCase();
  if (!canonical) return false;
  if (
    canonical === 'localhost'
    || canonical.endsWith('.localhost')
    || canonical.endsWith('.local')
    || canonical.endsWith('.internal')
  ) return false;
  if (canonical.includes(':')) return !isNonPublicIpv6(canonical);
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(canonical)) return !isNonPublicIpv4(canonical);
  if (!canonical.includes('.')) return false;
  return !isNonPublicIpv4(canonical) && !isNonPublicIpv6(canonical);
}

export function normalizePublicHttpsUrl(value) {
  if (typeof value !== 'string' || !value.trim() || value.includes('\\')) return null;
  try {
    const parsed = new URL(value.trim());
    if (
      parsed.protocol !== 'https:'
      || parsed.username
      || parsed.password
      || (parsed.port && parsed.port !== '443')
      || !isPublicHostname(parsed.hostname)
    ) return null;
    parsed.search = '';
    parsed.hash = '';
    return parsed.href;
  } catch {
    return null;
  }
}

function safeVideoId(value) {
  return /^[a-zA-Z0-9_-]{6,128}$/.test(value ?? '') ? value : null;
}

export function toSafeLivecamEmbedUrl(value) {
  const normalized = normalizePublicHttpsUrl(value);
  if (!normalized) return null;
  const parsed = new URL(normalized);
  const hostname = parsed.hostname.toLowerCase();
  const parts = parsed.pathname.split('/').filter(Boolean);

  if (['youtu.be', 'www.youtu.be'].includes(hostname)) {
    const videoId = safeVideoId(parts[0]);
    return videoId ? `https://www.youtube-nocookie.com/embed/${videoId}` : null;
  }
  if (['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com'].includes(hostname)) {
    const markerIndex = parts.findIndex((part) => ['embed', 'live', 'shorts'].includes(part));
    if (markerIndex < 0) return null;
    const videoId = safeVideoId(parts[markerIndex + 1]);
    return videoId ? `https://www.youtube-nocookie.com/embed/${videoId}` : null;
  }
  if (['vimeo.com', 'www.vimeo.com'].includes(hostname)) {
    const videoId = /^\d+$/.test(parts[0] ?? '') ? parts[0] : null;
    return videoId ? `https://player.vimeo.com/video/${videoId}` : null;
  }
  if (hostname === 'player.vimeo.com' && parts[0] === 'video') {
    const videoId = /^\d+$/.test(parts[1] ?? '') ? parts[1] : null;
    return videoId ? `https://player.vimeo.com/video/${videoId}` : null;
  }
  return null;
}

function toScore(value) {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(100, Math.max(0, Math.round(parsed))) : null;
}

function demoForSpot(spot, demoCams) {
  return demoCams.find((cam) => (
    (spot?.livecamId && String(cam?.id) === String(spot.livecamId))
    || (spot?.id !== undefined && String(cam?.spotId) === String(spot.id))
  )) ?? null;
}

export function buildLivecamCards(spots, demoCams) {
  const spotList = asArray(spots);
  const fixtureList = asArray(demoCams);
  const cards = [];
  const consumedDemoIds = new Set();

  spotList.forEach((spot, index) => {
    const demoCam = demoForSpot(spot, fixtureList);
    const candidateUrl = normalizePublicHttpsUrl(spot?.livecamUrl ?? spot?.livecam_url);
    if (!demoCam && !candidateUrl) return;
    if (demoCam?.id !== undefined) consumedDemoIds.add(String(demoCam.id));

    const isApiSpot = spot?.spotSource === 'api';
    const isVerified = String(spot?.catalogVerification ?? spot?.catalog_verification)
      .toLowerCase() === 'verified';
    const officialUrl = isApiSpot && isVerified ? candidateUrl : null;
    const availability = isApiSpot
      ? (officialUrl ? OFFICIAL_AVAILABILITY : UNKNOWN_AVAILABILITY)
      : DEMO_AVAILABILITY;
    const demoMetrics = !isApiSpot;

    cards.push({
      id: String(demoCam?.id ?? `spot-livecam-${spot?.id ?? index}`),
      spot,
      name: String(spot?.name || demoCam?.name || ''),
      region: String(spot?.region || demoCam?.region || ''),
      tags: asArray(spot?.tags).length ? asArray(spot.tags) : asArray(demoCam?.tags),
      availability,
      officialUrl,
      embedUrl: officialUrl ? toSafeLivecamEmbedUrl(officialUrl) : null,
      poster: typeof demoCam?.poster === 'string' ? demoCam.poster : '',
      posterKind: demoCam?.poster ? 'demo' : 'missing',
      waterIndex: demoMetrics ? toScore(demoCam?.waterIndex ?? spot?.index) : null,
      conditions: demoMetrics ? (spot?.conditions ?? {}) : {},
      safety: demoMetrics ? (spot?.safety ?? null) : null,
      verifiedAt: isApiSpot ? (spot?.catalogVerifiedAt ?? spot?.catalog_verified_at ?? null) : null,
    });
  });

  fixtureList.forEach((demoCam, index) => {
    if (consumedDemoIds.has(String(demoCam?.id))) return;
    const spot = spotList.find((item) => String(item?.id) === String(demoCam?.spotId)) ?? null;
    cards.push({
      id: String(demoCam?.id ?? `demo-livecam-${index}`),
      spot,
      name: String(demoCam?.name || spot?.name || ''),
      region: String(demoCam?.region || spot?.region || ''),
      tags: asArray(demoCam?.tags),
      availability: DEMO_AVAILABILITY,
      officialUrl: null,
      embedUrl: null,
      poster: typeof demoCam?.poster === 'string' ? demoCam.poster : '',
      posterKind: demoCam?.poster ? 'demo' : 'missing',
      waterIndex: toScore(demoCam?.waterIndex ?? spot?.index),
      conditions: spot?.conditions ?? {},
      safety: spot?.safety ?? null,
      verifiedAt: null,
    });
  });

  return cards;
}
