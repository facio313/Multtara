import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildLivecamCards,
  normalizePublicHttpsUrl,
  toSafeLivecamEmbedUrl,
} from './livecamData.js';

test('public livecam URLs require credential-free HTTPS public destinations', () => {
  assert.equal(
    normalizePublicHttpsUrl('https://camera.example.com/live?token=secret#frame'),
    'https://camera.example.com/live',
  );
  assert.equal(normalizePublicHttpsUrl('http://camera.example.com/live'), null);
  assert.equal(normalizePublicHttpsUrl('https://user:pass@camera.example.com/live'), null);
  assert.equal(normalizePublicHttpsUrl('https://127.0.0.1/live'), null);
  assert.equal(normalizePublicHttpsUrl('https://10.0.0.8/live'), null);
  assert.equal(normalizePublicHttpsUrl('https://camera.internal/live'), null);
  assert.equal(normalizePublicHttpsUrl('https://camera.example.com:8443/live'), null);
  assert.equal(normalizePublicHttpsUrl('https://intranet/live'), null);
});

test('only known video providers receive a sandboxable embed URL', () => {
  assert.equal(
    toSafeLivecamEmbedUrl('https://youtu.be/abcDEF_1234'),
    'https://www.youtube-nocookie.com/embed/abcDEF_1234',
  );
  assert.equal(
    toSafeLivecamEmbedUrl('https://vimeo.com/123456789'),
    'https://player.vimeo.com/video/123456789',
  );
  assert.equal(toSafeLivecamEmbedUrl('https://youtube.com/arbitraryPath'), null);
  assert.equal(toSafeLivecamEmbedUrl('https://camera.example.com/live'), null);
});

test('a verified API spot exposes its public link without claiming stream health', () => {
  const [card] = buildLivecamCards([{
    id: 'api-4',
    spotSource: 'api',
    name: 'Verified beach',
    region: 'Gangneung',
    livecamUrl: 'https://youtu.be/abcDEF_1234',
    catalogVerification: 'verified',
    catalogVerifiedAt: '2026-08-18T00:00:00Z',
  }], []);

  assert.equal(card.availability, 'official');
  assert.equal(card.officialUrl, 'https://youtu.be/abcDEF_1234');
  assert.equal(card.embedUrl, 'https://www.youtube-nocookie.com/embed/abcDEF_1234');
  assert.equal(card.waterIndex, null);
  assert.deepEqual(card.conditions, {});
});

test('missing or partially verified API URLs remain UNKNOWN and unclickable', () => {
  const cards = buildLivecamCards([{
    id: 'api-5',
    spotSource: 'api',
    name: 'Missing camera',
    livecamId: 'fixture-five',
    catalogVerification: 'verified',
  }, {
    id: 'api-6',
    spotSource: 'api',
    name: 'Partial camera',
    livecamUrl: 'https://camera.example.com/live',
    catalogVerification: 'partial',
  }], [{
    id: 'fixture-five',
    spotId: 5,
    isLive: true,
    officialUrl: 'https://untrusted.example.com/live',
    poster: 'https://images.example.com/demo.jpg',
  }]);

  assert.deepEqual(cards.map((card) => card.availability), ['unknown', 'unknown']);
  assert.ok(cards.every((card) => card.officialUrl === null));
  assert.equal(cards[0].posterKind, 'demo');
});

test('DEMO fixture flags and URLs can never create an official card', () => {
  const [card] = buildLivecamCards([], [{
    id: 'demo-one',
    spotId: 1,
    name: 'Demo camera',
    isLive: true,
    status: 'LIVE',
    officialUrl: 'https://camera.example.com/live',
  }]);

  assert.equal(card.availability, 'demo');
  assert.equal(card.officialUrl, null);
  assert.equal(card.embedUrl, null);
});
