// 최종 확인용 새 조건 (임계값 고정 후 1회만 실행, 이 결과로 재조정하지 않음)
// 벽 x 위치·두께, 진행 방향(오른쪽→왼쪽), 입구 위치·폭, 무리 크기를 앞 조건과 다르게 둔다.
const RTS = require(process.argv[2] || './ai_artifact/engine.js');
let pass = 0, total = 0; const lines = [];
for (const [wx, ww] of [[300, 24], [620, 60]]) for (const gy of [90, 260, 470]) for (const wpx of [16, 18, 21, 26, 40]) for (const n of [12, 35]) {
  const cols = 5, rows = Math.ceil(n / cols), g = [gy, gy + wpx], units = [];
  const x0 = wx + ww + 120, y0 = Math.min(540 - (rows - 1) * 22, Math.max(20, gy + wpx / 2 - (rows - 1) * 11));
  for (let i = 0; i < n; i++) units.push({ id: 'R' + (i + 1), team: 2, x: x0 + (i % cols) * 22, y: y0 + Math.floor(i / cols) * 22 });
  const sc = { width: 960, height: 560, walls: [{ x: wx, y: 0, w: ww, h: g[0] }, { x: wx, y: g[1], w: ww, h: 560 - g[1] }], units,
    commands: [{ tick: 0, ids: units.map(u => u.id), kind: 'move', x: Math.max(40, wx - 150), y: 280 }], ticks: 15000, seed: 11 };
  let r; try { r = RTS.simulate(sc); } catch (e) { lines.push(`벽 x${wx} w${ww} 입구 y${gy} ${wpx}px n${n}: 입력 거절 ${e.message.slice(0, 50)}`); continue; }
  total++;
  const left = r.final.filter(u => u.x < wx - 8).length; let all = -1;
  r.frames.forEach(f => { if (all < 0 && f.units.every(u => u.x < wx - 8)) all = f.tick; });
  // 비관통 검사
  let viol = 0; for (const f of r.frames) { const a = f.units; for (let i = 0; i < a.length; i++) { for (const w of sc.walls) { const cx = Math.min(Math.max(a[i].x, w.x), w.x + w.w), cy = Math.min(Math.max(a[i].y, w.y), w.y + w.h); const d = (cx === a[i].x && cy === a[i].y) ? -1 : Math.sqrt((a[i].x - cx) ** 2 + (a[i].y - cy) ** 2); if (d < 8 - 1e-6) viol++; } for (let j = i + 1; j < a.length; j++) if ((a[i].x - a[j].x) ** 2 + (a[i].y - a[j].y) ** 2 < 256 - 1e-6) viol++; } }
  if (left === n && viol === 0) pass++;
  lines.push(`벽 x${wx} w${ww} 입구 y${gy} ${wpx}px n${n}: ${left}/${n}${all >= 0 ? ' @' + all : ''} 관통 ${viol}`);
}
console.log(lines.join('\n')); console.log(`전원 통과·관통 0: ${pass}/${total} 조건`);
