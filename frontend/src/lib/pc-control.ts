import { iblExecuteApp } from './instrument';

export type PCPlatform = 'darwin' | 'windows';
export type PCAction = 'status' | 'volume' | 'mute' | 'open_url' | 'lock' | 'youtube_status' | 'youtube_replace' | 'youtube_stop';
export interface PCVideo { url: string; title: string; duration_seconds: number }
export interface PCPlayback { title?: string; url?: string; state?: string; position?: number; duration?: number; ad?: boolean }
export interface PCTarget { id: string; name: string; connected: boolean; ready: boolean; local: boolean }
export interface PCOutput {
  id: string; name: string; volume: number | null; muted: boolean | null;
  default?: boolean; is_default?: boolean; can_set_volume: boolean; can_mute: boolean;
}
export interface PCState {
  success: boolean; platform: PCPlatform; action: PCAction; hostname: string; os_version: string;
  observed_at: string; verified: boolean; message: string; devices?: PCOutput[];
  device?: PCOutput; audio_error?: string; can_lock?: boolean; source_sha256?: string;
  tabs?: PCPlayback[]; playback?: PCPlayback;
}
type RecordValue = Record<string, unknown>;
const record = (v: unknown): RecordValue => v && typeof v === 'object' && !Array.isArray(v) ? v as RecordValue : {};
export const LOCAL_PC = '__local__';
export const pcBootstrap = '$s = [self:read]{path:"~workspace/data/instruments/pc_control.py"}\n' +
  '$f = [self:write]{path:"~turn/pc_control.py",content:$s.text}\n';

export function pcPlatform(value: unknown): PCPlatform | null {
  const os = String(value || '').toLowerCase();
  return ['darwin', 'macos', 'mac', 'osx'].includes(os) ? 'darwin' : ['windows', 'win32', 'win'].includes(os) ? 'windows' : null;
}

export function pcTargets(value: unknown, platform: PCPlatform): PCTarget[] {
  const root = record(value), host = record(root.host);
  if (host.success !== true || !Array.isArray(root.limbs)) throw new Error('PC 목록을 확인하지 못했습니다.');
  const rows: PCTarget[] = pcPlatform(host.host_platform) === platform
    ? [{ id: LOCAL_PC, name: '이 본체 PC', connected: true, ready: true, local: true }] : [];
  for (const raw of root.limbs) {
    const row = record(raw), reg = record(row.registration), caps = record(reg.capabilities), env = record(row.env);
    if (row.revoked || row.expired || row.invitation || reg.state !== 'active' ||
        pcPlatform(caps.os ?? env.os) !== platform || typeof row.device_id !== 'string') continue;
    rows.push({ id: row.device_id, name: String(row.alias || row.device_id), local: false,
      connected: row.connected === true, ready: caps.shell === true && reg.paused !== true });
  }
  return rows;
}

export async function listControlPCs(platform: PCPlatform): Promise<PCTarget[]> {
  const code = '#!ibl edition=2\n' + pcBootstrap +
    '$host = [self:script]{path:$f.path,args:{op:"contract"}}\n' +
    '$list = [self:limb]{op:"list"}\nreturn {host:$host,limbs:$list.limbs}';
  return pcTargets(await iblExecuteApp(code), platform);
}

/** Only wiring here. Native source and shared validators are read from the hub at execution time. */
export function pcCommandCode(target: string, platform: PCPlatform, action: PCAction, args: RecordValue = {}): string {
  if (!target.trim()) throw new Error('제어할 PC를 선택해 주세요.');
  const youtube = action.startsWith('youtube_');
  const file = youtube ? 'pc_youtube_windows.ps1' : platform === 'darwin' ? 'pc_control_mac.py' : 'pc_control_windows.ps1';
  const request = JSON.stringify({ ...args, action });
  let code = '#!ibl edition=2\n' + pcBootstrap +
    `$native = [self:read]{path:"~workspace/data/instruments/${file}"}\n`;
  if (target === LOCAL_PC) {
    return code + `return [self:script]{path:$f.path,args:{op:"local",platform:${JSON.stringify(platform)},source:$native.text,request:${request}},timeout:${youtube ? 120 : 35}}`;
  }
  code += `$p = [self:script]{path:$f.path,args:{op:"prepare",platform:${JSON.stringify(platform)},source:$native.text,request:${request}}}\n`;
  code += 'assert $p.success == true, "PC 제어 인수를 확인하세요.", {result:$p}\n';
  code += `$job = [limbs:guestpc]{limb:${JSON.stringify(target)},op:"shell",cmd:$p.command,stdin:$p.stdin,request_id:$p.request.request_id,timeout:${youtube ? 120 : 30},background:true,mode:"interactive"}\n`;
  code += 'assert $job.success == true, "PC 작업 접수 실패", {result:$job}\n';
  code += `$r = [self:task]{op:"wait",ref:$job.task_ref,timeout:${youtube ? 150 : 60}}\n`;
  code += 'assert get($r,"terminal",false) == true && $r.state == "succeeded", "PC 작업이 완료되지 않았습니다. task_ref로 기다리고 변경을 재전송하지 마세요.", {result:$r,task_ref:$job.task_ref}\n';
  code += 'assert $r.result != null && $r.result.exit == 0, "PC 실행 실패. 상태를 다시 조회하세요.", {result:$r}\n';
  return code + 'return [self:script]{path:$f.path,args:{op:"decode",plan:$p,output:$r.result.output}}';
}

export async function searchPCVideos(query: string): Promise<PCVideo[]> {
  const result = record(await iblExecuteApp('#!ibl edition=2\nreturn [sense:search_youtube]' + JSON.stringify({ query, limit: 6 })));
  if (result.success !== true || !Array.isArray(result.items)) throw new Error(String(result.error || '영상을 검색하지 못했습니다.'));
  return result.items.flatMap(raw => {
    const row = record(raw), parts = String(row.duration || '').split(':');
    if (parts.length < 2 || parts.length > 3 || parts.some(p => !/^\d+$/.test(p))) return [];
    const duration = parts.reduce((seconds, part) => seconds * 60 + Number(part), 0);
    if (duration < 1 || duration > 86400 || typeof row.url !== 'string' || typeof row.title !== 'string') return [];
    return [{url: row.url, title: row.title, duration_seconds: duration}];
  });
}

export function pcState(value: unknown, platform: PCPlatform, action: PCAction): PCState {
  const state = record(value);
  if (state.success !== true || state.error) throw new Error(String(state.error || 'PC 제어 결과가 불완전합니다.'));
  if (state.protocol !== 'pc-control/1' || state.platform !== platform || state.action !== action) throw new Error('요청과 다른 PC 응답입니다.');
  if (action === 'status' && !Array.isArray(state.devices)) throw new Error('출력 장치 목록을 확인하지 못했습니다.');
  return state as unknown as PCState;
}

export async function controlPC(target: string, platform: PCPlatform, action: PCAction, args: RecordValue = {}): Promise<PCState> {
  return pcState(await iblExecuteApp(pcCommandCode(target, platform, action, args)), platform, action);
}

export async function capturePC(target: string): Promise<string> {
  if (!target || target === LOCAL_PC) throw new Error('원격 PC를 선택하세요.');
  const result = record(await iblExecuteApp('#!ibl edition=2\n$s = [limbs:guestpc]' +
    JSON.stringify({ limb: target, op: 'screen', mode: 'interactive', max_width: 1280 }) +
    '\nreturn {success:$s.success,b64:$s.image_data.b64,media_type:$s.image_data.media_type}'));
  if (result.success !== true || typeof result.b64 !== 'string' || !result.b64 ||
      !['image/png', 'image/jpeg'].includes(String(result.media_type))) throw new Error('화면을 받지 못했습니다. 대상 PC의 화면 권한을 확인하세요.');
  return `data:${result.media_type};base64,${result.b64}`;
}
