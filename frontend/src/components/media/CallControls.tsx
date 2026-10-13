/** In-call controls: mic, camera, switch camera, output device, hang up. Local choices always win. */
import { Mic, MicOff, Video, VideoOff, SwitchCamera, PhoneOff, Volume2 } from 'lucide-react';
import type { DeviceChoice, DeviceList } from '../../lib/media/devices';
import { supportsSinkId } from '../../lib/media/devices';
import type { TrackPlan } from '../../lib/media/tracks';

export function CallControls({ plan, micMuted, cameraOff, devices, choice, disabled, onMic, onCamera, onSwitchCamera, onDevice, onHangUp }: {
  plan: TrackPlan | null; micMuted: boolean; cameraOff: boolean; devices: DeviceList; choice: DeviceChoice; disabled: boolean;
  onMic: () => void; onCamera: () => void; onSwitchCamera: () => void;
  onDevice: (kind: 'camera' | 'microphone' | 'speaker', id: string) => void; onHangUp: () => void;
}) {
  const button = 'flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white hover:bg-white/20 disabled:opacity-40';
  const select = 'max-w-[11rem] rounded border border-white/20 bg-stone-900 px-2 py-1 text-xs text-white';
  return (
    <footer className="flex shrink-0 flex-wrap items-center justify-center gap-3 border-t border-white/10 bg-stone-950 px-4 py-3">
      {plan?.sendMic && (
        <button className={`${button} ${micMuted ? 'bg-red-600/80' : ''}`} disabled={disabled} onClick={onMic}
          aria-pressed={micMuted} title={micMuted ? '마이크 켜기' : '마이크 끄기'} aria-label={micMuted ? '마이크 켜기' : '마이크 끄기'}>
          {micMuted ? <MicOff size={18} /> : <Mic size={18} />}
        </button>
      )}
      {plan?.sendCamera && (
        <button className={`${button} ${cameraOff ? 'bg-red-600/80' : ''}`} disabled={disabled} onClick={onCamera}
          aria-pressed={cameraOff} title={cameraOff ? '카메라 켜기' : '카메라 끄기'} aria-label={cameraOff ? '카메라 켜기' : '카메라 끄기'}>
          {cameraOff ? <VideoOff size={18} /> : <Video size={18} />}
        </button>
      )}
      {plan?.sendCamera && devices.cameras.length > 1 && (
        <button className={button} disabled={disabled || cameraOff} onClick={onSwitchCamera} title="카메라 전환" aria-label="카메라 전환">
          <SwitchCamera size={18} />
        </button>
      )}
      {plan?.sendMic && devices.microphones.length > 1 && (
        <select className={select} aria-label="마이크 선택" value={choice.microphone ?? ''} onChange={e => onDevice('microphone', e.target.value)}>
          <option value="">기본 마이크</option>
          {devices.microphones.map(d => <option key={d.deviceId} value={d.deviceId}>{d.label || '마이크'}</option>)}
        </select>
      )}
      {plan?.recvAudio && supportsSinkId() && devices.speakers.length > 0 && (
        <label className="flex items-center gap-1 text-xs text-stone-300" title="출력 장치">
          <Volume2 size={14} />
          <select className={select} aria-label="출력 장치 선택" value={choice.speaker ?? ''} onChange={e => onDevice('speaker', e.target.value)}>
            <option value="">기본 스피커</option>
            {devices.speakers.map(d => <option key={d.deviceId} value={d.deviceId}>{d.label || '스피커'}</option>)}
          </select>
        </label>
      )}
      <button className={`${button} bg-red-600 hover:bg-red-500`} onClick={onHangUp} title="종료" aria-label="종료">
        <PhoneOff size={18} />
      </button>
    </footer>
  );
}
