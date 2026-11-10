import * as THREE from "three";

export interface Environment {
  group: THREE.Group;
  dispose(): void;
}

export function createEnvironment(): Environment {
  const group = new THREE.Group();
  const groundGeometry = new THREE.PlaneGeometry(120, 80);
  const roadGeometry = new THREE.BoxGeometry(120, 0.08, 7.2);
  const sidewalkGeometry = new THREE.BoxGeometry(120, 0.18, 1.8);
  const kerbGeometry = new THREE.BoxGeometry(120, 0.28, 0.18);
  const dashGeometry = new THREE.BoxGeometry(1.25, 0.025, 0.11);
  const groundMaterial = new THREE.MeshStandardMaterial({ color: "#2b3745", roughness: 1 });
  const roadMaterial = new THREE.MeshStandardMaterial({ color: "#252d38", roughness: 0.96 });
  const sidewalkMaterial = new THREE.MeshStandardMaterial({ color: "#303944", roughness: 1 });
  const kerbMaterial = new THREE.MeshStandardMaterial({ color: "#48505a", roughness: 1 });
  const dashMaterial = new THREE.MeshStandardMaterial({
    color: "#c5a15b",
    emissive: "#48371d",
    roughness: 0.8,
  });
  const skylineGeometry = new THREE.BoxGeometry(1, 1, 1);
  const skylineMaterial = new THREE.MeshStandardMaterial({ color: "#17212d", roughness: 1 });

  const ground = new THREE.Mesh(groundGeometry, groundMaterial);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.12;
  group.add(ground);
  const frontRoad = new THREE.Mesh(roadGeometry, roadMaterial);
  const rearRoad = new THREE.Mesh(roadGeometry, roadMaterial);
  frontRoad.position.set(0, 0, 0);
  rearRoad.position.set(0, 0, -17);
  group.add(frontRoad, rearRoad);

  [-4.5, 4.5, -12.5, -21.5].forEach((z) => {
    const sidewalk = new THREE.Mesh(sidewalkGeometry, sidewalkMaterial);
    sidewalk.position.set(0, 0.04, z);
    group.add(sidewalk);
    const kerb = new THREE.Mesh(kerbGeometry, kerbMaterial);
    kerb.position.set(0, 0.13, z < 0 ? z + 0.95 : z - 0.95);
    group.add(kerb);
  });
  for (let x = -56; x <= 56; x += 3) {
    const dash = new THREE.Mesh(dashGeometry, dashMaterial);
    dash.position.set(x, 0.055, 0);
    group.add(dash);
  }
  const skyline = new THREE.InstancedMesh(skylineGeometry, skylineMaterial, 18);
  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  for (let index = 0; index < 18; index += 1) {
    const height = 3 + (index * 7 % 11);
    position.set(-55 + index * 6.4, height / 2 - 0.1, -33 - (index % 2) * 2);
    scale.set(3.2 + (index % 3), height, 2.4);
    matrix.compose(position, quaternion, scale);
    skyline.setMatrixAt(index, matrix);
  }
  group.add(skyline);

  const starsGeometry = new THREE.BufferGeometry();
  const stars = new Float32Array(360 * 3);
  let seed = 8917;
  const random = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
  for (let index = 0; index < stars.length; index += 3) {
    stars[index] = (random() - 0.5) * 100;
    stars[index + 1] = 15 + random() * 22;
    stars[index + 2] = (random() - 0.5) * 50 - 20;
  }
  starsGeometry.setAttribute("position", new THREE.BufferAttribute(stars, 3));
  const starField = new THREE.Points(
    starsGeometry,
    new THREE.PointsMaterial({ color: "#91a0b7", size: 0.12, sizeAttenuation: true }),
  );
  group.add(starField);
  const moon = new THREE.DirectionalLight("#bac6d8", 1.1);
  moon.position.set(-12, 18, -8);
  group.add(moon);
  group.add(new THREE.AmbientLight("#8998ad", 0.72));

  return {
    group,
    dispose() {
      const geometries = new Set<THREE.BufferGeometry>();
      const materials = new Set<THREE.Material>();
      group.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Points || object instanceof THREE.InstancedMesh) {
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
