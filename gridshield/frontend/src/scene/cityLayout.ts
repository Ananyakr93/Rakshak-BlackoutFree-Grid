import * as THREE from "three";

function stableNoise(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

export function positionForBuilding(index: number, count: number, id: string): THREE.Vector3 {
  if (!Number.isInteger(index) || index < 0 || !Number.isInteger(count) || count <= index) {
    throw new RangeError("Building index must be within a positive building count.");
  }

  const frontCount = count > 6 ? 6 : Math.ceil(count / 2);
  const frontRow = index < frontCount;
  const rowIndex = frontRow ? index : index - frontCount;
  const rowCount = frontRow ? frontCount : count - frontCount;
  const spacing = count >= 9 ? 6.4 : count >= 5 ? 6.0 : 5.4;
  const x = (rowIndex - (rowCount - 1) / 2) * spacing + (frontRow ? 0 : spacing * 0.22);
  const z = frontRow ? 5.8 : -6.2;
  const jitter = stableNoise(id);
  const jitter2 = stableNoise(`${id}:z`);
  return new THREE.Vector3(
    x + (jitter - 0.5) * 0.3,
    0,
    z + (jitter2 - 0.5) * 0.3,
  );
}
