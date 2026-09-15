import { useState } from 'react';
import type { RouteResult } from './types';
import { fmtDistance } from './types';
import { segmentLabel, sortTransit, transitRoutes } from './transit';
import type { TransitOrder } from './transit';

export function TransitRoutes({ result, selected, onSelect }: {
  result: RouteResult; selected: number | null; onSelect: (id: number) => void;
}) {
  const [order, setOrder] = useState<TransitOrder>('duration_min');
  const routes = sortTransit(transitRoutes(result), order);
  if (!routes.length) return null;
  return <div className="space-y-3">
    <div className="flex items-center justify-between gap-2">
      <h3 className="text-sm font-semibold">대중교통 {routes.length}개 경로</h3>
      <select aria-label="경로 정렬" value={order} onChange={(e) => setOrder(e.target.value as TransitOrder)}
        className="rounded-lg border border-stone-200 bg-white px-2 py-1 text-xs">
        <option value="duration_min">빠른 순</option><option value="transfer_count">환승 적은 순</option>
        <option value="walking_distance_m">도보 짧은 순</option>
      </select>
    </div>
    <p className="text-[11px] text-stone-500">ODsay 예상 시간·요금 · 실시간 도착 정보 미포함. 노선 운행시간은 별도로 확인하세요.</p>
    {result.partial && <p role="status" className="text-xs text-amber-700">일부 경로를 불러오지 못했습니다. 확인된 경로만 표시합니다.</p>}
    {routes.map((route) => {
      const active = selected === route.route_index;
      return <section key={route.route_index} className={`rounded-xl border bg-white overflow-hidden ${active ? 'border-blue-400 ring-1 ring-blue-100' : 'border-stone-200'}`}>
        <button onClick={() => onSelect(route.route_index)} aria-expanded={active}
          aria-label={`경로 ${route.route_index + 1}, ${route.duration_min}분, 환승 ${route.transfer_count}회`}
          className="w-full text-left p-3 hover:bg-blue-50/40">
          <div className="flex items-baseline gap-2"><strong className="text-lg">{route.duration_min}분</strong>
            <span className="text-xs text-stone-500">환승 {route.transfer_count}회</span>
            <span className="ml-auto text-sm">{route.fare_krw.toLocaleString()}원</span></div>
          <div className="mt-1 text-xs text-stone-500">도보 {fmtDistance(route.walking_distance_m)}</div>
          <div className="mt-2 flex flex-wrap gap-1 text-xs">
            {route.segments.filter((s) => s.trafficType !== 3).map((s, i) =>
              <span key={i} className={`px-2 py-1 rounded-md ${s.trafficType === 1 ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'}`}>
                {s.trafficType === 1 ? '🚇' : '🚌'} {segmentLabel(s)}
              </span>)}
          </div>
        </button>
        {active && <div className="px-3 pb-3 border-t border-stone-100">
          <ol aria-label="이동 구간" className="divide-y divide-stone-100">
            {route.segments.map((s, i) => <li key={i} className="py-2 text-xs">
              <div className="flex gap-2"><span>{s.trafficType === 3 ? '🚶' : s.trafficType === 1 ? '🚇' : '🚌'}</span>
                <span className="font-medium">{segmentLabel(s)}</span><span className="ml-auto text-stone-500">{s.sectionTime}분</span></div>
              {s.trafficType === 3 ? <div className="ml-6 text-stone-500">{fmtDistance(s.distance)}</div> :
                <div className="ml-6 mt-1 space-y-0.5"><div>{s.startName || '승차 정류장'} → {s.endName || '하차 정류장'}</div>
                  <div className="text-stone-500">{s.way && `${s.way} 방면`}{s.stationCount != null && ` · ${s.stationCount}개 정류장`}</div>
                </div>}
            </li>)}
          </ol>
          <p className="text-[11px] text-stone-400 mt-1">지도에는 이 경로의 정류장 위치를 표시합니다. 노선 선형과 도보 경로는 표시하지 않습니다.</p>
        </div>}
      </section>;
    })}
  </div>;
}
