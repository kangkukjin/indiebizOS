/** Camera / microphone / speaker enumeration with a remembered choice (localStorage, best-effort). */

export type DeviceKind = 'camera' | 'microphone' | 'speaker';
export interface DeviceChoice { camera?: string; microphone?: string; speaker?: string }
export interface DeviceList { cameras: MediaDeviceInfo[]; microphones: MediaDeviceInfo[]; speakers: MediaDeviceInfo[] }

const STORAGE_KEY = 'indiebiz_media_devices';

export function loadChoice(): DeviceChoice {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as DeviceChoice : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch { return {}; }
}

export function rememberChoice(kind: DeviceKind, deviceId: string | undefined): DeviceChoice {
  const next = { ...loadChoice(), [kind]: deviceId };
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* private mode or blocked storage */ }
  return next;
}

export async function listDevices(): Promise<DeviceList> {
  const empty: DeviceList = { cameras: [], microphones: [], speakers: [] };
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) return empty;
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    return {
      cameras: all.filter(d => d.kind === 'videoinput'),
      microphones: all.filter(d => d.kind === 'audioinput'),
      speakers: all.filter(d => d.kind === 'audiooutput'),
    };
  } catch { return empty; }
}

/** Keep a remembered id only while that device is still plugged in. */
export function resolveChoice(list: DeviceList, choice: DeviceChoice): DeviceChoice {
  const keep = (devices: MediaDeviceInfo[], id?: string) => (id && devices.some(d => d.deviceId === id) ? id : undefined);
  return { camera: keep(list.cameras, choice.camera), microphone: keep(list.microphones, choice.microphone), speaker: keep(list.speakers, choice.speaker) };
}

export function supportsSinkId(): boolean {
  return typeof HTMLMediaElement !== 'undefined' && 'setSinkId' in HTMLMediaElement.prototype;
}

/** Route an element's audio to a speaker when the platform allows it; silently keeps the default otherwise. */
export async function applySink(element: HTMLMediaElement | null, deviceId: string | undefined): Promise<boolean> {
  if (!element || !deviceId || !supportsSinkId()) return false;
  try {
    await (element as HTMLMediaElement & { setSinkId(id: string): Promise<void> }).setSinkId(deviceId);
    return true;
  } catch { return false; }
}

/** The "other" camera for a switch button (front/back on laptops is just next-in-list). */
export function nextCamera(list: DeviceList, current?: string): string | undefined {
  if (list.cameras.length < 2) return undefined;
  const index = list.cameras.findIndex(d => d.deviceId === current);
  return list.cameras[(index + 1) % list.cameras.length]?.deviceId;
}
