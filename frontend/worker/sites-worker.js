import { spots } from '../src/data/pongdangData.js';

/** Cloudflare Worker entry point used only by the private Sites deployment. */

const ROOT_SOCIAL_IMAGE = '/og-pongdang.jpg';

function escapeAttribute(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function escapeText(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function escapePattern(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function replaceMeta(html, attribute, key, value) {
  const pattern = new RegExp(
    `<meta\\s+[^>]*${attribute}=["']${escapePattern(key)}["'][^>]*>`,
    'i',
  );
  return html.replace(pattern, (tag) => {
    const content = `content="${escapeAttribute(value)}"`;
    if (/content=["'][^"']*["']/i.test(tag)) {
      return tag.replace(/content=["'][^"']*["']/i, content);
    }
    return tag.replace(/\s*\/?\s*>$/, ` ${content} />`);
  });
}

function removeMeta(html, attribute, key) {
  const pattern = new RegExp(
    `\\s*<meta\\s+[^>]*${attribute}=["']${escapePattern(key)}["'][^>]*>`,
    'i',
  );
  return html.replace(pattern, '');
}

function replaceTitle(html, value) {
  return html.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeText(value)}</title>`);
}

function isLocalOrUnqualifiedHostname(hostname) {
  const canonical = hostname
    .replace(/^\[|\]$/g, '')
    .replace(/\.$/, '')
    .toLowerCase();

  if (
    canonical === 'localhost'
    || canonical === 'localhost.localdomain'
    || canonical.endsWith('.localhost')
    || canonical.endsWith('.local')
    || canonical.endsWith('.internal')
  ) {
    return true;
  }

  // Social images are curated DNS assets. Reject literal addresses and
  // single-label hosts instead of risking a private-network fetch by a crawler.
  return !canonical.includes('.') || canonical.includes(':') || /^\d+(?:\.\d+){3}$/.test(canonical);
}

export function publicImageUrl(value) {
  if (typeof value !== 'string' || !value.trim() || value.includes('\\')) return '';

  try {
    const url = new URL(value.trim());
    if (
      url.protocol !== 'https:'
      || !url.hostname
      || url.username
      || url.password
      || (url.port && url.port !== '443')
      || isLocalOrUnqualifiedHostname(url.hostname)
    ) {
      return '';
    }
    url.search = '';
    url.hash = '';
    return url.toString();
  } catch {
    return '';
  }
}

export function applyRouteMetadata(html, requestUrl) {
  const url = new URL(requestUrl);
  const rootImage = new URL(ROOT_SOCIAL_IMAGE, url.origin).toString();
  let result = replaceMeta(html, 'property', 'og:image', rootImage);
  result = replaceMeta(result, 'name', 'twitter:image', rootImage);

  const match = url.pathname.match(/^\/(?:spot|spots)\/(\d+)\/?$/);
  if (!match) return result;

  const spot = spots.find((item) => String(item.id) === match[1]);
  if (!spot) return result;

  const title = `${spot.name} · 퐁당 PongDang`;
  const description = spot.description || spot.summary;
  const image = publicImageUrl(spot.imageUrl || spot.image_url);

  result = replaceTitle(result, title);
  result = replaceMeta(result, 'name', 'description', description);
  result = replaceMeta(result, 'property', 'og:title', title);
  result = replaceMeta(result, 'property', 'og:description', description);
  result = replaceMeta(result, 'name', 'twitter:title', title);
  result = replaceMeta(result, 'name', 'twitter:description', description);
  result = replaceMeta(result, 'property', 'og:image:alt', `${spot.name} 여행지 미리보기`);
  result = removeMeta(result, 'property', 'og:image:width');
  result = removeMeta(result, 'property', 'og:image:height');
  if (image) {
    result = replaceMeta(result, 'property', 'og:image', image);
    result = replaceMeta(result, 'name', 'twitter:image', image);
  } else {
    result = removeMeta(result, 'property', 'og:image');
    result = removeMeta(result, 'property', 'og:image:alt');
    result = removeMeta(result, 'name', 'twitter:image');
  }
  return result;
}

export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const contentType = response.headers.get('content-type') ?? '';

    if (!contentType.includes('text/html')) return response;

    const html = applyRouteMetadata(await response.text(), request.url);
    const headers = new Headers(response.headers);
    headers.delete('content-length');
    headers.set('x-content-type-options', 'nosniff');
    headers.set('referrer-policy', 'strict-origin-when-cross-origin');
    headers.set('permissions-policy', 'camera=(), microphone=(), geolocation=(self)');
    headers.set('x-frame-options', 'DENY');

    return new Response(html, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
