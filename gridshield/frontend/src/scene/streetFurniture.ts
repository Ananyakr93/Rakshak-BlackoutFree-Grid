import * as THREE from "three";

export interface StreetFurniture {
  group: THREE.Group;
  polePositions: THREE.Vector3[];
  dispose(): void;
}

function instanced(
  geometry: THREE.BufferGeometry,
  material: THREE.Material,
  positions: THREE.Vector3[],
  scale: THREE.Vector3,
): THREE.InstancedMesh {
  const items = new THREE.InstancedMesh(geometry, material, positions.length);
  const matrix = new THREE.Matrix4();
  const rotation = new THREE.Quaternion();
  positions.forEach((position, index) => {
    matrix.compose(position, rotation, scale);
    items.setMatrixAt(index, matrix);
  });
  items.instanceMatrix.needsUpdate = true;
  return items;
}

export function createStreetFurniture(): StreetFurniture {
  const group = new THREE.Group();
  const poleGeometry = new THREE.CylinderGeometry(0.055, 0.095, 6.2, 6);
  const crossbarGeometry = new THREE.BoxGeometry(0.85, 0.12, 0.12);
  const lampArmGeometry = new THREE.BoxGeometry(0.75, 0.08, 0.08);
  const lampBulbGeometry = new THREE.SphereGeometry(0.13, 8, 6);
  const treeTrunkGeometry = new THREE.CylinderGeometry(0.13, 0.2, 1.5, 6);
  const treeCanopyGeometry = new THREE.ConeGeometry(0.9, 1.65, 6);
  const transformerGeometry = new THREE.BoxGeometry(1.5, 1.25, 1.2);
  const insulatorGeometry = new THREE.CylinderGeometry(0.12, 0.12, 0.35, 6);
  const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  const poleMaterial = new THREE.MeshStandardMaterial({ color: "#454c55", roughness: 0.85 });
  const lampMaterial = new THREE.MeshStandardMaterial({
    color: "#d9b469",
    emissive: "#c99234",
    emissiveIntensity: 1.5,
  });
  const canopyMaterial = new THREE.MeshStandardMaterial({ color: "#233b37", roughness: 1 });
  const trunkMaterial = new THREE.MeshStandardMaterial({ color: "#53473b", roughness: 1 });
  const transformerMaterial = new THREE.MeshStandardMaterial({ color: "#59616b", roughness: 0.8 });
  const insulatorMaterial = new THREE.MeshStandardMaterial({
    color: "#b59c64",
    emissive: "#57411e",
    emissiveIntensity: 0.4,
  });

  const polePositions: THREE.Vector3[] = [];
  const lampPositions: THREE.Vector3[] = [];
  for (let x = -21; x <= 21; x += 7) {
    polePositions.push(new THREE.Vector3(x, 3.1, -3.45));
    lampPositions.push(new THREE.Vector3(x, 2.8, 4.1));
  }
  group.add(instanced(poleGeometry, poleMaterial, polePositions, new THREE.Vector3(1, 1, 1)));
  const crossbarPositions = polePositions.map((pole) => new THREE.Vector3(pole.x, 6.1, pole.z));
  group.add(instanced(crossbarGeometry, poleMaterial, crossbarPositions, new THREE.Vector3(1, 1, 1)));
  polePositions.forEach((pole) => {
    [-0.28, 0, 0.28].forEach((offset) => {
      const insulator = new THREE.Mesh(insulatorGeometry, insulatorMaterial);
      insulator.position.set(pole.x + offset, 6.32, pole.z);
      group.add(insulator);
    });
  });

  const lampPosts = lampPositions.map((position) =>
    new THREE.Vector3(position.x, 2.8, position.z),
  );
  group.add(instanced(poleGeometry, poleMaterial, lampPosts, new THREE.Vector3(0.78, 0.9, 0.78)));
  lampPositions.forEach((position) => {
    const arm = new THREE.Mesh(lampArmGeometry, poleMaterial);
    arm.position.set(position.x + 0.32, 5.35, position.z);
    arm.rotation.z = -0.25;
    group.add(arm);
    const bulb = new THREE.Mesh(lampBulbGeometry, lampMaterial);
    bulb.position.set(position.x + 0.65, 5.23, position.z);
    group.add(bulb);
    const light = new THREE.PointLight("#dca957", 0.34, 8, 2);
    light.position.copy(bulb.position);
    group.add(light);
  });

  for (let x = -20; x <= 20; x += 10) {
    const trunk = new THREE.Mesh(treeTrunkGeometry, trunkMaterial);
    trunk.position.set(x + 2.3, 0.8, 10.1);
    group.add(trunk);
    const canopy = new THREE.Mesh(treeCanopyGeometry, canopyMaterial);
    canopy.position.set(x + 2.3, 2.1, 10.1);
    group.add(canopy);
  }

  const transformer = new THREE.Mesh(transformerGeometry, transformerMaterial);
  transformer.position.set(-25, 0.72, -3.3);
  group.add(transformer);
  [-0.42, 0, 0.42].forEach((x) => {
    const insulator = new THREE.Mesh(insulatorGeometry, insulatorMaterial);
    insulator.position.set(-25 + x, 1.53, -3.3);
    group.add(insulator);
  });

  const busStop = new THREE.Group();
  const busRoof = new THREE.Mesh(boxGeometry, poleMaterial);
  busRoof.position.set(0, 2.4, 0);
  busRoof.scale.set(2.4, 0.12, 0.9);
  busStop.add(busRoof);
  [-1, 1].forEach((x) => {
    const support = new THREE.Mesh(poleGeometry, poleMaterial);
    support.position.set(x, 1.2, 0);
    support.scale.set(0.55, 0.4, 0.55);
    busStop.add(support);
  });
  busStop.position.set(23, 0, 8.5);
  group.add(busStop);

  [-12, 18].forEach((x, index) => {
    const car = new THREE.Group();
    const body = new THREE.Mesh(boxGeometry, new THREE.MeshStandardMaterial({
      color: index === 0 ? "#606c77" : "#78624d",
      roughness: 0.5,
      metalness: 0.22,
    }));
    body.position.y = 0.36;
    body.scale.set(1.55, 0.46, 0.72);
    const cabin = new THREE.Mesh(boxGeometry, poleMaterial);
    cabin.position.set(-0.1, 0.68, 0);
    cabin.scale.set(0.82, 0.28, 0.58);
    car.add(body, cabin);
    car.position.set(x, 0, index === 0 ? -1.7 : 1.7);
    group.add(car);
  });
  [-8, 8].forEach((x) => {
    const bin = new THREE.Mesh(boxGeometry, transformerMaterial);
    bin.position.set(x, 0.38, 9.2);
    bin.scale.set(0.42, 0.76, 0.42);
    group.add(bin);
  });

  return {
    group,
    polePositions,
    dispose() {
      const geometries = new Set<THREE.BufferGeometry>();
      const materials = new Set<THREE.Material>();
      group.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.InstancedMesh) {
          geometries.add(object.geometry);
          if (Array.isArray(object.material)) object.material.forEach((material) => materials.add(material));
          else materials.add(object.material);
        }
      });
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((material) => material.dispose());
    },
  };
}
