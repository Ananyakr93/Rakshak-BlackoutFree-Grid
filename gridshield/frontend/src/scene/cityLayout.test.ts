// Runtime validation coverage for representative neighborhood sizes.
import { describe, expect, it } from "vitest";
import { positionForBuilding } from "./cityLayout";

describe("city layout", () => {
  it.each([3, 5, 10, 12])("places %i buildings in stable street rows", (count) => {
    const positions = Array.from({ length: count }, (_, index) =>
      positionForBuilding(index, count, `B${String(index + 1).padStart(2, "0")}`),
    );
    const uniqueCenters = new Set(positions.map(({ x, z }) => `${x.toFixed(3)}:${z.toFixed(3)}`));

    expect(positions).toHaveLength(count);
    expect(uniqueCenters.size).toBe(count);
    expect(positions.every(({ x, y, z }) =>
      Number.isFinite(x) && y === 0 && Number.isFinite(z),
    )).toBe(true);

    const frontCount = count > 6 ? 6 : Math.ceil(count / 2);
    expect(positions.slice(0, frontCount).every(({ z }) => z > 5)).toBe(true);
    expect(positions.slice(frontCount).every(({ z }) => z < -6)).toBe(true);

    const repeated = positionForBuilding(0, count, "B01");
    expect(repeated.x).toBe(positions[0].x);
    expect(repeated.z).toBe(positions[0].z);
  });

  it("rejects indices outside the requested building count", () => {
    expect(() => positionForBuilding(2, 2, "B03")).toThrow(RangeError);
  });
});
