import { expect, test } from "@playwright/test";

const apiOrigin = process.env.GRIDSHIELD_E2E_API_ORIGIN ?? "http://127.0.0.1:8001";

test("runs a fault scenario and renders reasoned backend decisions", async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  const failedApiRequests: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    if (request.url().startsWith(`${apiOrigin}/api/`)) {
      failedApiRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`);
    }
  });

  await page.goto("/");
  await expect(page).toHaveTitle("Rakshak — City Grid Resilience Digital Twin");
  await expect(page.locator(".brand-name")).toHaveText("Rakshak");
  await expect(page.getByText("API connected")).toBeVisible();
  const scenarioSelect = page.getByLabel("Scenario");
  await expect(scenarioSelect).toHaveValue("default_scenario");
  await scenarioSelect.selectOption("severe_generation_loss");

  const policySelect = page.getByLabel("Control policy");
  await policySelect.selectOption("P1_adms_feeder");
  await page.locator(".tuning-disclosure > summary").click();
  await expect(page.locator("#simulation-duration")).toHaveAttribute("max", "1800");
  await expect(page.locator("#communication-loss")).toHaveAttribute("max", "100");
  await expect(page.locator("#communication-loss")).toBeDisabled();
  await expect(page.locator("#p1-recovery-hold")).toBeEnabled();
  await expect(page.locator("#restoration-stable-hold")).toBeDisabled();
  await expect(page.locator("#edge-mode-select")).toBeDisabled();
  await policySelect.selectOption("P2_priority_edge");
  await expect(page.locator("#communication-loss")).toBeEnabled();
  await expect(page.locator("#restoration-stable-hold")).toBeEnabled();
  await expect(page.locator("#edge-mode-select")).toBeEnabled();
  await page.locator(".tuning-disclosure > summary").click();

  const scenarioCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/scenarios",
  );
  const runStarted = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/runs",
  );
  const decisionsReceived = page.waitForResponse(
    async (response) => {
      if (
        response.request().method() !== "GET" ||
        !new URL(response.url()).pathname.endsWith("/events")
      ) {
        return false;
      }
      const events = (await response.json()) as Array<{ reason?: unknown }>;
      return events.some(
        (event) => typeof event.reason === "string" && event.reason.trim().length > 0,
      );
    },
    { timeout: 60_000 },
  );

  await page.getByRole("button", { name: "Start simulation" }).click();
  const scenarioResponse = await scenarioCreated;
  expect(scenarioResponse.status()).toBe(201);
  expect((await scenarioResponse.json()).scenario_id).toBeTruthy();

  const runResponse = await runStarted;
  expect(runResponse.status()).toBe(202);
  const run = (await runResponse.json()) as {
    run_id: string;
    status: string;
    policy: string;
  };
  expect(run.status).toBe("pending");
  expect(run.policy).toBe("P2_priority_edge");

  await expect(page.locator(".frequency-value")).not.toHaveText("— — Hz");
  const decisionsResponse = await decisionsReceived;
  expect(decisionsResponse.status()).toBe(200);
  await expect.poll(() => page.locator(".event-item").count()).toBeGreaterThan(0);
  await expect(page.locator(".event-reason").first()).not.toBeEmpty();
  await page.getByRole("button", { name: "Resilience systems" }).click();
  await expect(page.getByRole("heading", { name: "Run inspector" })).toBeVisible();
  const effectiveRun = await page.request.get(`${apiOrigin}/api/v1/runs/${run.run_id}`);
  expect(effectiveRun.status()).toBe(200);
  const effectiveScenario = (await effectiveRun.json()).scenario as { name: string };
  await expect(
    page.locator(".clinical-metrics strong").filter({ hasText: effectiveScenario.name }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Operations" }).click();
  const pauseResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/v1/runs/${run.run_id}/pause`),
  );
  await page.getByRole("button", { name: "Pause" }).click();
  expect((await pauseResponse).status()).toBe(200);
  await expect(page.locator(".run-chip")).toHaveText(/paused/i);

  const resumeResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/v1/runs/${run.run_id}/resume`),
  );
  await page.getByRole("button", { name: "Resume" }).click();
  expect((await resumeResponse).status()).toBe(200);
  await expect(page.locator(".run-chip")).toHaveText(/running/i);

  const speedResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/v1/runs/${run.run_id}/speed`),
  );
  await page.getByLabel("Simulation playback speed").selectOption("120");
  const speedResult = await speedResponse;
  expect(speedResult.status()).toBe(200);
  expect((await speedResult.json()).playback_speed).toBe(120);

  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain("Stop this simulation run?");
    void dialog.accept();
  });
  const stopResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/v1/runs/${run.run_id}/stop`),
  );
  await page.getByRole("button", { name: "Stop" }).click();
  expect((await stopResponse).status()).toBe(200);
  await expect(page.locator(".run-chip")).toHaveText(/completed/i, { timeout: 30_000 });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(failedApiRequests).toEqual([]);
});
