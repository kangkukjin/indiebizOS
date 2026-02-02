/**
 * TimelineView - 타임라인 뷰 (줌 가능)
 */

import { useState, useEffect, useCallback } from 'react';
import { Camera, Video, RefreshCw, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, BarChart, Bar
} from 'recharts';

interface TimelineViewProps {
  apiUrl: string;
  selectedPath: string;
  onSelectItem: (item: any, index: number, items: any[]) => void;
}

export function TimelineView({
  apiUrl,
  selectedPath,
  onSelectItem
}: TimelineViewProps) {
  const [timelineData, setTimelineData] = useState<any>(null);
  const [timelineStartDate, setTimelineStartDate] = useState<string>('');
  const [timelineEndDate, setTimelineEndDate] = useState<string>('');
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [zoomHistory, setZoomHistory] = useState<Array<{start: string, end: string}>>([]);

  // 타임라인 데이터 로드
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
        setCurrentPage(0);
      }
    } catch (err) {
      console.error('타임라인 로드 실패:', err);
    } finally {
      setTimelineLoading(false);
    }
  }, [apiUrl, selectedPath]);

  // 초기 로드
  useEffect(() => {
    loadTimelineZoom();
  }, [loadTimelineZoom]);

  // 타임라인 범위 변경 핸들러
  const handleTimelineRangeChange = () => {
    loadTimelineZoom(timelineStartDate || undefined, timelineEndDate || undefined);
  };

  // 타임라인 리셋
  const resetTimeline = () => {
    setTimelineStartDate('');
    setTimelineEndDate('');
    setZoomHistory([]);
    loadTimelineZoom();
  };

  // 한 단계 줌아웃 (뒤로가기)
  const zoomOut = () => {
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

  // 막대 클릭으로 줌인
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
    } else if (period.length === 10) {
      startDate = period;
      endDate = period;
    } else {
      return;
    }

    setTimelineStartDate(startDate);
    setTimelineEndDate(endDate);
    loadTimelineZoom(startDate, endDate);
  };

  // 파일 열기
  const openWithDefaultApp = async (filePath: string) => {
    try {
      await fetch(`${apiUrl}/photo/open-external?path=${encodeURIComponent(filePath)}`, {
        method: 'POST'
      });
    } catch (err) {
      console.error('파일 열기 실패:', err);
    }
  };

  if (timelineLoading && !timelineData) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-8 h-8 text-[#8B7355] animate-spin" />
      </div>
    );
  }

  if (!timelineData) {
    return <div className="text-center text-[#9B8B7A]">데이터 없음</div>;
  }

  const { time_range, stats, density, density_label, files, show_files } = timelineData;

  return (
    <div className="flex flex-col h-full">
      {/* 상단 컨트롤 */}
      <div className="flex items-center gap-4 mb-4 p-3 bg-[#F5F3F0] rounded-lg">
        <div className="text-xs text-[#9B8B7A]">
          전체: {time_range?.min_date?.slice(0, 10)} ~ {time_range?.max_date?.slice(0, 10)}
          <span className="ml-2">({time_range?.total_files?.toLocaleString()}개)</span>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-2">
          <input
            type="date"
            value={timelineStartDate}
            onChange={(e) => setTimelineStartDate(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-[#E8E4DC] bg-white"
          />
          <span className="text-[#9B8B7A]">~</span>
          <input
            type="date"
            value={timelineEndDate}
            onChange={(e) => setTimelineEndDate(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-[#E8E4DC] bg-white"
          />
          <button
            onClick={handleTimelineRangeChange}
            className="p-1.5 rounded bg-[#8B7355] text-white hover:bg-[#7A6349]"
            title="적용"
          >
            <ZoomIn size={14} />
          </button>
          <button
            onClick={zoomOut}
            disabled={zoomHistory.length === 0 && !timelineStartDate && !timelineEndDate}
            className="p-1.5 rounded bg-[#6B9B8B] text-white hover:bg-[#5B8B7B] disabled:opacity-50 disabled:cursor-not-allowed"
            title={`한 단계 뒤로 (${zoomHistory.length})`}
          >
            <ZoomOut size={14} />
          </button>
          <button
            onClick={resetTimeline}
            className="p-1.5 rounded bg-[#9B8B7A] text-white hover:bg-[#8B7B6A]"
            title="초기화"
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      {/* 현재 선택 범위 통계 */}
      {stats && (
        <div className="flex items-center gap-4 mb-4 px-2">
          <div className="text-sm">
            <span className="text-[#9B8B7A]">선택 범위:</span>
            <span className="ml-2 font-medium text-[#5C5347]">
              {stats.range_start?.slice(0, 10)} ~ {stats.range_end?.slice(0, 10)}
            </span>
          </div>
          <div className="text-sm flex items-center gap-1">
            <Camera size={12} className="text-[#8B7355]" />
            <span className="font-medium text-[#8B7355]">{stats.photo_count?.toLocaleString()}</span>
          </div>
          <div className="text-sm flex items-center gap-1">
            <Video size={12} className="text-[#6B9B8B]" />
            <span className="font-medium text-[#6B9B8B]">{stats.video_count?.toLocaleString()}</span>
          </div>
          <div className="text-sm">
            <span className="text-[#9B8B7A]">용량:</span>
            <span className="ml-1 font-medium text-[#5C5347]">{stats.total_size_mb?.toLocaleString()} MB</span>
          </div>
          <div className="text-xs text-[#B0A090]">
            ({density_label === 'year' ? '년' : density_label === 'month' ? '월' : '일'} 단위)
          </div>
        </div>
      )}

      {/* 밀도 차트 */}
      <div className="mb-4">
        <div className="text-xs text-[#9B8B7A] mb-2 px-2">
          차트를 클릭하면 해당 기간으로 줌인됩니다
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart
            data={density.map((d: any) => ({ ...d, _clickArea: 1 }))}
            margin={{ top: 10, right: 30, left: 20, bottom: 40 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DC" />
            <XAxis
              dataKey="period"
              angle={-45}
              textAnchor="end"
              tick={{ fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis yAxisId="left" tick={{ fontSize: 10 }} />
            <YAxis yAxisId="click" hide domain={[0, 1]} />
            <Tooltip
              contentStyle={{ backgroundColor: '#FAFAF8', border: '1px solid #E8E4DC' }}
              formatter={(value, name) => {
                if (name === '_clickArea' || value === undefined) return null;
                const v = Number(value);
                if (name === 'photos') return [`${v.toLocaleString()} 장`, '사진'];
                if (name === 'videos') return [`${v.toLocaleString()} 개`, '동영상'];
                return [v.toLocaleString(), String(name)];
              }}
              filterNull={true}
            />
            <Bar
              yAxisId="click"
              dataKey="_clickArea"
              fill="transparent"
              cursor="pointer"
              onClick={handleBarClick}
            />
            <Bar yAxisId="left" dataKey="photos" fill="#8B7355" name="photos" stackId="stack" />
            <Bar yAxisId="left" dataKey="videos" fill="#6B9B8B" name="videos" stackId="stack" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 썸네일 갤러리 (줌인 상태에서만) */}
      {show_files && files && files.length > 0 && (
        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="text-xs text-[#9B8B7A] mb-2 px-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ZoomIn size={12} />
              미디어 파일 ({files.length}개) - 클릭: 미리보기 / 더블클릭: 파일 열기
            </div>
            {files.length > 50 && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                  disabled={currentPage === 0}
                  className="px-2 py-1 bg-[#F0EDE8] rounded disabled:opacity-50 hover:bg-[#E8E4DC]"
                >
                  ◀
                </button>
                <span>{currentPage + 1} / {Math.ceil(files.length / 50)}</span>
                <button
                  onClick={() => setCurrentPage(Math.min(Math.ceil(files.length / 50) - 1, currentPage + 1))}
                  disabled={currentPage >= Math.ceil(files.length / 50) - 1}
                  className="px-2 py-1 bg-[#F0EDE8] rounded disabled:opacity-50 hover:bg-[#E8E4DC]"
                >
                  ▶
                </button>
              </div>
            )}
          </div>
          <div className="overflow-y-auto flex-1 border border-[#E8E4DC] rounded-lg p-2">
            <div className="grid grid-cols-5 lg:grid-cols-8 xl:grid-cols-10 gap-2">
              {files.slice(currentPage * 50, (currentPage + 1) * 50).map((file: any, idx: number) => {
                const pageFiles = files.slice(currentPage * 50, (currentPage + 1) * 50);
                return (
                <div
                  key={idx}
                  className="aspect-square bg-[#F0EDE8] rounded-lg overflow-hidden cursor-pointer relative group hover:ring-2 hover:ring-[#8B7355] transition-all"
                  onClick={() => onSelectItem(file, idx, pageFiles)}
                  onDoubleClick={() => openWithDefaultApp(file.path)}
                  title={`${file.filename}\n${(file.taken_date || file.mtime)?.slice(0, 16).replace('T', ' ')}\n클릭: 미리보기 / 더블클릭: 파일 열기`}
                >
                  {file.media_type === 'photo' ? (
                    <img
                      src={`http://127.0.0.1:8765/photo/thumbnail?path=${encodeURIComponent(file.path)}&size=150`}
                      alt={file.filename}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-[#2D2A26]">
                      <Video className="w-8 h-8 text-white opacity-70" />
                    </div>
                  )}
                  <div className="absolute top-1 right-1 p-1 bg-black/50 rounded text-white">
                    {file.media_type === 'photo' ? (
                      <Camera size={10} />
                    ) : (
                      <Video size={10} />
                    )}
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div className="text-[10px] text-white truncate">{file.filename}</div>
                    <div className="text-[8px] text-white/70">{(file.taken_date || file.mtime)?.slice(0, 10)}</div>
                  </div>
                </div>
              );})}
            </div>
          </div>
        </div>
      )}

      {/* 파일이 너무 많을 때 안내 */}
      {!show_files && stats?.file_count > 0 && (
        <div className="flex-1 flex items-center justify-center text-[#9B8B7A]">
          <div className="text-center">
            <ZoomIn className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>파일이 {stats.file_count.toLocaleString()}개 있습니다.</p>
            <p className="text-xs mt-1">더 좁은 기간을 선택하면 개별 파일을 볼 수 있습니다.</p>
          </div>
        </div>
      )}
    </div>
  );
}
