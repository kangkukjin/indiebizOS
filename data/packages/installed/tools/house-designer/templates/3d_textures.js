// House Designer v3 - Procedural Texture Generators
// 벽/바닥 재질별 프로시저럴 텍스처를 Canvas에 그려 Three.js 텍스처로 반환

function createProceduralTexture(type, color) {
  const canvas = document.createElement('canvas');
  canvas.width = 256; canvas.height = 256;
  const ctx = canvas.getContext('2d');
  const baseColor = color || '#C0BEB5';

  switch (type) {
    case 'brick': drawBrickPattern(ctx, baseColor); break;
    case 'wood': drawWoodPattern(ctx, baseColor); break;
    case 'stone': drawStonePattern(ctx, baseColor); break;
    case 'concrete': drawConcretePattern(ctx, baseColor); break;
    case 'metal': drawMetalPattern(ctx, baseColor); break;
    case 'stucco': drawStuccoPattern(ctx, baseColor); break;
    case 'tile': drawTilePattern(ctx, baseColor); break;
    default:
      ctx.fillStyle = baseColor;
      ctx.fillRect(0, 0, 256, 256);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(2, 2);
  return tex;
}

function drawBrickPattern(ctx, c) {
  ctx.fillStyle = c; ctx.fillRect(0, 0, 256, 256);
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  for (let r = 0; r < 8; r++) {
    const y = r * 32;
    ctx.fillRect(0, y, 256, 3);
    const o = (r % 2) * 32;
    for (let i = -1; i < 5; i++) ctx.fillRect(o + i * 64, y, 3, 32);
  }
  for (let i = 0; i < 200; i++) {
    ctx.fillStyle = `rgba(${Math.random() > 0.5 ? 255 : 0},0,0,0.03)`;
    ctx.fillRect(Math.random() * 256, Math.random() * 256, 8, 4);
  }
}

function drawWoodPattern(ctx, c) {
  ctx.fillStyle = c; ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 30; i++) {
    ctx.strokeStyle = `rgba(100,60,20,${0.1 + Math.random() * 0.15})`;
    ctx.lineWidth = 1 + Math.random() * 2;
    ctx.beginPath();
    const y = Math.random() * 256;
    ctx.moveTo(0, y + Math.random() * 8);
    for (let x = 0; x < 256; x += 20) ctx.lineTo(x, y + Math.sin(x * 0.05) * 4 + Math.random() * 3);
    ctx.stroke();
  }
}

function drawStonePattern(ctx, c) {
  ctx.fillStyle = c; ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 12; i++) {
    const x = Math.random() * 220, y = Math.random() * 220;
    const w = 30 + Math.random() * 50, h = 20 + Math.random() * 40;
    const s = Math.random() * 40 - 20;
    ctx.fillStyle = `rgba(${128 + s},${128 + s},${128 + s},0.3)`;
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = 'rgba(0,0,0,0.2)'; ctx.lineWidth = 1;
    ctx.strokeRect(x, y, w, h);
  }
}

function drawConcretePattern(ctx, c) {
  ctx.fillStyle = c; ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 500; i++) {
    const g = 100 + Math.random() * 100;
    ctx.fillStyle = `rgba(${g},${g},${g},0.08)`;
    ctx.fillRect(Math.random() * 256, Math.random() * 256, 2 + Math.random() * 4, 2 + Math.random() * 4);
  }
}

function drawMetalPattern(ctx, c) {
  ctx.fillStyle = c; ctx.fillRect(0, 0, 256, 256);
  for (let y = 0; y < 256; y += 2) {
    ctx.strokeStyle = `rgba(255,255,255,${0.03 + Math.random() * 0.05})`;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(256, y); ctx.stroke();
  }
}

function drawStuccoPattern(ctx, c) {
  ctx.fillStyle = c; ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 300; i++) {
    const g = 200 + Math.random() * 55;
    ctx.fillStyle = `rgba(${g},${g},${g - 20},0.1)`;
    ctx.beginPath();
    ctx.arc(Math.random() * 256, Math.random() * 256, 1 + Math.random() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawTilePattern(ctx, c) {
  ctx.fillStyle = c; ctx.fillRect(0, 0, 256, 256);
  ctx.strokeStyle = 'rgba(0,0,0,0.15)'; ctx.lineWidth = 2;
  for (let x = 0; x <= 256; x += 64) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 256); ctx.stroke();
  }
  for (let y = 0; y <= 256; y += 64) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(256, y); ctx.stroke();
  }
}
