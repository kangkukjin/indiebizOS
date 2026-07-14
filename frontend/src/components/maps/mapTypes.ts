/**
 * 지도 표시 데이터 타입 — 단일 소스.
 *
 * 백엔드 위치 액션이 emit하는 표시 봉투(map_data)와 1:1 대응한다.
 * 좌표는 항상 {lat, lng} (number). 봉투 빌더는
 *   location-services/handler.py build_location_map / build_route_map,
 *   cctv/handler.py (cctvs[].lat/lng) 와 규약을 공유한다.
 */

export interface MarkerData {
  name: string;
  lat: number;
  lng: number;
  meta?: string;   // 부가 정보 한 줄 (가격·평점 등) — 마커 팝업에 표시
  url?: string;    // 상세 페이지 링크 — 마커 팝업에 "자세히 보기 →"로 표시
}

export interface LocationMapData {
  type: 'location_map';
  center: MarkerData;
  zoom: number;
  markers: MarkerData[];
}

export interface RouteMapData {
  type: 'route_map';
  origin: MarkerData;
  destination: MarkerData;
  path: [number, number][]; // [lat, lng][]
  summary: {
    distance_km: number;
    duration_min: number;
    toll: number;
  };
}
