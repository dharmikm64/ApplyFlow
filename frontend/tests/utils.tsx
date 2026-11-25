import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { Me } from "../src/api/types";

export type Handler = (url: string, init?: RequestInit) => unknown | Promise<unknown>;

/** Route fetch calls by "METHOD path" prefix. Returning undefined -> 204. */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: { method: string; url: string; body?: unknown; headers?: HeadersInit }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined, headers: init?.headers });
    const key = Object.keys(routes)
      .filter((k) => {
        const [m, p] = k.split(" ");
        return m === method && url.startsWith(p);
      })
      .sort((a, b) => b.length - a.length)[0];
    if (!key) return new Response(JSON.stringify({ error: "not_found", message: url }), { status: 404 });
    const out = await routes[key](url, init);
    if (out instanceof Response) return out;
    if (out === undefined) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export function renderWithProviders(ui: ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

export function makeMe(over: Partial<Me> = {}): Me {
  return {
    user: { email: "jordan@example.test", displayName: "Jordan" },
    csrfToken: "csrf-1",
    gmail: { status: "connected", address: "jordan@example.test" },
    cycle: { startDate: "2026-09-01", timezone: "America/New_York", lastSuccessfulSyncAt: "2026-10-01T00:00:00+00:00" },
    ...over,
  };
}

export const ROWS = [
  { id: "a1", company: "Acme Robotics", position: "Software Engineer", dateApplied: "2026-09-04", dateAppliedSource: "estimated", status: "rejected", beforeCycle: false, pendingReview: false },
  { id: "a2", company: "Globex", position: "Data Analyst", dateApplied: null, dateAppliedSource: "unknown", status: "rejected", beforeCycle: false, pendingReview: false },
];

export function run(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: "r1", kind: "initial", status, windowStart: "2026-09-01T04:00:00+00:00", windowEnd: "2026-10-01T00:00:00+00:00",
    progress: { listed: 40, estimatedTotal: 100, screened: 40, candidates: 6, processed: 40 },
    results: { createdApps: 2, updatedApps: 0, reviewItems: 0 }, failureCode: null, startedAt: null, finishedAt: null,
    ...extra,
  };
}
