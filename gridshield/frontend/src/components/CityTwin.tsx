import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ApplianceSnapshot,
  BuildingSnapshot,
  ScenarioBuildingConfig,
} from "../types";
import { buildingArchetypeLabel, getBuildingStatus } from "../scene/buildings";
import { archetype_for } from "../scene/archetypes";
import { estimateThreePhaseCurrentA } from "../scene/feederEstimate";
import { createStage, type CityStage, type LabelProjection } from "../scene/createStage";

export interface CityBuilding {
  building_id: string;
  weight_k: number;
  demand_kw: number;
  estimated_current_a: number;
  appliances: ApplianceSnapshot[];
}

interface CityTwinProps {
  buildings: CityBuilding[];
  selectedBuildingId: string | null;
  onSelectBuilding: (buildingId: string) => void;
  isLive: boolean;
  demandPu: number | null;
  generationPu: number | null;
  isPaused: boolean;
}

export function scenarioBuildings(config: ScenarioBuildingConfig[]): CityBuilding[] {
  return config.map((building) => ({
    building_id: building.building_id,
    weight_k: building.weight_k,
    demand_kw: building.appliances.reduce(
      (sum, appliance) => sum + appliance.rated_power_kw * building.weight_k,
      0,
    ),
    estimated_current_a: estimateThreePhaseCurrentA(
      building.appliances.reduce(
        (sum, appliance) => sum + appliance.rated_power_kw * building.weight_k,
        0,
      ),
    ),
    appliances: building.appliances.map((appliance) => ({
      ...appliance,
      rated_power_kw: appliance.rated_power_kw * building.weight_k,
      state: "ON",
      current_power_kw: appliance.rated_power_kw * building.weight_k,
    })),
  }));
}

export function liveBuildings(snapshot: BuildingSnapshot[]): CityBuilding[] {
  return snapshot.map((building) => ({
    building_id: building.building_id,
    weight_k: building.weight_k,
    demand_kw: building.demand_kw,
    estimated_current_a: estimateThreePhaseCurrentA(building.demand_kw),
    appliances: building.appliances,
  }));
}

export function getRenderedBuildings(buildings: CityBuilding[]): CityBuilding[] {
  const ordered = [...buildings].sort((a, b) => a.building_id.localeCompare(b.building_id));
  if (ordered.length <= 12) return ordered;
  return Array.from({ length: 12 }, (_, index) => {
    const sampleIndex = Math.round(index * (ordered.length - 1) / 11);
    return ordered[sampleIndex];
  });
}

function stateClass(building: CityBuilding): string {
  return `state-${getBuildingStatus(building)}`;
}

export default function CityTwin({
  buildings,
  selectedBuildingId,
  onSelectBuilding,
  isLive,
  demandPu,
  generationPu,
  isPaused,
}: CityTwinProps): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<CityStage | null>(null);
  const labelRefs = useRef(new Map<string, HTMLDivElement>());
  const selectedRef = useRef(selectedBuildingId);
  const onSelectRef = useRef(onSelectBuilding);
  const hoveredRef = useRef<string | null>(null);
  const [stageError, setStageError] = useState<string | null>(null);
  const orderedBuildings = useMemo(
    () => [...buildings].sort((a, b) => a.building_id.localeCompare(b.building_id)),
    [buildings],
  );
  const representativeBuildings = useMemo(() => {
    return getRenderedBuildings(orderedBuildings);
  }, [orderedBuildings]);
  const householdEquivalents = useMemo(
    () => orderedBuildings.reduce((total, building) => {
      const archetype = archetype_for(
        building.building_id,
        building.appliances,
        building.weight_k,
      );
      return total + (
        archetype === "apartment" ||
        archetype === "bungalow" ||
        archetype === "row-house" ||
        archetype === "solar-midrise"
          ? building.weight_k
          : 0
      );
    }, 0),
    [orderedBuildings],
  );
  selectedRef.current = selectedBuildingId;
  onSelectRef.current = onSelectBuilding;

  const updateLabels = useCallback((projections: LabelProjection[]) => {
    projections.forEach((projection) => {
      const element = labelRefs.current.get(projection.buildingId);
      if (!element) return;
      const detailed = projection.buildingId === selectedRef.current || projection.buildingId === hoveredRef.current;
      element.style.transform = `translate3d(${projection.x}px, ${projection.y}px, 0)`;
      element.style.opacity = projection.visible ? "1" : "0";
      element.classList.toggle("detailed", detailed);
    });
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    try {
      const stage = createStage(canvas, {
        select: (buildingId) => onSelectRef.current(buildingId),
        hover: (buildingId) => {
          hoveredRef.current = buildingId;
        },
        labels: updateLabels,
      });
      stageRef.current = stage;
      const resize = new ResizeObserver((entries) => {
        const bounds = entries[0]?.contentRect;
        if (bounds) stage.resize(bounds.width, bounds.height);
      });
      resize.observe(container);
      stage.resize(container.clientWidth, container.clientHeight);
      return () => {
        resize.disconnect();
        stage.dispose();
        stageRef.current = null;
      };
    } catch (error) {
      setStageError(error instanceof Error ? error.message : "WebGL is unavailable in this browser.");
      return undefined;
    }
  }, [updateLabels]);

  useEffect(() => {
    stageRef.current?.updateBuildings(representativeBuildings);
  }, [representativeBuildings]);

  useEffect(() => {
    stageRef.current?.setSelectedBuilding(selectedBuildingId);
  }, [selectedBuildingId]);

  useEffect(() => {
    stageRef.current?.setGridBalance(demandPu, generationPu);
  }, [demandPu, generationPu]);

  useEffect(() => {
    stageRef.current?.setPaused(isPaused);
  }, [isPaused]);

  const labelRef = (buildingId: string) => (element: HTMLDivElement | null) => {
    if (element) labelRefs.current.set(buildingId, element);
    else labelRefs.current.delete(buildingId);
  };

  return (
    <div className="city-stage-shell" ref={containerRef}>
      <canvas
        aria-label={`${representativeBuildings.length} rendered 3D buildings; all are selectable. The simulation includes ${householdEquivalents} residential household equivalents.`}
        className="city-canvas"
        ref={canvasRef}
        role="img"
      />
      {stageError ? (
        <div className="scene-fallback" role="status">
          <strong>3D view unavailable</strong>
          <span>{stageError}</span>
          <span>The building list and telemetry remain available.</span>
        </div>
      ) : null}
      <div className="building-label-layer" aria-hidden="true">
        {representativeBuildings.map((building) => (
          <div
            className={`building-label-chip ${stateClass(building)}`}
            key={building.building_id}
            ref={labelRef(building.building_id)}
          >
            <i />
            <span className="label-building-id">{building.building_id}</span>
            <span className="label-detail">
              {buildingArchetypeLabel(building)} · {building.demand_kw.toFixed(2)} kW
            </span>
          </div>
        ))}
      </div>
      <div className="scene-tools">
        <button type="button" onClick={() => stageRef.current?.streetView()}>Street view</button>
        <button
          type="button"
          disabled={!selectedBuildingId}
          onClick={() => stageRef.current?.focusBuilding(selectedBuildingId)}
        >
          Focus building
        </button>
      </div>
      <div className="scene-caption">
        {representativeBuildings.length} 3D assets · {representativeBuildings.length} selectable
        {householdEquivalents > 0 ? ` · ${householdEquivalents} home equivalents` : ""}
        {isLive ? " · live twin" : " · scenario state"} · current estimate; flow animation is illustrative
      </div>
      <div className="flow-legend" aria-label="Animated power flow legend">
        <i />
        <span>Estimated feeder current</span>
        <small>400 V / 0.95 PF assumption · visual flow, not solved network power flow</small>
      </div>
      <div className="building-keyboard-list" aria-label="Select a representative building">
        <span>
          Buildings {representativeBuildings.length < orderedBuildings.length
            ? `· showing ${representativeBuildings.length} of ${orderedBuildings.length}`
            : ""}
        </span>
        {representativeBuildings.map((building) => (
          <button
            aria-pressed={selectedBuildingId === building.building_id}
            key={building.building_id}
            onClick={() => onSelectRef.current(building.building_id)}
            type="button"
          >
            {building.building_id} — {buildingArchetypeLabel(building)}, {building.demand_kw.toFixed(2)} kW
          </button>
        ))}
      </div>
      {orderedBuildings.length === 0 ? (
        <div className="scene-empty">
          <strong>No buildings in this scenario</strong>
          <span>Choose a scenario with a configured building model.</span>
        </div>
      ) : null}
    </div>
  );
}
