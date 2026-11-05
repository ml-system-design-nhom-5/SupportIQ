const BACKEND = "https://supportiq-i9f8.onrender.com"\;

export async function onRequest({ request, params }) {
  const path = params.path ? params.path.join("/") : "";
  return fetch(`${BACKEND}/health/${path}`);
}
