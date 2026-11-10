import type { BuildingSnapshot, BuildingStateUpdate } from "../types";

export function mergeBuildingStateUpdate(
  buildings: BuildingSnapshot[],
  update: BuildingStateUpdate,
): BuildingSnapshot[] {
  let matched = false;
  const updatedBuildings = buildings.map((building) => {
    if (
      building.building_id !== update.building_id ||
      building.run_id !== update.run_id ||
      building.sequence_number >= update.sequence_number
    ) {
      return building;
    }

    let matchedAppliance = false;
    const appliances = building.appliances.map((appliance) => {
      if (appliance.appliance_id !== update.appliance_id) return appliance;
      matchedAppliance = true;
      return {
        ...appliance,
        state: update.current_state,
        current_power_kw: update.current_power_kw,
        rated_power_kw: update.rated_power_kw,
      };
    });
    if (!matchedAppliance) return building;

    matched = true;
    return {
      ...building,
      demand_kw: building.demand_kw
        + update.current_power_kw
        - (building.appliances.find(
          (appliance) => appliance.appliance_id === update.appliance_id,
        )?.current_power_kw ?? 0),
      simulation_time_s: update.simulation_time_s,
      sequence_number: update.sequence_number,
      updated_at: update.updated_at,
      appliances,
    };
  });

  return matched ? updatedBuildings : buildings;
}
