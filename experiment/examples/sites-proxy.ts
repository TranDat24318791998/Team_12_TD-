/** Server-side adapter only. Do not bundle VIDEO_API_TOKEN into browser JS.
 * Wire authenticatedUserId to Sites getChatGPTUser(), and derive owner on the server.
 * Never forward a browser-provided X-Owner-ID. No user means no access.
 */
export async function forwardVideoRequest(
  request: Request,
  apiPath: string,
  authenticatedUserId: string | null,
  env: { VIDEO_API_BASE_URL: string; VIDEO_API_TOKEN: string },
): Promise<Response> {
  if (!authenticatedUserId) return new Response('Unauthorized', { status: 401 });
  if (!/^\/v1\/(assets|images|image-jobs|image-styles|videos|jobs(?:\/[a-f0-9]{32})?|readiness)$/.test(apiPath)) {
    return new Response('Invalid endpoint', { status: 400 });
  }
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(authenticatedUserId));
  const owner = Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
  const headers = new Headers({ Authorization: `Bearer ${env.VIDEO_API_TOKEN}`, 'X-Owner-ID': owner });
  for (const name of ['content-type', 'content-length', 'idempotency-key']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const upstream = await fetch(env.VIDEO_API_BASE_URL.replace(/\/$/, '') + apiPath, {
    method: request.method,
    headers,
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
  });
  const resultHeaders = new Headers(upstream.headers);
  resultHeaders.set('Cache-Control', 'private, no-store');
  return new Response(upstream.body, { status: upstream.status, headers: resultHeaders });
}
