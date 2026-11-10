import { describe, expect, it } from "vitest";
import type { CityBuilding } from "../components/CityTwin";
import { canReuseBuildingRigs } from "./createStage";

function building(buildingId: string): CityBuilding {
  return {
    building_id: buildingId,
    weight_k: 1,
    demand_kw: 0,
    estimated_current_a: 0,
    appliances: [],
  };
}

describe("building rig reuse", () => {
  it("reuses rigs when live updates replace models but preserve building identities", () => {
    const existing = new Map([
      ["B01", {}],
      ["B02", {}],
    ]);

    expect(canReuseBuildingRigs(existing, [building("B02"), building("B01")])).toBe(true);
  });

  it("rebuilds rigs when a building is added, removed, or replaced", () => {
    const existing = new Map([
      ["B01", {}],
      ["B02", {}],
    ]);

    expect(canReuseBuildingRigs(existing, [building("B01")])).toBe(false);
    expect(canReuseBuildingRigs(existing, [building("B01"), building("B03")])).toBe(false);
  });
});
