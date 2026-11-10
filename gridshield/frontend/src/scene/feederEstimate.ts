export const NOMINAL_LINE_VOLTAGE_V = 400;
export const ASSUMED_POWER_FACTOR = 0.95;

export function estimateThreePhaseCurrentA(
  activePowerKw: number,
  voltageV = NOMINAL_LINE_VOLTAGE_V,
  powerFactor = ASSUMED_POWER_FACTOR,
): number {
  if (!Number.isFinite(activePowerKw) || activePowerKw < 0) {
    throw new RangeError("Active power must be a non-negative finite value.");
  }
  if (!Number.isFinite(voltageV) || voltageV <= 0) {
    throw new RangeError("Line voltage must be a positive finite value.");
  }
  if (!Number.isFinite(powerFactor) || powerFactor <= 0 || powerFactor > 1) {
    throw new RangeError("Power factor must be in the range (0, 1].");
  }
  return activePowerKw * 1000 / (Math.sqrt(3) * voltageV * powerFactor);
}
