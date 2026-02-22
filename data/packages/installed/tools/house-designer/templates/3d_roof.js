// House Designer v3 - Roof Builder
// 다양한 지붕 타입(hip, gable, flat, mansard, gable_glass) 생성
// 전역 변수 의존: THREE, DESIGN, ROOF_CONFIG, MATERIALS_DATA, centerX, centerZ,
//                roomBBox, hexColorToInt, roofGroup, houseGroup

function buildRoof() {
  if (DESIGN.floors.length === 0) return;

  // Find building bounds from all floors
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  let topElev = 0;
  for (const floor of DESIGN.floors) {
    const rooms = floor.rooms || [];
    const floorElev = (floor.elevation || 0) + (floor.height || 2.8);
    if (floorElev > topElev && rooms.length > 0) topElev = floorElev;
    for (const room of rooms) {
      const bb = roomBBox(room);
      minX = Math.min(minX, bb.minX); maxX = Math.max(maxX, bb.maxX);
      minZ = Math.min(minZ, bb.minY); maxZ = Math.max(maxZ, bb.maxY);
    }
  }
  if (minX === Infinity) return; // No rooms at all

  const roofType = ROOF_CONFIG.type || 'hip';
  const roofH = ROOF_CONFIG.height || Math.min(Math.min(maxX - minX, maxZ - minZ) * 0.25, 2.5);
  const overhang = ROOF_CONFIG.overhang || 0.3;
  const direction = ROOF_CONFIG.direction || 'x';

  const w = maxX - minX + 0.6;
  const d = maxZ - minZ + 0.6;
  const cx = (minX + maxX) / 2 - centerX;
  const cz = (minZ + maxZ) / 2 - centerZ;
  const hw = w / 2 + overhang;
  const hd = d / 2 + overhang;

  // Roof material
  const roofMatName = ROOF_CONFIG.material || 'shingle';
  const roofMatDef = MATERIALS_DATA.roof_materials[roofMatName] || { color: '#5D4E37' };
  const roofColor = hexColorToInt(roofMatDef.color || '#5D4E37');
  const roofOpacity = roofMatDef.opacity || 1.0;
  const roofMat = new THREE.MeshStandardMaterial({
    color: roofColor, roughness: 0.8, side: THREE.DoubleSide,
    transparent: roofOpacity < 1, opacity: roofOpacity,
  });

  if (roofType === 'flat') {
    // Flat roof
    const geo = new THREE.BoxGeometry(w + overhang * 2, 0.2, d + overhang * 2);
    const mesh = new THREE.Mesh(geo, roofMat);
    mesh.position.set(cx, topElev + 0.1, cz);
    mesh.castShadow = true;
    roofGroup.add(mesh);

  } else if (roofType === 'gable' || roofType === 'gable_glass') {
    // Gable roof
    const geo = new THREE.BufferGeometry();
    let vertices, indices;

    if (direction === 'x' || (direction === 'auto' && w >= d)) {
      // Ridge along X axis
      vertices = new Float32Array([
        -hw, 0, -hd, hw, 0, -hd, hw, 0, hd, -hw, 0, hd, // base 0-3
        -hw, roofH, 0, hw, roofH, 0,                        // ridge 4-5
      ]);
      indices = [
        0, 1, 5, 0, 5, 4, // front slope
        2, 3, 4, 2, 4, 5, // back slope
      ];
    } else {
      // Ridge along Z axis
      vertices = new Float32Array([
        -hw, 0, -hd, hw, 0, -hd, hw, 0, hd, -hw, 0, hd,
        0, roofH, -hd, 0, roofH, hd,
      ]);
      indices = [
        3, 0, 4, 3, 4, 5, // left slope
        1, 2, 5, 1, 5, 4, // right slope
      ];
    }
    geo.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    const slopeRoof = new THREE.Mesh(geo, roofMat);
    slopeRoof.position.set(cx, topElev, cz);
    slopeRoof.castShadow = true;
    roofGroup.add(slopeRoof);

    // Gable end walls (triangles)
    if (roofType === 'gable_glass') {
      const glassMat = new THREE.MeshPhysicalMaterial({
        color: 0x88ccff, transparent: true, opacity: 0.3,
        roughness: 0.05, metalness: 0.1, transmission: 0.6,
        side: THREE.DoubleSide,
      });
      buildGableEnd(roofGroup, cx, cz, topElev, hw, hd, roofH, direction, glassMat);
    } else {
      buildGableEnd(roofGroup, cx, cz, topElev, hw, hd, roofH, direction, roofMat);
    }

  } else if (roofType === 'mansard') {
    // Mansard: lower steep slope + upper gentle slope
    const lowerH = roofH * 0.6;
    const upperH = roofH * 0.4;
    const inset = Math.min(w, d) * 0.15;

    // Lower slopes (steep, 4 trapezoid faces)
    const lGeo = new THREE.BufferGeometry();
    const lVerts = new Float32Array([
      -hw, 0, -hd, hw, 0, -hd, hw, 0, hd, -hw, 0, hd, // base
      -(hw - inset), lowerH, -(hd - inset), (hw - inset), lowerH, -(hd - inset),
      (hw - inset), lowerH, (hd - inset), -(hw - inset), lowerH, (hd - inset),
    ]);
    lGeo.setAttribute('position', new THREE.BufferAttribute(lVerts, 3));
    lGeo.setIndex([
      0, 1, 5, 0, 5, 4, // front
      1, 2, 6, 1, 6, 5, // right
      2, 3, 7, 2, 7, 6, // back
      3, 0, 4, 3, 4, 7, // left
    ]);
    lGeo.computeVertexNormals();
    const lower = new THREE.Mesh(lGeo, roofMat);
    lower.position.set(cx, topElev, cz);
    lower.castShadow = true;
    roofGroup.add(lower);

    // Upper hip roof
    const uhw = hw - inset, uhd = hd - inset;
    const ridgeHalf = Math.max(0, (Math.max(w, d) - Math.min(w, d)) / 2 - inset);
    const uGeo = new THREE.BufferGeometry();
    let uVerts, uIdx;
    if (w >= d) {
      uVerts = new Float32Array([
        -uhw, 0, -uhd, uhw, 0, -uhd, uhw, 0, uhd, -uhw, 0, uhd,
        -ridgeHalf, upperH, 0, ridgeHalf, upperH, 0,
      ]);
      uIdx = [0, 1, 5, 0, 5, 4, 2, 3, 4, 2, 4, 5, 3, 0, 4, 1, 2, 5];
    } else {
      uVerts = new Float32Array([
        -uhw, 0, -uhd, uhw, 0, -uhd, uhw, 0, uhd, -uhw, 0, uhd,
        0, upperH, -ridgeHalf, 0, upperH, ridgeHalf,
      ]);
      uIdx = [0, 1, 4, 2, 3, 5, 3, 0, 4, 3, 4, 5, 1, 2, 5, 1, 5, 4];
    }
    uGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(uVerts), 3));
    uGeo.setIndex(uIdx);
    uGeo.computeVertexNormals();
    const upper = new THREE.Mesh(uGeo, roofMat);
    upper.position.set(cx, topElev + lowerH, cz);
    upper.castShadow = true;
    roofGroup.add(upper);

  } else {
    // Hip roof (default)
    const ridgeHalf = Math.max(0, (Math.max(w, d) - Math.min(w, d)) / 2);
    const geo = new THREE.BufferGeometry();
    let vertices, indices;
    if (w >= d) {
      vertices = new Float32Array([
        -hw, 0, -hd, hw, 0, -hd, hw, 0, hd, -hw, 0, hd,
        -ridgeHalf, roofH, 0, ridgeHalf, roofH, 0,
      ]);
      indices = [0, 1, 5, 0, 5, 4, 2, 3, 4, 2, 4, 5, 3, 0, 4, 1, 2, 5];
    } else {
      vertices = new Float32Array([
        -hw, 0, -hd, hw, 0, -hd, hw, 0, hd, -hw, 0, hd,
        0, roofH, -ridgeHalf, 0, roofH, ridgeHalf,
      ]);
      indices = [0, 1, 4, 2, 3, 5, 3, 0, 4, 3, 4, 5, 1, 2, 5, 1, 5, 4];
    }
    geo.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    const roof = new THREE.Mesh(geo, roofMat);
    roof.position.set(cx, topElev, cz);
    roof.castShadow = true;
    roofGroup.add(roof);
  }

  houseGroup.add(roofGroup);
}

function buildGableEnd(group, cx, cz, topElev, hw, hd, roofH, direction, mat) {
  const isX = direction === 'x' || direction === 'auto';
  for (const sign of [-1, 1]) {
    const g = new THREE.BufferGeometry();
    let v;
    if (isX) {
      v = [-hw, 0, sign * hd, hw, 0, sign * hd, 0, roofH, sign * hd];
    } else {
      v = [sign * hw, 0, -hd, sign * hw, 0, hd, sign * hw, roofH, 0];
    }
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(v), 3));
    g.setIndex([0, 1, 2]);
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat);
    m.position.set(cx, topElev, cz);
    group.add(m);
  }
}
