// House Designer v3 - Furniture Builder
// 가구 스타일 정의 및 타입별 3D 형태 생성
// 전역 변수 의존: THREE, centerX, centerZ, makeLabel

// Furniture styles: [color, height]
const FS = {
  sofa: [0xB8860B, 0.75], bed_single: [0x6B8E23, 0.5], bed_double: [0x6B8E23, 0.5],
  bed_queen: [0x6B8E23, 0.5], bed_king: [0x6B8E23, 0.5],
  dining_table: [0x8B4513, 0.75], desk: [0xA0522D, 0.75],
  wardrobe: [0x696969, 2.0], bookshelf: [0xD2691E, 1.8],
  tv_stand: [0x2F4F4F, 0.5], toilet: [0xEEEEEE, 0.45],
  bathtub: [0xDDEEFF, 0.55], shower: [0xCCDDEE, 2.0],
  sink: [0xDDDDDD, 0.85], kitchen_sink: [0xBBBBBB, 0.85],
  stove: [0xCD5C5C, 0.85], refrigerator: [0xC0C0C0, 1.8],
  washing_machine: [0xD3D3D3, 0.85], chair: [0xDEB887, 0.45],
  coffee_table: [0xBC8F8F, 0.4],
};
const FURNITURE_STYLES = {};
for (const [k, v] of Object.entries(FS)) FURNITURE_STYLES[k] = { color: v[0], height: v[1] };
const FURNITURE_DEFAULT = { color: 0x8B7355, height: 0.6 };

function buildFurniture(f, elev) {
  const w = f.width || 1, d = f.depth || 1;
  const style = FURNITURE_STYLES[f.type] || FURNITURE_DEFAULT;
  const fh = f.height || style.height;
  const fType = f.type || 'other';

  const group = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: style.color, roughness: 0.6 });

  // Helper to add a mesh part to group
  function addPart(geo, m, pos, rot) {
    const mesh = new THREE.Mesh(geo, m || mat);
    mesh.position.set(pos[0] || 0, pos[1] || 0, pos[2] || 0);
    if (rot) {
      if (rot[0]) mesh.rotation.x = rot[0];
      if (rot[1]) mesh.rotation.y = rot[1];
    }
    mesh.castShadow = true;
    group.add(mesh);
    return mesh;
  }

  const darkMat = new THREE.MeshStandardMaterial({ color: 0x5C4033, roughness: 0.6 });
  const metalMat = new THREE.MeshStandardMaterial({ color: 0xBBBBBB, metalness: 0.5, roughness: 0.3 });

  if (fType === 'toilet') {
    addPart(new THREE.BoxGeometry(w * 0.9, fh * 0.7, d * 0.3), mat, [0, fh * 0.35, -d * 0.35]);
    addPart(new THREE.CylinderGeometry(w * 0.35, w * 0.3, fh * 0.5, 12), mat, [0, fh * 0.25, d * 0.1]);
    addPart(new THREE.TorusGeometry(w * 0.3, 0.03, 8, 16), mat, [0, fh * 0.5, d * 0.1], [-Math.PI / 2]);

  } else if (fType === 'bathtub') {
    const wMat = new THREE.MeshStandardMaterial({ color: 0xEEEEEE, roughness: 0.3 });
    addPart(new THREE.BoxGeometry(w, fh, d), wMat, [0, fh / 2, 0]);
    addPart(new THREE.BoxGeometry(w - 0.1, fh * 0.6, d - 0.1),
      new THREE.MeshStandardMaterial({ color: 0xCCDDFF, roughness: 0.2 }), [0, fh * 0.5, 0]);

  } else if (fType === 'sofa') {
    const sH = fh * 0.45, aW = 0.12;
    addPart(new THREE.BoxGeometry(w - aW * 2, sH, d * 0.8), mat, [0, sH / 2, d * 0.1]);
    addPart(new THREE.BoxGeometry(w, fh, d * 0.2), mat, [0, fh / 2, -d * 0.4]);
    for (const s of [-1, 1])
      addPart(new THREE.BoxGeometry(aW, fh * 0.7, d), mat, [s * (w / 2 - aW / 2), fh * 0.35, 0]);

  } else if (fType.startsWith('bed')) {
    const mH = fh * 0.6, hH = fh * 1.2;
    addPart(new THREE.BoxGeometry(w, mH, d), mat, [0, mH / 2, 0]);
    addPart(new THREE.BoxGeometry(w, hH, 0.05), darkMat, [0, hH / 2, -d / 2 + 0.025]);
    const pMat = new THREE.MeshStandardMaterial({ color: 0xFFF8DC, roughness: 0.8 });
    const nP = w > 1.2 ? 2 : 1, pW = (w - 0.2) / nP;
    for (let i = 0; i < nP; i++)
      addPart(new THREE.BoxGeometry(pW - 0.05, 0.08, 0.3), pMat,
        [(i - (nP - 1) / 2) * pW, mH + 0.04, -d / 2 + 0.25]);

  } else if (fType === 'dining_table' || fType === 'desk' || fType === 'coffee_table') {
    addPart(new THREE.BoxGeometry(w, 0.04, d), mat, [0, fh - 0.02, 0]);
    const lH = fh - 0.04;
    for (const [lx, lz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]])
      addPart(new THREE.CylinderGeometry(0.025, 0.025, lH, 6), darkMat,
        [lx * (w / 2 - 0.05), lH / 2, lz * (d / 2 - 0.05)]);

  } else if (fType === 'refrigerator') {
    addPart(new THREE.BoxGeometry(w, fh, d), mat, [0, fh / 2, 0]);
    addPart(new THREE.BoxGeometry(w * 0.95, 0.02, 0.01),
      new THREE.MeshStandardMaterial({ color: 0x888888 }), [0, fh * 0.7, d / 2 + 0.005]);
    for (const hy of [fh * 0.5, fh * 0.85])
      addPart(new THREE.CylinderGeometry(0.012, 0.012, fh * 0.15, 8), metalMat,
        [w * 0.35, hy, d / 2 + 0.02]);

  } else if (fType === 'stove') {
    addPart(new THREE.BoxGeometry(w, fh, d), mat, [0, fh / 2, 0]);
    const bS = Math.min(w, d) * 0.22;
    const bMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.8 });
    for (const [bx, bz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]])
      addPart(new THREE.TorusGeometry(bS * 0.6, 0.015, 6, 16), bMat,
        [bx * bS, fh + 0.01, bz * bS], [-Math.PI / 2]);

  } else if (fType === 'sink' || fType === 'kitchen_sink') {
    const sMat = new THREE.MeshStandardMaterial({ color: 0xDDDDDD, roughness: 0.4 });
    addPart(new THREE.BoxGeometry(w, fh, d), sMat, [0, fh / 2, 0]);
    addPart(new THREE.CylinderGeometry(Math.min(w, d) * 0.3, Math.min(w, d) * 0.24, 0.12, 16),
      new THREE.MeshStandardMaterial({ color: 0xBBCCDD, roughness: 0.2 }), [0, fh + 0.01, 0]);
    const fcMat = new THREE.MeshStandardMaterial({ color: 0xCCCCCC, metalness: 0.6, roughness: 0.2 });
    addPart(new THREE.CylinderGeometry(0.015, 0.015, 0.2, 8), fcMat, [0, fh + 0.1, -d * 0.35]);
    addPart(new THREE.CylinderGeometry(0.012, 0.012, 0.12, 8), fcMat,
      [0, fh + 0.18, -d * 0.25], [Math.PI / 2.5]);

  } else if (fType === 'wardrobe') {
    addPart(new THREE.BoxGeometry(w, fh, d), mat, [0, fh / 2, 0]);
    addPart(new THREE.BoxGeometry(0.01, fh * 0.9, 0.01),
      new THREE.MeshStandardMaterial({ color: 0x444444 }), [0, fh / 2, d / 2 + 0.005]);
    for (const hx of [-0.08, 0.08])
      addPart(new THREE.CylinderGeometry(0.01, 0.01, 0.1, 8), metalMat,
        [hx, fh * 0.55, d / 2 + 0.015]);

  } else {
    // Default: simple box
    addPart(new THREE.BoxGeometry(w, fh, d), mat, [0, fh / 2, 0]);
  }

  // Position the furniture group
  group.position.set(f.x + w / 2 - centerX, elev + 0.05, f.y + d / 2 - centerZ);
  if (f.rotation) group.rotation.y = -f.rotation * Math.PI / 180;
  group.userData = { type: 'furniture', name: f.name };

  const label = makeLabel(f.name, 0.3);
  label.position.set(0, fh / 2 + 0.3, 0);
  group.add(label);
  return group;
}
