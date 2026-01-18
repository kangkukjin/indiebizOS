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

  // 데이터 유효성 검사
  const isValidCoord = (lat: unknown, lng: unknown): boolean => {
    return typeof lat === 'number' && typeof lng === 'number' &&
           !isNaN(lat) && !isNaN(lng) &&
           lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
  };

  const hasValidCenter = data?.center && isValidCoord(data.center.lat, data.center.lng);
  const validMarkers = (data?.markers || []).filter(m => isValidCoord(m.lat, m.lng));

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // 유효한 좌표가 없으면 지도 생성하지 않음
    if (!hasValidCenter && validMarkers.length === 0) {
      console.error('[LocationMap] 유효한 좌표가 없습니다:', data);
      return;
    }

    // 중심점 결정: center가 유효하면 사용, 아니면 첫 번째 유효한 마커 사용
    const centerLat = hasValidCenter ? data.center.lat : validMarkers[0]?.lat || 37.5665;
    const centerLng = hasValidCenter ? data.center.lng : validMarkers[0]?.lng || 126.9780;
    const zoom = data?.zoom || 15;

    // 지도 생성
    const map = L.map(mapRef.current, {
      scrollWheelZoom: false,  // 스크롤 줌 비활성화 (채팅 스크롤과 충돌 방지)
    }).setView([centerLat, centerLng], zoom);

    mapInstanceRef.current = map;

    // OpenStreetMap 타일 레이어
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    // 마커 추가 (유효한 마커만)
    validMarkers.forEach((marker, index) => {
      const isCenter = index === 0;
      const markerIcon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="background: ${isCenter ? '#3B82F6' : '#EF4444'}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; white-space: nowrap; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">${marker.name || '위치'}</div>`,
        iconAnchor: [40, 40],
      });
      L.marker([marker.lat, marker.lng], { icon: markerIcon }).addTo(map);
    });

    // 마커가 여러 개면 모두 보이도록 범위 조정
    if (validMarkers.length > 1) {
      const bounds = L.latLngBounds(
        validMarkers.map(m => [m.lat, m.lng] as L.LatLngExpression)
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

  // 유효한 데이터가 없으면 에러 메시지 표시
  if (!hasValidCenter && validMarkers.length === 0) {
    return (
      <div className="location-map-container rounded-lg overflow-hidden border border-[#D5CFC5] bg-gray-100 p-4">
        <div className="text-center text-gray-500">
          <p>지도를 표시할 수 없습니다.</p>
          <p className="text-xs mt-1">유효한 위치 정보가 없습니다.</p>
        </div>
      </div>
    );
  }

  const displayName = hasValidCenter ? data.center.name : validMarkers[0]?.name || '위치';

  return (
    <div className="location-map-container rounded-lg overflow-hidden border border-[#D5CFC5]">
      {/* 장소 정보 */}
      <div className="bg-white px-3 py-2 text-sm border-b border-[#E5DFD5]">
        <strong>{displayName}</strong>
        {validMarkers.length > 1 && (
          <span className="text-xs text-[#8A8070] ml-2">
            외 {validMarkers.length - 1}곳
          </span>
        )}
      </div>
      {/* 지도 */}
      <div ref={mapRef} style={{ height: '400px', width: '100%' }} />
    </div>
  );
});
