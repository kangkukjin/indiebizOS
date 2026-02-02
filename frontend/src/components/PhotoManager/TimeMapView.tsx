/**
 * TimeMapView - 타임라인 기반 지역별 보기 (타임지도)
 */

import { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, MapPin, RefreshCw, RotateCcw } from 'lucide-react';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, BarChart, Bar
} from 'recharts';

interface TimeMapViewProps {
  apiUrl: string;
  selectedPath: string;
  onSelectItem: (item: any, index: number, items: any[]) => void;
}

export function TimeMapView({
  apiUrl,
  selectedPath,
  onSelectItem
}: TimeMapViewProps) {
  const [timelineData, setTimelineData] = useState<any>(null);
  const [timelineStartDate, setTimelineStartDate] = useState<string>('');
  const [timelineEndDate, setTimelineEndDate] = useState<string>('');
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [zoomHistory, setZoomHistory] = useState<Array<{start: string, end: string}>>([]);

  // 지역 리스트 데이터
  const [regions, setRegions] = useState<any[]>([]);
  const [regionsLoading, setRegionsLoading] = useState(false);
  const [selectedRegion, setSelectedRegion] = useState<any | null>(null);
  const [regionPhotos, setRegionPhotos] = useState<any[]>([]);
  const [regionPhotosLoading, setRegionPhotosLoading] = useState(false);

  // 타임라인 데이터 로드 (줌인/아웃용)
  const loadTimelineZoom = useCallback(async (startDate?: string, endDate?: string) => {
    if (!selectedPath || !apiUrl) return;

    setTimelineLoading(true);
    try {
      let endpoint = `${apiUrl}/photo/timeline-zoom?path=${encodeURIComponent(selectedPath)}`;
      if (startDate) endpoint += `&start_date=${startDate}`;
      if (endDate) endpoint += `&end_date=${endDate}`;

      const res = await fetch(endpoint);
      const result = await res.json();

      if (result.success) {
        setTimelineData(result);

        // 만약 'day' 단위(한 달 보기)라면 지역 데이터 로드
        if (result.density_label === 'day') {
          const rangeStart = startDate || result.stats.range_start;
          const rangeEnd = endDate || result.stats.range_end;
          loadRegions(rangeStart, rangeEnd);
        } else {
          setRegions([]);
          setSelectedRegion(null);
        }
      }
    } catch (err) {
      console.error('타임라인 로드 실패:', err);
    } finally {
      setTimelineLoading(false);
    }
  }, [apiUrl, selectedPath]);

  // 지역 데이터 로드
  const loadRegions = async (start: string, end: string) => {
    setRegionsLoading(true);
    try {
      const res = await fetch(`${apiUrl}/photo/timemap-regions?path=${encodeURIComponent(selectedPath)}&start_date=${start}&end_date=${end}`);
      const data = await res.json();
      if (data.success) {
        setRegions(data.regions);
      }
    } catch (err) {
      console.error('지역 데이터 로드 실패:', err);
    } finally {
      setRegionsLoading(false);
    }
  };

  // 특정 지역의 사진 로드
  const loadRegionPhotos = async (region: any) => {
    setSelectedRegion(region);
    setRegionPhotosLoading(true);
    try {
      const res = await fetch(`${apiUrl}/photo/list-by-ids?path=${encodeURIComponent(selectedPath)}&ids=${region.ids.join(',')}`);
      const data = await res.json();
      if (data.success) {
        setRegionPhotos(data.files);
      }
    } catch (err) {
      console.error('지역 사진 로드 실패:', err);
    } finally {
      setRegionPhotosLoading(false);
    }
  };

  // 초기 로드
  useEffect(() => {
    loadTimelineZoom();
  }, [loadTimelineZoom]);

  const resetTimeline = () => {
    setTimelineStartDate('');
    setTimelineEndDate('');
    setZoomHistory([]);
    setSelectedRegion(null);
    loadTimelineZoom();
  };

  const zoomOut = () => {
    if (selectedRegion) {
      setSelectedRegion(null);
      return;
    }
    if (zoomHistory.length === 0) {
      resetTimeline();
      return;
    }
    const newHistory = [...zoomHistory];
    const prev = newHistory.pop();
    setZoomHistory(newHistory);
    setTimelineStartDate(prev?.start || '');
    setTimelineEndDate(prev?.end || '');
    loadTimelineZoom(prev?.start || undefined, prev?.end || undefined);
  };

  const handleBarClick = (data: any) => {
    const period = data?.period || data?.payload?.period;
    if (!period) return;

    setZoomHistory(prev => [...prev, { start: timelineStartDate, end: timelineEndDate }]);

    let startDate: string;
    let endDate: string;

    if (period.length === 4) {
      startDate = `${period}-01-01`;
      endDate = `${period}-12-31`;
    } else if (period.length === 7) {
      const [year, month] = period.split('-');
      const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate();
      startDate = `${period}-01`;
      endDate = `${period}-${String(lastDay).padStart(2, '0')}`;
    } else {
      return;
    }

    setTimelineStartDate(startDate);
    setTimelineEndDate(endDate);
    loadTimelineZoom(startDate, endDate);
  };

  if (timelineLoading && !timelineData) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-8 h-8 text-[#8B7355] animate-spin" />
      </div>
    );
  }

  if (!timelineData) return <div className="text-center text-[#9B8B7A]">데이터 없음</div>;

  const { density, density_label } = timelineData;
  const isDayLevel = density_label === 'day';

  return (
    <div className="flex flex-col h-full">
      {/* 상단 컨트롤 */}
      <div className="flex items-center gap-4 mb-4 p-3 bg-[#F5F3F0] rounded-lg">
        <button
          onClick={zoomOut}
          disabled={zoomHistory.length === 0 && !timelineStartDate && !timelineEndDate && !selectedRegion}
          className="p-1.5 rounded bg-[#6B9B8B] text-white hover:bg-[#5B8B7B] disabled:opacity-50"
        >
          <ChevronLeft size={16} />
        </button>
        <div className="text-sm font-medium text-[#5C5347]">
          {selectedRegion ? `${selectedRegion.region_name}` :
           isDayLevel ? `${timelineStartDate.slice(0, 7)} 방문 지역` : '기간별 방문 기록'}
        </div>
        <div className="flex-1" />
        <button
          onClick={resetTimeline}
          className="p-1.5 rounded bg-[#9B8B7A] text-white hover:bg-[#8B7B6A]"
        >
          <RotateCcw size={14} />
        </button>
      </div>

      {/* 메인 콘텐츠 */}
      <div className="flex-1 overflow-auto">
        {selectedRegion ? (
          /* 지역별 갤러리 */
          <div>
            <div className="flex items-center gap-2 mb-4 text-[#9B8B7A]">
              <MapPin size={14} />
              <span className="text-sm">{selectedRegion.region_name} - {selectedRegion.count}장의 사진</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {regionPhotosLoading ? (
                <div className="col-span-full flex justify-center py-12">
                  <RefreshCw className="animate-spin text-[#8B7355]" />
                </div>
              ) : (
                regionPhotos.map((item, idx) => (
                  <div
                    key={item.id}
                    className="aspect-square rounded-lg overflow-hidden border border-[#E8E4DC] cursor-pointer hover:ring-2 hover:ring-[#8B7355] transition-all"
                    onClick={() => onSelectItem(item, idx, regionPhotos)}
                  >
                    <img
                      src={`${apiUrl}/photo/thumbnail?path=${encodeURIComponent(item.path)}&size=300`}
                      alt={item.filename}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  </div>
                ))
              )}
            </div>
          </div>
        ) : isDayLevel ? (
          /* 지역 리스트 */
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {regionsLoading ? (
              <div className="col-span-full flex justify-center py-12">
                <RefreshCw className="animate-spin text-[#8B7355]" />
              </div>
            ) : regions.length === 0 ? (
              <div className="col-span-full text-center py-12 text-[#9B8B7A]">
                위치 정보가 있는 사진이 없습니다.
              </div>
            ) : (
              regions.map((region) => (
                <div
                  key={region.region_name}
                  className="bg-white p-4 rounded-xl border border-[#E8E4DC] shadow-sm hover:shadow-md cursor-pointer transition-all group"
                  onClick={() => loadRegionPhotos(region)}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-16 h-16 rounded-lg bg-[#F5F3F0] overflow-hidden flex-shrink-0">
                      {region.representative_path ? (
                        <img
                          src={`${apiUrl}/photo/thumbnail?path=${encodeURIComponent(region.representative_path)}&size=100`}
                          className="w-full h-full object-cover"
                          alt=""
                        />
                      ) : (
                        <MapPin className="w-full h-full p-4 text-[#D4C8B8]" />
                      )}
                    </div>
                    <div>
                      <h3 className="font-medium text-[#5C5347] group-hover:text-[#8B7355] transition-colors">
                        {region.region_name}
                      </h3>
                      <p className="text-xs text-[#9B8B7A] mt-1">
                        사진 {region.count}장
                      </p>
                    </div>
                    <ChevronRight className="ml-auto text-[#D4C8B8]" size={18} />
                  </div>
                </div>
              ))
            )}
          </div>
        ) : (
          /* 년/월 단위 차트 */
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={density}
                margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DC" vertical={false} />
                <XAxis
                  dataKey="period"
                  tick={{ fontSize: 12, fill: '#9B8B7A' }}
                  axisLine={{ stroke: '#E8E4DC' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12, fill: '#9B8B7A' }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: '#F5F3F0' }}
                  contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                  formatter={(value: number | undefined, name: string | undefined) => {
                    if (name === 'photos') return [`${value ?? 0}장`, '사진'];
                    if (name === 'videos') return [`${value ?? 0}개`, '동영상'];
                    return [String(value ?? 0), name ?? ''];
                  }}
                />
                {/* 사진/동영상 스택 막대 - 클릭 가능 */}
                <Bar
                  dataKey="photos"
                  fill="#8B7355"
                  name="photos"
                  stackId="stack"
                  radius={[0, 0, 0, 0]}
                  cursor="pointer"
                  onClick={handleBarClick}
                />
                <Bar
                  dataKey="videos"
                  fill="#6B9B8B"
                  name="videos"
                  stackId="stack"
                  radius={[4, 4, 0, 0]}
                  cursor="pointer"
                  onClick={handleBarClick}
                />
              </BarChart>
            </ResponsiveContainer>
            <p className="text-center text-xs text-[#9B8B7A] mt-4">
              막대를 클릭하여 해당 기간의 방문 지역을 확인하세요
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
