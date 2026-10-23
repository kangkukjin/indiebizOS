/* 기본 전장: 평지 + 좁은 입구가 있는 세로 벽, 양측 마린 20기 (배치는 근사 선택) */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.RTS_SCENARIO = api;
})(this, function () {
  'use strict';
  var GAP_TOP = 250, GAP_BOTTOM = 310; // 입구 폭 60px (마린 지름 16px 근사의 3.75배)
  function defaultScenario(opts) {
    opts = opts || {};
    var units = [];
    for (var i = 0; i < 20; i++) {
      var col = i % 4, row = Math.floor(i / 4);
      units.push({ id: 'A' + (i + 1), team: 1, x: 100 + col * 26, y: 220 + row * 26 });
      units.push({ id: 'B' + (i + 1), team: 2, x: 780 + col * 26, y: 220 + row * 26 });
    }
    return {
      width: 960, height: 560,
      walls: [
        { x: 460, y: 0, w: 40, h: GAP_TOP },
        { x: 460, y: GAP_BOTTOM, w: 40, h: 560 - GAP_BOTTOM }
      ],
      units: units,
      commands: (opts.commands || []).slice(),
      ticks: opts.ticks === undefined ? 0 : opts.ticks,
      seed: opts.seed === undefined ? 12345 : opts.seed
    };
  }
  // 적(팀 2) 자동 지휘: 대기 중인 적에게 가장 가까운 상대 위치로 공격 이동 명령을 낸다.
  // 명령은 기록에 남으므로 재생 시 같은 결과가 된다.
  function enemyAiCommands(world, team, period, startTick) {
    var t = world.tick;
    if (t < startTick || (t - startTick) % period !== 0) return [];
    var ids = [], tx = 0, ty = 0, n = 0;
    world.order.forEach(function (u) {
      if (u.alive && u.team !== team) { tx += u.x; ty += u.y; n++; }
    });
    if (!n) return [];
    world.order.forEach(function (u) {
      if (u.alive && u.team === team && !u.order && !u.target) ids.push(u.id);
    });
    if (!ids.length) return [];
    return [{ tick: t, ids: ids, kind: 'attackMove', x: Math.round(tx / n), y: Math.round(ty / n), source: 'ai' }];
  }
  return { defaultScenario: defaultScenario, enemyAiCommands: enemyAiCommands, GAP_TOP: GAP_TOP, GAP_BOTTOM: GAP_BOTTOM };
});
