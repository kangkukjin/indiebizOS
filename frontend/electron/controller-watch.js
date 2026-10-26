/**
 * controller-watch.js — 재기동 제어자 부재 판정 (electron 비의존 순수 함수, node --test 로 검사)
 *
 * 2026-10-26: 제어자(pid 39960)가 소리 없이 죽고 워커만 남아, 11:38 편집이 재기동으로 안 올라오고
 * `restart --wait` 요청이 접수함에 5시간 머물렀다. 런처는 제어자를 띄우기만 하고 다시 보지 않았다.
 * 제어자는 "자기 죽음 이후 단계"를 자기 계획에 넣을 수 없으므로, 죽음을 넘어 살아 있는 런처가
 * 같은 `api.py start` 로 되살린다(start 는 owner.lock 보유자가 있으면 0 으로 양보 — 멱등).
 *
 * 판정 입력은 state.json(제어자가 쓰는 정본) + pid 생존 + 의도적 종료 표식뿐이다. 포트 소탕·손 표식 없음.
 */

export const STALE_ACTIVE_S = 180;   // ACTIVE 는 매 tick(0.5s) 관측을 저장한다 — 3분 침묵 = pid 재사용 의심
export const REVIVE_BACKOFF_MS = 60000;

/**
 * @param {object|null} state  data/restart_control/state.json
 * @param {(pid:number)=>boolean} pidAlive
 * @param {{nowS?:number, intentional?:boolean}} opts  intentional = data/.intentional_shutdown 존재
 * @returns {{revive:boolean, reason:string, pid?:number}}
 */
export function controllerVerdict(state, pidAlive, opts = {}) {
  const nowS = opts.nowS ?? Date.now() / 1000;
  if (opts.intentional) return { revive: false, reason: 'intentional_shutdown' };
  if (!state || !state.phase) return { revive: false, reason: 'no_state' };
  if (state.phase === 'STOPPED') return { revive: false, reason: 'stopped' };
  const ctl = state.controller;
  if (!ctl || !Number.isInteger(ctl.pid)) return { revive: true, reason: 'no_controller_recorded' };
  if (!pidAlive(ctl.pid)) return { revive: true, reason: 'controller_pid_gone', pid: ctl.pid };
  const age = nowS - Number(state.updated_at || 0);
  if (state.phase === 'ACTIVE' && age > STALE_ACTIVE_S) {
    // pid 는 살아 있다고 나오지만(재사용 가능) ACTIVE 가 3분째 한 번도 저장하지 않았다.
    // start 는 잠금 보유자가 있으면 양보하므로 오탐의 비용은 파이썬 한 번 뜨는 것이다.
    return { revive: true, reason: 'state_stale', pid: ctl.pid, ageS: Math.round(age) };
  }
  return { revive: false, reason: 'alive', pid: ctl.pid };
}

/** 되살리기 사이 최소 간격 — 느린 워커(관측 unknown)로 ACTIVE 저장이 멎은 동안 매 tick 파이썬을 띄우지 않는다. */
export function shouldAttemptRevive(verdict, lastAttemptMs, nowMs = Date.now()) {
  if (!verdict.revive) return false;
  if (!lastAttemptMs) return true;   // 첫 시도는 즉시
  return nowMs - lastAttemptMs >= REVIVE_BACKOFF_MS;
}

export function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return e && e.code === 'EPERM';  // 남의 프로세스 — 살아는 있다
  }
}
