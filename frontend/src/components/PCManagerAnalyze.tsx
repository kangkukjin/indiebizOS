/**
 * PCManagerAnalyze - 스토리지 분석 시각화 컴포넌트
 * 트리맵, 타임라인, 확장자 차트, 폴더맵, 산점도 5가지 시각화 제공
 */

import { useEffect, useState } from 'react';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
  LineChart, Line, CartesianGrid,
  ScatterChart, Scatter, ZAxis,
  Treemap,
  BarChart, Bar
} from 'recharts';
import {
  LayoutGrid, Clock, FileType, FolderTree, Sparkles,
  RefreshCw, HardDrive, FolderOpen, FolderSearch, Trash2,
  ZoomIn, ZoomOut, RotateCcw
} from 'lucide-react';

type ViewMode = 'treemap' | 'timeline' | 'extensions' | 'folders' | 'scatter';

// 색상 팔레트
const COLORS = [
  '#D4A574', '#8B7B6B', '#6B9B8B', '#9B7B8B', '#7B8B9B',
  '#A5B4A2', '#B8A590', '#95A5A6', '#7FDBFF', '#B10DC9',
  '#FFDC00', '#FF851B', '#FF4136', '#85144b', '#3D9970'
];

// 볼륨 정보 인터페이스
interface VolumeInfo {
  id: number;
  name: string;
  root_path: string;
  file_count: number;
  total_size_mb: number;
  last_scan: string | null;
}

export function PCManagerAnalyze() {
  // API URL 가져오기
  const getApiUrl = async () => {
    if (window.electron?.getApiPort) {
      const port = await window.electron.getApiPort();
      return `http://127.0.0.1:${port}`;
    }
    return 'http://127.0.0.1:8765';
  };

  const [apiUrl, setApiUrl] = useState('http://127.0.0.1:8765');
  const [selectedPath, setSelectedPath] = useState<string>('');
  const [volumes, setVolumes] = useState<VolumeInfo[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('treemap');
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [scanExists, setScanExists] = useState(false);
  const [scanInfo, setScanInfo] = useState<VolumeInfo | null>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [newScanPath, setNewScanPath] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<any>(null);

  // 타임라인 줌 상태
  const [timelineData, setTimelineData] = useState<any>(null);
  const [timelineStartDate, setTimelineStartDate] = useState<string>('');
  const [timelineEndDate, setTimelineEndDate] = useState<string>('');
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [zoomHistory, setZoomHistory] = useState<Array<{start: string, end: string}>>([]);

  // 볼륨 목록 로드
  const loadVolumes = async (url: string) => {
    try {
      const res = await fetch(`${url}/pcmanager/analyze/volumes`);
      const result = await res.json();
      if (result.success) {
        setVolumes(result.volumes || []);
        // 볼륨이 있으면 첫 번째 선택
        if (result.volumes && result.volumes.length > 0) {
          const firstVolume = result.volumes[0];
          setSelectedPath(firstVolume.root_path);
          setScanInfo(firstVolume);
          setScanExists(true);
        }
      }
    } catch (err) {
      console.error('볼륨 목록 로드 실패:', err);
    }
  };

  // 스캔 삭제
  const deleteScan = async (scanId: number) => {
    if (!confirm('이 스캔 데이터를 삭제하시겠습니까?')) return;

    try {
      const res = await fetch(`${apiUrl}/pcmanager/analyze/scan/${scanId}`, {
        method: 'DELETE'
      });
      const result = await res.json();
      if (result.success) {
        // 삭제된 스캔이 현재 선택된 것이면 초기화
        const deletedVolume = volumes.find(v => v.id === scanId);
        if (deletedVolume && deletedVolume.root_path === selectedPath) {
          setSelectedPath('');
          setScanExists(false);
          setScanInfo(null);
          setData(null);
        }
        // 볼륨 목록 새로고침
        await loadVolumes(apiUrl);
      } else {
        setError(result.error || '삭제 실패');
      }
    } catch (err) {
      setError('삭제 중 오류 발생');
    }
  };

  // Finder에서 파일/폴더 선택 (reveal)
  const openInFinder = async (filePath: string) => {
    if (window.electron?.openPath) {
      await window.electron.openPath(filePath);
    } else {
      try {
        await fetch(`${apiUrl}/pcmanager/open?path=${encodeURIComponent(filePath)}&reveal=true`);
      } catch (err) {
        console.error('파일 열기 실패:', err);
      }
    }
  };

  // 기본 앱으로 파일 열기
  const openWithDefaultApp = async (filePath: string) => {
    try {
      await fetch(`${apiUrl}/pcmanager/open?path=${encodeURIComponent(filePath)}&reveal=false`);
    } catch (err) {
      console.error('파일 열기 실패:', err);
    }
  };

  // 스캔 실행
  const runScan = async (path?: string) => {
    const scanPath = path || selectedPath || newScanPath;
    if (!scanPath) return;

    setIsScanning(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/pcmanager/analyze/scan?path=${encodeURIComponent(scanPath)}`, {
        method: 'POST'
      });
      const result = await res.json();
      if (result.success) {
        setScanExists(true);
        setSelectedPath(scanPath);
        setScanInfo({
          name: result.volume_name,
          root_path: scanPath,
          file_count: result.file_count,
          total_size_mb: result.total_size_mb,
          last_scan: result.scan_time
        });
        setNewScanPath('');
        await loadVolumes(apiUrl);
        loadData(viewMode, scanPath);
      } else {
        setError(result.error || '스캔 실패');
      }
    } catch (err) {
      setError('스캔 중 오류 발생');
    } finally {
      setIsScanning(false);
    }
  };

  // 데이터 로드
  const loadData = async (mode: ViewMode, path?: string) => {
    const targetPath = path || selectedPath;
    if (!targetPath) return;

    setIsLoading(true);
    setError(null);
    try {
      const endpoint = {
        treemap: 'treemap',
        timeline: 'timeline',
        extensions: 'extensions',
        folders: 'folders',
        scatter: 'scatter'
      }[mode];

      const url = await getApiUrl();
      const res = await fetch(`${url}/pcmanager/analyze/${endpoint}?path=${encodeURIComponent(targetPath)}`);
      const result = await res.json();

      if (result.success) {
        setData(result.data);
      } else {
        setError(result.error || '데이터 로드 실패');
      }
    } catch (err) {
      setError('데이터 로드 중 오류 발생');
    } finally {
      setIsLoading(false);
    }
  };

  // 초기 로드
  useEffect(() => {
    const init = async () => {
      const url = await getApiUrl();
      setApiUrl(url);
      await loadVolumes(url);
      setIsLoading(false);
    };
    init();
  }, []);

  // 선택된 경로 변경 시 데이터 로드
  useEffect(() => {
    if (selectedPath && scanExists) {
      // 타임라인 데이터도 리셋
      setTimelineData(null);
      setTimelineStartDate('');
      setTimelineEndDate('');
      loadData(viewMode);
    }
  }, [selectedPath]);

  // 뷰 모드 변경 시 데이터 로드
  useEffect(() => {
    if (scanExists && selectedPath) {
      setData(null);  // 이전 데이터 초기화
      // 타임라인 모드로 전환 시 타임라인 데이터 리셋
      if (viewMode === 'timeline') {
        setTimelineData(null);
        setTimelineStartDate('');
        setTimelineEndDate('');
      } else {
        loadData(viewMode);
      }
    }
  }, [viewMode]);

  // 볼륨 선택
  const handleVolumeSelect = (volume: VolumeInfo) => {
    setSelectedPath(volume.root_path);
    setScanInfo(volume);
    setScanExists(true);
  };

  // 폴더 선택 다이얼로그
  const handleSelectFolder = async () => {
    if (window.electron?.selectFolder) {
      const folderPath = await window.electron.selectFolder();
      if (folderPath) {
        setNewScanPath(folderPath);
        // 선택 후 바로 스캔 시작
        runScan(folderPath);
      }
    } else {
      alert('폴더 선택 기능은 데스크톱 앱에서만 사용 가능합니다.');
    }
  };

  // 뷰 모드 버튼
  const ViewModeButton = ({ mode, icon: Icon, label }: { mode: ViewMode; icon: any; label: string }) => (
    <button
      onClick={() => setViewMode(mode)}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
        viewMode === mode
          ? 'bg-[#D4A574] text-white'
          : 'bg-[#F0EDE7] text-[#6B5B4F] hover:bg-[#E8E4DC]'
      }`}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );

  // 트리맵 렌더링
  const renderTreemap = () => {
    if (!data || data.length === 0) return <div className="text-center text-[#8B7B6B]">데이터 없음</div>;

    const CustomizedContent = (props: any) => {
      const { x, y, width, height, name, size_mb } = props;
      if (width < 50 || height < 30) return null;
      return (
        <g>
          <rect x={x} y={y} width={width} height={height} fill={COLORS[props.index % COLORS.length]} stroke="#fff" strokeWidth={2} rx={4} />
          <text x={x + width / 2} y={y + height / 2 - 8} textAnchor="middle" fill="#fff" fontSize={12} fontWeight="500">
            {name.length > 15 ? name.slice(0, 15) + '...' : name}
          </text>
          <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fill="#fff" fontSize={10} opacity={0.9}>
            {size_mb} MB
          </text>
        </g>
      );
    };

    return (
      <ResponsiveContainer width="100%" height={400}>
        <Treemap
          data={data}
          dataKey="size"
          aspectRatio={4 / 3}
          stroke="#fff"
          content={<CustomizedContent />}
        />
      </ResponsiveContainer>
    );
  };

  // 타임라인 데이터 로드 (줌 가능)
  const loadTimelineZoom = async (startDate?: string, endDate?: string) => {
    if (!selectedPath) return;

    setTimelineLoading(true);
    try {
      const url = await getApiUrl();
      let endpoint = `${url}/pcmanager/analyze/timeline-zoom?path=${encodeURIComponent(selectedPath)}`;
      if (startDate) endpoint += `&start_date=${startDate}`;
      if (endDate) endpoint += `&end_date=${endDate}`;

      const res = await fetch(endpoint);
      const result = await res.json();

      if (result.success) {
        setTimelineData(result);
      }
    } catch (err) {
      console.error('타임라인 로드 실패:', err);
    } finally {
      setTimelineLoading(false);
    }
  };

  // 타임라인 범위 변경 핸들러
  const handleTimelineRangeChange = () => {
    // 현재 범위를 히스토리에 저장
    if (timelineStartDate || timelineEndDate) {
      setZoomHistory(prev => [...prev, { start: timelineStartDate, end: timelineEndDate }]);
    }
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
      // 히스토리가 없으면 전체 보기
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
  const handleBarClick = (data: any, index: number, event: any) => {
    console.log('Bar clicked:', data, index);

    // data가 직접 period를 가지거나, payload 안에 있을 수 있음
    const period = data?.period || data?.payload?.period;
    if (!period) {
      console.log('No period found in data');
      return;
    }

    // 현재 범위를 히스토리에 저장 (줌인 전)
    setZoomHistory(prev => [...prev, { start: timelineStartDate, end: timelineEndDate }]);

    let startDate: string;
    let endDate: string;

    // 기간에 따라 줌인
    if (period.length === 4) {
      // 년 → 해당 년도 전체
      startDate = `${period}-01-01`;
      endDate = `${period}-12-31`;
    } else if (period.length === 7) {
      // 월 → 해당 월 전체
      const [year, month] = period.split('-');
      const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate();
      startDate = `${period}-01`;
      endDate = `${period}-${String(lastDay).padStart(2, '0')}`;
    } else if (period.length === 10) {
      // 일 → 해당 일 하루만 (단일 날짜 줌)
      startDate = period;
      endDate = period;
    } else {
      console.log('Unknown period format:', period);
      return;
    }

    console.log('Zooming to:', startDate, endDate);
    setTimelineStartDate(startDate);
    setTimelineEndDate(endDate);
    loadTimelineZoom(startDate, endDate);
  };

  // 타임라인 렌더링 (줌 가능)
  const renderTimeline = () => {
    // 타임라인 뷰로 전환 시 데이터 로드
    if (!timelineData && !timelineLoading) {
      loadTimelineZoom();
      return <div className="flex items-center justify-center h-full"><RefreshCw className="w-8 h-8 text-[#D4A574] animate-spin" /></div>;
    }

    if (timelineLoading) {
      return <div className="flex items-center justify-center h-full"><RefreshCw className="w-8 h-8 text-[#D4A574] animate-spin" /></div>;
    }

    if (!timelineData) {
      return <div className="text-center text-[#8B7B6B]">데이터 없음</div>;
    }

    const { time_range, stats, density, density_label, files, show_files } = timelineData;

    return (
      <div className="flex flex-col h-full">
        {/* 상단 컨트롤 */}
        <div className="flex items-center gap-4 mb-4 p-3 bg-[#F5F1EB] rounded-lg">
          {/* 시간 범위 정보 */}
          <div className="text-xs text-[#8B7B6B]">
            전체: {time_range?.min_date?.slice(0, 10)} ~ {time_range?.max_date?.slice(0, 10)}
            <span className="ml-2">({time_range?.total_files?.toLocaleString()}개 파일)</span>
          </div>

          <div className="flex-1" />

          {/* 날짜 범위 선택 */}
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={timelineStartDate}
              onChange={(e) => setTimelineStartDate(e.target.value)}
              className="px-2 py-1 text-xs rounded border border-[#E5E0D8] bg-white"
            />
            <span className="text-[#8B7B6B]">~</span>
            <input
              type="date"
              value={timelineEndDate}
              onChange={(e) => setTimelineEndDate(e.target.value)}
              className="px-2 py-1 text-xs rounded border border-[#E5E0D8] bg-white"
            />
            <button
              onClick={handleTimelineRangeChange}
              className="p-1.5 rounded bg-[#D4A574] text-white hover:bg-[#C49464]"
              title="적용"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <button
              onClick={zoomOut}
              disabled={zoomHistory.length === 0 && !timelineStartDate && !timelineEndDate}
              className="p-1.5 rounded bg-[#6B9B8B] text-white hover:bg-[#5B8B7B] disabled:opacity-50 disabled:cursor-not-allowed"
              title={`한 단계 뒤로 (${zoomHistory.length})`}
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              onClick={resetTimeline}
              className="p-1.5 rounded bg-[#8B7B6B] text-white hover:bg-[#6B5B4F]"
              title="초기화"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 현재 선택 범위 통계 */}
        {stats && (
          <div className="flex items-center gap-4 mb-4 px-2">
            <div className="text-sm">
              <span className="text-[#8B7B6B]">선택 범위:</span>
              <span className="ml-2 font-medium text-[#4A4A4A]">
                {stats.range_start?.slice(0, 10)} ~ {stats.range_end?.slice(0, 10)}
              </span>
            </div>
            <div className="text-sm">
              <span className="text-[#8B7B6B]">파일 수:</span>
              <span className="ml-2 font-medium text-[#D4A574]">{stats.file_count?.toLocaleString()}</span>
            </div>
            <div className="text-sm">
              <span className="text-[#8B7B6B]">용량:</span>
              <span className="ml-2 font-medium text-[#6B9B8B]">{stats.total_size_mb?.toLocaleString()} MB</span>
            </div>
            <div className="text-xs text-[#A0A0A0]">
              ({density_label === 'year' ? '년' : density_label === 'month' ? '월' : '일'} 단위)
            </div>
          </div>
        )}

        {/* 밀도 차트 (컬럼 전체 클릭 가능) */}
        <div className="mb-4">
          <div className="text-xs text-[#8B7B6B] mb-2 px-2">
            차트를 클릭하면 해당 기간으로 줌인됩니다
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={density.map((d: any) => ({ ...d, _clickArea: 1 }))}
              margin={{ top: 10, right: 30, left: 20, bottom: 40 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E0D8" />
              <XAxis
                dataKey="period"
                angle={-45}
                textAnchor="end"
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis yAxisId="left" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="click" hide domain={[0, 1]} />
              <Tooltip
                contentStyle={{ backgroundColor: '#FAFAF8', border: '1px solid #E5E0D8' }}
                formatter={(value: number, name: string) => {
                  if (name === '_clickArea') return null;
                  return [name === 'file_count' ? `${value.toLocaleString()} 개` : `${value.toLocaleString()} MB`, name === 'file_count' ? '파일 수' : '용량'];
                }}
                filterNull={true}
              />
              {/* 투명한 클릭 영역 - 전체 높이 */}
              <Bar
                yAxisId="click"
                dataKey="_clickArea"
                fill="transparent"
                cursor="pointer"
                onClick={handleBarClick}
              />
              {/* 실제 데이터 막대 */}
              <Bar yAxisId="left" dataKey="file_count" fill="#D4A574" name="file_count" />
              <Bar yAxisId="right" dataKey="size_mb" fill="#6B9B8B" name="size_mb" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* 개별 파일 목록 (줌인 상태에서만) */}
        {show_files && files && files.length > 0 && (
          <div className="flex-1 overflow-hidden">
            <div className="text-xs text-[#8B7B6B] mb-2 px-2 flex items-center gap-2">
              <ZoomIn className="w-3 h-3" />
              개별 파일 목록 ({files.length}개)
            </div>
            <div className="overflow-y-auto max-h-[400px] border border-[#E5E0D8] rounded-lg">
              <table className="w-full text-xs text-[#2D2D2D]">
                <thead className="sticky top-0 bg-[#F5F1EB]">
                  <tr>
                    <th className="text-left p-2 font-semibold">시간</th>
                    <th className="text-left p-2 font-semibold">파일명</th>
                    <th className="text-right p-2 font-semibold">크기</th>
                    <th className="text-left p-2 font-semibold">확장자</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file: any, idx: number) => (
                    <tr
                      key={idx}
                      className="border-t border-[#E5E0D8] hover:bg-[#F0EDE7] cursor-pointer"
                      onClick={() => setSelectedFile(file)}
                      onDoubleClick={() => openWithDefaultApp(file.path)}
                      title="더블클릭: 파일 열기"
                    >
                      <td className="p-2 text-[#8B7B6B] whitespace-nowrap">
                        {file.mtime?.slice(0, 16).replace('T', ' ')}
                      </td>
                      <td className="p-2 truncate max-w-[200px]" title={file.path}>
                        {file.filename}
                      </td>
                      <td className="p-2 text-right">{file.size_mb} MB</td>
                      <td className="p-2 text-[#6B9B8B]">.{file.extension || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 파일이 너무 많을 때 안내 */}
        {!show_files && stats?.file_count > 0 && (
          <div className="flex-1 flex items-center justify-center text-[#8B7B6B]">
            <div className="text-center">
              <ZoomIn className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>파일이 {stats.file_count.toLocaleString()}개 있습니다.</p>
              <p className="text-xs mt-1">더 좁은 기간을 선택하면 개별 파일을 볼 수 있습니다.</p>
            </div>
          </div>
        )}
      </div>
    );
  };

  // 확장자 차트 렌더링
  const renderExtensions = () => {
    if (!data || data.length === 0 || !data[0]?.count) return <div className="text-center text-[#8B7B6B]">데이터 없음</div>;

    return (
      <div className="flex gap-4">
        <div className="w-1/2">
          <ResponsiveContainer width="100%" height={350}>
            <PieChart>
              <Pie
                data={data}
                dataKey="size_mb"
                nameKey="extension"
                cx="50%"
                cy="50%"
                outerRadius={120}
                innerRadius={60}
                label={(props: any) => `${props.name} (${((props.percent || 0) * 100).toFixed(0)}%)`}
                labelLine={false}
              >
                {data.map((_: any, index: number) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => `${value} MB`} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="w-1/2 overflow-y-auto max-h-[350px]">
          <table className="w-full text-sm text-[#2D2D2D]">
            <thead className="sticky top-0 bg-[#F5F1EB]">
              <tr>
                <th className="text-left p-2 font-semibold text-[#1A1A1A]">확장자</th>
                <th className="text-right p-2 font-semibold text-[#1A1A1A]">파일 수</th>
                <th className="text-right p-2 font-semibold text-[#1A1A1A]">용량</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item: any, idx: number) => (
                <tr key={idx} className="border-t border-[#E5E0D8]">
                  <td className="p-2 flex items-center gap-2 font-medium">
                    <div className="w-3 h-3 rounded" style={{ backgroundColor: COLORS[idx % COLORS.length] }} />
                    {item.extension}
                  </td>
                  <td className="text-right p-2">{item.count.toLocaleString()}</td>
                  <td className="text-right p-2">{item.size_mb} MB</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // 폴더 맵 렌더링
  const renderFolders = () => {
    if (!data || data.length === 0 || !data[0]?.file_count) return <div className="text-center text-[#8B7B6B]">데이터 없음</div>;

    return (
      <div className="overflow-y-auto max-h-[400px]">
        <table className="w-full text-sm text-[#2D2D2D]">
          <thead className="sticky top-0 bg-[#F5F1EB]">
            <tr>
              <th className="text-left p-2 font-semibold text-[#1A1A1A]">폴더</th>
              <th className="text-right p-2 font-semibold text-[#1A1A1A]">파일 수</th>
              <th className="text-right p-2 font-semibold text-[#1A1A1A]">용량</th>
              <th className="text-left p-2 font-semibold text-[#1A1A1A]">주석</th>
            </tr>
          </thead>
          <tbody>
            {data.map((item: any, idx: number) => (
              <tr key={idx} className="border-t border-[#E5E0D8] hover:bg-[#F0EDE7]">
                <td className="p-2 max-w-[300px] truncate font-medium" title={item.full_path}>
                  {item.path}
                </td>
                <td className="text-right p-2">{item.file_count.toLocaleString()}</td>
                <td className="text-right p-2">{item.size_mb} MB</td>
                <td className="p-2 text-[#4A4A4A] italic max-w-[200px] truncate">
                  {item.annotation || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // 산점도 렌더링
  const renderScatter = () => {
    if (!data || data.length === 0) return <div className="text-center text-[#8B7B6B]">데이터 없음</div>;

    // mtime을 숫자로 변환
    const scatterData = data.map((d: any) => ({
      ...d,
      mtimeNum: new Date(d.mtime).getTime()
    }));

    // 파일 클릭 핸들러
    const handleScatterClick = (data: any) => {
      if (data && data.payload) {
        setSelectedFile(data.payload);
      }
    };

    return (
      <div className="flex gap-4">
        <div className="flex-1">
          <ResponsiveContainer width="100%" height={400}>
            <ScatterChart margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E0D8" />
              <XAxis
                dataKey="mtimeNum"
                type="number"
                domain={['dataMin', 'dataMax']}
                tickFormatter={(val) => new Date(val).toLocaleDateString('ko-KR', { year: '2-digit', month: 'short' })}
                name="수정일"
                tick={{ fontSize: 10 }}
              />
              <YAxis dataKey="size_mb" name="크기 (MB)" tick={{ fontSize: 11 }} />
              <ZAxis dataKey="size_mb" range={[20, 400]} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ payload }) => {
                  if (!payload || !payload[0]) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-white p-2 border border-[#E5E0D8] rounded shadow-sm text-sm">
                      <div className="font-medium">{d.filename}</div>
                      <div className="text-[#8B7B6B]">{d.size_mb} MB</div>
                      <div className="text-[#8B7B6B]">{new Date(d.mtime).toLocaleDateString('ko-KR')}</div>
                    </div>
                  );
                }}
              />
              <Scatter
                data={scatterData}
                fill="#D4A574"
                fillOpacity={0.6}
                onClick={handleScatterClick}
                cursor="pointer"
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* 선택된 파일 정보 패널 */}
        {selectedFile && (
          <div className="w-72 bg-[#F5F1EB] rounded-lg p-4 flex flex-col">
            <div className="text-xs text-[#8B7B6B] mb-2">선택된 파일</div>
            <div className="text-lg font-bold text-[#2D2D2D] mb-4 break-all">
              {selectedFile.filename}
            </div>

            <div className="space-y-3 flex-1">
              <div>
                <div className="text-xs text-[#8B7B6B] mb-1">위치</div>
                <div className="text-sm font-semibold text-[#4A4A4A] break-all">
                  {selectedFile.path}
                </div>
              </div>

              <div>
                <div className="text-xs text-[#8B7B6B] mb-1">크기</div>
                <div className="text-sm font-semibold text-[#4A4A4A]">
                  {selectedFile.size_mb} MB
                </div>
              </div>

              <div>
                <div className="text-xs text-[#8B7B6B] mb-1">마지막 수정</div>
                <div className="text-sm font-semibold text-[#4A4A4A]">
                  {new Date(selectedFile.mtime).toLocaleString('ko-KR')}
                </div>
              </div>

              {selectedFile.extension && (
                <div>
                  <div className="text-xs text-[#8B7B6B] mb-1">확장자</div>
                  <div className="text-sm font-semibold text-[#4A4A4A]">
                    .{selectedFile.extension}
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={() => openInFinder(selectedFile.path)}
              className="mt-4 w-full py-2 bg-[#D4A574] text-white rounded-md hover:bg-[#C49464] transition-colors font-medium"
            >
              Finder에서 열기
            </button>

            <button
              onClick={() => setSelectedFile(null)}
              className="mt-2 w-full py-1.5 text-[#8B7B6B] text-sm hover:text-[#6B5B4F]"
            >
              닫기
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8]">
      <div className="flex-1 flex overflow-hidden">
        {/* 사이드바 - 볼륨 목록 */}
        <div className="w-56 bg-[#F5F1EB] border-r border-[#E5E0D8] overflow-y-auto p-3">
          <div className="text-xs font-semibold text-[#8B7B6B] mb-2 px-2">스캔된 저장소</div>

          {/* 볼륨 목록 */}
          {volumes.length === 0 ? (
            <div className="text-xs text-[#8B7B6B] px-2 py-4 text-center">
              스캔된 저장소가 없습니다
            </div>
          ) : (
            volumes.map((volume) => (
              <div
                key={volume.root_path}
                className={`group w-full flex items-center px-2 py-2 rounded-md text-sm mb-1 transition-colors ${
                  selectedPath === volume.root_path
                    ? 'bg-[#D4A574] text-white'
                    : 'text-[#4A4A4A] hover:bg-[#E8E4DC]'
                }`}
              >
                <button
                  onClick={() => handleVolumeSelect(volume)}
                  className="flex-1 flex items-center text-left min-w-0"
                >
                  <HardDrive className="w-4 h-4 mr-2 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="truncate font-medium">{volume.name}</div>
                    <div className={`text-xs truncate ${selectedPath === volume.root_path ? 'text-white/80' : 'text-[#8B7B6B]'}`}>
                      {volume.file_count.toLocaleString()} 파일 · {volume.total_size_mb} MB
                    </div>
                  </div>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteScan(volume.id);
                  }}
                  className={`ml-1 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity ${
                    selectedPath === volume.root_path
                      ? 'hover:bg-white/20'
                      : 'hover:bg-red-100'
                  }`}
                  title="스캔 삭제"
                >
                  <Trash2 className={`w-3.5 h-3.5 ${
                    selectedPath === volume.root_path ? 'text-white' : 'text-red-500'
                  }`} />
                </button>
              </div>
            ))
          )}

          {/* 새 스캔 */}
          <div className="mt-4 pt-4 border-t border-[#E5E0D8]">
            <div className="text-xs font-semibold text-[#8B7B6B] mb-2 px-2">새 폴더 스캔</div>
            <div className="px-1">
              {/* 폴더 찾아보기 버튼 */}
              <button
                onClick={handleSelectFolder}
                disabled={isScanning}
                className="w-full flex items-center justify-center gap-1.5 px-2 py-2 bg-[#D4A574] text-white rounded text-xs hover:bg-[#C49464] disabled:opacity-50 disabled:cursor-not-allowed mb-3"
              >
                <FolderSearch className="w-4 h-4" />
                폴더 찾아보기
              </button>

              {/* 또는 직접 입력 */}
              <div className="text-xs text-[#A0A0A0] text-center mb-2">또는 직접 입력</div>
              <input
                type="text"
                value={newScanPath}
                onChange={(e) => setNewScanPath(e.target.value)}
                placeholder="/Volumes/... 또는 ~/..."
                className="w-full px-2 py-1.5 text-xs rounded border border-[#E5E0D8] bg-white text-[#4A4A4A] placeholder-[#A0A0A0] mb-2"
              />
              <button
                onClick={() => runScan(newScanPath)}
                disabled={!newScanPath || isScanning}
                className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 bg-[#6B5B4F] text-white rounded text-xs hover:bg-[#5A4A3F] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <FolderOpen className="w-3.5 h-3.5" />
                스캔 시작
              </button>
            </div>
          </div>
        </div>

        {/* 메인 콘텐츠 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 스캔 중 */}
          {isScanning && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <RefreshCw className="w-12 h-12 text-[#D4A574] mx-auto mb-4 animate-spin" />
                <h3 className="text-lg font-medium text-[#4A4A4A]">스캔 중...</h3>
                <p className="text-sm text-[#8B7B6B]">잠시만 기다려주세요</p>
              </div>
            </div>
          )}

          {/* 스캔 필요 화면 */}
          {!scanExists && !isScanning && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Sparkles className="w-12 h-12 text-[#D4A574] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[#4A4A4A] mb-2">분석할 폴더를 선택하세요</h3>
                <p className="text-sm text-[#8B7B6B] mb-4">
                  왼쪽에서 스캔된 저장소를 선택하거나<br/>
                  새 폴더 경로를 입력해 스캔을 시작하세요
                </p>
              </div>
            </div>
          )}

          {/* 분석 화면 */}
          {scanExists && !isScanning && (
            <>
              {/* 헤더 + 탭 버튼 */}
              <div className="flex items-center gap-2 p-3 bg-[#F5F1EB] border-b border-[#E5E0D8]">
                <ViewModeButton mode="treemap" icon={LayoutGrid} label="트리맵" />
                <ViewModeButton mode="timeline" icon={Clock} label="타임라인" />
                <ViewModeButton mode="extensions" icon={FileType} label="확장자" />
                <ViewModeButton mode="folders" icon={FolderTree} label="폴더" />
                <ViewModeButton mode="scatter" icon={Sparkles} label="산점도" />
                <div className="flex-1" />
                {scanInfo && (
                  <span className="text-xs text-[#8B7B6B]">
                    {scanInfo.file_count?.toLocaleString()} 파일 · {scanInfo.total_size_mb} MB
                  </span>
                )}
                <button
                  onClick={() => runScan()}
                  disabled={isScanning}
                  className="p-1.5 rounded hover:bg-[#E8E4DC] disabled:opacity-50"
                  title="다시 스캔"
                >
                  <RefreshCw className={`w-4 h-4 text-[#6B5B4F] ${isScanning ? 'animate-spin' : ''}`} />
                </button>
              </div>

              {/* 차트 영역 */}
              <div className="flex-1 p-4 overflow-auto">
                {isLoading ? (
                  <div className="flex items-center justify-center h-full">
                    <RefreshCw className="w-8 h-8 text-[#D4A574] animate-spin" />
                  </div>
                ) : error ? (
                  <div className="flex items-center justify-center h-full text-red-500">
                    {error}
                  </div>
                ) : (
                  <>
                    {viewMode === 'treemap' && renderTreemap()}
                    {viewMode === 'timeline' && renderTimeline()}
                    {viewMode === 'extensions' && renderExtensions()}
                    {viewMode === 'folders' && renderFolders()}
                    {viewMode === 'scatter' && renderScatter()}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
