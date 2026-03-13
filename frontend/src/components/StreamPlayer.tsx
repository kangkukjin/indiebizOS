/**
 * CCTV/웹캠 실시간 스트림 플레이어
 * [STREAM:{url, name, source, lat, lng}] 태그로 렌더링
 *
 * m3u8(HLS) URL → hls.js로 채팅창 안에서 바로 재생
 * 재생 불가 시 → 브라우저 열기 폴백
 */
import { useEffect, useRef, useState } from 'react';
import { Video, ExternalLink, MapPin, Play, Pause, RefreshCw, Maximize2 } from 'lucide-react';
import type { StreamData } from './chat/chatUtils';

interface StreamPlayerProps {
  data: StreamData;
  variant?: 'warm' | 'neutral';
}

/* ── hls.js 동적 로드 (CDN, 한 번만) ─────────────── */
let hlsPromise: Promise<any> | null = null;

function loadHls(): Promise<any> {
  if (hlsPromise) return hlsPromise;
  hlsPromise = new Promise((resolve, reject) => {
    // 이미 로드됐으면 바로 반환
    if ((window as any).Hls) {
      resolve((window as any).Hls);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/hls.js@latest/dist/hls.min.js';
    script.onload = () => resolve((window as any).Hls);
    script.onerror = () => reject(new Error('hls.js 로드 실패'));
    document.head.appendChild(script);
  });
  return hlsPromise;
}

/* ── 컴포넌트 ────────────────────────────────────── */
export function StreamPlayer({ data, variant = 'warm' }: StreamPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<any>(null);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const borderClass = variant === 'warm' ? 'border-[#D5CFC5]' : 'border-gray-200';
  const bgClass = variant === 'warm' ? 'bg-[#F5F0E8]' : 'bg-gray-50';
  const headerBg = variant === 'warm' ? 'bg-[#E5DFD5]' : 'bg-gray-100';
  const textColor = variant === 'warm' ? 'text-[#4A4035]' : 'text-gray-700';
  const subTextColor = variant === 'warm' ? 'text-[#8A8478]' : 'text-gray-500';

  const isHls = data.url?.includes('.m3u8') || data.url?.includes('ktict.co.kr') || data.url?.includes('eseoul.go.kr') || data.url?.includes(':1935/');

  /* 재생 시작 */
  const startPlay = async () => {
    if (!data.url || !videoRef.current) return;
    setLoading(true);
    setError(null);

    const video = videoRef.current;

    try {
      if (isHls) {
        const Hls = await loadHls();
        if (Hls.isSupported()) {
          // 기존 인스턴스 정리
          if (hlsRef.current) {
            hlsRef.current.destroy();
          }
          const hls = new Hls({
            enableWorker: true,
            lowLatencyMode: true,
            maxBufferLength: 10,
            maxMaxBufferLength: 20,
          });
          hlsRef.current = hls;

          hls.on(Hls.Events.ERROR, (_: any, errData: any) => {
            if (errData.fatal) {
              setError('스트림 연결 실패');
              setPlaying(false);
              setLoading(false);
            }
          });

          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            video.play().then(() => {
              setPlaying(true);
              setLoading(false);
            }).catch(() => {
              setLoading(false);
              setError('자동재생 차단됨');
            });
          });

          hls.loadSource(data.url);
          hls.attachMedia(video);
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
          // Safari 네이티브 HLS
          video.src = data.url;
          await video.play();
          setPlaying(true);
          setLoading(false);
        } else {
          setError('HLS 미지원 브라우저');
          setLoading(false);
        }
      } else {
        // 일반 비디오 URL
        video.src = data.url;
        await video.play();
        setPlaying(true);
        setLoading(false);
      }
    } catch (e) {
      setError('재생 실패');
      setLoading(false);
    }
  };

  /* 정지 */
  const stopPlay = () => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.src = '';
    }
    setPlaying(false);
  };

  /* 브라우저에서 열기 */
  const handleOpen = () => {
    if (data.url) {
      window.electron?.openExternal(data.url);
    }
  };

  /* 언마운트 시 정리 */
  useEffect(() => {
    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
      }
    };
  }, []);

  return (
    <div className={`border ${borderClass} rounded-lg overflow-hidden ${bgClass}`}>
      {/* 헤더 */}
      <div className={`flex items-center justify-between px-3 py-2 ${headerBg}`}>
        <div className="flex items-center gap-2">
          <Video size={16} className="text-red-500" />
          <span className={`text-sm font-medium ${textColor}`}>
            {data.name || '실시간 CCTV'}
          </span>
          {playing && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {data.source && (
            <span className={`text-xs ${subTextColor}`}>{data.source}</span>
          )}
        </div>
      </div>

      {/* 비디오 영역 */}
      <div
        className="relative bg-gradient-to-br from-gray-800 to-gray-900 w-full"
        style={{ aspectRatio: '16/9', maxHeight: '240px' }}
      >
        {/* 실제 video 엘리먼트 (항상 DOM에 존재) */}
        <video
          ref={videoRef}
          className={`absolute inset-0 w-full h-full object-contain ${playing ? 'block' : 'hidden'}`}
          muted
          playsInline
          autoPlay
        />

        {/* 미재생 상태: 재생 버튼 */}
        {!playing && !loading && (
          <button
            onClick={startPlay}
            className="absolute inset-0 flex flex-col items-center justify-center cursor-pointer hover:bg-white/5 transition-colors group"
          >
            <div className="flex flex-col items-center gap-3 text-white/70 group-hover:text-white transition-colors">
              <div className="w-14 h-14 rounded-full bg-white/10 group-hover:bg-white/20 flex items-center justify-center transition-colors">
                <Play size={28} className="ml-1" />
              </div>
              <span className="text-sm font-medium">
                {error || '실시간 영상 재생'}
              </span>
            </div>
          </button>
        )}

        {/* 로딩 */}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <RefreshCw size={28} className="text-white/60 animate-spin" />
          </div>
        )}

        {/* 재생 중 컨트롤 오버레이 */}
        {playing && (
          <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/60 to-transparent opacity-0 hover:opacity-100 transition-opacity flex items-center justify-between">
            <button
              onClick={stopPlay}
              className="text-white/80 hover:text-white p-1"
              title="정지"
            >
              <Pause size={18} />
            </button>
            <div className="flex items-center gap-2">
              <button
                onClick={startPlay}
                className="text-white/80 hover:text-white p-1"
                title="새로고침"
              >
                <RefreshCw size={16} />
              </button>
              <button
                onClick={handleOpen}
                className="text-white/80 hover:text-white p-1"
                title="브라우저에서 열기"
              >
                <Maximize2 size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 푸터 */}
      <div className={`flex items-center gap-3 px-3 py-1.5 text-xs ${subTextColor}`}>
        {data.lat && data.lng && (
          <span className="flex items-center gap-1">
            <MapPin size={11} />
            {data.lat.toFixed(4)}, {data.lng.toFixed(4)}
          </span>
        )}
        <button
          onClick={handleOpen}
          className="ml-auto flex items-center gap-1 text-blue-500 hover:text-blue-600"
        >
          <ExternalLink size={11} />
          브라우저에서 열기
        </button>
      </div>
    </div>
  );
}
