import deviceSource from '../../../data/instruments/phone_device.py?raw';
import { iblExecuteApp } from './instrument';

export type HardwareOp = 'status' | 'brightness' | 'brightness_auto' | 'rotation' | 'timeout' |
  'sensor' | 'torch' | 'screen_on' | 'screen_off' | 'settings_permission';
export interface HardwareState {
  success: boolean; hardware_control?: number; op?: HardwareOp; message?: string; verified?: boolean;
  screen_on?: boolean; locked?: boolean; brightness?: number; brightness_auto?: boolean;
  auto_rotate?: boolean; screen_timeout_ms?: number; battery?: number; charging?: boolean;
  power_save?: boolean; wifi_enabled?: boolean | null; network_transports?: string[];
  capabilities?: Record<string, boolean>;
  sensors?: { id: string; name: string }[];
  torches?: { id: string; enabled: boolean | null; available: boolean }[];
  sensor?: string; reading?: { values: number[]; accuracy: number; timestamp_ns: number };
}
type RecordValue = Record<string, unknown>;
const object = (v: unknown): RecordValue => v && typeof v === 'object' && !Array.isArray(v) ? v as RecordValue : {};

export function phoneActionCode(target: string, op: HardwareOp, args: RecordValue = {}): string {
  if (!target.trim()) throw new Error('제어할 폰을 선택해 주세요.');
  return '#!ibl edition=2\nreturn [limbs:guestpc]' + JSON.stringify({
    limb: target, op: 'python', code: deviceSource, inputs: { ...args, op }, timeout: 20,
  });
}
export function phoneActionState(value: unknown): HardwareState {
  const outer = object(value), remote = object(outer.result), state = object(remote.value);
  for (const layer of [outer, remote, state]) {
    if (layer.success !== true || layer.error) {
      throw new Error(String(layer.error || layer.message || '실행 결과가 불완전합니다. 상태를 다시 조회하세요.'));
    }
  }
  return state as unknown as HardwareState;
}
export async function runPhoneAction(target: string, op: HardwareOp, args: RecordValue = {}): Promise<HardwareState> {
  return phoneActionState(await iblExecuteApp(phoneActionCode(target, op, args)));
}
