import type { ApplianceSnapshot } from "../types";
import type { CityBuilding } from "../components/CityTwin";

export interface BuildingVisualState {
  lighting: number;
  lightingStates: boolean[];
  hasLightingAppliance: boolean;
  hasAnyPower: boolean;
  criticalUnavailable: boolean;
  restoring: boolean;
  shed: boolean;
  blackout: boolean;
  acRunning: boolean;
  geyserRunning: boolean;
  pumpRunning: boolean;
  evState: "on" | "shed" | "waiting" | "off";
  refrigeratorRunning: boolean;
  medicalRunning: boolean;
  inverterRunning: boolean;
  demandRatio: number;
  status: "normal" | "shed" | "restoring" | "critical" | "blackout";
}

function isOn(appliance: ApplianceSnapshot): boolean {
  return (appliance.state === "ON" || appliance.state === "RUNNING") &&
    appliance.current_power_kw > 0;
}

export function getBuildingVisualState(building: CityBuilding): BuildingVisualState {
  const appliances = building.appliances;
  const lighting = appliances.filter((item) => item.appliance_type === "lighting_led");
  const ratedLightingPower = lighting.reduce(
    (sum, appliance) => sum + appliance.rated_power_kw,
    0,
  );
  const currentLightingPower = lighting.reduce(
    (sum, appliance) => sum + (isOn(appliance) ? appliance.current_power_kw : 0),
    0,
  );
  const lightingRatio = ratedLightingPower > 0
    ? Math.max(0, Math.min(1, currentLightingPower / ratedLightingPower))
    : 0;
  const lightingStates = lighting.map(isOn);
  const hasAnyPower = appliances.some(isOn);
  const criticalUnavailable = appliances.some(
    (item) => item.priority === "critical" && !isOn(item),
  );
  const restoring = appliances.some((item) => item.state === "WAITING_RESTORATION");
  const shed = appliances.some((item) =>
    item.state === "SHED" || item.state === "LOCKED_OUT",
  );
  const blackout = appliances.length > 0 && !hasAnyPower;
  const sumRated = appliances.reduce((sum, item) => sum + item.rated_power_kw, 0);
  const demandRatio = sumRated > 0 ? Math.min(1, building.demand_kw / sumRated) : 0;

  return {
    lighting: lightingRatio,
    lightingStates,
    hasLightingAppliance: lighting.length > 0,
    hasAnyPower,
    criticalUnavailable,
    restoring,
    shed,
    blackout,
    acRunning: appliances.some((item) =>
      item.appliance_type.startsWith("split_ac_") && isOn(item),
    ),
    geyserRunning: appliances.some((item) =>
      item.appliance_type === "geyser_15l" && isOn(item),
    ),
    pumpRunning: appliances.some((item) =>
      item.appliance_type === "water_pump" && isOn(item),
    ),
    evState: appliances.some((item) =>
      item.appliance_type.startsWith("ev_charger_") && isOn(item),
    ) ? "on" : appliances.some((item) =>
      item.appliance_type.startsWith("ev_charger_") && item.state === "SHED",
    ) ? "shed" : appliances.some((item) =>
      item.appliance_type.startsWith("ev_charger_") && item.state === "WAITING_RESTORATION",
    ) ? "waiting" : "off",
    refrigeratorRunning: appliances.some((item) =>
      item.appliance_type === "refrigerator" && isOn(item),
    ),
    medicalRunning: appliances.some((item) =>
      item.appliance_type === "medical_device" && isOn(item),
    ),
    inverterRunning: appliances.some((item) =>
      item.appliance_type === "inverter_backed_load" && isOn(item),
    ),
    demandRatio,
    status: blackout ? "blackout" : criticalUnavailable ? "critical" :
      restoring ? "restoring" : shed ? "shed" : "normal",
  };
}
