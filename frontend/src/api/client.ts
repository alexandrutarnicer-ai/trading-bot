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
    try {
      const d = await res.json();
      // detail poate fi text sau obiect {message, log_tail} (ex: /engines/{id}/start esuat)
      if (typeof d.detail === "string") msg = d.detail;
      else if (d.detail?.message) msg = [d.detail.message, ...(d.detail.log_tail ?? [])].join("\n");
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}
