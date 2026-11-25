import { expect, test } from "@playwright/test";
import { chooseStartDate, connectMailbox, rows, setClock, testLogin } from "./helpers";

test("pages expose labeled landmarks, controls, and keyboard access", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "ApplyFlow" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in with Google" })).toBeVisible();

  const csrf = await testLogin(page, "e2e-a11y");
  await setClock(page, csrf, "2026-10-01T00:00:00+00:00");
  await connectMailbox(page, csrf, "core-journey");
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await chooseStartDate(page, "2026-09-01");
  await page.getByRole("button", { name: "Scan emails" }).click();
  await expect(rows(page)).toHaveCount(3);

  // Table semantics: caption, column headers, sortable header state.
  const table = page.getByRole("table");
  await expect(table.locator("caption")).toHaveText("3 applications");
  await expect(table.getByRole("columnheader")).toHaveCount(4);
  await expect(table.getByRole("columnheader", { name: /Date Applied/ })).toHaveAttribute("aria-sort", "descending");
  await expect(page.getByRole("search")).toBeVisible();
  await expect(page.getByLabel("Search company or position")).toBeVisible();
  await expect(page.getByRole("group", { name: "Status" })).toBeVisible();

  // Keyboard: focus a row, Enter opens the drawer and focuses its heading, Escape closes it.
  await rows(page).first().focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { level: 2 })).toBeFocused();
  await expect(dialog.getByLabel("Company")).toBeVisible();
  await expect(dialog.getByLabel("Application Status")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Sort toggle is a real button reachable by keyboard.
  await page.getByRole("button", { name: /Date Applied/ }).press("Enter");
  await expect(table.getByRole("columnheader", { name: /Date Applied/ })).toHaveAttribute("aria-sort", "ascending");

  for (const [path, heading] of [["/review", "Review"], ["/settings", "Settings"], ["/connect", "Connect Gmail (read-only)"]]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }
  await page.goto("/settings");
  await expect(page.getByLabel("New start date")).toBeVisible();
  const snapshot = await page.locator("main").ariaSnapshot();
  expect(snapshot).toContain('heading "Gmail connection"');
  expect(snapshot).toContain('button "Delete account"');
});
