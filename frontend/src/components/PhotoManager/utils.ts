/**
 * PhotoManager 유틸리티 함수
 */

import L from 'leaflet';
import type { MediaItem } from './types';

// 백엔드 기본 주소 — 풍부창은 Electron 로컬 창이라 포트가 고정(런타임 조회는 getApiUrl).
const API = 'http://127.0.0.1:8765';

// USB 로 붙은 폰의 파일은 로컬 디스크에 없다 → 전용 엔드포인트(요청 시 adb 로 당겨 온다).
// 썸네일·원본 URL 이 갈리는 유일한 지점 — 뷰들이 각자 문자열을 짜지 않게 여기로 모은다.
export const thumbUrl = (item: MediaItem, size: number): string => {
  const p = encodeURIComponent(item.path);
  if (item.source === 'usb') return `${API}/photo/usb-thumbnail?path=${p}&size=${size}`;
  const ep = item.media_type === 'video' ? 'video-thumbnail' : 'thumbnail';
  return `${API}/photo/${ep}?path=${p}&size=${size}`;
};

/** 썸네일을 창 밖(바탕화면·파인더)으로 끌어 저장 — dragstart 에서 부른다.
    HTML5 드래그는 창 밖으로 파일을 못 내보내므로 preventDefault 로 접고, 메인 프로세스가
    네이티브 OS 드래그로 전환한다. 내 사진은 원본 경로를 그대로 집고(복사 0),
    폰 사진은 여기 없으니 URL 로 받아서 집는다. 비 Electron(웹)에선 아무것도 안 한다. */
export const dragOutMedia = (e: { preventDefault: () => void }, item: MediaItem): void => {
  const el = (window as any).electron;
  if (!el?.dragOutFile) return;
  e.preventDefault();
  el.dragOutFile(
    item.source === 'usb'
      ? { url: originUrl(item), name: item.filename, mtime: item.mtime || '' }
      : { path: item.path, name: item.filename }
  );
  window.addEventListener('mouseup', () => el.dragOutCancel?.(), { once: true });
};

export const originUrl = (item: MediaItem): string => {
  const p = encodeURIComponent(item.path);
  if (item.media_type === 'video') {
    return `${API}/photo/${item.source === 'usb' ? 'usb-video' : 'video'}?path=${p}`;
  }
  return `${API}/photo/${item.source === 'usb' ? 'usb-image' : 'image'}?path=${p}`;
};

// Leaflet 기본 마커 아이콘 설정
export const initLeafletIcons = () => {
  delete (L.Icon.Default.prototype as any)._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  });
};

// 클러스터 아이콘 생성 함수
export const createClusterCustomIcon = (cluster: any) => {
  const count = cluster.getChildCount();
  let size = 'small';
  let dimension = 30;

  if (count >= 100) {
    size = 'large';
    dimension = 50;
  } else if (count >= 10) {
    size = 'medium';
    dimension = 40;
  }

  return L.divIcon({
    html: `<div style="
      background-color: #8B7355;
      color: white;
      border-radius: 50%;
      width: ${dimension}px;
      height: ${dimension}px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: ${size === 'large' ? '14px' : size === 'medium' ? '12px' : '10px'};
      border: 3px solid white;
      box-shadow: 0 2px 5px rgba(0,0,0,0.3);
    ">${count}</div>`,
    className: 'custom-cluster-icon',
    iconSize: L.point(dimension, dimension),
  });
};

// API URL 가져오기
export const getApiUrl = async (): Promise<string> => {
  try {
    if (window.electron) {
      const port = await window.electron.getApiPort();
      return `http://127.0.0.1:${port}`;
    }
    return 'http://127.0.0.1:8765';
  } catch {
    return 'http://127.0.0.1:8765';
  }
};
