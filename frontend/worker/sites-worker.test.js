import assert from 'node:assert/strict';
import test from 'node:test';

import worker, { applyRouteMetadata, publicImageUrl } from './sites-worker.js';

const document = `<!doctype html>
<html lang="ko">
  <head>
    <meta name="description" content="root description" />
    <meta property="og:title" content="root title" />
    <meta property="og:description" content="root description" />
    <meta property="og:image" content="/og-pongdang.jpg" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:image:alt" content="root image" />
    <meta name="twitter:title" content="root title" />
    <meta name="twitter:description" content="root description" />
    <meta name="twitter:image" content="/og-pongdang.jpg" />
    <title>root title</title>
  </head>
  <body><div id="root"></div></body>
</html>`;

test('root social images become absolute without changing root copy', () => {
  const html = applyRouteMetadata(document, 'https://pongdang.example/');

  assert.match(html, /content="https:\/\/pongdang\.example\/og-pongdang\.jpg"/);
  assert.match(html, /<title>root title<\/title>/);
});

test('known spot route uses that visible record for all share metadata', () => {
  const html = applyRouteMetadata(document, 'https://pongdang.example/spot/1');

  assert.match(html, /<title>안목해변 · 퐁당 PongDang<\/title>/);
  assert.match(html, /property="og:title" content="안목해변 · 퐁당 PongDang"/);
  assert.match(html, /name="twitter:title" content="안목해변 · 퐁당 PongDang"/);
  assert.match(html, /안목의 해변 산책과 카페거리 체류를 연결해/);
  assert.match(html, /images\.unsplash\.com\/photo-1507525428034-b723cf961d3e/);
  assert.doesNotMatch(html, /content="https:\/\/pongdang\.example\/og-pongdang\.jpg"/);
  assert.doesNotMatch(html, /og:image:(?:width|height)/);
});

test('plural spot alias receives the same detail metadata', () => {
  const html = applyRouteMetadata(document, 'https://pongdang.example/spots/3');

  assert.match(html, /<title>사천진해변 · 퐁당 PongDang<\/title>/);
  assert.match(html, /photo-1455729552865-3658a5d39692/);
});

test('worker preserves response status and headers while rewriting HTML only', async () => {
  const response = await worker.fetch(
    new Request('https://pongdang.example/spot/2'),
    {
      ASSETS: {
        fetch: async () => new Response(document, {
          status: 200,
          headers: {
            'content-type': 'text/html; charset=UTF-8',
            'x-origin-proof': 'asset',
          },
        }),
      },
    },
  );

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-origin-proof'), 'asset');
  assert.equal(response.headers.get('content-length'), null);
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('x-frame-options'), 'DENY');
  assert.match(await response.text(), /경포해변 · 퐁당 PongDang/);
});

test('worker serves the root SPA shell with route metadata for direct detail requests', async () => {
  const fetchedPaths = [];
  const response = await worker.fetch(
    new Request('https://pongdang.example/spot/2'),
    {
      ASSETS: {
        fetch: async (request) => {
          const pathname = new URL(request.url).pathname;
          fetchedPaths.push(pathname);
          if (pathname === '/') {
            return new Response(document, {
              status: 200,
              headers: { 'content-type': 'text/html; charset=UTF-8' },
            });
          }
          return new Response('missing', {
            status: 404,
            headers: { 'content-type': 'text/plain; charset=UTF-8' },
          });
        },
      },
    },
  );

  assert.equal(response.status, 200);
  assert.deepEqual(fetchedPaths, ['/spot/2', '/']);
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('referrer-policy'), 'strict-origin-when-cross-origin');
  assert.equal(response.headers.get('permissions-policy'), 'camera=(), microphone=(), geolocation=(self)');
  assert.equal(response.headers.get('x-frame-options'), 'DENY');
  assert.match(await response.text(), /<title>경포해변 · 퐁당 PongDang<\/title>/);
});

test('worker never turns missing API or static asset responses into the SPA shell', async () => {
  const excludedPaths = [
    '/api',
    '/api/v1/spots/',
    '/assets',
    '/assets/',
    '/assets/missing',
    '/assets/missing.js',
    '/assets/missing.abcdefghijklmn',
  ];

  for (const pathname of excludedPaths) {
    const fetchedPaths = [];
    const response = await worker.fetch(
      new Request(`https://pongdang.example${pathname}`),
      {
        ASSETS: {
          fetch: async (request) => {
            fetchedPaths.push(new URL(request.url).pathname);
            return new Response('missing', {
              status: 404,
              headers: { 'content-type': 'text/plain; charset=UTF-8' },
            });
          },
        },
      },
    );

    assert.equal(response.status, 404);
    assert.deepEqual(fetchedPaths, [pathname]);
    assert.equal(await response.text(), 'missing');
  }
});

test('unknown spot keeps site metadata and absolute root image', () => {
  const html = applyRouteMetadata(document, 'https://pongdang.example/spot/99999');

  assert.match(html, /<title>root title<\/title>/);
  assert.match(html, /content="https:\/\/pongdang\.example\/og-pongdang\.jpg"/);
});

test('social image projection removes credentials and rejects local destinations', () => {
  assert.equal(
    publicImageUrl('https://images.example.com/photo.jpg?token=secret#crop'),
    'https://images.example.com/photo.jpg',
  );
  assert.equal(publicImageUrl('https://user:secret@images.example.com/photo.jpg'), '');
  assert.equal(publicImageUrl('https://localhost/photo.jpg'), '');
  assert.equal(publicImageUrl('https://127.0.0.1/photo.jpg'), '');
  assert.equal(publicImageUrl('https://images.internal/photo.jpg'), '');
  assert.equal(publicImageUrl('https://images.example.com:8443/photo.jpg'), '');
  assert.equal(publicImageUrl('http://images.example.com/photo.jpg'), '');
});
