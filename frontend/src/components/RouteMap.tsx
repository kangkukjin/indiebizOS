/**
 * 경로 지도 컴포넌트 (Leaflet 기반)
 */

import { useEffect, useRef, memo } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Leaflet 기본 마커 아이콘 문제 해결
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = DefaultIcon;

export interface RouteMapData {
  type: 'route_map';
  origin: {
    lat: number;
    lng: number;
    name: string;
  };
  destination: {
    lat: number;
    lng: number;
    name: string;
  };
  path: [number, number][];  // [lat, lng][]
  summary: {
    distance_km: number;
    duration_min: number;
    toll: number;
  };
}

interface RouteMapProps {
  data: RouteMapData;
}

export const RouteMap = memo(function RouteMap({ data }: RouteMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // 지도 생성
    const map = L.map(mapRef.current, {
      scrollWheelZoom: false,  // 스크롤 줌 비활성화 (채팅 스크롤과 충돌 방지)
    });
    mapInstanceRef.current = map;

    // OpenStreetMap 타일 레이어
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    // 경로 그리기
    if (data.path && data.path.length > 0) {
      const polyline = L.polyline(data.path as L.LatLngExpression[], {
        color: '#3B82F6',
        weight: 5,
        opacity: 0.8,
      }).addTo(map);

      // 경로에 맞게 지도 범위 조정
      map.fitBounds(polyline.getBounds(), { padding: [20, 20] });
    } else {
      // 경로가 없으면 출발지/목적지 기준으로 범위 설정
      const bounds = L.latLngBounds(
        [data.origin.lat, data.origin.lng],
        [data.destination.lat, data.destination.lng]
      );
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    // 출발지 마커 (초록색)
    const originIcon = L.divIcon({
      className: 'custom-marker',
      html: `<div style="background: #22C55E; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; white-space: nowrap; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">출발: ${data.origin.name}</div>`,
      iconAnchor: [40, 40],
    });
    L.marker([data.origin.lat, data.origin.lng], { icon: originIcon }).addTo(map);

    // 목적지 마커 (빨간색)
    const destIcon = L.divIcon({
      className: 'custom-marker',
      html: `<div style="background: #EF4444; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; white-space: nowrap; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">도착: ${data.destination.name}</div>`,
      iconAnchor: [40, 40],
    });
    L.marker([data.destination.lat, data.destination.lng], { icon: destIcon }).addTo(map);

    // 클린업
    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);  // 최초 마운트 시 1회만 실행 (data는 props로 받은 시점에 이미 확정됨)

  const tollInfo = data.summary.toll > 0 ? ` | 톨비: ${data.summary.toll.toLocaleString()}원` : '';

  return (
    <div className="route-map-container rounded-lg overflow-hidden border border-[#D5CFC5]">
      {/* 요약 정보 */}
      <div className="bg-white px-3 py-2 text-sm border-b border-[#E5DFD5]">
        <strong>{data.origin.name}</strong>
        <span className="mx-2">→</span>
        <strong>{data.destination.name}</strong>
        <div className="text-xs text-[#8A8070] mt-1">
          거리: {data.summary.distance_km}km | 예상 시간: {data.summary.duration_min}분{tollInfo}
        </div>
      </div>
      {/* 지도 */}
      <div ref={mapRef} style={{ height: '400px', width: '100%' }} />
    </div>
  );
});
