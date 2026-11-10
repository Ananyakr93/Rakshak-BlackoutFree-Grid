import * as THREE from "three";

interface FlowBranch {
  buildingId: string;
  curve: THREE.CatmullRomCurve3;
  line: THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>;
  particles: THREE.Mesh[];
  demandKw: number;
  estimatedCurrentA: number;
}

export interface PowerLineNetwork {
  group: THREE.Group;
  setBuildingDemand(buildingId: string, demandKw: number, estimatedCurrentA: number): void;
  setSupplyRatio(ratio: number): void;
  update(delta: number, paused: boolean): void;
  dispose(): void;
}

export function createPowerLines(
  polePositions: THREE.Vector3[],
  buildingPositions: Map<string, THREE.Vector3>,
): PowerLineNetwork {
  const group = new THREE.Group();
  const branches = new Map<string, FlowBranch>();
  const particleGeometry = new THREE.SphereGeometry(0.13, 8, 6);
  const trunkMaterial = new THREE.LineBasicMaterial({
    color: "#77a7b6",
    transparent: true,
    opacity: 0.58,
  });
  const systemMaterial = new THREE.MeshBasicMaterial({ color: "#8fd5e2" });
  const energizedColor = new THREE.Color("#8fd5e2");
  const constrainedColor = new THREE.Color("#e6b868");
  const criticalColor = new THREE.Color("#e17d75");
  let supplyRatio = 1;
  let activeTime = 0;
  let totalDemandKw = 0;
  let totalCurrentA = 0;

  const createBranch = (
    buildingId: string,
    points: THREE.Vector3[],
    material = new THREE.LineBasicMaterial({
      color: energizedColor,
      transparent: true,
      opacity: 0.68,
    }),
  ) => {
    const curve = new THREE.CatmullRomCurve3(points);
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(curve.getPoints(32)),
      material,
    );
    line.userData.buildingId = buildingId;
    group.add(line);
    const particles = Array.from({ length: 4 }, () => {
      const particle = new THREE.Mesh(particleGeometry, systemMaterial.clone());
      particle.visible = false;
      particle.userData.buildingId = buildingId;
      group.add(particle);
      return particle;
    });
    branches.set(buildingId, {
      buildingId,
      curve,
      line,
      particles,
      demandKw: 0,
      estimatedCurrentA: 0,
    });
  };

  const trunk = polePositions.map((position, index) =>
    new THREE.Vector3(position.x, 6.2 - (index % 2) * 0.16, position.z),
  );
  if (trunk.length >= 2) createBranch("__trunk", trunk, trunkMaterial);

  buildingPositions.forEach((position, buildingId) => {
    const nearest = polePositions.reduce((closest, pole) =>
      Math.abs(pole.x - position.x) < Math.abs(closest.x - position.x) ? pole : closest,
    );
    createBranch(buildingId, [
      new THREE.Vector3(nearest.x, 6.2, nearest.z),
      new THREE.Vector3((nearest.x + position.x) / 2, 5.9, (nearest.z + position.z) / 2),
      new THREE.Vector3(position.x, 4.8, position.z),
    ]);
  });

  return {
    group,
    setBuildingDemand(buildingId, demandKw, estimatedCurrentA) {
      const branch = branches.get(buildingId);
      if (!branch) return;
      totalDemandKw += demandKw - branch.demandKw;
      branch.demandKw = Math.max(0, demandKw);
      totalCurrentA += estimatedCurrentA - branch.estimatedCurrentA;
      branch.estimatedCurrentA = Math.max(0, estimatedCurrentA);
      const trunkBranch = branches.get("__trunk");
      if (trunkBranch) {
        trunkBranch.demandKw = totalDemandKw;
        trunkBranch.estimatedCurrentA = totalCurrentA;
      }
    },
    setSupplyRatio(ratio) {
      supplyRatio = THREE.MathUtils.clamp(ratio, 0, 1);
    },
    update(delta, paused) {
      if (!paused) activeTime += delta;
      const tint = supplyRatio >= 0.92
        ? energizedColor
        : supplyRatio >= 0.75
          ? constrainedColor
          : criticalColor;
      branches.forEach((branch) => {
        branch.line.material.color.copy(tint);
        const loadRatio = Math.min(
          1,
          branch.estimatedCurrentA / Math.max(1, totalCurrentA),
        );
        branch.particles.forEach((particle, index) => {
          particle.visible = branch.demandKw > 0;
          if (!particle.visible) return;
          const speed = 0.22 + Math.min(1, Math.sqrt(branch.estimatedCurrentA) / 12) * 0.48;
          const progress = (activeTime * speed + index / branch.particles.length) % 1;
          branch.curve.getPointAt(progress, particle.position);
          const material = particle.material as THREE.MeshBasicMaterial;
          material.color.copy(tint);
          material.opacity = 0.6 + loadRatio * 0.4;
          particle.scale.setScalar(0.8 + loadRatio * 0.65);
        });
      });
    },
    dispose() {
      branches.forEach((branch) => {
        branch.line.geometry.dispose();
        if (branch.line.material !== trunkMaterial) branch.line.material.dispose();
        branch.particles.forEach((particle) => {
          if (Array.isArray(particle.material)) {
            particle.material.forEach((material) => material.dispose());
          } else {
            particle.material.dispose();
          }
        });
      });
      particleGeometry.dispose();
      systemMaterial.dispose();
      trunkMaterial.dispose();
    },
  };
}
