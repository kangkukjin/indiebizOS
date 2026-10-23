/* UI: 같은 engine.js 의 createWorld/step 으로 진행하며, 모든 명령(사용자·적 자동 지휘)을 tick 과 함께 기록한다. */
(function () {
  'use strict';
  var RTS = window.RTS, SC = window.RTS_SCENARIO, R = RTS.RULES;
  var cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  var PLAYER = 1, ENEMY = 2, AI_PERIOD = 48, AI_START = 24;

  var app = {
    base: null, world: null, log: [], pending: [], selected: {}, inspect: null,
    paused: false, mode: 'live', replay: null, cmdMode: null, drag: null,
    flashes: [], lastFrame: null, ended: false, expected: null
  };
  window.APP = app; // 헤드리스 검증용 읽기 창구

  function msg(text, err) { var m = document.getElementById('msg'); m.textContent = text; m.className = err ? 'err' : ''; }

  function start(scenario, mode, expected) {
    app.base = scenario;
    app.world = RTS.createWorld(scenario);
    app.log = []; app.pending = []; app.selected = {}; app.inspect = null; app.cmdMode = null;
    app.flashes = []; app.ended = false; app.mode = mode; app.expected = expected || null;
    app.replayTicks = mode === 'replay' ? scenario.ticks : null;
    app.paused = false; app.acc = 0;
  }
  function restart() {
    start(SC.defaultScenario({ seed: 12345 }), 'live');
    msg('재시작: 같은 초기 배치(seed 12345), 명령 기록 비움');
  }

  function aliveUnits(team) { return app.world.order.filter(function (u) { return u.alive && (team === undefined || u.team === team); }); }
  function selectedIds() {
    return app.world.order.filter(function (u) { return u.alive && app.selected[u.id]; }).map(function (u) { return u.id; });
  }

  function issue(kind, x, y, targetId) {
    if (app.mode !== 'live') { msg('재생 중에는 명령을 낼 수 없습니다. 재시작(R)으로 실시간 모드로 돌아갑니다.', true); return; }
    var ids = selectedIds();
    if (!ids.length) { msg('선택된 아군이 없습니다', true); return; }
    var c = { tick: app.world.tick, ids: ids, kind: kind, source: 'user' };
    if (kind === 'move' || kind === 'attackMove') { c.x = Math.round(x); c.y = Math.round(y); }
    if (kind === 'attack') c.targetId = targetId;
    app.pending.push(c);
    msg(kind + ' 명령 (' + ids.length + '기) → tick ' + c.tick + ' 시작에 적용');
  }

  function tickOnce() {
    var w = app.world;
    if (app.mode === 'live') {
      var add = (document.getElementById('cAI').checked ? SC.enemyAiCommands(w, ENEMY, AI_PERIOD, AI_START) : []).concat(app.pending);
      app.pending = [];
      add.forEach(function (c) { (w.commandsByTick[w.tick] = w.commandsByTick[w.tick] || []).push(c); app.log.push(c); });
    }
    var evStart = w.events.length;
    app.lastFrame = RTS.step(w);
    for (var i = evStart; i < w.events.length; i++) {
      var e = w.events[i];
      if (e.type === 'fire') app.flashes.push({ a: e.attacker, t: e.target, until: w.tick + 3 });
    }
    app.flashes = app.flashes.filter(function (f) { return f.until > w.tick; });
    if (app.mode === 'replay' && w.tick >= app.replayTicks) {
      app.paused = true; app.ended = true;
      var h = currentHash();
      if (app.expected && app.expected.hash) msg('재생 종료 tick ' + w.tick + ' · hash ' + h + (h === app.expected.hash ? ' = 기록 시 hash (일치)' : ' ≠ 기록 시 hash ' + app.expected.hash + ' (불일치)'), h !== app.expected.hash);
      else msg('재생 종료 tick ' + w.tick + ' · hash ' + h);
    }
    if (!app.ended && (!aliveUnits(PLAYER).length || !aliveUnits(ENEMY).length)) {
      app.ended = true;
      msg((aliveUnits(PLAYER).length ? '아군 승리' : aliveUnits(ENEMY).length ? '적 승리' : '양측 전멸') + ' · tick ' + w.tick + ' · hash ' + currentHash() + ' (계속 진행 가능, 기록 내보내기 가능)');
    }
  }
  function currentHash() { return RTS.hashString(JSON.stringify(RTS.finalState(app.world)) + '|' + JSON.stringify(app.world.events)); }

  function exportRecord() {
    var w = app.world;
    var scenario = JSON.parse(JSON.stringify(app.base));
    scenario.commands = JSON.parse(JSON.stringify(app.mode === 'live' ? app.log : app.base.commands));
    scenario.ticks = w.tick;
    return { format: 'marine-skirmish-record/1', engine: RTS.version, scenario: scenario, expected: { ticks: w.tick, hash: currentHash() } };
  }
  function download(obj) {
    var blob = new Blob([JSON.stringify(obj, null, 1)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'marine-record-tick' + obj.scenario.ticks + '.json';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }
  function replayRecord(rec) {
    var sc = rec && rec.scenario ? rec.scenario : rec;
    try { RTS.validate(JSON.parse(JSON.stringify(sc))); }
    catch (e) { msg('불러오기 거절: ' + e.message, true); return false; }
    start(sc, 'replay', rec.expected);
    msg('재생 시작: 명령 ' + sc.commands.length + '건, ' + sc.ticks + ' tick');
    return true;
  }
  app.exportRecord = exportRecord; app.replayRecord = replayRecord; app.currentHash = currentHash;

  // ---------- 입력 ----------
  function mousePos(ev) { var r = cv.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; }
  function unitAt(p) {
    var best = null, bd = Infinity;
    app.world.order.forEach(function (u) {
      if (!u.alive) return;
      var d = Math.hypot(u.x - p.x, u.y - p.y);
      if (d <= u.r + 3 && d < bd) { bd = d; best = u; }
    });
    return best;
  }
  cv.addEventListener('contextmenu', function (ev) { ev.preventDefault(); });
  cv.addEventListener('mousedown', function (ev) {
    var p = mousePos(ev);
    if (ev.button === 2) {
      var u = unitAt(p);
      if (u && u.team !== PLAYER) issue('attack', 0, 0, u.id); else issue('move', p.x, p.y);
      app.cmdMode = null; return;
    }
    if (ev.button !== 0) return;
    if (app.cmdMode) {
      var t = unitAt(p);
      if (app.cmdMode === 'attackMove' && t && t.team !== PLAYER) issue('attack', 0, 0, t.id);
      else issue(app.cmdMode, p.x, p.y);
      app.cmdMode = null; return;
    }
    app.drag = { x0: p.x, y0: p.y, x1: p.x, y1: p.y, add: ev.shiftKey };
  });
  window.addEventListener('mousemove', function (ev) { if (app.drag) { var p = mousePos(ev); app.drag.x1 = p.x; app.drag.y1 = p.y; } });
  window.addEventListener('mouseup', function (ev) {
    if (!app.drag || ev.button !== 0) return;
    var d = app.drag; app.drag = null;
    var x0 = Math.min(d.x0, d.x1), x1 = Math.max(d.x0, d.x1), y0 = Math.min(d.y0, d.y1), y1 = Math.max(d.y0, d.y1);
    if (!d.add) app.selected = {};
    app.inspect = null;
    if (x1 - x0 < 4 && y1 - y0 < 4) {
      var u = unitAt({ x: d.x1, y: d.y1 });
      if (u && u.team === PLAYER) { if (d.add && app.selected[u.id]) delete app.selected[u.id]; else app.selected[u.id] = true; }
      else if (u) app.inspect = u.id;
    } else {
      aliveUnits(PLAYER).forEach(function (u) { if (u.x >= x0 && u.x <= x1 && u.y >= y0 && u.y <= y1) app.selected[u.id] = true; });
    }
  });
  window.addEventListener('keydown', function (ev) {
    if (ev.target && ev.target.tagName === 'INPUT') return;
    var k = ev.key.toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && k === 'a') { ev.preventDefault(); app.selected = {}; aliveUnits(PLAYER).forEach(function (u) { app.selected[u.id] = true; }); return; }
    if (k === ' ' || k === 'p') { ev.preventDefault(); togglePause(); }
    else if (k === 'r') restart();
    else if (k === 'a') { app.cmdMode = 'attackMove'; msg('공격 이동: 좌클릭으로 지점(또는 적) 지정'); }
    else if (k === 'm') { app.cmdMode = 'move'; msg('이동: 좌클릭으로 지점 지정'); }
    else if (k === 's') issue('stop');
    else if (k === 'escape') { app.cmdMode = null; msg(''); }
  });
  function togglePause() { if (app.ended && app.mode === 'replay') return; app.paused = !app.paused; }

  document.getElementById('bPause').onclick = togglePause;
  document.getElementById('bRestart').onclick = restart;
  document.getElementById('bExport').onclick = function () { download(exportRecord()); msg('기록 내보내기: 명령 ' + exportRecord().scenario.commands.length + '건'); };
  document.getElementById('bReplay').onclick = function () { replayRecord(exportRecord()); };
  document.getElementById('fImport').onchange = function (ev) {
    var f = ev.target.files[0]; if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      var rec; try { rec = JSON.parse(rd.result); } catch (e) { msg('JSON 파싱 실패: ' + e.message, true); return; }
      replayRecord(rec);
    };
    rd.readAsText(f); ev.target.value = '';
  };

  // ---------- 그리기 ----------
  function draw() {
    var w = app.world;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = '#2b3324'; ctx.fillRect(0, 0, w.width, w.height);
    ctx.fillStyle = '#6b6252'; ctx.strokeStyle = '#998';
    w.walls.forEach(function (b) { ctx.fillRect(b.x, b.y, b.w, b.h); ctx.strokeRect(b.x + 0.5, b.y + 0.5, b.w - 1, b.h - 1); });
    var showAll = document.getElementById('cRanges').checked;
    // 사망 표시
    w.order.forEach(function (u) {
      if (u.alive) return;
      ctx.strokeStyle = u.team === PLAYER ? '#4a6080' : '#80504a'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(u.x - 5, u.y - 5); ctx.lineTo(u.x + 5, u.y + 5); ctx.moveTo(u.x + 5, u.y - 5); ctx.lineTo(u.x - 5, u.y + 5); ctx.stroke();
    });
    ctx.lineWidth = 1;
    // 사거리(가장자리 기준 → 원 중심에서 r + rangePx) · 시야
    w.order.forEach(function (u) {
      if (!u.alive) return;
      var sel = app.selected[u.id] || app.inspect === u.id;
      if (sel || showAll) {
        ctx.strokeStyle = u.team === PLAYER ? 'rgba(120,180,255,0.55)' : 'rgba(255,130,120,0.55)';
        ctx.beginPath(); ctx.arc(u.x, u.y, u.r + R.rangePx, 0, 6.2832); ctx.stroke();
      }
      if (sel) {
        ctx.setLineDash([4, 4]); ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.beginPath(); ctx.arc(u.x, u.y, u.r + R.sightPx, 0, 6.2832); ctx.stroke(); ctx.setLineDash([]);
        if (u.target && u.target.alive) { ctx.strokeStyle = 'rgba(255,80,80,0.5)'; ctx.beginPath(); ctx.moveTo(u.x, u.y); ctx.lineTo(u.target.x, u.target.y); ctx.stroke(); }
        else if (u.order && u.order.x !== undefined) { ctx.strokeStyle = u.order.kind === 'move' ? 'rgba(120,255,120,0.4)' : 'rgba(255,200,80,0.45)'; ctx.beginPath(); ctx.moveTo(u.x, u.y); ctx.lineTo(u.order.x, u.order.y); ctx.stroke(); }
      }
    });
    // 발사 섬광
    app.flashes.forEach(function (f) {
      var a = RTS_get(f.a), t = RTS_get(f.t); if (!a || !t) return;
      ctx.strokeStyle = 'rgba(255,240,150,0.9)'; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(t.x, t.y); ctx.stroke();
    });
    // 유닛, 체력 막대, 공격 주기(쿨다운) 막대
    w.order.forEach(function (u) {
      if (!u.alive) return;
      ctx.fillStyle = u.team === PLAYER ? '#3d8bff' : '#e5483f';
      ctx.beginPath(); ctx.arc(u.x, u.y, u.r, 0, 6.2832); ctx.fill();
      if (app.selected[u.id]) { ctx.strokeStyle = '#7f7'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(u.x, u.y, u.r + 2, 0, 6.2832); ctx.stroke(); ctx.lineWidth = 1; }
      var hpw = 18, hx = u.x - hpw / 2, hy = u.y - u.r - 7;
      ctx.fillStyle = '#300'; ctx.fillRect(hx, hy, hpw, 3);
      var ratio = u.hp / R.maxHp;
      ctx.fillStyle = ratio > 0.6 ? '#3e3' : ratio > 0.3 ? '#ec3' : '#e33'; ctx.fillRect(hx, hy, hpw * ratio, 3);
      if (u.cooldown > 0) { ctx.fillStyle = '#ccf'; ctx.fillRect(hx, hy + 4, hpw * u.cooldown / R.cooldownTicks, 2); }
    });
    if (app.drag) {
      var d = app.drag; ctx.strokeStyle = '#7f7';
      ctx.strokeRect(Math.min(d.x0, d.x1), Math.min(d.y0, d.y1), Math.abs(d.x1 - d.x0), Math.abs(d.y1 - d.y0));
    }
    if (app.paused) { ctx.fillStyle = 'rgba(0,0,0,0.35)'; ctx.fillRect(0, 0, 150, 30); ctx.fillStyle = '#fff'; ctx.font = '16px sans-serif'; ctx.fillText(app.ended && app.mode === 'replay' ? '재생 종료' : '일시정지', 10, 21); }
    renderPanels();
  }
  function RTS_get(id) { var u = app.world.byId[typeof id + ':' + id]; return u; }

  function renderPanels() {
    var w = app.world;
    var a = aliveUnits(PLAYER).length, e = aliveUnits(ENEMY).length;
    var kills = w.events.filter(function (x) { return x.type === 'death'; }).length;
    document.getElementById('status').innerHTML =
      '모드 <b>' + (app.mode === 'live' ? '실시간' : '재생') + '</b>' + (app.paused ? ' (일시정지)' : '') +
      '<br>tick <b>' + w.tick + '</b> (UI ' + document.getElementById('sSpeed').value + ' tick/s — 시간 환산은 근사)' +
      '<br>아군 <b>' + a + '</b>/20 · 적 <b>' + e + '</b>/20 · 사망 ' + kills +
      '<br>기록된 명령 ' + (app.mode === 'live' ? app.log.length + app.pending.length : app.base.commands.length) +
      (app.cmdMode ? '<br>명령 대기: <b>' + app.cmdMode + '</b>' : '') +
      '<br><small>HP ' + R.maxHp + ' · 공격 ' + R.damage + ' · 장갑 ' + R.armor + ' · 공격 주기 ' + R.cooldownTicks + ' tick · 사거리 ' + R.rangePx + 'px · 시야 ' + R.sightPx + 'px</small>';
    var ids = selectedIds();
    var html = '<b>선택 ' + ids.length + '기</b>';
    var list = ids.length ? ids.slice(0, 8) : (app.inspect !== null ? [app.inspect] : []);
    list.forEach(function (id) {
      var u = RTS_get(id); if (!u) return;
      html += '<br>' + id + (u.team === PLAYER ? '' : ' (적)') + ' HP ' + u.hp + '/' + R.maxHp + ' · 쿨다운 ' + u.cooldown + ' · ' + (u.order ? u.order.kind : '대기') + (u.target ? ' → ' + u.target.id : '') + (u.alive ? '' : ' · 사망');
    });
    if (ids.length > 8) html += '<br>…';
    document.getElementById('sel').innerHTML = html;
  }

  var lastT = null;
  function loop(ts) {
    if (lastT === null) lastT = ts;
    var dt = Math.min(250, ts - lastT); lastT = ts;
    if (!app.paused) {
      var tps = +document.getElementById('sSpeed').value;
      app.acc += dt * tps / 1000;
      var n = 0;
      while (app.acc >= 1 && n < 20 && !app.paused) { tickOnce(); app.acc -= 1; n++; }
      if (n >= 20) app.acc = 0;
    }
    draw();
    requestAnimationFrame(loop);
  }
  app.tickOnce = tickOnce;
  restart(); msg('준비: 아군(파랑)을 선택해 명령하세요. 적(빨강)은 tick ' + AI_START + '부터 공격 이동합니다.');
  requestAnimationFrame(loop);
})();
