/** Cloudflare Worker entry point used only by the private Sites deployment. */
export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const contentType = response.headers.get('content-type') ?? '';

    if (!contentType.includes('text/html')) return response;

    const origin = new URL(request.url).origin;
    const html = (await response.text()).replaceAll(
      'content="/og-pongdang.jpg"',
      `content="${origin}/og-pongdang.jpg"`,
    );
    const headers = new Headers(response.headers);
    headers.delete('content-length');

    return new Response(html, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
