import { expect, test, type Page } from "@playwright/test";

const apiOrigin = process.env.GRIDSHIELD_E2E_API_ORIGIN ?? "http://127.0.0.1:8001";
const scenarios = [
  "default_scenario",
  "severe_generation_loss",
  "solar_surplus_scenario",
  "communication_fault_scenario",
] as const;
const policies = [
  "P0_unmanaged",
  "P1_adms_feeder",
  "P2_priority_edge",
  "P2_priority_edge_synchronized",
  "P3_priority_edge_no_restoration",
] as const;

async function startFromControls(
  page: Page,
  scenario: string,
  policy: string,
): Promise<{ runId: string }> {
  await page.getByLabel("Scenario").selectOption(scenario);
  await page.getByLabel("Control policy").selectOption(policy);
  const started = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/runs",
  );
  await page.getByRole("button", { name: /Start simulation|Start another run/ }).click();
  const response = await started;
  expect(response.status()).toBe(202);
  const body = (await response.json()) as { run_id: string; policy: string };
  expect(body.policy).toBe(policy);
  await page.getByLabel("Simulation playback speed").selectOption("120");
  return { runId: body.run_id };
}

async function stopFromControls(page: Page): Promise<void> {
  const stopButton = page.getByRole("button", { name: "Stop" });
  if (!(await stopButton.isVisible().catch(() => false))) {
    await expect(page.locator(".run-chip")).toHaveText(/completed/i, { timeout: 30_000 });
    return;
  }
  page.once("dialog", (dialog) => void dialog.accept());
  const stopped = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/stop"),
  );
  await page.getByRole("button", { name: "Stop" }).click();
  expect((await stopped).status()).toBe(200);
  await expect(page.locator(".run-chip")).toHaveText(/completed/i, { timeout: 30_000 });
}

async function getRun(page: Page, runId: string): Promise<Record<string, any>> {
  const response = await page.request.get(`${apiOrigin}/api/v1/runs/${runId}`);
  expect(response.status()).toBe(200);
  return (await response.json()) as Record<string, any>;
}

test.describe("manual frontend and visual integration validation", () => {
  test.describe.configure({ mode: "serial", timeout: 180_000 });

  test("submits every shipped scenario with every control policy", async ({ page }) => {
    test.setTimeout(600_000);
    await page.goto("/");
    await expect(page.getByText("API connected")).toBeVisible();
    const templatesResponse = await page.request.get(`${apiOrigin}/api/v1/scenarios/templates`);
    const templates = (await templatesResponse.json()) as Array<{
      template_id: string;
      config: Record<string, any>;
    }>;

    for (const templateId of scenarios) {
      const template = templates.find((item) => item.template_id === templateId);
      expect(template).toBeTruthy();
      const config = {
        ...template!.config,
        scenario_id: crypto.randomUUID(),
        simulation_duration_s: 90,
        seed: 42,
      };
      const scenarioResponse = await page.request.post(`${apiOrigin}/api/v1/scenarios`, {
        data: config,
      });
      expect(scenarioResponse.status()).toBe(201);
      const scenario = (await scenarioResponse.json()) as { scenario_id: string };
      for (const policy of policies) {
        const runResponse = await page.request.post(`${apiOrigin}/api/v1/runs`, {
          data: {
            scenario_id: scenario.scenario_id,
            policy,
            seed: 42,
            playback_speed: 120,
          },
        });
        expect(runResponse.status()).toBe(202);
        const runStart = (await runResponse.json()) as { run_id: string; policy: string };
        expect(runStart.policy).toBe(policy);
        await expect.poll(async () => (await getRun(page, runStart.run_id)).status, {
          timeout: 90_000,
        }).toMatch(/completed|failed/);
        const run = await getRun(page, runStart.run_id);
        expect(run.status).toBe("completed");
        expect(run.policy).toBe(policy);
        expect(run.scenario.name).toBeTruthy();
        expect(run.scenario.seed).toBe(42);
        expect(run.scenario.buildings).toHaveLength(12);
      }
    }
  });

  test("persists each edited control in the effective backend snapshot", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Scenario").selectOption("default_scenario");
    await page.getByLabel("Control policy").selectOption("P2_priority_edge");
    await page.locator(".tuning-disclosure > summary").click();
    await page.locator("#disturbance-type").selectOption("solar_cloud_drop");
    await page.locator("#disturbance-magnitude").fill("18");
    await page.locator("#solar-share").fill("80");
    await page.locator("#recovery-ramp").fill("60");
    await page.locator("#grid-inertia").fill("8");
    await page.locator("#disturbance-start").fill("30");
    await page.locator("#simulation-duration").fill("90");
    await page.locator("#governor-droop").fill("12");
    await page.locator("#governor-response").fill("0.5");
    await page.locator("#s1-threshold").fill("49.9");
    await page.locator("#s2-threshold").fill("49.7");
    await page.locator(".advanced-tuning > summary").click();
    await page.locator("#s0-hold").fill("0");
    await page.locator("#s1-hold").fill("0");
    await page.locator("#o1-hold").fill("0");
    await page.locator("#restoration-stable-hold").fill("6");
    await page.locator("#communication-loss").fill("100");

    const { runId } = await startFromControls(page, "default_scenario", "P2_priority_edge");
    const run = await getRun(page, runId);
    const config = run.scenario;
    expect(config.simulation_duration_s).toBe(90);
    expect(config.disturbance.type).toBe("solar_cloud_drop");
    expect(config.disturbance.magnitude_pu).toBeCloseTo(0.18);
    expect(config.disturbance.solar_share_pu).toBeCloseTo(0.8);
    expect(config.disturbance.recovery_ramp_s).toBe(60);
    expect(config.disturbance.start_time_s).toBe(30);
    expect(config.grid_params.H).toBe(8);
    expect(config.grid_params.R).toBeCloseTo(0.12);
    expect(config.grid_params.Tg).toBe(0.5);
    expect(config.grid_params.f_s1_hz).toBeCloseTo(49.9);
    expect(config.grid_params.f_s2_hz).toBeCloseTo(49.7);
    expect(config.grid_params.t_s0_hold_s).toBe(0);
    expect(config.grid_params.t_s1_hold_s).toBe(0);
    expect(config.grid_params.t_o1_hold_s).toBe(0);
    expect(config.grid_params.t_stable_s).toBe(6);
    expect(config.fault_config.loss_probability).toBe(1);
  });

  test("keeps critical loads protected, renders diagnostics, and captures lifecycle states", async ({ page }) => {
    await page.goto("/");
    const { runId } = await startFromControls(page, "severe_generation_loss", "P2_priority_edge");
    await page.getByLabel("Simulation playback speed").selectOption("120");
    await page.getByRole("button", { name: "Pause" }).click();
    await expect(page.locator(".run-chip")).toHaveText(/paused/i);
    await page.screenshot({ path: "test-results/normal-operation.png", fullPage: true });
    await page.getByRole("button", { name: "Resume" }).click();
    await expect(page.locator(".run-chip")).toHaveText(/running/i);

    await page.getByRole("button", { name: "Resilience systems" }).click();
    for (const panel of [
      ["Run inspector", "Run inspector"],
      ["Medical loads", "Medical-priority appliances"],
      ["Edge agents", "Building edge agents"],
      ["Restoration", "Restoration queue"],
      ["NILM", "Aggregate signal & step estimates"],
      ["Feeder estimates", "Branch load & current estimates"],
      ["Hardware / HIL", "Hardware-in-the-loop status"],
    ]) {
      await page.getByRole("button", { name: panel[0] }).click();
      await expect(page.getByRole("heading", { name: panel[1] })).toBeVisible();
    }
    const run = await getRun(page, runId);
    const buildings = await (await page.request.get(`${apiOrigin}/api/v1/runs/${runId}/buildings`)).json();
    const b01 = buildings.find((building: { building_id: string }) => building.building_id === "B01");
    expect(b01).toBeTruthy();
    const critical = b01.appliances.filter((appliance: { priority: string }) => appliance.priority === "critical");
    expect(critical.every((appliance: { state: string }) => appliance.state !== "SHED")).toBeTruthy();
    expect(run.run_id).toBe(runId);

    await page.getByRole("button", { name: "Operations" }).click();
    await stopFromControls(page);
    await page.screenshot({ path: "test-results/recovery.png", fullPage: true });
  });

  test("exercises solar O1 absorption, edge loss, and run history", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Scenario").selectOption("solar_surplus_scenario");
    await page.getByLabel("Control policy").selectOption("P2_priority_edge");
    await page.locator(".tuning-disclosure > summary").click();
    await page.locator("#disturbance-magnitude").fill("12");
    await page.locator(".advanced-tuning > summary").click();
    await page.locator("#o1-hold").fill("0");
    await page.locator("#communication-loss").fill("100");
    const { runId } = await startFromControls(page, "solar_surplus_scenario", "P2_priority_edge");
    const run = await getRun(page, runId);
    const b02 = run.scenario.buildings.find((building: { building_id: string }) => building.building_id === "B02");
    const offDeferrable = b02.appliances.find(
      (appliance: { initial_state: string; priority: string }) =>
        appliance.initial_state === "OFF" && appliance.priority === "deferrable",
    );
    expect(offDeferrable).toBeTruthy();

    await expect.poll(async () => {
      const response = await page.request.get(`${apiOrigin}/api/v1/runs/${runId}/events`);
      const events = (await response.json()) as Array<{ event_type: string }>;
      return events.some((event) => event.event_type === "absorb_deferrable");
    }, { timeout: 60_000 }).toBe(true);
    await page.getByRole("button", { name: "Resilience systems" }).click();
    await page.getByRole("button", { name: "Building edge agents" }).click();
    await expect(page.getByRole("heading", { name: "Building edge agents" })).toBeVisible();
    await page.screenshot({ path: "test-results/partial-blackout.png", fullPage: true });
    await page.getByRole("button", { name: "Operations" }).click();
    await stopFromControls(page);

    const events = await (await page.request.get(`${apiOrigin}/api/v1/runs/${runId}/events`)).json();
    expect(events.some((event: { event_type: string }) => event.event_type === "absorb_deferrable")).toBeTruthy();
    expect(events.some((event: { event_type: string }) => /shed|throttle/.test(event.event_type))).toBeTruthy();
    await page.getByRole("button", { name: "Results & history" }).click();
    await expect(page.getByText(/history/i).first()).toBeVisible();
    await page.screenshot({ path: "test-results/complete-feeder-blackout.png", fullPage: true });
  });

  test("keeps the city usable at desktop, tablet, and mobile viewports", async ({ page }) => {
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 768, height: 1024 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await expect(page.locator("canvas.city-canvas")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      expect(overflow).toBe(false);
      await page.screenshot({
        path: `test-results/viewport-${viewport.width}x${viewport.height}.png`,
        fullPage: true,
      });
    }
  });
});
