/**
 * API helper — injects the Bearer token into every fetch call.
 */

let _token = (typeof localStorage !== 'undefined' ? localStorage.getItem('dashboard_token') : null) ?? '';
export function setToken(t: string) { _token = t; }
export function getToken(): string { return _token; }

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const t = token ?? _token;
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
      Authorization: `Bearer ${t}`,
    },
  });
  if (res.status === 401) {
    localStorage.removeItem('dashboard_token');
    window.location.reload();
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) {
    return res.json() as Promise<T>;
  }
  return res.text() as unknown as Promise<T>;
}
