import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Settings } from "../src/pages/Settings";
import { makeMe, mockFetch, renderWithProviders } from "./utils";

afterEach(() => vi.unstubAllGlobals());

describe("Settings", () => {
  it("disconnect asks for confirmation and explains the effects", async () => {
    const { calls } = mockFetch({ "DELETE /api/gmail": () => undefined, "GET /api/me": () => makeMe() });
    renderWithProviders(<Settings me={makeMe()} />);
    await userEvent.click(screen.getByRole("button", { name: "Disconnect Gmail" }));
    expect(screen.getByRole("dialog", { name: "Disconnect Gmail?" })).toHaveTextContent("Your application table is kept");
    expect(calls).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/gmail")).toBe(true));
  });

  it("delete imported data requires typing DELETE", async () => {
    const { calls } = mockFetch({ "DELETE /api/data": () => undefined });
    renderWithProviders(<Settings me={makeMe()} />);
    await userEvent.click(screen.getByRole("button", { name: "Delete imported data" }));
    const confirm = screen.getAllByRole("button", { name: "Delete imported data" }).at(-1)!;
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => expect(calls.find((c) => c.url === "/api/data")?.body).toEqual({ confirm: "DELETE" }));
  });

  it("delete account requires typing DELETE and sends the confirmation", async () => {
    const { calls } = mockFetch({ "DELETE /api/account": () => undefined });
    renderWithProviders(<Settings me={makeMe()} />);
    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));
    expect(screen.getByRole("dialog", { name: "Delete your ApplyFlow account?" })).toHaveTextContent("You will be signed out");
    const confirm = screen.getAllByRole("button", { name: "Delete account" }).at(-1)!;
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "DELET");
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "E");
    await userEvent.click(confirm);
    await waitFor(() => expect(calls.find((c) => c.url === "/api/account")?.body).toEqual({ confirm: "DELETE" }));
  });

  it("shows the start-date preview before confirming", async () => {
    const { calls } = mockFetch({
      "GET /api/cycle/preview-change": () => ({
        direction: "later", rowsMarkedBeforeCycle: 2, rowsDeleted: 0, willScanAddedPeriod: false,
        message: "No rows are deleted. 2 row(s) whose emails are all before the new date will be labeled \"Before current cycle\".",
      }),
      "PUT /api/cycle": () => makeMe().cycle,
      "GET /api/me": () => makeMe(),
    });
    renderWithProviders(<Settings me={makeMe()} />);
    const input = screen.getByLabelText("New start date");
    await userEvent.clear(input);
    await userEvent.type(input, "2026-09-10");
    await userEvent.click(screen.getByRole("button", { name: "Preview change" }));
    expect(await screen.findByTestId("cycle-preview")).toHaveTextContent("No rows are deleted. 2 row(s)");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ startDate: "2026-09-10", timezone: "America/New_York", confirm: true }));
  });
});
