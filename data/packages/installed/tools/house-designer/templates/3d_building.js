// House Designer v3 - Building Elements
// 문짝/프레임, 기둥, 보, 계단, 발코니 난간 빌더 함수들
// 전역 변수 의존: THREE, centerX, centerZ, MATERIALS_DATA, hexColorToInt

// ============================================================
// Door panels & frames
// ============================================================
function buildDoorPanel(group, sx, sy, dx, dy, door, elev, h, angle) {
  const dW = door.width || 0.9;
  const dH = Math.min((h || 2.8) - 0.3, 2.1);
  const dType = door.type || 'single';
  const pos = door.position || 0;

  const fMat = new THREE.MeshStandardMaterial({ color: 0x8B7355, roughness: 0.5 });
  const pMat = new THREE.MeshStandardMaterial({ color: 0xD2B48C, roughness: 0.6 });
  const fw = 0.05, fd = 0.12;
  const dG = new THREE.Group();

  // Frame: left/right jambs + header
  const lj = new THREE.Mesh(new THREE.BoxGeometry(fw, dH, fd), fMat);
  lj.position.set(pos - dW / 2, dH / 2, 0);
  lj.castShadow = true;
  const rj = lj.clone();
  rj.position.set(pos + dW / 2, dH / 2, 0);
  const hd = new THREE.Mesh(new THREE.BoxGeometry(dW + fw * 2, fw, fd), fMat);
  hd.position.set(pos, dH + fw / 2, 0);
  dG.add(lj); dG.add(rj); dG.add(hd);

  if (dType === 'single' || dType === 'double') {
    const nP = dType === 'double' ? 2 : 1;
    const pW = dW / nP;
    const oA = 15 * Math.PI / 180;
    const hMat = new THREE.MeshStandardMaterial({ color: 0xC0C0C0, metalness: 0.6, roughness: 0.3 });

    for (let i = 0; i < nP; i++) {
      const pm = new THREE.Mesh(new THREE.BoxGeometry(pW, dH - 0.02, 0.04), pMat);
      const pv = new THREE.Group();
      pv.position.set(i === 0 ? pos - dW / 2 : pos + dW / 2, dH / 2, 0);
      pm.position.set(i === 0 ? pW / 2 : -pW / 2, 0, 0);
      pm.castShadow = true;
      pv.add(pm);
      pv.rotation.y = i === 0 ? oA : -oA;
      dG.add(pv);

      // Handle
      const hl = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.1, 8), hMat);
      hl.rotation.x = Math.PI / 2;
      hl.position.set(i === 0 ? pW * 0.8 : -pW * 0.8, 0, 0.04);
      pv.add(hl);
    }
  } else if (dType === 'sliding') {
    const sp = new THREE.Mesh(new THREE.BoxGeometry(dW, dH - 0.02, 0.04), pMat);
    sp.position.set(pos + dW * 0.45, dH / 2, -0.05);
    sp.castShadow = true;
    dG.add(sp);
    const tr = new THREE.Mesh(new THREE.BoxGeometry(dW * 2, 0.02, 0.03), fMat);
    tr.position.set(pos, dH + 0.01, 0);
    dG.add(tr);
  }

  dG.position.set(sx + dx * pos - centerX, elev, sy + dy * pos - centerZ);
  dG.rotation.y = -angle;
  group.add(dG);
}

// ============================================================
// Structural elements: Column & Beam
// ============================================================
function buildColumn(group, col, elev, floorH) {
  const x = col.x, z = col.y;
  const w = col.width || 0.4, d = col.depth || 0.4;
  const shape = col.shape || 'rect';
  const colH = floorH;

  let geo;
  if (shape === 'round') {
    const radius = Math.max(w, d) / 2;
    geo = new THREE.CylinderGeometry(radius, radius, colH, 16);
  } else {
    geo = new THREE.BoxGeometry(w, colH, d);
  }

  const mat = new THREE.MeshStandardMaterial({ color: 0xA0A0A0, roughness: 0.6 });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(x - centerX, elev + colH / 2, z - centerZ);
  mesh.castShadow = true; mesh.receiveShadow = true;
  mesh.userData = { type: 'column', name: col.id || 'column' };
  group.add(mesh);
}

function buildBeam(group, beam, elev, floorH) {
  const [sx, sy] = beam.start;
  const [ex, ey] = beam.end;
  const len = Math.hypot(ex - sx, ey - sy);
  if (len < 0.001) return;
  const bw = beam.width || 0.3;
  const bd = beam.depth || 0.5;
  const angle = Math.atan2(ey - sy, ex - sx);

  const geo = new THREE.BoxGeometry(len, bd, bw);
  const mat = new THREE.MeshStandardMaterial({ color: 0xB0B0B0, roughness: 0.6 });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(
    (sx + ex) / 2 - centerX,
    elev + floorH - bd / 2,
    (sy + ey) / 2 - centerZ
  );
  mesh.rotation.y = -angle;
  mesh.castShadow = true;
  group.add(mesh);
}

// ============================================================
// Stairs
// ============================================================
function buildStairs(group, stair, elev, floorH) {
  const sx = stair.start[0], sy = stair.start[1];
  const w = stair.width || 1.0;
  const numTreads = stair.num_treads || 15;
  const td = stair.tread_depth || 0.28;
  const rh = stair.riser_height || (floorH / numTreads);
  const dir = stair.direction || 0;
  const stype = stair.type || 'straight';
  const landing = stair.landing_depth || 1.0;
  const turnDir = stair.turn_direction || 'right';

  const stairGroup = new THREE.Group();

  // Direction rotation (0=+Y, 90=+X, 180=-Y, 270=-X)
  const dirRad = -dir * Math.PI / 180;

  const treadMat = new THREE.MeshStandardMaterial({ color: 0xD2B48C, roughness: 0.6 });
  const riserMat = new THREE.MeshStandardMaterial({ color: 0xBCA888, roughness: 0.7 });
  const stringerMat = new THREE.MeshStandardMaterial({ color: 0x8B7355, roughness: 0.6 });
  const railMat = new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.4 });

  if (stype === 'straight') {
    // Treads and risers
    for (let i = 0; i < numTreads; i++) {
      const tGeo = new THREE.BoxGeometry(w, 0.04, td);
      const tMesh = new THREE.Mesh(tGeo, treadMat);
      tMesh.position.set(w / 2, (i + 1) * rh, i * td + td / 2);
      tMesh.castShadow = true; tMesh.receiveShadow = true;
      stairGroup.add(tMesh);

      const rgeo = new THREE.BoxGeometry(w, rh, 0.02);
      const rMesh = new THREE.Mesh(rgeo, riserMat);
      rMesh.position.set(w / 2, i * rh + rh / 2, i * td);
      stairGroup.add(rMesh);
    }

    // Stringers (side beams)
    const totalRun = numTreads * td;
    const totalRise = numTreads * rh;
    const stringerLen = Math.sqrt(totalRun * totalRun + totalRise * totalRise);
    const stringerAngle = Math.atan2(totalRise, totalRun);
    for (const side of [-0.02, w + 0.02]) {
      const sGeo = new THREE.BoxGeometry(0.06, 0.2, stringerLen);
      const sMesh = new THREE.Mesh(sGeo, stringerMat);
      sMesh.position.set(side, totalRise / 2, totalRun / 2);
      sMesh.rotation.x = -stringerAngle;
      sMesh.castShadow = true;
      stairGroup.add(sMesh);
    }

    // Handrails
    const handrail = stair.handrail || 'both';
    const railH = 0.9;
    const railPositions = [];
    if (handrail === 'both' || handrail === 'left') railPositions.push(-0.04);
    if (handrail === 'both' || handrail === 'right') railPositions.push(w + 0.04);

    for (const rp of railPositions) {
      // Top rail
      const rGeo = new THREE.CylinderGeometry(0.02, 0.02, stringerLen, 8);
      const rMesh = new THREE.Mesh(rGeo, railMat);
      rMesh.position.set(rp, totalRise / 2 + railH, totalRun / 2);
      rMesh.rotation.x = Math.PI / 2 - stringerAngle;
      stairGroup.add(rMesh);

      // Vertical posts (balusters) every 3 treads
      for (let i = 0; i < numTreads; i += 3) {
        const postH = railH;
        const pGeo = new THREE.CylinderGeometry(0.015, 0.015, postH, 6);
        const pMesh = new THREE.Mesh(pGeo, railMat);
        pMesh.position.set(rp, (i + 1) * rh + postH / 2, i * td + td / 2);
        stairGroup.add(pMesh);
      }
    }

  } else if (stype === 'l_shape' || stype === 'u_turn') {
    const half = Math.floor(numTreads / 2);
    const secondHalf = numTreads - half;
    const turnSign = turnDir === 'right' ? 1 : -1;

    // First run
    for (let i = 0; i < half; i++) {
      const t = new THREE.Mesh(new THREE.BoxGeometry(w, 0.04, td), treadMat);
      t.position.set(w / 2, (i + 1) * rh, i * td + td / 2);
      t.castShadow = true;
      stairGroup.add(t);

      const r = new THREE.Mesh(new THREE.BoxGeometry(w, rh, 0.02), riserMat);
      r.position.set(w / 2, i * rh + rh / 2, i * td);
      stairGroup.add(r);
    }

    const lz = half * td, le = half * rh;

    if (stype === 'l_shape') {
      // Landing + perpendicular second run
      const lg = new THREE.Mesh(new THREE.BoxGeometry(w + landing, 0.04, landing), treadMat);
      lg.position.set(turnSign > 0 ? (w + landing) / 2 : (w - landing) / 2, le, lz + landing / 2);
      lg.castShadow = true;
      stairGroup.add(lg);

      for (let i = 0; i < secondHalf; i++) {
        const t = new THREE.Mesh(new THREE.BoxGeometry(td, 0.04, w), treadMat);
        t.position.set(turnSign > 0 ? w + i * td + td / 2 : -i * td - td / 2 + w, le + (i + 1) * rh, lz + landing + w / 2);
        t.castShadow = true;
        stairGroup.add(t);
      }
    } else {
      // U-turn: landing + parallel reverse second run
      const gap = 0.1;
      const lg = new THREE.Mesh(new THREE.BoxGeometry(w * 2 + gap, 0.04, landing), treadMat);
      lg.position.set(w + gap / 2, le, lz + landing / 2);
      lg.castShadow = true;
      stairGroup.add(lg);

      for (let i = 0; i < secondHalf; i++) {
        const t = new THREE.Mesh(new THREE.BoxGeometry(w, 0.04, td), treadMat);
        t.position.set(w * 1.5 + gap, le + (i + 1) * rh, lz + landing - i * td - td / 2);
        t.castShadow = true;
        stairGroup.add(t);
      }
    }
  }

  // Position and rotate the entire stair group
  stairGroup.position.set(sx - centerX, elev, sy - centerZ);
  stairGroup.rotation.y = dirRad;
  group.add(stairGroup);
}

// ============================================================
// Balcony railing
// ============================================================
function buildRailing(group, room, elev, floorH) {
  const railing = room.railing;
  const rH = railing.height || 1.1;
  const rType = railing.type || 'metal';
  const verts = roomVertices(room);
  const edges = roomEdges(room);

  const railMats = MATERIALS_DATA.railing_materials || {};
  const rMatDef = railMats[rType] || { color: '#555555', opacity: 1.0 };
  const railColor = hexColorToInt(rMatDef.color || '#555555');
  const isGlass = rType === 'glass';

  for (const [p1, p2] of edges) {
    const ex = p2[0] - p1[0], ey = p2[1] - p1[1];
    const len = Math.sqrt(ex * ex + ey * ey);
    if (len < 0.1) continue;
    const angle = Math.atan2(ey, ex);
    const mx = (p1[0] + p2[0]) / 2 - centerX;
    const mz = (p1[1] + p2[1]) / 2 - centerZ;

    if (isGlass) {
      // Glass panel + metal cap
      const glassMat = new THREE.MeshPhysicalMaterial({
        color: railColor, transparent: true, opacity: 0.25,
        roughness: 0.05, metalness: 0.1, transmission: 0.6, side: THREE.DoubleSide,
      });
      const panelGeo = new THREE.BoxGeometry(len, rH - 0.1, 0.015);
      const panel = new THREE.Mesh(panelGeo, glassMat);
      panel.position.set(mx, elev + rH / 2, mz);
      panel.rotation.y = -angle;
      group.add(panel);

      const capMat = new THREE.MeshStandardMaterial({ color: 0x888888, roughness: 0.3, metalness: 0.5 });
      const capGeo = new THREE.BoxGeometry(len + 0.02, 0.04, 0.06);
      const cap = new THREE.Mesh(capGeo, capMat);
      cap.position.set(mx, elev + rH, mz);
      cap.rotation.y = -angle;
      cap.castShadow = true;
      group.add(cap);
    } else {
      // Metal/wood railing: top + bottom rail + vertical balusters
      const postMat = new THREE.MeshStandardMaterial({
        color: railColor, roughness: 0.4, metalness: rType === 'metal' ? 0.5 : 0.1,
      });

      const railG = new THREE.Group();
      railG.position.set(mx, elev + rH, mz);
      railG.rotation.y = -angle;
      const tr = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, len, 8), postMat);
      tr.rotation.z = Math.PI / 2;
      railG.add(tr);
      const br = tr.clone();
      br.position.y = -(rH - 0.1);
      railG.add(br);
      group.add(railG);

      // Vertical balusters (every 0.12m)
      const numBal = Math.max(2, Math.floor(len / 0.12));
      const balH = rH - 0.1;
      for (let i = 0; i <= numBal; i++) {
        const frac = i / numBal;
        const bx = p1[0] + ex * frac - centerX;
        const bz = p1[1] + ey * frac - centerZ;
        const bGeo = new THREE.CylinderGeometry(0.012, 0.012, balH, 6);
        const bMesh = new THREE.Mesh(bGeo, postMat);
        bMesh.position.set(bx, elev + 0.1 + balH / 2, bz);
        group.add(bMesh);
      }
    }
  }
}
