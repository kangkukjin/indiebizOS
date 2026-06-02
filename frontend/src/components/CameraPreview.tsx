/**
 * 카메라 미리보기 컴포넌트
 * Electron 앱 내에서 웹캠 미리보기 및 캡처
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Camera, X } from 'lucide-react';

interface CameraPreviewProps {
  isOpen: boolean;
  onClose: () => void;
  onCapture: (imageData: { base64: string; blob: Blob }) => void;
}

export function CameraPreview({ isOpen, onClose, onCapture }: CameraPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const [lastCapture, setLastCapture] = useState<string | null>(null);

  // 카메라 시작
  const startCamera = useCallback(async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user'
        },
        audio: false
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        setIsStreaming(true);
      }
    } catch (err: any) {
      console.error('Camera error:', err);
      if (err.name === 'NotAllowedError') {
        setError('카메라 권한이 거부되었습니다. 시스템 설정에서 권한을 허용해주세요.');
      } else if (err.name === 'NotFoundError') {
        setError('카메라를 찾을 수 없습니다.');
      } else {
        setError(`카메라 오류: ${err.message}`);
      }
    }
  }, []);

  // 카메라 중지
  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsStreaming(false);
  }, []);

  // 캡처
  const capture = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;

    // 비디오 크기에 맞춰 캔버스 설정
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // 비디오 프레임을 캔버스에 그리기
    ctx.drawImage(video, 0, 0);

    // 플래시 효과
    setFlash(true);
    setTimeout(() => setFlash(false), 150);

    // base64로 변환
    const base64 = canvas.toDataURL('image/jpeg', 0.9);
    setLastCapture(base64);

    // Blob으로도 변환
    canvas.toBlob((blob) => {
      if (blob) {
        onCapture({
          base64: base64.split(',')[1], // data:image/jpeg;base64, 제거
          blob
        });
      }
    }, 'image/jpeg', 0.9);
  }, [onCapture]);

  // 모달 열릴 때 카메라 시작
  useEffect(() => {
    if (isOpen) {
      startCamera();
    } else {
      stopCamera();
      setLastCapture(null);
    }

    return () => {
      stopCamera();
    };
  }, [isOpen, startCamera, stopCamera]);

  // 키보드 단축키
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.code === 'Space' && isStreaming) {
        e.preventDefault();
        capture();
      } else if (e.code === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isStreaming, capture, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-[#2d2d2d] rounded-xl overflow-hidden shadow-2xl max-w-3xl w-full mx-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-4 py-3 bg-[#1a1a1a]">
          <div className="flex items-center gap-2 text-white">
            <Camera size={20} />
            <span className="font-medium">카메라</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* 비디오 영역 */}
        <div className="relative bg-black aspect-video">
          {error ? (
            <div className="absolute inset-0 flex items-center justify-center text-red-400 p-4 text-center">
              {error}
            </div>
          ) : (
            <>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
              />

              {/* 플래시 효과 */}
              {flash && (
                <div className="absolute inset-0 bg-white animate-pulse" />
              )}

              {/* 마지막 캡처 미리보기 */}
              {lastCapture && (
                <div className="absolute bottom-4 right-4 w-24 h-24 rounded-lg overflow-hidden border-2 border-white shadow-lg">
                  <img src={lastCapture} alt="Last capture" className="w-full h-full object-cover" />
                </div>
              )}
            </>
          )}

          {/* 숨겨진 캔버스 (캡처용) */}
          <canvas ref={canvasRef} className="hidden" />
        </div>

        {/* 컨트롤 */}
        <div className="flex items-center justify-center gap-4 p-4 bg-[#1a1a1a]">
          <button
            onClick={capture}
            disabled={!isStreaming}
            className="flex items-center gap-2 px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
          >
            <Camera size={20} />
            캡처 (Space)
          </button>

          <button
            onClick={onClose}
            className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
          >
            <X size={20} />
            닫기 (Esc)
          </button>
        </div>

        {/* 안내 */}
        <div className="px-4 py-2 bg-[#252525] text-gray-400 text-sm text-center">
          Space 키로 캡처, Esc 키로 닫기
        </div>
      </div>
    </div>
  );
}
