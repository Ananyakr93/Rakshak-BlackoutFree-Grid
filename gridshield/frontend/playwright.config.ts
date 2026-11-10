import { defineConfig } from "@playwright/test";
import { rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";

const frontendRoot = process.cwd();
const backendRoot = resolve(frontendRoot, "..", "backend");
const apiOrigin = process.env.GRIDSHIELD_E2E_API_ORIGIN ?? "http://127.0.0.1:8001";
const frontendOrigin =
  process.env.GRIDSHIELD_E2E_FRONTEND_ORIGIN ?? "http://127.0.0.1:3001";
const databasePath = join(tmpdir(), `gridshield-e2e-${process.pid}.sqlite3`);
rmSync(databasePath, { force: true });

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: "list",
  use: {
    baseURL: frontendOrigin,
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `python -m uvicorn app.main:app --host 127.0.0.1 --port ${new URL(apiOrigin).port}`,
      cwd: backendRoot,
      url: `${apiOrigin}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DATABASE_URL: `sqlite+aiosqlite:///${databasePath.replace(/\\/g, "/")}`,
        CORS_ORIGINS: JSON.stringify([frontendOrigin, "http://localhost:3001"]),
        LOG_LEVEL: "WARNING",
      },
    },
    {
      command:
        `npm run build && npm run preview -- --host 127.0.0.1 --port ${new URL(frontendOrigin).port}`,
      cwd: frontendRoot,
      url: frontendOrigin,
      reuseExistingServer: false,
      timeout: 90_000,
      env: { VITE_API_BASE_URL: apiOrigin },
    },
  ],
});
