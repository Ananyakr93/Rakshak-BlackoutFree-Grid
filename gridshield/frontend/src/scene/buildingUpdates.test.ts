import { describe, expect, it } from "vitest";
import type { BuildingSnapshot, BuildingStateUpdate } from "../types";
import { mergeBuildingStateUpdate } from "./buildingUpdates";

const initial: BuildingSnapshot = {
  run_id: "run-1",
  building_id: "B01",
  weight_k: 2,
  demand_kw: 0.08,
  simulation_time_s: 0,
  sequence_number: 0,
  updated_at: null,
  appliances: [
    {
      appliance_id: "light",
      appliance_type: "lighting_led",
      priority: "essential",
      rated_power_kw: 0.08,
      enrolled: true,
      state: "ON",
      current_power_kw: 0.08,
    },
  ],
};

const update: BuildingStateUpdate = {
  type: "building_state_update",
  schema_version: "1.0",
  run_id: "run-1",
  building_id: "B01",
  appliance_id: "light",
  appliance_type: "lighting_led",
  priority: "essential",
  previous_state: "ON",
  current_state: "SHED",
  current_power_kw: 0,
  rated_power_kw: 0.08,
  simulation_time_s: 2,
  sequence_number: 1,
  updated_at: "2025-01-01T00:00:02Z",
};

describe("mergeBuildingStateUpdate", () => {
  it("updates appliance, aggregate demand, and sequence metadata", () => {
    const [building] = mergeBuildingStateUpdate([initial], update);

    expect(building.demand_kw).toBe(0);
    expect(building.appliances[0].state).toBe("SHED");
    expect(building.appliances[0].current_power_kw).toBe(0);
    expect(building.sequence_number).toBe(1);
    expect(building.simulation_time_s).toBe(2);
    expect(building.updated_at).toBe(update.updated_at);
  });

  it("does not apply an update from another run", () => {
    const buildings = [initial];
    expect(
      mergeBuildingStateUpdate(buildings, { ...update, run_id: "run-2" }),
    ).toBe(buildings);
  });

  it("does not let a stale update replace a newer snapshot", () => {
    const newerSnapshot = { ...initial, sequence_number: 2 };
    const buildings = [newerSnapshot];

    expect(mergeBuildingStateUpdate(buildings, update)).toBe(buildings);
  });
});
