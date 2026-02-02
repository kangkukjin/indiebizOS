/**
 * PhotoManager 유틸리티 함수
 */

import L from 'leaflet';

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
