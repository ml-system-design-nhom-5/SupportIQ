const BACKEND = "https://supportiq-i9f8.onrender.com";

export async function onRequest({ request, params }) {
  const path = params.path ? params.path.join("/") : "";
  const url = new URL(request.url);
  const target = `${BACKEND}/v1/${path}${url.search}`;
  const headers = new Headers(request.headers);
  headers.set("x-forwarded-host", url.hostname);
  return fetch(target, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
  });
}
