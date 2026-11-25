import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApplicationDetailDrawer } from "../src/components/ApplicationDetailDrawer";
import { Review } from "../src/pages/Review";
import { mockFetch, renderWithProviders } from "./utils";

afterEach(() => vi.unstubAllGlobals());

const DETAIL = {
  application: {
    id: "a1", company: "Acme Robotics", position: "Software Engineer", dateApplied: "2026-09-04",
    dateAppliedSource: "estimated", status: "submitted", beforeCycle: false, pendingReview: false,
    reqId: null, overriddenFields: [], dismissedAt: null,
  },
  dateAppliedExplanation: "Estimated from the date of the confirmation email (2026-09-04, America/New_York).",
  events: [
    {
      id: "e1", kind: "confirmation", occurredAt: "2026-09-04T16:00:00+00:00", detail: null,
      evidence: { sender: "Acme Robotics <no-reply@greenhouse.io>", subject: "Thanks", date: "2026-09-04T16:00:00+00:00",
        excerpt: "Thanks for applying <img src=x onerror=alert(1)> to Acme." },
    },
  ],
  reviewItems: [],
};

describe("Application detail", () => {
  it("shows evidence as literal text and saves corrections via PATCH", async () => {
    const { calls } = mockFetch({
      "GET /api/applications/a1": () => DETAIL,
      "PATCH /api/applications/a1": () => ({ ...DETAIL, application: { ...DETAIL.application, company: "Acme Robotics Inc" } }),
    });
    const { container } = renderWithProviders(<ApplicationDetailDrawer id="a1" onClose={() => {}} />);
    expect(await screen.findByText(/Estimated from the date/)).toBeInTheDocument();
    // HTML inside an excerpt is rendered as text, never as markup.
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();

    const company = screen.getByLabelText("Company");
    await userEvent.clear(company);
    await userEvent.type(company, "Acme Robotics Inc");
    await userEvent.click(screen.getByRole("button", { name: "Save corrections" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ company: "Acme Robotics Inc" });
  });

  it("limits status to the three allowed values", async () => {
    mockFetch({ "GET /api/applications/a1": () => DETAIL });
    renderWithProviders(<ApplicationDetailDrawer id="a1" onClose={() => {}} />);
    const select = await screen.findByLabelText("Application Status");
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Submitted", "In progress", "Rejected"]);
  });
});

describe("Review page", () => {
  it("resolving an item removes it", async () => {
    let items = [
      { id: "r1", type: "offer_or_withdrawal", explanation: "This email looks like an offer.", evidence: null,
        application: null, candidates: [], suggestion: { action: "dismiss" } },
    ];
    const { calls } = mockFetch({
      "GET /api/review-items": () => ({ items, pendingCount: items.length }),
      "POST /api/review-items/r1/resolve": () => {
        items = [];
        return { id: "r1", state: "dismissed" };
      },
    });
    renderWithProviders(<Review />);
    expect(await screen.findByText("This email looks like an offer.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(await screen.findByText("Nothing to review")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "dismiss" });
  });
});
