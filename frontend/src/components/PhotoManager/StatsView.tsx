/**
 * StatsView - 통계 뷰 컴포넌트
 */

interface StatsViewProps {
  data: any;
}

export function StatsView({ data }: StatsViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-[#9B8B7A]">
        통계 데이터를 불러오는 중...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 요약 */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{(data.photo_count || 0).toLocaleString()}</div>
          <div className="text-sm text-[#9B8B7A]">사진</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{(data.video_count || 0).toLocaleString()}</div>
          <div className="text-sm text-[#9B8B7A]">동영상</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{(data.total_size_mb || 0).toLocaleString()} MB</div>
          <div className="text-sm text-[#9B8B7A]">총 용량</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-sm font-medium text-[#5C5347]">{data.last_scan ? new Date(data.last_scan).toLocaleDateString() : '-'}</div>
          <div className="text-sm text-[#9B8B7A]">마지막 스캔</div>
        </div>
      </div>

      {/* 확장자별 통계 */}
      {data.extensions && data.extensions.length > 0 && (
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <h3 className="text-sm font-semibold text-[#5C5347] mb-3">확장자별 분포</h3>
          <div className="space-y-2">
            {data.extensions.map((ext: any, idx: number) => (
              <div key={idx} className="flex items-center gap-3">
                <span className="w-16 text-sm font-mono text-[#6B5D4D]">.{ext.extension}</span>
                <div className="flex-1 h-4 bg-[#F0EDE8] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[#8B7355] rounded-full"
                    style={{ width: `${Math.min(100, (ext.count / (data.photo_count + data.video_count)) * 100)}%` }}
                  />
                </div>
                <span className="w-16 text-right text-sm text-[#9B8B7A]">{ext.count}개</span>
                <span className="w-20 text-right text-sm text-[#9B8B7A]">{ext.size_mb} MB</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 카메라별 통계 */}
      {data.cameras && data.cameras.length > 0 && (
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <h3 className="text-sm font-semibold text-[#5C5347] mb-3">카메라별 분포</h3>
          <div className="grid grid-cols-2 gap-2">
            {data.cameras.map((cam: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-2 bg-[#FAF9F7] rounded-lg">
                <span className="text-sm text-[#5C5347]">{cam.camera}</span>
                <span className="text-sm text-[#9B8B7A]">{cam.count}개</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
