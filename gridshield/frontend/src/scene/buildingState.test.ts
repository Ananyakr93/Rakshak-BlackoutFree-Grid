// Runtime validation coverage for simulation-driven building visuals.
import { describe, expect, it } from "vitest";
import type { ApplianceSnapshot } from "../types";
import type { CityBuilding } from "../components/CityTwin";
import { getBuildingVisualState } from "./buildingState";

function appliance(overrides: Partial<ApplianceSnapshot>): ApplianceSnapshot {
  return {
    appliance_id: "B01_A01",
    appliance_type: "lighting_led",
    priority: "essential",
    rated_power_kw: 0.04,
    enrolled: true,
    state: "ON",
    current_power_kw: 0.04,
    ...overrides,
  };
}

function building(appliances: ApplianceSnapshot[], demandKw: number): CityBuilding {
  return {
    building_id: "B01",
    weight_k: 1,
    demand_kw: demandKw,
    estimated_current_a: 0,
    appliances,
  };
}

describe("simulation-driven building visuals", () => {
  it("maps active loads and demand into the initial building state", () => {
    const lighting = appliance({});
    const ev = appliance({
      appliance_id: "B01_A02",
      appliance_type: "ev_charger_car",
      priority: "deferrable",
      rated_power_kw: 3.3,
      state: "SHED",
      current_power_kw: 0,
    });
    const refrigerator = appliance({
      appliance_id: "B01_A03",
      appliance_type: "refrigerator",
      rated_power_kw: 0.15,
      current_power_kw: 0.15,
    });

    const visual = getBuildingVisualState(building([lighting, ev, refrigerator], 0.19));

    expect(visual.status).toBe("shed");
    expect(visual.lighting).toBe(1);
    expect(visual.evState).toBe("shed");
    expect(visual.refrigeratorRunning).toBe(true);
    expect(visual.demandRatio).toBeCloseTo(0.19 / 3.49);
  });

  it("marks critical appliances unavailable without calling the whole building blacked out", () => {
    const medical = appliance({
      appliance_type: "medical_device",
      priority: "critical",
      rated_power_kw: 0.5,
      state: "UNAVAILABLE",
      current_power_kw: 0,
    });
    const lighting = appliance({ appliance_id: "B01_A02" });

    const visual = getBuildingVisualState(building([medical, lighting], 0.04));

    expect(visual.criticalUnavailable).toBe(true);
    expect(visual.blackout).toBe(false);
    expect(visual.status).toBe("critical");
  });

  it("gives a complete outage precedence over other building status", () => {
    const medical = appliance({
      appliance_type: "medical_device",
      priority: "critical",
      rated_power_kw: 0.5,
      state: "OFF",
      current_power_kw: 0,
    });

    const visual = getBuildingVisualState(building([medical], 0));

    expect(visual.blackout).toBe(true);
    expect(visual.criticalUnavailable).toBe(true);
    expect(visual.status).toBe("blackout");
  });

  it("distinguishes a waiting restoration state from a shed state", () => {
    const lighting = appliance({});
    const ev = appliance({
      appliance_id: "B01_A02",
      appliance_type: "ev_charger_car",
      priority: "deferrable",
      rated_power_kw: 3.3,
      state: "WAITING_RESTORATION",
      current_power_kw: 0,
    });

    const visual = getBuildingVisualState(building([lighting, ev], 0.04));

    expect(visual.restoring).toBe(true);
    expect(visual.shed).toBe(false);
    expect(visual.evState).toBe("waiting");
    expect(visual.status).toBe("restoring");
  });

  it("uses LED current power, not appliance counts, for window illumination", () => {
    const firstLed = appliance({ rated_power_kw: 0.04, current_power_kw: 0.04 });
    const secondLed = appliance({
      appliance_id: "B01_A02",
      rated_power_kw: 0.08,
      current_power_kw: 0.02,
      state: "RUNNING",
    });

    const visual = getBuildingVisualState(building([firstLed, secondLed], 0.06));

    expect(visual.lighting).toBeCloseTo(0.06 / 0.12);
    expect(visual.lightingStates).toEqual([true, true]);
  });

  it.each(["SHED", "WAITING_RESTORATION", "LOCKED_OUT", "OFF", "UNAVAILABLE"] as const)(
    "keeps %s LED windows dark",
    (state) => {
      const led = appliance({
        state,
        current_power_kw: 0,
      });

      expect(getBuildingVisualState(building([led], 0)).lighting).toBe(0);
    },
  );

  it("does not display an ON LED as powered when its current power is zero", () => {
    const led = appliance({ state: "ON", current_power_kw: 0 });

    expect(getBuildingVisualState(building([led], 0)).lighting).toBe(0);
  });

  it("lights windows after an LED is restored", () => {
    const shedLed = appliance({ state: "SHED", current_power_kw: 0 });
    const restoredLed = { ...shedLed, state: "ON" as const, current_power_kw: 0.04 };

    expect(getBuildingVisualState(building([shedLed], 0)).lighting).toBe(0);
    expect(getBuildingVisualState(building([restoredLed], 0.04)).lighting).toBe(1);
  });

  it("keeps each LED window group independently controllable", () => {
    const firstLed = appliance({ current_power_kw: 0.04 });
    const secondLed = appliance({
      appliance_id: "B01_A02",
      state: "SHED",
      current_power_kw: 0,
    });

    expect(getBuildingVisualState(building([firstLed, secondLed], 0.04)).lightingStates)
      .toEqual([true, false]);
  });

  it("does not let ceiling fans determine window lighting", () => {
    const ledOn = appliance({});
    const fanOff = appliance({
      appliance_id: "B01_FAN",
      appliance_type: "ceiling_fan",
      rated_power_kw: 0.075,
      state: "OFF",
      current_power_kw: 0,
    });
    const fanOn = { ...fanOff, state: "ON" as const, current_power_kw: 0.075 };
    const ledOff = { ...ledOn, state: "OFF" as const, current_power_kw: 0 };

    expect(getBuildingVisualState(building([ledOn, fanOff], 0.04)).lighting).toBe(1);
    expect(getBuildingVisualState(building([ledOff, fanOn], 0.075)).lighting).toBe(0);
  });

  it.each(["refrigerator", "split_ac_1ton", "medical_device"] as const)(
    "does not illuminate windows for %s without an LED load",
    (applianceType) => {
      const nonLightingLoad = appliance({
        appliance_type: applianceType,
        current_power_kw: 0.5,
      });
      const visual = getBuildingVisualState(building([nonLightingLoad], 0.5));

      expect(visual.hasLightingAppliance).toBe(false);
      expect(visual.lighting).toBe(0);
    },
  );

  it("clamps over-rated LED current to fully illuminated", () => {
    const led = appliance({ current_power_kw: 0.08, rated_power_kw: 0.04 });

    expect(getBuildingVisualState(building([led], 0.08)).lighting).toBe(1);
  });

  it("turns off every powered indicator during a complete building blackout", () => {
    const loads = [
      appliance({ appliance_type: "split_ac_1ton" }),
      appliance({ appliance_id: "geyser", appliance_type: "geyser_15l" }),
      appliance({ appliance_id: "pump", appliance_type: "water_pump" }),
      appliance({ appliance_id: "ev", appliance_type: "ev_charger_car" }),
      appliance({ appliance_id: "fridge", appliance_type: "refrigerator" }),
      appliance({ appliance_id: "medical", appliance_type: "medical_device" }),
      appliance({ appliance_id: "inverter", appliance_type: "inverter_backed_load" }),
      appliance({ appliance_id: "light", appliance_type: "lighting_led" }),
    ].map((item) => ({ ...item, state: "SHED" as const, current_power_kw: 0 }));
    const visual = getBuildingVisualState(building(loads, 0));

    expect(visual.blackout).toBe(true);
    expect(visual.lighting).toBe(0);
    expect(visual.acRunning).toBe(false);
    expect(visual.geyserRunning).toBe(false);
    expect(visual.pumpRunning).toBe(false);
    expect(visual.evState).toBe("shed");
    expect(visual.refrigeratorRunning).toBe(false);
    expect(visual.medicalRunning).toBe(false);
    expect(visual.inverterRunning).toBe(false);
  });

  it("shows each appliance indicator while its matching load is powered", () => {
    const loads = [
      appliance({ appliance_type: "split_ac_1ton" }),
      appliance({ appliance_id: "geyser", appliance_type: "geyser_15l" }),
      appliance({ appliance_id: "pump", appliance_type: "water_pump" }),
      appliance({ appliance_id: "ev", appliance_type: "ev_charger_car" }),
      appliance({ appliance_id: "fridge", appliance_type: "refrigerator" }),
      appliance({ appliance_id: "medical", appliance_type: "medical_device" }),
      appliance({ appliance_id: "inverter", appliance_type: "inverter_backed_load" }),
    ];
    const visual = getBuildingVisualState(building(loads, 7));

    expect(visual.acRunning).toBe(true);
    expect(visual.geyserRunning).toBe(true);
    expect(visual.pumpRunning).toBe(true);
    expect(visual.evState).toBe("on");
    expect(visual.refrigeratorRunning).toBe(true);
    expect(visual.medicalRunning).toBe(true);
    expect(visual.inverterRunning).toBe(true);
  });
});
