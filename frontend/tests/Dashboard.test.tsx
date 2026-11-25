import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../src/pages/Dashboard";
import { makeMe, mockFetch, renderWithProviders, ROWS, run } from "./utils";

afterEach(() => vi.unstubAllGlobals());

describe("Dashboard states", () => {
  it("shows loading while applications load", () => {
    mockFetch({ "GET /api/scans/current": () => run("succeeded"), "GET /api/applications": () => new Promise(() => {}) });
    renderWithProviders(<Dashboard me={makeMe()} />);
    expect(screen.getByText("Loading applications…")).toBeInTheDocument();
  });

  it("shows the empty-no-scan state and Scan emails before the first scan", async () => {
    mockFetch({ "GET /api/scans/current": () => undefined, "GET /api/applications": () => ({ items: [], total: 0 }) });
    renderWithProviders(<Dashboard me={makeMe({ cycle: { startDate: "2026-09-01", timezone: "UTC", lastSuccessfulSyncAt: null } })} />);
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scan emails" })).toBeEnabled();
  });

  it("shows the empty-found-nothing state after a scan with no results", async () => {
    mockFetch({ "GET /api/scans/current": () => run("succeeded"), "GET /api/applications": () => ({ items: [], total: 0 }) });
    renderWithProviders(<Dashboard me={makeMe()} />);
    expect(await screen.findByText("No applications found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
  });

  it("shows the failed-scan state with Retry", async () => {
    mockFetch({
      "GET /api/scans/current": () => run("failed", { failureCode: "gmail_unavailable" }),
      "GET /api/applications": () => ({ items: ROWS, total: 2 }),
    });
    renderWithProviders(<Dashboard me={makeMe()} />);
    expect(await screen.findByText("The last scan didn't finish")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows progress while a scan runs", async () => {
    mockFetch({ "GET /api/scans/current": () => run("running"), "GET /api/applications": () => ({ items: [], total: 0 }) });
    renderWithProviders(<Dashboard me={makeMe()} />);
    expect(await screen.findByTestId("scan-progress")).toHaveTextContent("Examined 40 of ~100 emails");
    expect(screen.getByRole("button", { name: "Sync now" })).toBeDisabled();
  });

  it("renders a populated table with exactly four column headers", async () => {
    mockFetch({ "GET /api/scans/current": () => run("succeeded"), "GET /api/applications": () => ({ items: ROWS, total: 2 }) });
    renderWithProviders(<Dashboard me={makeMe()} />);
    const table = await screen.findByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent?.replace(/[▲▼].*$/, "").trim());
    expect(headers).toEqual(["Company", "Position", "Date Applied", "Application Status"]);
    expect(within(table).getAllByText("Rejected")).toHaveLength(2);
    expect(within(table).getByText("Unknown")).toBeInTheDocument();
    expect(within(table).getByText("est.")).toBeInTheDocument();
    expect(screen.getByText(/Only applications with available, recognizable email evidence/)).toBeInTheDocument();
  });

  it("shows the reconnect state while keeping the table", async () => {
    mockFetch({ "GET /api/scans/current": () => run("failed", { failureCode: "reconnect_required" }), "GET /api/applications": () => ({ items: ROWS, total: 2 }) });
    renderWithProviders(<Dashboard me={makeMe({ gmail: { status: "revoked", address: "jordan@example.test" } })} />);
    expect(await screen.findByText("Reconnect Gmail to keep syncing")).toBeInTheDocument();
    expect(screen.getByText(/7 days of access/)).toBeInTheDocument();
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });
});
