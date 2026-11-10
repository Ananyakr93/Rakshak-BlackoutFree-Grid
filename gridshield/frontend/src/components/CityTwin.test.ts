import { describe, expect, it } from "vitest";
import type { CityBuilding } from "./CityTwin";
import { getRenderedBuildings } from "./CityTwin";

function makeBuildings(count: number): CityBuilding[] {
  return Array.from({ length: count }, (_, index) => ({
    building_id: `B${String(index + 1).padStart(3, "0")}`,
    weight_k: 1,
    demand_kw: 1,
    estimated_current_a: 1,
    appliances: [],
  }));
}

describe("rendered neighborhood assets", () => {
  it("renders all 12 individually selectable scenario buildings", () => {
    const buildings = makeBuildings(12);
    const rendered = getRenderedBuildings(buildings);

    expect(rendered).toHaveLength(12);
    expect(new Set(rendered.map((building) => building.building_id)).size).toBe(12);
    expect(rendered.map((building) => building.building_id)).toEqual(
      buildings.map((building) => building.building_id),
    );
  });

  it("limits a large fleet view to 12 distinct representative simulation entities", () => {
    const rendered = getRenderedBuildings(makeBuildings(500));

    expect(rendered).toHaveLength(12);
    expect(new Set(rendered.map((building) => building.building_id)).size).toBe(12);
    expect(rendered[0].building_id).toBe("B001");
    expect(rendered[11].building_id).toBe("B500");
  });
});
