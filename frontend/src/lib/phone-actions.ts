import { androidCommandCode, androidState, executeAndroid } from './android-control';

export type HardwareOp = 'status' | 'brightness' | 'brightness_auto' | 'rotation' | 'timeout' |
  'sensor' | 'torch' | 'screen_on' | 'screen_off' | 'settings_permission';
export interface HardwareState {
  observation_scope?: 'settings';
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

export function phoneActionCode(target: string, op: HardwareOp, args: RecordValue = {}): string {
  return androidCommandCode(target, { ...args, action: op });
}
export function phoneActionState(value: unknown): HardwareState {
  const state = androidState(value);
  return state as unknown as HardwareState;
}
export async function runPhoneAction(target: string, op: HardwareOp, args: RecordValue = {}): Promise<HardwareState> {
  return phoneActionState(await executeAndroid(target, phoneActionCode(target, op, args)));
}

// Partial setting observations update only their fields; full reads replace old state.
export function mergeHardwareState(previous: HardwareState | null, next: HardwareState): HardwareState {
  if (next.observation_scope !== 'settings') return next;
  return { ...previous, ...next, capabilities: { ...previous?.capabilities, ...next.capabilities } };
}
