import test from 'node:test';
import assert from 'node:assert/strict';
import { controllerVerdict, shouldAttemptRevive, pidAlive, REVIVE_BACKOFF_MS } from './controller-watch.js';

const now = 1_000_000;
const live = (state) => controllerVerdict(state, () => true, { nowS: now });
const dead = (state) => controllerVerdict(state, () => false, { nowS: now });

test('dead controller pid with a live worker is revived; STOPPED and intentional shutdown are not', () => {
  const active = { phase: 'ACTIVE', controller: { pid: 39960, born: 1 }, updated_at: now - 1 };
  assert.deepEqual(dead(active), { revive: true, reason: 'controller_pid_gone', pid: 39960 });
  assert.equal(dead({ ...active, phase: 'STOPPED' }).revive, false);
  assert.equal(controllerVerdict(active, () => false, { nowS: now, intentional: true }).reason, 'intentional_shutdown');
  assert.equal(dead({ ...active, phase: 'FAILED' }).revive, true);   // FAILED 도 명시 재시도 요청을 받으려면 제어자가 있어야 한다
});

test('live controller is left alone unless ACTIVE has stopped saving for minutes (pid reuse)', () => {
  const fresh = { phase: 'ACTIVE', controller: { pid: 7, born: 1 }, updated_at: now - 2 };
  assert.equal(live(fresh).reason, 'alive');
  assert.equal(live({ ...fresh, updated_at: now - 400 }).reason, 'state_stale');
  // DRAINING/STARTING 은 전이 때만 저장하므로 침묵이 죽음이 아니다
  assert.equal(live({ ...fresh, phase: 'DRAINING', updated_at: now - 400 }).reason, 'alive');
  assert.equal(live({ phase: 'ACTIVE', updated_at: now }).reason, 'no_controller_recorded');
  assert.equal(live(null).reason, 'no_state');
});

test('revive attempts are rate limited and never fire for a non-revive verdict', () => {
  const v = { revive: true, reason: 'controller_pid_gone' };
  assert.equal(shouldAttemptRevive(v, 0, 10), true);
  assert.equal(shouldAttemptRevive(v, 10, 10 + REVIVE_BACKOFF_MS - 1), false);
  assert.equal(shouldAttemptRevive(v, 10, 10 + REVIVE_BACKOFF_MS), true);
  assert.equal(shouldAttemptRevive({ revive: false, reason: 'alive' }, 0, 10), false);
});

test('pidAlive answers for this process and for a pid that cannot exist', () => {
  assert.equal(pidAlive(process.pid), true);
  assert.equal(pidAlive(2 ** 22 - 1), false);
});
