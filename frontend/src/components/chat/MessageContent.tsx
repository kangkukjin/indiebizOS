/**
 * 메시지 콘텐츠 렌더링 (이미지, 지도, 도구 결과, 마크다운)
 */
import { FileText, CheckCircle2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { parseImagePaths, parseMapData } from './chatUtils';
import type { ToolActivity } from './types';
import { RouteMap } from '../RouteMap';
import { LocationMap } from '../LocationMap';

interface MessageContentProps {
  content: string;
  role: 'user' | 'assistant';
  images?: string[];
  textFiles?: { name: string; content: string }[];
  toolActivities?: ToolActivity[];
  variant?: 'warm' | 'neutral';
}

export function MessageContent({ content, role, images, textFiles, toolActivities, variant = 'warm' }: MessageContentProps) {
  const isUser = role === 'user';

  // AI 응답에서 이미지 경로 및 지도 데이터 파싱
  const parsedContent = !isUser ? parseImagePaths(content) : { text: content, images: [] };
  const parsedMaps = !isUser ? parseMapData(parsedContent.text) : { text: parsedContent.text, routeMaps: [], locationMaps: [] };
  const finalText = !isUser ? parsedMaps.text : content;

  const userBgClass = variant === 'warm' ? 'bg-blue-400/30' : 'bg-amber-400/30';
  const toolBorderClass = variant === 'warm' ? 'border-[#C5BFB5]' : 'border-gray-200';
  const toolHeaderBg = variant === 'warm' ? 'bg-[#E5DFD5]/50 border-b border-[#D5CFC5]' : 'bg-gray-50 border-b border-gray-200';
  const toolNameColor = variant === 'warm' ? 'text-[#4A4035]' : 'text-gray-700';
  const imgBorder = variant === 'warm' ? 'border-[#E5DFD5]' : 'border-gray-200';

  return (
    <>
      {/* 사용자 첨부 이미지 표시 */}
      {images && images.filter(img => img && img.trim() !== '').length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {images.filter(img => img && img.trim() !== '').map((img, index) => (
            <img
              key={index}
              src={img}
              alt={`첨부 이미지 ${index + 1}`}
              className="max-w-[200px] max-h-[200px] rounded-lg object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          ))}
        </div>
      )}

      {/* 사용자 첨부 텍스트 파일 표시 */}
      {textFiles && textFiles.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {textFiles.map((tf, index) => (
            <div key={index} className={`flex items-center gap-2 px-2 py-1 rounded ${isUser ? userBgClass : (variant === 'warm' ? 'bg-[#D5CFC5]' : 'bg-gray-200')}`}>
              <FileText size={14} />
              <span className="text-xs font-medium">{tf.name}</span>
            </div>
          ))}
        </div>
      )}

      {/* 저장된 도구 결과에서 이미지 표시 */}
      {!isUser && toolActivities && toolActivities.length > 0 && (
        <div className="mb-2 space-y-2">
          {toolActivities.map((tool, idx) => {
            const parsed = tool.result ? parseImagePaths(tool.result) : { text: '', images: [] };
            if (parsed.images.length === 0) return null;
            return (
              <div key={idx} className={`text-xs border ${toolBorderClass} rounded-lg overflow-hidden bg-white/60`}>
                <div className={`flex items-center gap-2 px-3 py-1.5 ${toolHeaderBg}`}>
                  <CheckCircle2 size={12} className="text-green-500 shrink-0" />
                  <span className={`font-medium ${toolNameColor}`}>{tool.name}</span>
                </div>
                <div className="p-2 flex flex-wrap gap-2">
                  {parsed.images.map((imgPath, imgIdx) => (
                    <img
                      key={imgIdx}
                      src={`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`}
                      alt={`결과 이미지 ${imgIdx + 1}`}
                      className={`max-w-full max-h-60 rounded border ${imgBorder} cursor-pointer hover:opacity-90 transition-opacity`}
                      onClick={() => window.electron?.openExternal(`file://${imgPath}`)}
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* AI 응답 내 이미지 표시 */}
      {!isUser && parsedContent.images.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {parsedContent.images.map((imgPath, index) => (
            <img
              key={index}
              src={`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`}
              alt={`생성된 이미지 ${index + 1}`}
              className="max-w-full max-h-[300px] rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity"
              onClick={() => window.electron?.openExternal(`file://${imgPath}`)}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              title="클릭하여 원본 보기"
            />
          ))}
        </div>
      )}

      {/* 경로 지도 표시 */}
      {!isUser && parsedMaps.routeMaps.length > 0 && (
        <div className="mb-2 space-y-2">
          {parsedMaps.routeMaps.map((mapData, index) => (
            <RouteMap key={`route-${index}`} data={mapData} />
          ))}
        </div>
      )}

      {/* 위치 지도 표시 */}
      {!isUser && parsedMaps.locationMaps.length > 0 && (
        <div className="mb-2 space-y-2">
          {parsedMaps.locationMaps.map((mapData, index) => (
            <LocationMap key={`location-${index}`} data={mapData} />
          ))}
        </div>
      )}

      {/* 텍스트 내용 */}
      {finalText && (
        <div className={variant === 'warm' ? 'chat-markdown' : 'prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2'}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => (
                <a
                  href={href}
                  onClick={(e) => {
                    e.preventDefault();
                    if (href) {
                      window.electron?.openExternal(href);
                    }
                  }}
                  className="text-blue-500 hover:underline cursor-pointer"
                >
                  {children}
                </a>
              ),
            }}
          >
            {finalText}
          </ReactMarkdown>
        </div>
      )}
    </>
  );
}
