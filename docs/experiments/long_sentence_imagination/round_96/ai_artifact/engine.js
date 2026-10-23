/*
 * 마린 소규모 전투 프로토타입 엔진 (직접 작성, 원본 엔진과의 일치를 주장하지 않음)
 * 공식 문서 수치와 근사 규칙의 구분은 rules.json 참조. 아래 RULES 는 rules.json 과 같은 값이다.
 * 브라우저: window.RTS / Node: module.exports
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.RTS = api;
  else if (root) root.RTS = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var RULES = {
    // 공식 문서 원값 (classic.battle.net 사본)
    maxHp: 40,            // "Hit Points: 40"
    damage: 6,            // "Ground Attack: 6"
    armor: 0,             // "Armor: 0"
    cooldownTicks: 15,    // "Cool 15" — 단위 미기재. 근사: 1 tick = 문서 단위 1
    // 근사 환산 (문서에 단위 없음)
    tilePx: 32,           // 근사: 1 타일 = 32px
    rangePx: 4 * 32,      // "Range: 4" × tilePx, 가장자리 간 거리로 비교 (근사)
    sightPx: 7 * 32,      // "Sight: 7" × tilePx, 가장자리 간 거리 (근사)
    // 문서에 없는 값 (선택한 근사)
    radius: 8,            // 충돌 반지름 px ("Size: Small" 은 정성 표기뿐)
    speed: 1.25,          // px/tick
    gridCell: 8,          // 경로탐색 격자 px
    repathTicks: 12,
    waitTicks: 4,         // 판본 2: 유닛에 막혔을 때 옆 걸음 전 대기 tick (근사)
    yieldAfter: 6,        // 판본 2: 유닛에 막힌 상태가 이만큼 이어지면 양보 후퇴 (근사)
    chokeClearance: 80    // 판본 2: 대기·양보 규칙을 적용하는 벽 근처 범위 px (근사)
  };

  var KINDS = { move: 1, attack: 1, attackMove: 1, stop: 1 };
  var EPS = 1e-7;

  function ScenarioError(message) {
    var e = new Error('잘못된 scenario: ' + message);
    e.name = 'ScenarioError';
    e.code = 'INVALID_SCENARIO';
    return e;
  }

  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function isInt(v) { return isNum(v) && Math.floor(v) === v; }
  function isId(v) { return (typeof v === 'string' && v.length > 0) || isInt(v); }

  function cmpId(a, b) {
    var na = typeof a === 'number', nb = typeof b === 'number';
    if (na && nb) return a - b;
    if (na !== nb) return na ? -1 : 1;
    return a < b ? -1 : a > b ? 1 : 0;
  }

  // mulberry32: 시드 기반 결정론 PRNG
  function makeRng(seed) {
    var s = seed >>> 0;
    return function () {
      s = (s + 0x6D2B79F5) >>> 0;
      var t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---------- 기하 ----------
  function circleRectDist(x, y, w) {
    var cx = x < w.x ? w.x : (x > w.x + w.w ? w.x + w.w : x);
    var cy = y < w.y ? w.y : (y > w.y + w.h ? w.y + w.h : y);
    var dx = x - cx, dy = y - cy;
    // 중심이 사각형 안이면 음수 취급
    if (dx === 0 && dy === 0) return -1;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function staticOk(world, x, y, r) {
    if (x < r - EPS || y < r - EPS || x > world.width - r + EPS || y > world.height - r + EPS) return false;
    for (var i = 0; i < world.walls.length; i++) {
      if (circleRectDist(x, y, world.walls[i]) < r - EPS) return false;
    }
    return true;
  }

  // 점에서 벽·맵 경계까지의 최소 거리 (판본 2, 경로 격자 대표점 선택용)
  function clearance(world, x, y) {
    var c = Math.min(x, y, world.width - x, world.height - y);
    for (var i = 0; i < world.walls.length; i++) c = Math.min(c, circleRectDist(x, y, world.walls[i]));
    return c;
  }

  function unitsOk(world, u, x, y) {
    var us = world.order;
    for (var i = 0; i < us.length; i++) {
      var o = us[i];
      if (o === u || !o.alive) continue;
      var dx = o.x - x, dy = o.y - y, rr = o.r + u.r;
      if (dx * dx + dy * dy < rr * rr - EPS) return false;
    }
    return true;
  }

  function edgeDist(a, b) {
    var dx = a.x - b.x, dy = a.y - b.y;
    return Math.sqrt(dx * dx + dy * dy) - a.r - b.r;
  }

  // ---------- 입력 검증 ----------
  function validate(sc) {
    if (!sc || typeof sc !== 'object' || Array.isArray(sc)) throw ScenarioError('객체가 아님');
    if (!isNum(sc.width) || sc.width <= 0 || sc.width > 8192) throw ScenarioError('width 는 (0,8192] 숫자여야 함');
    if (!isNum(sc.height) || sc.height <= 0 || sc.height > 8192) throw ScenarioError('height 는 (0,8192] 숫자여야 함');
    if (!isInt(sc.ticks) || sc.ticks < 0 || sc.ticks > 200000) throw ScenarioError('ticks 는 0~200000 정수여야 함');
    if (!isInt(sc.seed)) throw ScenarioError('seed 는 정수여야 함');
    if (!Array.isArray(sc.walls)) throw ScenarioError('walls 는 배열이어야 함');
    sc.walls.forEach(function (w, i) {
      if (!w || typeof w !== 'object') throw ScenarioError('walls[' + i + '] 가 객체가 아님');
      ['x', 'y', 'w', 'h'].forEach(function (k) {
        if (!isNum(w[k])) throw ScenarioError('walls[' + i + '].' + k + ' 는 유한 숫자여야 함');
      });
      if (w.w <= 0 || w.h <= 0) throw ScenarioError('walls[' + i + '] 의 w,h 는 양수여야 함');
    });
    if (!Array.isArray(sc.units) || sc.units.length === 0) throw ScenarioError('units 는 비지 않은 배열이어야 함');
    var byId = {};
    var tmpWorld = { width: sc.width, height: sc.height, walls: sc.walls };
    sc.units.forEach(function (u, i) {
      var p = 'units[' + i + ']';
      if (!u || typeof u !== 'object') throw ScenarioError(p + ' 가 객체가 아님');
      if (!isId(u.id)) throw ScenarioError(p + '.id 는 비지 않은 문자열 또는 정수여야 함');
      var key = typeof u.id + ':' + u.id;
      if (byId[key]) throw ScenarioError(p + '.id 중복: ' + u.id);
      byId[key] = u;
      if (!isId(u.team)) throw ScenarioError(p + '.team 은 문자열 또는 정수여야 함');
      if (!isNum(u.x) || !isNum(u.y)) throw ScenarioError(p + '.x/.y 는 유한 숫자여야 함');
      if (u.hp !== undefined && (!isNum(u.hp) || u.hp <= 0 || u.hp > RULES.maxHp))
        throw ScenarioError(p + '.hp 는 (0,' + RULES.maxHp + '] 숫자여야 함');
      if (!staticOk(tmpWorld, u.x, u.y, RULES.radius))
        throw ScenarioError(p + ' (id=' + u.id + ') 가 맵 밖이거나 벽과 겹침 (반지름 ' + RULES.radius + 'px)');
    });
    for (var i = 0; i < sc.units.length; i++) for (var j = i + 1; j < sc.units.length; j++) {
      var a = sc.units[i], b = sc.units[j];
      var dx = a.x - b.x, dy = a.y - b.y, rr = 2 * RULES.radius;
      if (dx * dx + dy * dy < rr * rr - EPS)
        throw ScenarioError('units id=' + a.id + ' 와 id=' + b.id + ' 가 겹침 (중심거리 < ' + rr + 'px)');
    }
    if (!Array.isArray(sc.commands)) throw ScenarioError('commands 는 배열이어야 함');
    sc.commands.forEach(function (c, i) {
      var p = 'commands[' + i + ']';
      if (!c || typeof c !== 'object') throw ScenarioError(p + ' 가 객체가 아님');
      if (!isInt(c.tick) || c.tick < 0) throw ScenarioError(p + '.tick 은 0 이상 정수여야 함');
      if (!KINDS[c.kind]) throw ScenarioError(p + '.kind 는 move/attack/attackMove/stop 중 하나여야 함 (받음: ' + c.kind + ')');
      if (!Array.isArray(c.ids) || c.ids.length === 0) throw ScenarioError(p + '.ids 는 비지 않은 배열이어야 함');
      c.ids.forEach(function (id) {
        if (!isId(id) || !byId[typeof id + ':' + id]) throw ScenarioError(p + '.ids 에 없는 유닛: ' + JSON.stringify(id));
      });
      if (c.kind === 'move' || c.kind === 'attackMove') {
        if (!isNum(c.x) || !isNum(c.y)) throw ScenarioError(p + ' (' + c.kind + ') 은 유한 숫자 x,y 가 필요함');
      }
      if (c.kind === 'attack') {
        var t = isId(c.targetId) ? byId[typeof c.targetId + ':' + c.targetId] : null;
        if (!t) throw ScenarioError(p + ' (attack) 의 targetId 가 없는 유닛: ' + JSON.stringify(c.targetId));
        c.ids.forEach(function (id) {
          if (byId[typeof id + ':' + id].team === t.team)
            throw ScenarioError(p + ' (attack) 은 같은 팀 유닛을 대상으로 할 수 없음 (id=' + id + ')');
        });
      }
    });
  }

  // ---------- 경로탐색 (격자 A*, 벽만 고려) ----------
  function buildGrid(world) {
    var cs = RULES.gridCell;
    var gw = Math.max(1, Math.floor(world.width / cs)), gh = Math.max(1, Math.floor(world.height / cs));
    var n = gw * gh, free = new Uint8Array(n), px = new Float64Array(n), py = new Float64Array(n);
    var r = RULES.radius, half = cs / 2, SUB = 0.5, CAP = r + cs;
    // 판본 2: 칸마다 '대표점'을 둔다. 칸 안 0.5px 표본 중 벽·경계까지의 여유(clearance, 상한 r+칸)가
    // 가장 큰 점, 동률이면 칸 중심에 가까운 점. 여유가 r 이상인 점이 없으면 막힌 칸.
    // 여유 최대점은 좁은 통로에서 중심선에 정렬돼 이웃 대표점끼리 연결된다.
    // (판본 1 은 칸 중심 + 여유 1px 만 보아 지름 근처 폭의 입구를 막힌 것으로 판정했다.)
    for (var gy = 0; gy < gh; gy++) for (var gx = 0; gx < gw; gx++) {
      var k = gy * gw + gx, cx = gx * cs + half, cy = gy * cs + half;
      if (clearance(world, cx, cy) >= CAP) { free[k] = 1; px[k] = cx; py[k] = cy; continue; }
      var bestC = -1, bestD = Infinity;
      for (var oy = 0; oy <= cs; oy += SUB) for (var ox = 0; ox <= cs; ox += SUB) {
        var qx = gx * cs + ox, qy = gy * cs + oy;
        var cl = Math.min(CAP, clearance(world, qx, qy));
        if (cl < r - EPS) continue;
        var dd = (qx - cx) * (qx - cx) + (qy - cy) * (qy - cy);
        if (cl > bestC + EPS || (Math.abs(cl - bestC) <= EPS && dd < bestD)) { bestC = cl; bestD = dd; px[k] = qx; py[k] = qy; }
      }
      if (bestC >= 0) free[k] = 1;
    }
    // 이웃 칸 사이 간선: 두 대표점을 잇는 선분 위에 반지름 r 원이 벽 없이 놓일 때만 연결
    var DX = [1, -1, 0, 0, 1, 1, -1, -1], DY = [0, 0, 1, -1, 1, -1, 1, -1];
    var edge = new Uint8Array(n * 8);
    for (var k2 = 0; k2 < n; k2++) {
      if (!free[k2]) continue;
      var x0 = k2 % gw, y0 = (k2 / gw) | 0;
      for (var d = 0; d < 8; d++) {
        var nx = x0 + DX[d], ny = y0 + DY[d];
        if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue;
        var nk = ny * gw + nx;
        if (free[nk] && segmentClear(world, px[k2], py[k2], px[nk], py[nk], r, 1)) edge[k2 * 8 + d] = 1;
      }
    }
    return { cs: cs, gw: gw, gh: gh, free: free, px: px, py: py, edge: edge };
  }

  function nearestFree(grid, gx, gy) {
    gx = Math.min(grid.gw - 1, Math.max(0, gx)); gy = Math.min(grid.gh - 1, Math.max(0, gy));
    if (grid.free[gy * grid.gw + gx]) return gy * grid.gw + gx;
    for (var rad = 1; rad < Math.max(grid.gw, grid.gh); rad++) {
      var best = -1, bd = Infinity;
      for (var dy = -rad; dy <= rad; dy++) for (var dx = -rad; dx <= rad; dx++) {
        if (Math.abs(dx) !== rad && Math.abs(dy) !== rad) continue;
        var x = gx + dx, y = gy + dy;
        if (x < 0 || y < 0 || x >= grid.gw || y >= grid.gh) continue;
        var k = y * grid.gw + x;
        if (grid.free[k]) { var d = dx * dx + dy * dy; if (d < bd) { bd = d; best = k; } }
      }
      if (best >= 0) return best;
    }
    return -1;
  }

  function segmentClear(world, ax, ay, bx, by, radius, stepPx) {
    if (radius === undefined) radius = RULES.radius + 0.5;
    var dx = bx - ax, dy = by - ay, len = Math.sqrt(dx * dx + dy * dy);
    var n = Math.max(1, Math.ceil(len / (stepPx || 3)));
    for (var i = 0; i <= n; i++) {
      if (!staticOk(world, ax + dx * i / n, ay + dy * i / n, radius)) return false;
    }
    return true;
  }

  function findPath(world, sx, sy, tx, ty) {
    if (segmentClear(world, sx, sy, tx, ty)) return [{ x: tx, y: ty }];
    var g = world.grid, cs = g.cs;
    var s = nearestFree(g, Math.floor(sx / cs), Math.floor(sy / cs));
    var t = nearestFree(g, Math.floor(tx / cs), Math.floor(ty / cs));
    if (s < 0 || t < 0) return [];
    var n = g.gw * g.gh;
    var gs = new Float64Array(n).fill(Infinity), came = new Int32Array(n).fill(-1), closed = new Uint8Array(n);
    var heap = []; // [f, seq, k] 이진 힙, 동률은 seq 로 고정
    var seq = 0;
    function push(f, k) {
      heap.push([f, seq++, k]); var i = heap.length - 1;
      while (i > 0) { var p = (i - 1) >> 1; if (less(heap[i], heap[p])) { var tmp = heap[i]; heap[i] = heap[p]; heap[p] = tmp; i = p; } else break; }
    }
    function less(a, b) { return a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]); }
    function pop() {
      var top = heap[0], last = heap.pop();
      if (heap.length) {
        heap[0] = last; var i = 0;
        for (;;) {
          var l = 2 * i + 1, r = l + 1, m = i;
          if (l < heap.length && less(heap[l], heap[m])) m = l;
          if (r < heap.length && less(heap[r], heap[m])) m = r;
          if (m === i) break; var tmp = heap[i]; heap[i] = heap[m]; heap[m] = tmp; i = m;
        }
      }
      return top;
    }
    var tgx = t % g.gw, tgy = (t / g.gw) | 0;
    function h(k) { var dx = Math.abs(k % g.gw - tgx), dy = Math.abs(((k / g.gw) | 0) - tgy); return Math.max(dx, dy) + 0.41421356 * Math.min(dx, dy); }
    gs[s] = 0; push(h(s), s);
    var DIRS = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1], [1, 1, 1.41421356], [1, -1, 1.41421356], [-1, 1, 1.41421356], [-1, -1, 1.41421356]];
    var found = false, bestK = s, bestH = h(s);
    while (heap.length) {
      var k = pop()[2];
      if (closed[k]) continue; closed[k] = 1;
      if (k === t) { found = true; break; }
      var hk = h(k);
      if (hk < bestH) { bestH = hk; bestK = k; }
      var x = k % g.gw, y = (k / g.gw) | 0;
      for (var d = 0; d < 8; d++) {
        if (!g.edge[k * 8 + d]) continue; // 간선 선분 검사로 모서리 자르기·벽 관통 차단
        var nk = (y + DIRS[d][1]) * g.gw + (x + DIRS[d][0]);
        if (closed[nk]) continue;
        var ng = gs[k] + DIRS[d][2];
        if (ng < gs[nk]) { gs[nk] = ng; came[nk] = k; push(ng + h(nk), nk); }
      }
    }
    // 판본 2: 목표에 닿을 수 없으면 도달 가능한 칸 중 목표에 가장 가까운 칸까지 간다
    var end = found ? t : bestK;
    var cells = [];
    for (var c = end; c !== -1; c = came[c]) cells.push(c);
    cells.reverse();
    var pts = cells.map(function (c) { return { x: g.px[c], y: g.py[c] }; });
    if (found && staticOk(world, tx, ty, RULES.radius)) pts.push({ x: tx, y: ty });
    // 가시선 단순화
    var out = [], cx = sx, cy = sy, i = 0;
    while (i < pts.length) {
      var j = pts.length - 1;
      while (j > i && !segmentClear(world, cx, cy, pts[j].x, pts[j].y)) j--;
      out.push(pts[j]); cx = pts[j].x; cy = pts[j].y; i = j + 1;
    }
    return out;
  }

  // ---------- 월드 ----------
  function createWorld(scenario) {
    validate(scenario);
    var world = {
      width: scenario.width, height: scenario.height,
      walls: scenario.walls.map(function (w) { return { x: w.x, y: w.y, w: w.w, h: w.h }; }),
      tick: 0, rng: makeRng(scenario.seed), events: [], units: [], byId: {}, commandsByTick: {}
    };
    world.grid = buildGrid(world);
    scenario.units.forEach(function (u) {
      var unit = {
        id: u.id, team: u.team, x: u.x, y: u.y, r: RULES.radius,
        hp: u.hp === undefined ? RULES.maxHp : u.hp, alive: true,
        cooldown: 0, order: null, target: null, autoTarget: false,
        path: [], pathGoal: null, pathAge: 0, stuck: 0, lastFire: -1, unitBlocked: 0, yieldTicks: 0
      };
      world.units.push(unit);
      world.byId[typeof u.id + ':' + u.id] = unit;
    });
    world.order = world.units.slice().sort(function (a, b) { return cmpId(a.id, b.id); });
    scenario.commands.forEach(function (c, i) {
      (world.commandsByTick[c.tick] = world.commandsByTick[c.tick] || []).push(c);
    });
    return world;
  }

  function getUnit(world, id) { return world.byId[typeof id + ':' + id] || null; }

  function applyCommand(world, c) {
    var target = c.kind === 'attack' ? getUnit(world, c.targetId) : null;
    c.ids.forEach(function (id) {
      var u = getUnit(world, id);
      if (!u || !u.alive) return; // 죽은 유닛 명령은 무시
      u.path = []; u.pathGoal = null; u.stuck = 0; u.autoTarget = false; u.unitBlocked = 0; u.yieldTicks = 0;
      if (c.kind === 'stop') { u.order = null; u.target = null; }
      else if (c.kind === 'move') { u.order = { kind: 'move', x: c.x, y: c.y }; u.target = null; }
      else if (c.kind === 'attackMove') { u.order = { kind: 'attackMove', x: c.x, y: c.y }; u.target = null; }
      else if (c.kind === 'attack') {
        if (!target || !target.alive) { u.order = null; u.target = null; }
        else { u.order = { kind: 'attack', targetId: c.targetId }; u.target = target; }
      }
    });
  }

  // 가장 가까운(가장자리 거리) 적, 동률은 시드 PRNG 로 결정
  function acquire(world, u, maxDist) {
    var best = [], bd = Infinity;
    for (var i = 0; i < world.order.length; i++) {
      var o = world.order[i];
      if (!o.alive || o.team === u.team) continue;
      var d = edgeDist(u, o);
      if (d > maxDist + EPS) continue;
      if (d < bd - EPS) { bd = d; best = [o]; } else if (Math.abs(d - bd) <= EPS) best.push(o);
    }
    if (!best.length) return null;
    if (best.length === 1) return best[0];
    return best[Math.floor(world.rng() * best.length)];
  }

  function decide(world, u) {
    // 표적 유효성
    if (u.target && !u.target.alive) { u.target = null; if (u.order && u.order.kind === 'attack') u.order = null; }
    var ord = u.order;
    if (ord && ord.kind === 'move') return { moveTo: { x: ord.x, y: ord.y } };
    if (ord && ord.kind === 'attack') return { attack: u.target };
    // attackMove 또는 대기: 시야 안의 적을 자동 획득
    if (u.target && u.autoTarget && edgeDist(u, u.target) > RULES.sightPx + EPS) u.target = null;
    if (!u.target) { u.target = acquire(world, u, RULES.sightPx); u.autoTarget = !!u.target; }
    if (u.target) return { attack: u.target };
    if (ord && ord.kind === 'attackMove') return { moveTo: { x: ord.x, y: ord.y } };
    return {};
  }

  // 회피 회전표 [cos, sin] (0°, ±25°, ±50°, ±75°, ±100°). 런타임마다 sin/cos/atan2 의 마지막 비트가
  // 다를 수 있어(Chrome 151 과 Node 20 에서 실측) 엔진은 사칙연산·sqrt(IEEE 정확 반올림)와 상수만 쓴다.
  var ROT = [[1, 0], [0.906321442627, 0.422588975998], [0.906321442627, -0.422588975998],
    [0.642760511226, 0.76606718061], [0.642760511226, -0.76606718061],
    [0.258816088398, 0.965926618531], [0.258816088398, -0.965926618531],
    [-0.173619370002, 0.984812832146], [-0.173619370002, -0.984812832146]];
  // 양보 후퇴 방향 [cos, sin] (180°, ±135°) — 판본 2
  var BACK = [[-1, 0], [-0.707106781187, 0.707106781187], [-0.707106781187, -0.707106781187]];

  function moveToward(world, u, gx, gy, arriveDist) {
    var dxg = gx - u.x, dyg = gy - u.y;
    var dist = Math.sqrt(dxg * dxg + dyg * dyg);
    if (dist <= arriveDist) return 'arrived';
    var needPath = !u.pathGoal || Math.abs(u.pathGoal.x - gx) > 16 || Math.abs(u.pathGoal.y - gy) > 16 || u.pathAge >= RULES.repathTicks * (u.path.length ? 4 : 1) || !u.path.length;
    if (needPath) { u.path = findPath(world, u.x, u.y, gx, gy); u.pathGoal = { x: gx, y: gy }; u.pathAge = 0; }
    u.pathAge++;
    // 판본 2: 2px 안에 들어왔더라도 다음 경유점까지 반지름 r 로 직진 가능할 때만 넘긴다
    // (좁은 통로에서 경유점을 일찍 버리고 벽 쪽으로 비스듬히 들어가 걸리는 것을 막음)
    while (u.path.length > 1) {
      var w = u.path[0], ddx = w.x - u.x, ddy = w.y - u.y, nxt = u.path[1];
      if (ddx * ddx + ddy * ddy > 4) break;
      if (segmentClear(world, u.x, u.y, nxt.x, nxt.y, u.r, 1)) { u.path.shift(); continue; }
      // 차선 합류: 경유점 근처에서 다음 구간으로 직진할 수 없으면(지름과 거의 같은 폭의 통로처럼
      // 오차 허용이 0에 가까운 경우) 구간 w→nxt 위의 수직 투영점을 새 경유점으로 삼아 선 위로 정확히 들어간다.
      var sx = nxt.x - w.x, sy = nxt.y - w.y, sl = sx * sx + sy * sy;
      if (sl > EPS) {
        var tt = ((u.x - w.x) * sx + (u.y - w.y) * sy) / sl;
        if (tt > 0 && tt < 1) {
          var qx = w.x + sx * tt, qy = w.y + sy * tt;
          var gap2 = (qx - u.x) * (qx - u.x) + (qy - u.y) * (qy - u.y);
          if (gap2 > EPS * EPS && staticOk(world, qx, qy, u.r)) u.path[0] = { x: qx, y: qy };
        }
      }
      break;
    }
    if (!u.path.length) { u.stuck++; return 'noPath'; }
    var wp = u.path[0];
    var dx = wp.x - u.x, dy = wp.y - u.y, d = Math.sqrt(dx * dx + dy * dy);
    if (d < EPS) { u.path.shift(); return 'moving'; }
    var step = Math.min(RULES.speed, d);
    var ux = dx / d, uy = dy / d;
    // 회피 방향 선호를 유닛마다 번갈아 대칭 교착 완화
    var idx = world.order.indexOf(u);
    var flip = (idx % 2) ? -1 : 1;
    // 판본 2: 양보 중이면 진행 반대쪽(180°, ±135°)으로 물러난다
    if (u.yieldTicks > 0) {
      u.yieldTicks--;
      for (var b = 0; b < BACK.length; b++) {
        var bc = BACK[b][0], bs = flip * BACK[b][1], bstep = RULES.speed * 0.6;
        var bx = u.x + (bc * ux - bs * uy) * bstep, by = u.y + (bs * ux + bc * uy) * bstep;
        if (staticOk(world, bx, by, u.r) && unitsOk(world, u, bx, by)) { u.x = bx; u.y = by; return 'yielding'; }
      }
      return 'blocked';
    }
    // 판본 2: 벽 근처(여유 < chokeClearance)에서 정면 한 걸음이 벽이 아니라 다른 유닛에 막히면 곧바로 옆으로
    // 끼어들지 않고 기다린다. waitTicks 동안 대기 → 이후 옆 걸음 허용 → yieldAfter 에 이르면 양보(후퇴).
    // 벽에 막힌 경우와 벽에서 먼 평지는 판본 1 처럼 바로 회전 후보로 미끄러진다.
    var fx = u.x + ux * step, fy = u.y + uy * step;
    var frontOk = staticOk(world, fx, fy, u.r);
    if (frontOk && unitsOk(world, u, fx, fy)) { u.x = fx; u.y = fy; u.unitBlocked = 0; u.stuck = Math.max(0, u.stuck - 1); return 'moving'; }
    if (frontOk && clearance(world, u.x, u.y) < RULES.chokeClearance) {
      u.unitBlocked++;
      if (u.unitBlocked >= RULES.yieldAfter) { u.unitBlocked = 0; u.yieldTicks = 2 + (idx % 4); u.stuck++; return 'blocked'; }
      if (u.unitBlocked < RULES.waitTicks) { u.stuck++; return 'waiting'; }
    }
    var fracs = [1, 0.5];
    for (var f = 0; f < fracs.length; f++) {
      for (var a = 0; a < ROT.length; a++) {
        var c = ROT[a][0], sn = flip * ROT[a][1];
        var s = step * fracs[f] * (a === 0 ? 1 : 0.85);
        var nx = u.x + (c * ux - sn * uy) * s, ny = u.y + (sn * ux + c * uy) * s;
        if (staticOk(world, nx, ny, u.r) && unitsOk(world, u, nx, ny)) {
          u.x = nx; u.y = ny;
          if (!frontOk) u.unitBlocked = 0;
          u.stuck++;
          return 'moving';
        }
      }
    }
    u.stuck++;
    return 'blocked';
  }

  function snapshot(u) {
    return {
      id: u.id, team: u.team, x: u.x, y: u.y, hp: u.hp, alive: u.alive,
      cooldown: u.cooldown, order: u.order ? u.order.kind : null,
      targetId: u.target ? u.target.id : null
    };
  }

  // 한 tick 진행: (1) 이 tick 명령 적용 (2) 판단 (3) 동시 사격 해소 (4) 이동 (5) 프레임 기록
  function step(world, extraCommands) {
    var t = world.tick;
    var cmds = (world.commandsByTick[t] || []).concat(extraCommands || []);
    cmds.forEach(function (c) { applyCommand(world, c); });
    var us = world.order, plans = [], shots = [];
    for (var i = 0; i < us.length; i++) {
      var u = us[i];
      if (!u.alive) continue;
      if (u.cooldown > 0) u.cooldown--;
      var p = decide(world, u); p.u = u; plans.push(p);
      if (p.attack && edgeDist(u, p.attack) <= RULES.rangePx + EPS) {
        p.inRange = true;
        if (u.cooldown === 0) shots.push({ u: u, t: p.attack });
      }
    }
    // 동시 해소: 같은 tick 의 사격은 피해 적용 전에 모두 확정
    shots.forEach(function (s) {
      s.u.cooldown = RULES.cooldownTicks; s.u.lastFire = t;
      world.events.push({ tick: t, type: 'fire', attacker: s.u.id, target: s.t.id });
    });
    shots.forEach(function (s) {
      var dmg = Math.max(0.5, RULES.damage - RULES.armor);
      var before = s.t.hp;
      s.t.hp = Math.max(0, s.t.hp - dmg);
      world.events.push({ tick: t, type: 'damage', attacker: s.u.id, target: s.t.id, amount: before - s.t.hp, hp: s.t.hp });
    });
    shots.forEach(function (s) {
      if (s.t.alive && s.t.hp <= 0) {
        s.t.alive = false; s.t.order = null; s.t.target = null; s.t.path = [];
        world.events.push({ tick: t, type: 'death', unit: s.t.id, killer: s.u.id });
      }
    });
    plans.forEach(function (p) {
      var u = p.u;
      if (!u.alive) return;
      if (p.attack && !p.inRange && p.attack.alive) {
        moveToward(world, u, p.attack.x, p.attack.y, 0);
      } else if (p.moveTo) {
        var res = moveToward(world, u, p.moveTo.x, p.moveTo.y, 2);
        var dx = p.moveTo.x - u.x, dy = p.moveTo.y - u.y;
        var dist = Math.sqrt(dx * dx + dy * dy);
        // 도착 또는 목표 근처에서 막힘(무리 도착) → 대기 상태로
        if (res === 'arrived' || (u.stuck > 20 && dist < 64) || (res === 'noPath' && u.stuck > 5)) {
          u.order = null; u.path = []; u.stuck = 0;
        }
      }
    });
    world.tick = t + 1;
    var frame = { tick: t, units: world.units.map(snapshot) };
    return frame;
  }

  function finalState(world) {
    return world.units.map(function (u) { return { id: u.id, team: u.team, x: u.x, y: u.y, hp: u.hp, alive: u.alive }; });
  }

  function hashString(s) {
    var h = 0x811c9dc5;
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return ('00000000' + h.toString(16)).slice(-8);
  }

  function simulate(scenario) {
    var world = createWorld(scenario);
    var frames = [];
    for (var t = 0; t < scenario.ticks; t++) frames.push(step(world));
    var final = finalState(world);
    return {
      final: final, events: world.events, frames: frames, ticks: world.tick,
      hash: hashString(JSON.stringify(final) + '|' + JSON.stringify(world.events)),
      rules: RULES
    };
  }

  return {
    simulate: simulate, validate: validate, createWorld: createWorld, step: step,
    finalState: finalState, hashString: hashString, edgeDist: edgeDist,
    findPath: findPath, RULES: RULES, version: '0.2.0-variant'
  };
});
