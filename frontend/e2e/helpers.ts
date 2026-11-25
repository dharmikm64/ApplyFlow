import { expect, type Page } from "@playwright/test";

/** Sign in as a synthetic user via the APP_ENV=test route; returns the CSRF token. */
export async function testLogin(page: Page, sub: string, email = "jordan@example.test"): Promise<string> {
  const res = await page.request.post("/test/login", { data: { sub, email } });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).csrfToken as string;
}

export async function testPost(page: Page, csrf: string, path: string, data: unknown) {
  const res = await page.request.post(path, { data, headers: { "X-CSRF-Token": csrf } });
  expect(res.ok(), `${path} -> ${res.status()}`).toBeTruthy();
  return res;
}

export async function setClock(page: Page, csrf: string, iso: string) {
  await testPost(page, csrf, "/test/clock", { now: iso });
}

export async function connectMailbox(page: Page, csrf: string, mailbox: string) {
  await testPost(page, csrf, "/test/gmail/connect", { mailbox });
}

export async function chooseStartDate(page: Page, date: string, tz = "America/New_York") {
  await page.getByLabel("Recruiting cycle start date").fill(date);
  await page.getByLabel("Time zone").selectOption(tz);
  await page.getByRole("button", { name: "Save start date" }).click();
}

export function rows(page: Page) {
  return page.getByRole("table").locator("tbody tr");
}

export async function rowTexts(page: Page): Promise<string[][]> {
  const out: string[][] = [];
  const n = await rows(page).count();
  for (let i = 0; i < n; i++) {
    const cells = rows(page).nth(i).locator("td");
    out.push([0, 1, 2, 3].map(() => ""));
    for (let c = 0; c < 4; c++)
      out[i][c] = (await cells.nth(c).innerText()).replace(/\s+/g, " ").replace(/\s*est\.$/, " est.").trim();
  }
  return out;
}
