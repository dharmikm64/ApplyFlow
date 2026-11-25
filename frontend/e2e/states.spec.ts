import { expect, test } from "@playwright/test";
import { chooseStartDate, connectMailbox, rows, setClock, testLogin, testPost } from "./helpers";

async function scanned(page, sub: string, mailbox: string) {
  const csrf = await testLogin(page, sub);
  await setClock(page, csrf, "2026-10-01T00:00:00+00:00");
  await connectMailbox(page, csrf, mailbox);
  await page.goto("/");
  await chooseStartDate(page, "2026-09-01");
  await page.getByRole("button", { name: "Scan emails" }).click();
  return csrf;
}

test("revoked access during sync shows the reconnect state and keeps rows", async ({ page }) => {
  const csrf = await scanned(page, "e2e-revoked", "core-journey");
  await expect(rows(page)).toHaveCount(3);
  await testPost(page, csrf, "/test/gmail/revoke", {});
  await page.getByRole("button", { name: "Sync now" }).click();
  await expect(page.getByText("Reconnect Gmail to keep syncing")).toBeVisible();
  await expect(page.getByRole("link", { name: "Reconnect Gmail" })).toBeVisible();
  await expect(rows(page)).toHaveCount(3);
});

test("a scan that finds nothing shows the empty-found-nothing state", async ({ page }) => {
  await scanned(page, "e2e-empty", "empty-mailbox");
  await expect(page.getByText("No applications found")).toBeVisible();
});

test("review items can be resolved", async ({ page }) => {
  await scanned(page, "e2e-review", "core-journey");
  await expect(rows(page)).toHaveCount(3);
  await page.getByRole("link", { name: /Review/ }).click();
  await expect(page.getByRole("heading", { name: "Offer or withdrawal" })).toBeVisible();
  await page.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.getByText("Nothing to review")).toBeVisible();
});

test("not an application: dismiss and restore", async ({ page }) => {
  await scanned(page, "e2e-dismiss", "dismiss-then-sync");
  await expect(rows(page)).toHaveCount(1);
  await page.getByRole("row", { name: /Example Bank/ }).click();
  await page.getByRole("button", { name: "Not an application" }).click();
  await expect(page.getByText("No applications found")).toBeVisible();
  await page.getByRole("button", { name: "Dismissed" }).click();
  await page.getByRole("row", { name: /Example Bank/ }).click();
  await page.getByRole("button", { name: "Restore to table" }).click();
  await page.getByRole("button", { name: "Applications", exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
});
