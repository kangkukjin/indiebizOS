/**
 * 위치 지도 컴포넌트 (Leaflet 기반)
 * 특정 위치를 마커와 함께 표시
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

export interface LocationMapData {
  type: 'location_map';
  center: {
    lat: number;
    lng: number;
    name: string;
  };
  zoom: number;
  markers: {
    name: string;
    lat: number;
    lng: number;
  }[];
}

interface LocationMapProps {
  data: LocationMapData;
}

export const LocationMap = memo(function LocationMap({ data }: LocationMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // 지도 생성
    const map = L.map(mapRef.current, {
      scrollWheelZoom: false,  // 스크롤 줌 비활성화 (채팅 스크롤과 충돌 방지)
    }).setView([data.center.lat, data.center.lng], data.zoom);

    mapInstanceRef.current = map;

    // OpenStreetMap 타일 레이어
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    // 마커 추가
    data.markers.forEach((marker, index) => {
      const isCenter = index === 0;
      const markerIcon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="background: ${isCenter ? '#3B82F6' : '#EF4444'}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; white-space: nowrap; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">${marker.name}</div>`,
        iconAnchor: [40, 40],
      });
      L.marker([marker.lat, marker.lng], { icon: markerIcon }).addTo(map);
    });

    // 마커가 여러 개면 모두 보이도록 범위 조정
    if (data.markers.length > 1) {
      const bounds = L.latLngBounds(
        data.markers.map(m => [m.lat, m.lng] as L.LatLngExpression)
      );
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    // 클린업
    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);  // 최초 마운트 시 1회만 실행

  return (
    <div className="location-map-container rounded-lg overflow-hidden border border-[#D5CFC5]">
      {/* 장소 정보 */}
      <div className="bg-white px-3 py-2 text-sm border-b border-[#E5DFD5]">
        <strong>{data.center.name}</strong>
        {data.markers.length > 1 && (
          <span className="text-xs text-[#8A8070] ml-2">
            외 {data.markers.length - 1}곳
          </span>
        )}
      </div>
      {/* 지도 */}
      <div ref={mapRef} style={{ height: '400px', width: '100%' }} />
    </div>
  );
});
