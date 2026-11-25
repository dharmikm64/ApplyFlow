import { expect, test } from "@playwright/test";
import { chooseStartDate, connectMailbox, rowTexts, rows, setClock, testLogin, testPost } from "./helpers";

test("main journey: connect, scan, review, correct, sync, sign out and back in", async ({ page }) => {
  const csrf = await testLogin(page, "e2e-main");
  await setClock(page, csrf, "2026-10-01T00:00:00+00:00");

  // Onboarding: connect step with a plain-language explanation before Google consent.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Step 1: Connect Gmail" })).toBeVisible();
  await page.getByRole("link", { name: "Connect Gmail (read-only)" }).click();
  await expect(page.getByRole("heading", { name: "Connect Gmail (read-only)" })).toBeVisible();
  await expect(page.getByText("It never sends, deletes, labels, archives, or changes any email.")).toBeVisible();
  await expect(page.getByText(/never shared with third parties/)).toBeVisible();

  // (Real consent happens at Google; in APP_ENV=test a fixture mailbox is attached instead.)
  await connectMailbox(page, csrf, "core-journey");
  await page.goto("/");
  await chooseStartDate(page, "2026-09-01");

  await page.getByRole("button", { name: "Scan emails" }).click();
  await expect(rows(page)).toHaveCount(3);
  await expect(page.getByText("Only applications with available, recognizable email evidence")).toBeVisible();

  expect(await rowTexts(page)).toEqual([
    ["Acme Robotics", "Product Manager", "2026-09-06 est.", "Submitted"],
    ["Acme Robotics", "Software Engineer", "2026-09-04 est.", "Rejected"],
    ["Globex", "Data Analyst", "Unknown", "Rejected"],
  ]);
  await expect(page.getByRole("link", { name: /Review/ }).locator(".badge")).toHaveText("1");

  // Detail: evidence and the estimated-date explanation.
  await page.getByRole("row", { name: /Acme Robotics, Software Engineer/ }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText(/Estimated from the date of the confirmation email/)).toBeVisible();
  await expect(drawer.getByText("Application confirmed")).toBeVisible();
  await expect(drawer.getByText("Rejection")).toBeVisible();
  await expect(drawer.getByText(/decided to move forward with other candidates/)).toBeVisible();
  await drawer.getByRole("button", { name: "Close details" }).click();

  // Correct a company name.
  await page.getByRole("row", { name: /Globex, Data Analyst/ }).click();
  await page.getByRole("dialog").getByLabel("Company").fill("Globex Corporation");
  await page.getByRole("button", { name: "Save corrections" }).click();
  await expect(page.getByRole("dialog").getByText(/Your corrections \(company\)/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("cell", { name: "Globex Corporation" })).toBeVisible();

  // New mail arrives; Sync now updates the existing row without duplicates.
  await setClock(page, csrf, "2026-10-10T00:00:00+00:00");
  await testPost(page, csrf, "/test/gmail/append", { messages: ["fx-acme-pm-interview-oct"] });
  await page.getByRole("button", { name: "Sync now" }).click();
  await expect(page.getByRole("row", { name: /Acme Robotics, Product Manager/ })).toContainText("In progress");
  await expect(rows(page)).toHaveCount(3);
  await expect(page.getByTestId("last-sync")).toContainText("Last synced");

  // Sign out, sign back in: the table is still there.
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Sign in with Google" })).toBeVisible();
  await testLogin(page, "e2e-main");
  await page.goto("/");
  await expect(rows(page)).toHaveCount(3);
  await expect(page.getByRole("cell", { name: "Globex Corporation" })).toBeVisible();
  await expect(page.getByRole("row", { name: /Acme Robotics, Product Manager/ })).toContainText("In progress");
});
