import { describe, expect, it } from "vitest";
import { estimateThreePhaseCurrentA } from "./feederEstimate";

describe("reduced-order feeder current estimate", () => {
  it("uses balanced three-phase current at the documented voltage and power factor", () => {
    expect(estimateThreePhaseCurrentA(1)).toBeCloseTo(
      1000 / (Math.sqrt(3) * 400 * 0.95),
    );
  });

  it("rejects invalid loads and electrical assumptions", () => {
    expect(() => estimateThreePhaseCurrentA(-1)).toThrow(RangeError);
    expect(() => estimateThreePhaseCurrentA(1, 0)).toThrow(RangeError);
    expect(() => estimateThreePhaseCurrentA(1, 400, 1.1)).toThrow(RangeError);
  });
});
