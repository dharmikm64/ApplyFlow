import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../src/pages/Dashboard";
import { makeMe, mockFetch, renderWithProviders, ROWS, run } from "./utils";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Sync now", () => {
  it("starts a sync, disables during the run, stops polling on success, and refetches the table", async () => {
    let state = "succeeded";
    let listCalls = 0;
    const { calls } = mockFetch({
      "POST /api/scans": () => {
        state = "running";
        return run("running", { kind: "sync" });
      },
      "GET /api/scans/current": () => run(state, { kind: "sync" }),
      "GET /api/applications": () => {
        listCalls += 1;
        return { items: ROWS, total: 2 };
      },
      "GET /api/review-items": () => ({ items: [], pendingCount: 0 }),
      "GET /api/me": () => makeMe(),
    });
    renderWithProviders(<Dashboard me={makeMe()} />);
    const button = await screen.findByRole("button", { name: "Sync now" });
    await waitFor(() => expect(button).toBeEnabled());
    const before = listCalls;

    await userEvent.click(button);
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ kind: "sync" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Sync now" })).toBeDisabled());
    expect(await screen.findByTestId("scan-progress")).toBeInTheDocument();

    state = "succeeded";
    // Next poll (2 s) sees success -> progress disappears, table refetched.
    await waitFor(() => expect(screen.queryByTestId("scan-progress")).not.toBeInTheDocument(), { timeout: 4000 });
    await waitFor(() => expect(listCalls).toBeGreaterThan(before));
    const pollsAfter = calls.filter((c) => c.url.startsWith("/api/scans/current")).length;
    await act(() => new Promise((r) => setTimeout(r, 2500)));
    expect(calls.filter((c) => c.url.startsWith("/api/scans/current")).length).toBe(pollsAfter);
    expect(screen.getByRole("button", { name: "Sync now" })).toBeEnabled();
  });

  it("is disabled when Gmail is not connected", async () => {
    mockFetch({ "GET /api/scans/current": () => run("succeeded"), "GET /api/applications": () => ({ items: ROWS, total: 2 }) });
    renderWithProviders(<Dashboard me={makeMe({ gmail: { status: "not_connected", address: null } })} />);
    expect(await screen.findByRole("button", { name: "Sync now" })).toBeDisabled();
  });
});
