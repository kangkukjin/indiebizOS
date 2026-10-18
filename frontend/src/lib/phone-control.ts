import controlSource from '../../../data/instruments/phone_control.py?raw';
import { iblExecuteApp } from './instrument';

export interface PhoneTarget {
  id: string;
  name: string;
  connected: boolean;
  ready: boolean;
}
export interface PhoneState {
  success: boolean;
  stream: PhoneStream;
  actual: number;
  max: number;
  percent: number;
  fixed: boolean;
  can_restore: boolean;
  previous: number | null;
  model: string;
  android: string;
  battery: number;
  has_vibrator: boolean;
  message: string;
}
export type PhoneStream = 'music' | 'alarm' | 'ring' | 'notification';
export type PhoneCommand = 'status' | 'set' | 'step' | 'half' | 'mute' | 'restore' | 'vibrate';
type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};

export function phoneTargets(value: unknown): PhoneTarget[] {
  const root = record(value);
  if (root.success === false) throw new Error(String(root.error || '폰 목록을 가져오지 못했습니다.'));
  if (!Array.isArray(root.limbs)) throw new Error('폰 목록 응답을 확인할 수 없습니다.');
  return root.limbs.flatMap((raw) => {
    const phone = record(raw), registration = record(phone.registration);
    const caps = record(registration.capabilities), env = record(phone.env);
    if (phone.revoked || phone.expired || registration.state !== 'active' || (caps.os ?? env.os) !== 'android') return [];
    return [{ id: String(phone.device_id), name: String(phone.alias || phone.device_id),
      connected: phone.connected === true,
      ready: caps.execution_contract === 1 && record(record(caps.runtimes).python).ready === true }];
  }).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}

export async function listControlPhones(): Promise<PhoneTarget[]> {
  return phoneTargets(await iblExecuteApp('#!ibl edition=2\nreturn [self:limb]{op:"list"}'));
}

export function phoneCommandCode(target: string, op: PhoneCommand, value?: number, stream: PhoneStream = 'music'): string {
  if (!target.trim()) throw new Error('제어할 폰을 선택해 주세요.');
  const args = { op, stream, ...(value === undefined ? {} : { value }) };
  return '#!ibl edition=2\nreturn [limbs:guestpc]' + JSON.stringify({
    limb: target, op: 'python', code: controlSource, inputs: args, timeout: 20,
  });
}

export function controlState(value: unknown): PhoneState {
  const outer = record(value), remote = record(outer.result), state = record(remote.value);
  for (const layer of [outer, remote, state]) {
    if (layer.success !== true || layer.error) throw new Error(String(layer.error || '실행 결과를 확인하지 못했습니다. 상태를 새로 확인해 주세요.'));
  }
  if (typeof state.actual !== 'number' || typeof state.max !== 'number' || state.actual < 0 || state.actual > state.max) {
    throw new Error('실제 음량 응답을 확인할 수 없습니다.');
  }
  return state as unknown as PhoneState;
}

export async function controlPhone(target: string, op: PhoneCommand, value?: number, stream: PhoneStream = 'music'): Promise<PhoneState> {
  return controlState(await iblExecuteApp(phoneCommandCode(target, op, value, stream)));
}
