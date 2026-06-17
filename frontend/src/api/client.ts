const BASE = "http://localhost:8000/api";

export async function apiFetch<T>(
  path: string,
  opts?: { method?: string; body?: unknown },
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method:  opts?.method ?? "GET",
    headers: opts?.body ? { "Content-Type": "application/json" } : undefined,
    body:    opts?.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = `API error ${res.status}: ${path}`;
    try { const d = await res.json(); msg = d.detail ?? msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}
