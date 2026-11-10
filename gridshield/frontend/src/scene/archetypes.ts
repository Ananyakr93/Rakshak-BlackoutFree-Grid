import type { ApplianceSnapshot } from "../types";

export type Archetype =
  | "clinic"
  | "hospital"
  | "apartment"
  | "bungalow"
  | "shop"
  | "row-house"
  | "solar-midrise"
  | "school"
  | "office"
  | "bakery";

const ID_ARCHETYPES: Archetype[] = [
  "hospital",
  "apartment",
  "bungalow",
  "shop",
  "row-house",
  "row-house",
  "solar-midrise",
  "school",
  "office",
  "bakery",
  "bungalow",
  "clinic",
];

export function archetype_for(
  buildingId: string,
  appliances: ApplianceSnapshot[],
  weight = 1,
): Archetype {
  const numericId = Number(buildingId.match(/\d+/)?.[0]);
  if (Number.isInteger(numericId) && numericId > 0 && numericId <= ID_ARCHETYPES.length) {
    return ID_ARCHETYPES[numericId - 1];
  }
  if (appliances.some((appliance) => appliance.appliance_type === "medical_device")) {
    return "clinic";
  }
  if (appliances.filter((appliance) => appliance.appliance_type.startsWith("split_ac_")).length >= 3) {
    return "office";
  }
  if (appliances.some((appliance) => appliance.appliance_type.startsWith("ev_charger_"))) {
    return "bungalow";
  }
  if (weight >= 6) return "apartment";
  return "row-house";
}

export const ARCHETYPE_LABELS: Record<Archetype, string> = {
  clinic: "Clinic",
  hospital: "Hospital",
  apartment: "Apartment",
  bungalow: "Bungalow",
  shop: "Kirana",
  "row-house": "Row house",
  "solar-midrise": "Solar mid-rise",
  school: "School",
  office: "Office",
  bakery: "Bakery",
};
