import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Filters } from "../src/components/Filters";

describe("Filters", () => {
  it("debounces search input", async () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<Filters q="" statuses={[]} onChange={onChange} onClear={() => {}} debounceMs={300} />);
    fireEvent.change(screen.getByLabelText("Search company or position"), { target: { value: "acme" } });
    expect(onChange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(300);
    expect(onChange).toHaveBeenCalledWith({ q: "acme" });
    vi.useRealTimers();
  });

  it("toggles statuses", async () => {
    const onChange = vi.fn();
    render(<Filters q="" statuses={["rejected"]} onChange={onChange} onClear={() => {}} />);
    await userEvent.click(screen.getByLabelText("Submitted"));
    expect(onChange).toHaveBeenCalledWith({ statuses: ["rejected", "submitted"] });
    await userEvent.click(screen.getByLabelText("Rejected"));
    expect(onChange).toHaveBeenCalledWith({ statuses: [] });
  });

  it("clear button resets everything", async () => {
    const onClear = vi.fn();
    render(<Filters q="acme" statuses={["submitted"]} onChange={() => {}} onClear={onClear} />);
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClear).toHaveBeenCalled();
  });
});
