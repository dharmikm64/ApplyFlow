// Typed fetch client. Same-origin cookies; CSRF header on every mutating request.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export async function api<T>(method: Method, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const res = await fetch(url, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = (data ?? {}) as { error?: string; message?: string };
    throw new ApiError(res.status, err.error ?? "http_error", err.message ?? "Request failed.");
  }
  return data as T;
}

export const get = <T>(url: string) => api<T>("GET", url);
export const post = <T>(url: string, body?: unknown) => api<T>("POST", url, body ?? {});
export const put = <T>(url: string, body?: unknown) => api<T>("PUT", url, body);
export const patch = <T>(url: string, body?: unknown) => api<T>("PATCH", url, body);
export const del = <T>(url: string, body?: unknown) => api<T>("DELETE", url, body);
