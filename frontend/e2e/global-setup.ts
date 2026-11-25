import { request } from "@playwright/test";

export default async function globalSetup() {
  const ctx = await request.newContext({ baseURL: "http://localhost:8001" });
  const res = await ctx.post("/test/reset");
  if (!res.ok()) throw new Error(`reset failed: ${res.status()}`);
  await ctx.dispose();
}
