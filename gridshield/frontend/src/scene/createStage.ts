import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { CityBuilding } from "../components/CityTwin";
import { createBuildingRig, type BuildingRig } from "./buildings";
import { positionForBuilding } from "./cityLayout";
import { createEnvironment } from "./environment";
import { createPowerLines, type PowerLineNetwork } from "./powerLines";
import { createStreetFurniture } from "./streetFurniture";

export interface LabelProjection {
  buildingId: string;
  x: number;
  y: number;
  visible: boolean;
}

export interface StageCallbacks {
  select(buildingId: string): void;
  hover(buildingId: string | null): void;
  labels(projections: LabelProjection[]): void;
}

interface StageBuilding {
  model: CityBuilding;
  rig: BuildingRig;
}

export function canReuseBuildingRigs(
  existing: ReadonlyMap<string, unknown>,
  nextBuildings: CityBuilding[],
): boolean {
  return existing.size === nextBuildings.length &&
    nextBuildings.every((building) => existing.has(building.building_id));
}

export interface CityStage {
  resize(width: number, height: number): void;
  updateBuildings(buildings: CityBuilding[]): void;
  setSelectedBuilding(buildingId: string | null): void;
  focusBuilding(buildingId: string | null): void;
  streetView(): void;
  setGridBalance(demandPu: number | null, generationPu: number | null): void;
  setPaused(paused: boolean): void;
  dispose(): void;
}

export function createStage(canvas: HTMLCanvasElement, callbacks: StageCallbacks): CityStage {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor("#202d3b");
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#202d3b");
  scene.fog = new THREE.Fog("#202d3b", 38, 94);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 140);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = !reducedMotion;
  controls.dampingFactor = 0.075;
  controls.minPolarAngle = Math.PI * 0.18;
  controls.maxPolarAngle = Math.PI * 0.48;
  controls.minDistance = 11;
  controls.maxDistance = 39;
  const defaultCamera = new THREE.Vector3(0, 17, 26);
  const defaultTarget = new THREE.Vector3(0, 2.8, 0);
  camera.position.copy(defaultCamera);
  controls.target.copy(defaultTarget);
  controls.update();

  const environment = createEnvironment();
  scene.add(environment.group);
  const streetFurniture = createStreetFurniture();
  scene.add(streetFurniture.group);
  let powerLines: PowerLineNetwork | null = null;
  const buildings = new Map<string, StageBuilding>();
  const pickables: THREE.Object3D[] = [];
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const projected = new THREE.Vector3();
  const targetCamera = new THREE.Vector3();
  const targetFocus = new THREE.Vector3();
  let focusAnimating = false;
  let hoveredId: string | null = null;
  let disposed = false;
  let frameHandle = 0;
  let previousTime = 0;
  let simulationPaused = false;
  const labelPoints = new Map<string, THREE.Vector3>();
  const labelProjectionMap = new Map<string, LabelProjection>();
  const labelProjections: LabelProjection[] = [];

  const getBuildingAtPointer = (event: PointerEvent): string | null => {
    const bounds = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(pickables, false)[0];
    return typeof hit?.object.userData.buildingId === "string"
      ? hit.object.userData.buildingId
      : null;
  };

  const onPointerMove = (event: PointerEvent) => {
    const next = getBuildingAtPointer(event);
    if (next !== hoveredId) {
      hoveredId = next;
      buildings.forEach(({ rig }, buildingId) => rig.setHovered(buildingId === next));
      callbacks.hover(next);
      renderer.domElement.style.cursor = next ? "pointer" : "grab";
    }
  };
  const onPointerDown = (event: PointerEvent) => {
    const id = getBuildingAtPointer(event);
    if (id) callbacks.select(id);
  };
  const onDoubleClick = (event: MouseEvent) => {
    const id = getBuildingAtPointer(event as unknown as PointerEvent);
    if (id) focusBuilding(id);
  };

  function focusBuilding(buildingId: string | null): void {
    if (!buildingId) return;
    const entry = buildings.get(buildingId);
    if (!entry) return;
    targetFocus.copy(entry.rig.group.position).add(new THREE.Vector3(0, 2.5, 0));
    targetCamera.copy(entry.rig.group.position).add(new THREE.Vector3(8, 8.5, 11));
    focusAnimating = true;
  }

  function streetView(): void {
    targetCamera.copy(defaultCamera);
    targetFocus.copy(defaultTarget);
    focusAnimating = true;
  }

  function setSelectedBuilding(buildingId: string | null): void {
    buildings.forEach(({ rig }, id) => rig.setSelected(id === buildingId));
  }

  function updateBuildings(nextBuildings: CityBuilding[]): void {
    const sorted = [...nextBuildings].sort((a, b) => a.building_id.localeCompare(b.building_id));
    const sameIds = canReuseBuildingRigs(buildings, sorted);
    if (!sameIds) {
      buildings.forEach(({ rig }) => {
        scene.remove(rig.group);
        rig.dispose();
      });
      buildings.clear();
      pickables.length = 0;
      labelPoints.clear();
      labelProjectionMap.clear();
      labelProjections.length = 0;
      sorted.forEach((building, index) => {
        const rig = createBuildingRig(building, index);
        rig.group.position.copy(positionForBuilding(index, sorted.length, building.building_id));
        rig.group.traverse((object) => {
          if (object instanceof THREE.Mesh && object.parent === rig.group) {
            object.userData.buildingId = building.building_id;
            pickables.push(object);
          }
        });
        scene.add(rig.group);
        buildings.set(building.building_id, { model: building, rig });
        labelPoints.set(building.building_id, rig.labelAnchor.clone());
        const label = { buildingId: building.building_id, x: 0, y: 0, visible: false };
        labelProjectionMap.set(building.building_id, label);
        labelProjections.push(label);
      });
      if (powerLines) {
        scene.remove(powerLines.group);
        powerLines.dispose();
      }
      const positions = new Map<string, THREE.Vector3>();
      buildings.forEach(({ rig }, id) => positions.set(id, rig.group.position.clone()));
      powerLines = createPowerLines(streetFurniture.polePositions, positions);
      scene.add(powerLines.group);
    } else {
      sorted.forEach((building) => {
        const entry = buildings.get(building.building_id);
        if (entry) {
          entry.model = building;
          entry.rig.setBuilding(building);
        }
      });
    }
  }

  function resize(width: number, height: number): void {
    const safeWidth = Math.max(1, width);
    const safeHeight = Math.max(1, height);
    renderer.setSize(safeWidth, safeHeight, false);
    camera.aspect = safeWidth / safeHeight;
    camera.updateProjectionMatrix();
  }

  function render(time: number): void {
    if (disposed) return;
    const elapsed = time / 1000;
    const delta = previousTime ? Math.min((time - previousTime) / 1000, 0.05) : 0.016;
    previousTime = time;
    buildings.forEach(({ model, rig }, id) => {
      rig.update(delta, reducedMotion ? 0 : elapsed, reducedMotion);
      powerLines?.setBuildingDemand(
        id,
        model.demand_kw,
        model.estimated_current_a,
      );
    });
    powerLines?.update(delta, simulationPaused || reducedMotion);
    if (focusAnimating) {
      camera.position.lerp(targetCamera, Math.min(1, delta * 4.5));
      controls.target.lerp(targetFocus, Math.min(1, delta * 4.5));
      if (camera.position.distanceTo(targetCamera) < 0.08 && controls.target.distanceTo(targetFocus) < 0.08) {
        focusAnimating = false;
      }
    }
    controls.update();
    const width = renderer.domElement.clientWidth;
    const height = renderer.domElement.clientHeight;
    labelProjections.length = 0;
    buildings.forEach(({ rig }, buildingId) => {
      const anchor = labelPoints.get(buildingId);
      const projection = labelProjectionMap.get(buildingId);
      if (!anchor || !projection) return;
      projected.copy(anchor).add(rig.group.position).project(camera);
      projection.x = ((projected.x + 1) * width) / 2;
      projection.y = ((1 - projected.y) * height) / 2;
      projection.visible = projected.z > -1 && projected.z < 1;
      labelProjections.push(projection);
    });
    callbacks.labels(labelProjections);
    renderer.render(scene, camera);
    frameHandle = window.requestAnimationFrame(render);
  }

  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("dblclick", onDoubleClick);
  frameHandle = window.requestAnimationFrame(render);

  return {
    resize,
    updateBuildings,
    setSelectedBuilding,
    focusBuilding,
    streetView,
    setGridBalance(demandPu, generationPu) {
      if (demandPu === null || generationPu === null) {
        powerLines?.setSupplyRatio(1);
        return;
      }
      powerLines?.setSupplyRatio(generationPu / Math.max(demandPu, 0.001));
    },
    setPaused(paused) {
      simulationPaused = paused;
    },
    dispose() {
      disposed = true;
      window.cancelAnimationFrame(frameHandle);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("dblclick", onDoubleClick);
      controls.dispose();
      buildings.forEach(({ rig }) => rig.dispose());
      buildings.clear();
      powerLines?.dispose();
      streetFurniture.dispose();
      environment.dispose();
      renderer.dispose();
    },
  };
}
