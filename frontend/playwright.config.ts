import { defineConfig, devices } from "@playwright/test";

// E2E runs against APP_ENV=test: synthetic Gmail fixtures and a test-only sign-in route.
// Separate ports (8001 / 5174) so it never collides with the dev servers.
const BACKEND_PORT = 8001;
const FRONTEND_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "cd ../backend && APP_ENV=test WORKER_MODE=embedded .venv/bin/alembic upgrade head && " +
        `APP_ENV=test WORKER_MODE=embedded .venv/bin/uvicorn app.main:app --port ${BACKEND_PORT}`,
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `APPLYFLOW_BACKEND_URL=http://localhost:${BACKEND_PORT} npx vite --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
