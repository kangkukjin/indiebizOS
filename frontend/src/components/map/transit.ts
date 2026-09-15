/** 대중교통 응답의 표시용 선택·정렬·정류장 좌표. 경로 계산은 IBL이 소유한다. */
import type { RouteResult, TransitRoute, TransitSegment } from './types';

export type TransitOrder = 'duration_min' | 'transfer_count' | 'walking_distance_m';
export function transitRoutes(result: RouteResult | null): TransitRoute[] {
  if (result?.mode !== 'transit' || result.success === false || result.error) return [];
  return (result.items || []).filter((r) => r.complete === true && Array.isArray(r.segments));
}
export function sortTransit(routes: TransitRoute[], by: TransitOrder): TransitRoute[] {
  return [...routes].sort((a, b) => a[by] - b[by] || a.duration_min - b.duration_min || a.route_index - b.route_index);
}
export function segmentLabel(segment: TransitSegment): string {
  if (segment.trafficType === 3) return '도보';
  const names = (segment.lane || []).map((lane) => lane.busNo || lane.name).filter(Boolean);
  return names.join(' / ') || (segment.trafficType === 1 ? '지하철' : '버스');
}
export function transitStops(route?: TransitRoute): { lat: number; lng: number; name: string; type: number }[] {
  const stops: { lat: number; lng: number; name: string; type: number }[] = [];
  const seen = new Set<string>();
  const add = (x: unknown, y: unknown, name: string, type: number) => {
    if (x == null || y == null || x === '' || y === '') return;
    const lng = Number(x), lat = Number(y);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return;
    const key = `${lat},${lng}`;
    if (!seen.has(key)) { seen.add(key); stops.push({ lat, lng, name, type }); }
  };
  for (const seg of route?.segments || []) {
    if (seg.trafficType === 3) continue;
    add(seg.startX, seg.startY, seg.startName || '승차', seg.trafficType);
    for (const stop of seg.passStopList?.stations || []) add(stop.x, stop.y, stop.stationName || '경유 정류장', seg.trafficType);
    add(seg.endX, seg.endY, seg.endName || '하차', seg.trafficType);
  }
  return stops;
}
