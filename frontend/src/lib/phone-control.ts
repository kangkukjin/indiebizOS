import { iblExecuteApp } from './instrument';
import { androidCommandCode, androidState, executeAndroid } from './android-control';

export interface PhoneTarget {
  id: string;
  name: string;
  connected: boolean;
  ready: boolean;
  paused: boolean;
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
    if (phone.revoked || phone.expired || phone.invitation || typeof phone.device_id !== 'string' || registration.state !== 'active' || (caps.os ?? env.os) !== 'android') return [];
    return [{ id: String(phone.device_id), name: String(phone.alias || phone.device_id),
      connected: phone.connected === true,
      paused: registration.paused === true,
      ready: registration.paused !== true && caps.execution_contract === 1 && record(record(caps.runtimes).python).ready === true }];
  }).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}

export async function listControlPhones(): Promise<PhoneTarget[]> {
  return phoneTargets(await iblExecuteApp('#!ibl edition=2\nreturn [self:limb]{op:"list"}'));
}

export function phoneCommandCode(target: string, op: PhoneCommand, value?: number, stream: PhoneStream = 'music'): string {
  const actions = { status: 'volume_status', set: 'volume', step: 'volume_step', half: 'volume_half',
    mute: 'volume_mute', restore: 'volume_restore', vibrate: 'vibrate' };
  return androidCommandCode(target, { action: actions[op], stream, ...(value === undefined ? {} : { value }) });
}

export function controlState(value: unknown): PhoneState {
  const state = androidState(value);
  if (typeof state.actual !== 'number' || typeof state.max !== 'number' || state.actual < 0 || state.actual > state.max) {
    throw new Error('실제 음량 응답을 확인할 수 없습니다.');
  }
  return state as unknown as PhoneState;
}

export async function controlPhone(target: string, op: PhoneCommand, value?: number, stream: PhoneStream = 'music'): Promise<PhoneState> {
  return controlState(await executeAndroid(target, phoneCommandCode(target, op, value, stream)));
}
