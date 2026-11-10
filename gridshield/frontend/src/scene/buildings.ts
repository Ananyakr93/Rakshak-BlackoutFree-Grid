import * as THREE from "three";
import type { CityBuilding } from "../components/CityTwin";
import { ARCHETYPE_LABELS, archetype_for } from "./archetypes";
import { getBuildingVisualState, type BuildingVisualState } from "./buildingState";

export interface BuildingRig {
  group: THREE.Group;
  labelAnchor: THREE.Vector3;
  archetypeName: string;
  setBuilding(building: CityBuilding): void;
  setSelected(selected: boolean): void;
  setHovered(hovered: boolean): void;
  update(delta: number, elapsed: number, reducedMotion: boolean): void;
  dispose(): void;
}

const BODY_COLORS = ["#6c777f", "#727c72", "#83796c", "#687682", "#847d70", "#697b78"];
const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
const sphereGeometry = new THREE.SphereGeometry(1, 10, 8);
const coneGeometry = new THREE.ConeGeometry(1, 1, 5);
const cylinderGeometry = new THREE.CylinderGeometry(1, 1, 1, 8);
const litWindowColor = new THREE.Color("#e5c992");
const darkWindowColor = new THREE.Color("#303945");
const litWindowEmission = new THREE.Color("#e4a344");
const darkWindowEmission = new THREE.Color("#111820");
const blackoutColor = new THREE.Color("#202630");

function stableFraction(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

const ARCHETYPE_SIZES: Record<string, { width: number; height: number; depth: number; floors: number }> = {
  clinic: { width: 3.6, height: 3.8, depth: 3.1, floors: 2 },
  hospital: { width: 5.2, height: 5.1, depth: 4.2, floors: 3 },
  apartment: { width: 4.4, height: 8.4, depth: 3.4, floors: 5 },
  bungalow: { width: 4.2, height: 2.8, depth: 3.8, floors: 1 },
  shop: { width: 3.7, height: 3.0, depth: 3.4, floors: 1 },
  "row-house": { width: 2.7, height: 4.3, depth: 3.1, floors: 2 },
  "solar-midrise": { width: 4.0, height: 6.2, depth: 3.4, floors: 3 },
  school: { width: 6.0, height: 3.5, depth: 4.0, floors: 1 },
  office: { width: 4.6, height: 7.2, depth: 3.8, floors: 4 },
  bakery: { width: 4.3, height: 3.5, depth: 3.6, floors: 1 },
};

function mesh(
  geometry: THREE.BufferGeometry,
  material: THREE.Material,
  position: THREE.Vector3,
  scale: THREE.Vector3,
): THREE.Mesh {
  const object = new THREE.Mesh(geometry, material);
  object.position.copy(position);
  object.scale.copy(scale);
  object.castShadow = false;
  object.receiveShadow = false;
  return object;
}

export function createBuildingRig(building: CityBuilding, index: number): BuildingRig {
  const archetype = archetype_for(building.building_id, building.appliances, building.weight_k);
  const size = ARCHETYPE_SIZES[archetype];
  const applianceTypes = building.appliances.map((appliance) => appliance.appliance_type);
  const hasMedical = applianceTypes.includes("medical_device");
  const hasPump = applianceTypes.includes("water_pump");
  const hasAc = applianceTypes.some((type) => type.startsWith("split_ac_"));
  const acCount = Math.min(3, applianceTypes.filter((type) => type.startsWith("split_ac_")).length);
  const hasInverter = applianceTypes.includes("inverter_backed_load");
  const hasGeyser = applianceTypes.includes("geyser_15l");
  const hasEv = applianceTypes.some((type) => type.startsWith("ev_charger_"));
  const hasRefrigerator = applianceTypes.includes("refrigerator");
  const group = new THREE.Group();
  const walls = new THREE.MeshStandardMaterial({
    color: BODY_COLORS[index % BODY_COLORS.length],
    roughness: 0.91,
    metalness: 0.02,
  });
  const normalWallColor = new THREE.Color(BODY_COLORS[index % BODY_COLORS.length]);
  const roofMaterial = new THREE.MeshStandardMaterial({ color: "#454c56", roughness: 0.9 });
  const trimMaterial = new THREE.MeshStandardMaterial({ color: "#b3a68d", roughness: 0.82 });
  const darkMaterial = new THREE.MeshStandardMaterial({ color: "#171e28", roughness: 0.68 });
  const windows: THREE.Mesh[] = [];
  const windowMaterials: THREE.MeshStandardMaterial[] = [];
  const groupBody = mesh(
    boxGeometry,
    walls,
    new THREE.Vector3(0, size.height / 2 + 0.18, 0),
    new THREE.Vector3(size.width, size.height, size.depth),
  );
  group.add(groupBody);
  group.add(mesh(boxGeometry, roofMaterial, new THREE.Vector3(0, size.height + 0.2, 0),
    new THREE.Vector3(size.width + 0.18, 0.24, size.depth + 0.18)));

  const windowRows = Math.max(1, size.floors);
  const perRow = Math.max(2, Math.floor(size.width / 0.8));
  for (let floor = 0; floor < windowRows; floor += 1) {
    for (let column = 0; column < perRow; column += 1) {
      const x = -size.width / 2 + (column + 0.7) * (size.width / (perRow + 0.4));
      const y = 0.72 + floor * (size.height / (windowRows + 0.25));
      const windowMesh = mesh(
        boxGeometry,
        new THREE.MeshStandardMaterial({ color: "#303945", emissive: "#111820", roughness: 0.7 }),
        new THREE.Vector3(x, y, size.depth / 2 + 0.035),
        new THREE.Vector3(0.42, archetype === "shop" ? 0.72 : 0.58, 0.055),
      );
      windows.push(windowMesh);
      windowMaterials.push(windowMesh.material as THREE.MeshStandardMaterial);
      group.add(windowMesh);
    }
  }

  const acFans: THREE.Group[] = [];
  const fridgeGlows: THREE.Mesh[] = [];
  const tank = new THREE.Group();
  const medicalSign = new THREE.Group();
  const inverterLed = new THREE.Mesh(
    sphereGeometry,
    new THREE.MeshStandardMaterial({ color: "#273b2f", emissive: "#45b96d", emissiveIntensity: 0 }),
  );
  inverterLed.visible = hasInverter;
  inverterLed.position.set(size.width * 0.38, size.height + 0.34, size.depth * 0.32);
  inverterLed.scale.setScalar(0.11);
  const tankWater = new THREE.Mesh(
    cylinderGeometry,
    new THREE.MeshStandardMaterial({ color: "#3d82b3", transparent: true, opacity: 0.62, roughness: 0.4 }),
  );
  let tankLevel = 0.24;
  const pumpPipe = new THREE.Mesh(
    boxGeometry,
    new THREE.MeshStandardMaterial({ color: "#3479b7", emissive: "#348bd1", emissiveIntensity: 0 }),
  );
  pumpPipe.visible = hasPump;
  group.add(pumpPipe);
  tankWater.visible = hasPump || archetype === "apartment" || archetype === "row-house";
  tankWater.scale.set(0.48, tankLevel, 0.48);
  tankWater.position.set(size.width * 0.24, size.height + 0.5, 0);
  group.add(tankWater);
  const steam = new THREE.Group();
  const evRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.46, 0.04, 6, 24),
    new THREE.MeshStandardMaterial({ color: "#39d477", emissive: "#39d477", emissiveIntensity: 0 }),
  );
  const evPort = new THREE.Mesh(
    sphereGeometry,
    new THREE.MeshStandardMaterial({ color: "#39434b", emissive: "#36d17a", emissiveIntensity: 0 }),
  );

  if (archetype === "bungalow") {
    const leftRoof = mesh(boxGeometry, roofMaterial, new THREE.Vector3(-0.88, size.height + 0.54, 0),
      new THREE.Vector3(size.width * 0.58, 0.18, size.depth + 0.25));
    leftRoof.rotation.z = 0.32;
    const rightRoof = mesh(boxGeometry, roofMaterial, new THREE.Vector3(0.88, size.height + 0.54, 0),
      new THREE.Vector3(size.width * 0.58, 0.18, size.depth + 0.25));
    rightRoof.rotation.z = -0.32;
    group.add(leftRoof, rightRoof);
  } else if (archetype === "row-house" && index % 2 === 1) {
    const ridge = mesh(coneGeometry, roofMaterial, new THREE.Vector3(0, size.height + 0.45, 0),
      new THREE.Vector3(size.width * 0.68, 0.92, size.depth * 0.72));
    ridge.rotation.y = Math.PI / 4;
    group.add(ridge);
  }

  if (["clinic", "hospital", "apartment", "shop", "row-house", "solar-midrise", "school", "office", "bakery"].includes(archetype)) {
    const door = mesh(boxGeometry, darkMaterial, new THREE.Vector3(0, 0.72, size.depth / 2 + 0.05),
      new THREE.Vector3(0.58, 1.42, 0.08));
    group.add(door);
    const step = mesh(boxGeometry, trimMaterial, new THREE.Vector3(0, 0.14, size.depth / 2 + 0.22),
      new THREE.Vector3(0.9, 0.14, 0.42));
    group.add(step);
  }

  if ((archetype === "clinic" || archetype === "hospital") && hasMedical) {
    const crossMaterial = new THREE.MeshStandardMaterial({ color: "#ff71a7", emissive: "#ff5b98", emissiveIntensity: 1.4 });
    const crossVert = mesh(boxGeometry, crossMaterial, new THREE.Vector3(0, size.height - 0.1, size.depth / 2 + 0.18),
      new THREE.Vector3(0.22, 0.85, 0.1));
    const crossHoriz = mesh(boxGeometry, crossMaterial, new THREE.Vector3(0, size.height - 0.1, size.depth / 2 + 0.18),
      new THREE.Vector3(0.85, 0.22, 0.1));
    medicalSign.add(crossVert, crossHoriz);
    group.add(medicalSign);
  }

  if (tankWater.visible) {
    const tankBody = mesh(cylinderGeometry, trimMaterial, new THREE.Vector3(size.width * 0.24, size.height + 0.64, 0),
      new THREE.Vector3(0.62, 0.86, 0.62));
    tank.add(tankBody);
    group.add(tank);
  }

  if (hasAc) {
    for (let unit = 0; unit < acCount; unit += 1) {
      const x = -0.85 + unit * 0.85;
      const unitGroup = new THREE.Group();
      const ac = mesh(boxGeometry, trimMaterial, new THREE.Vector3(x, size.height + 0.38, size.depth * 0.28),
        new THREE.Vector3(0.64, 0.34, 0.48));
      const fan = new THREE.Group();
      fan.position.set(x, size.height + 0.4, size.depth * 0.28);
      const fanMat = new THREE.MeshStandardMaterial({ color: "#303943", metalness: 0.3, roughness: 0.65 });
      for (let blade = 0; blade < 4; blade += 1) {
        const bladeMesh = mesh(boxGeometry, fanMat, new THREE.Vector3(0, 0, 0.26),
          new THREE.Vector3(0.32, 0.04, 0.025));
        bladeMesh.rotation.z = blade * Math.PI / 2;
        fan.add(bladeMesh);
      }
      unitGroup.add(ac, fan);
      group.add(unitGroup);
      acFans.push(fan);
    }
  }

  if (archetype === "solar-midrise" || hasInverter) {
    for (let panel = 0; panel < 4; panel += 1) {
      const solar = mesh(boxGeometry,
        new THREE.MeshStandardMaterial({ color: "#344c62", emissive: "#234b70", emissiveIntensity: 0.16, metalness: 0.4 }),
        new THREE.Vector3(-1.25 + (panel % 2) * 1.05, size.height + 0.42, -0.45 + Math.floor(panel / 2) * 0.75),
        new THREE.Vector3(0.82, 0.08, 0.58));
      solar.rotation.x = -0.08;
      group.add(solar);
    }
    if (hasInverter) group.add(inverterLed);
  }

  if (archetype === "school") {
    const flagpole = mesh(cylinderGeometry, trimMaterial, new THREE.Vector3(size.width * 0.38, size.height + 1.0, 0),
      new THREE.Vector3(0.04, 1.9, 0.04));
    const flag = mesh(boxGeometry, new THREE.MeshStandardMaterial({ color: "#b85e4b" }),
      new THREE.Vector3(size.width * 0.38 + 0.25, size.height + 1.55, 0),
      new THREE.Vector3(0.48, 0.25, 0.035));
    group.add(flagpole, flag);
  }

  if (archetype === "bakery") {
    const chimney = mesh(boxGeometry, new THREE.MeshStandardMaterial({ color: "#765b4a" }),
      new THREE.Vector3(size.width * 0.34, size.height + 0.68, -0.55),
      new THREE.Vector3(0.44, 1.15, 0.46));
    group.add(chimney);
  }

  if (archetype === "bungalow" && hasEv) {
    const car = mesh(boxGeometry, new THREE.MeshStandardMaterial({ color: "#b19448", metalness: 0.3, roughness: 0.5 }),
      new THREE.Vector3(size.width * 0.35, 0.42, size.depth / 2 + 1.1),
      new THREE.Vector3(1.55, 0.56, 0.78));
    const cabin = mesh(boxGeometry, new THREE.MeshStandardMaterial({ color: "#59646c", roughness: 0.4 }),
      new THREE.Vector3(size.width * 0.35, 0.77, size.depth / 2 + 1.1),
      new THREE.Vector3(0.86, 0.35, 0.66));
    evRing.position.set(size.width * 0.35 + 0.79, 0.54, size.depth / 2 + 1.1);
    evPort.position.set(size.width * 0.35 + 0.79, 0.55, size.depth / 2 + 1.1);
    evPort.scale.setScalar(0.09);
    group.add(car, cabin, evRing, evPort);
  }

  if (archetype === "shop") {
    const awning = mesh(boxGeometry, new THREE.MeshStandardMaterial({ color: "#95584a" }),
      new THREE.Vector3(0, size.height * 0.5, size.depth / 2 + 0.28),
      new THREE.Vector3(size.width * 0.78, 0.28, 0.52));
    group.add(awning);
  }

  if (hasRefrigerator) {
    const fridgeGlow = mesh(boxGeometry,
      new THREE.MeshStandardMaterial({ color: "#9bd5ed", emissive: "#57a9d8", emissiveIntensity: 0 }),
      new THREE.Vector3(-size.width * 0.3, 0.85, size.depth / 2 + 0.1),
      new THREE.Vector3(0.25, 0.62, 0.06));
    fridgeGlows.push(fridgeGlow);
    group.add(fridgeGlow);
  }

  const steamMaterial = new THREE.MeshBasicMaterial({ color: "#c7d0d5", transparent: true, opacity: 0 });
  if (hasGeyser) {
    for (let puff = 0; puff < 3; puff += 1) {
      const cloud = new THREE.Mesh(sphereGeometry, steamMaterial);
      cloud.scale.setScalar(0.1 + puff * 0.04);
      cloud.position.set(size.width * 0.35, size.height + 0.6 + puff * 0.25, 0);
      steam.add(cloud);
    }
    group.add(steam);
  }
  const stateBar = new THREE.Mesh(
    boxGeometry,
    new THREE.MeshBasicMaterial({ color: "#6f9d83" }),
  );
  stateBar.scale.set(0.075, 0.65, 0.075);
  stateBar.position.set(size.width / 2 + 0.15, 0.58, size.depth / 2 + 0.05);
  group.add(stateBar);
  const baseRing = new THREE.Mesh(
    new THREE.TorusGeometry(Math.max(size.width, size.depth) * 0.55, 0.055, 5, 40),
    new THREE.MeshBasicMaterial({ color: "#d19a43", transparent: true, opacity: 0.7 }),
  );
  baseRing.rotation.x = Math.PI / 2;
  baseRing.position.y = 0.1;
  group.add(baseRing);
  const selectionRing = new THREE.Mesh(
    new THREE.TorusGeometry(Math.max(size.width, size.depth) * 0.62, 0.065, 6, 48),
    new THREE.MeshStandardMaterial({
        color: "#7a9db7",
        emissive: "#344d5c",
        emissiveIntensity: 0.35,
      transparent: true,
      opacity: 0.85,
    }),
  );
  selectionRing.rotation.x = Math.PI / 2;
  selectionRing.position.y = 0.17;
  selectionRing.visible = false;
  group.add(selectionRing);
  const beaconStem = mesh(cylinderGeometry, new THREE.MeshStandardMaterial({
    color: "#8e3542",
    emissive: "#c33e4b",
    emissiveIntensity: 0,
  }), new THREE.Vector3(size.width / 2 + 0.4, size.height + 0.5, 0), new THREE.Vector3(0.035, 0.9, 0.035));
  const beacon = new THREE.Mesh(
    sphereGeometry,
    new THREE.MeshStandardMaterial({ color: "#ec5055", emissive: "#df3e4d", emissiveIntensity: 0 }),
  );
  beacon.position.set(size.width / 2 + 0.4, size.height + 1.0, 0);
  beacon.scale.setScalar(0.15);
  group.add(beaconStem, beacon);

  let visual = getBuildingVisualState(building);
  let restoreProgress = 1;
  let evFlash = 0;
  let lastEvState = visual.evState;
  let hovered = false;
  let selected = false;
  const applyState = (nextBuilding: CityBuilding) => {
    const next = getBuildingVisualState(nextBuilding);
    if (next.restoring && !visual.restoring) restoreProgress = 0;
    if (next.evState === "shed" && lastEvState !== "shed") evFlash = 0.65;
    lastEvState = next.evState;
    visual = next;
  };

  return {
    group,
    labelAnchor: new THREE.Vector3(0, size.height + 1.7, 0),
    archetypeName: ARCHETYPE_LABELS[archetype],
    setBuilding: applyState,
    setSelected(value) {
      selected = value;
      selectionRing.visible = selected;
    },
    setHovered(value) {
      hovered = value;
    },
    update(delta, elapsed, reducedMotion) {
      const blend = Math.min(1, delta * 2.2);
      if (visual.restoring) restoreProgress = Math.min(1, restoreProgress + delta / 1.5);
      windows.forEach((_windowMesh, windowIndex) => {
        const lightingIndex = Math.min(
          visual.lightingStates.length - 1,
          Math.floor(windowIndex * visual.lightingStates.length / Math.max(1, windows.length)),
        );
        const shouldLight = lightingIndex >= 0
          ? visual.lightingStates[lightingIndex]
          : false;
        const material = windowMaterials[windowIndex];
        const restoringWindowReady = !visual.restoring ||
          restoreProgress > stableFraction(`${building.building_id}:${windowIndex}`) * 0.8;
        const desired = shouldLight && !visual.blackout && restoringWindowReady;
        material.emissiveIntensity += ((desired ? 1.15 : 0) - material.emissiveIntensity) * blend;
        material.color.lerp(desired ? litWindowColor : darkWindowColor, blend);
        material.emissive.lerp(desired ? litWindowEmission : darkWindowEmission, blend);
      });
      acFans.forEach((fan) => {
        fan.rotation.z += visual.acRunning && !reducedMotion ? delta * 7 : (0 - fan.rotation.z) * blend;
      });
      const pumpMaterial = pumpPipe.material as THREE.MeshStandardMaterial;
      pumpMaterial.emissiveIntensity = visual.pumpRunning ? 0.55 + Math.sin(elapsed * 4) * 0.18 : 0;
      if (visual.pumpRunning) tankLevel = Math.min(0.8, tankLevel + delta * 0.045);
      tankWater.scale.y = tankLevel;
      tankWater.position.y = size.height + 0.18 + tankLevel * 0.45;
      const signIntensity = visual.medicalRunning && !visual.criticalUnavailable
        ? 1.2 : visual.criticalUnavailable && Math.sin(elapsed * 9) > 0 ? 2 : 0.1;
      medicalSign.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          const material = object.material as THREE.MeshStandardMaterial;
          material.emissiveIntensity = signIntensity;
          if (visual.criticalUnavailable) material.color.set("#ee434c");
          else material.color.set("#ff71a7");
        }
      });
      const ledMaterial = inverterLed.material as THREE.MeshStandardMaterial;
      ledMaterial.emissiveIntensity = visual.inverterRunning ? 1.6 : 0;
      const evMaterial = evPort.material as THREE.MeshStandardMaterial;
      const ringMaterial = evRing.material as THREE.MeshStandardMaterial;
      evFlash = Math.max(0, evFlash - delta);
      const chargePower = visual.evState === "on" ? 1.4 + Math.sin(elapsed * 6) * 0.45 :
        visual.evState === "waiting" ? 1.0 : evFlash > 0 ? 1.5 : 0;
      evMaterial.emissiveIntensity = chargePower;
      ringMaterial.emissiveIntensity = chargePower;
      if (visual.evState === "waiting") {
        evMaterial.emissive.set("#e5a545");
        ringMaterial.emissive.set("#e5a545");
      } else if (evFlash > 0) {
        evMaterial.emissive.set("#e1484e");
        ringMaterial.emissive.set("#e1484e");
      } else {
        evMaterial.emissive.set("#35d479");
        ringMaterial.emissive.set("#35d479");
      }
      evRing.visible = visual.evState !== "off" || evFlash > 0;
      steam.children.forEach((cloud, puff) => {
        cloud.position.y = size.height + 0.6 + puff * 0.25 + (elapsed * 0.3 + puff * 0.3) % 0.4;
        (cloud as THREE.Mesh).material = steamMaterial;
        steamMaterial.opacity = visual.geyserRunning ? 0.16 : 0;
      });
      pumpPipe.visible = hasPump && visual.pumpRunning;
      pumpPipe.position.set(size.width / 2 + 0.18, 0.55 + Math.sin(elapsed * 2) * 0.04, 0);
      pumpPipe.scale.set(0.08, 0.9, 0.08);
      const stateTint = visual.status === "critical" ? "#bc6d70" :
        visual.status === "restoring" ? "#6d9da2" : visual.status === "shed" ? "#b18a50" : "#6f9d83";
      (stateBar.material as THREE.MeshBasicMaterial).color.set(stateTint);
      stateBar.scale.y = Math.max(0.05, visual.demandRatio * 0.8);
      stateBar.position.y = 0.25 + stateBar.scale.y / 2;
      baseRing.visible = visual.shed || visual.restoring || visual.criticalUnavailable;
      (baseRing.material as THREE.MeshBasicMaterial).color.set(
        visual.criticalUnavailable ? "#e44d58" : visual.restoring ? "#39aeb1" : "#d19a43",
      );
      baseRing.material.opacity = visual.criticalUnavailable
        ? 0.45 + Math.max(0, Math.sin(elapsed * 7)) * 0.4 : 0.68;
      const beaconIntensity = visual.criticalUnavailable
        ? 0.6 + Math.max(0, Math.sin(elapsed * 9)) * 1.3 : 0;
      (beacon.material as THREE.MeshStandardMaterial).emissiveIntensity = beaconIntensity;
      (beaconStem.material as THREE.MeshStandardMaterial).emissiveIntensity = beaconIntensity * 0.4;
      beacon.visible = visual.criticalUnavailable;
      beaconStem.visible = visual.criticalUnavailable;
      fridgeGlows.forEach((glow) => {
        (glow.material as THREE.MeshStandardMaterial).emissiveIntensity =
          visual.refrigeratorRunning ? 0.8 : 0;
      });
      groupBody.material = walls;
      walls.color.lerp(visual.blackout ? blackoutColor : normalWallColor, blend);
      walls.emissive.set(visual.criticalUnavailable ? "#5b1d27" : "#000000");
      walls.emissiveIntensity = visual.criticalUnavailable
        ? (0.12 + Math.max(0, Math.sin(elapsed * 8)) * 0.12)
        : hovered ? 0.11 : 0;
      (selectionRing.material as THREE.MeshStandardMaterial).opacity = selected ? 0.78 : 0;
      group.position.y = 0;
    },
    dispose() {
      const materials = new Set<THREE.Material>();
      group.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          if (Array.isArray(object.material)) {
            object.material.forEach((material: THREE.Material) => materials.add(material));
          } else {
            materials.add(object.material);
          }
        }
      });
      materials.forEach((material) => material.dispose());
    },
  };
}

export function getBuildingStatus(building: CityBuilding): BuildingVisualState["status"] {
  return getBuildingVisualState(building).status;
}

export function buildingArchetypeLabel(building: CityBuilding): string {
  return ARCHETYPE_LABELS[archetype_for(building.building_id, building.appliances, building.weight_k)];
}
