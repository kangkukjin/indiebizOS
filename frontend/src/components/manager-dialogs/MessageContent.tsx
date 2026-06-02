/**
 * MessageContent - 메시지 내용 컴포넌트 (이미지 표시 포함)
 */

// 이미지 경로 파싱 함수
export function parseImagePaths(content: string): { text: string; images: string[] } {
  const images: string[] = [];

  // 패턴 1: [IMAGE:/path/to/file.jpg] 형식
  const imageTagPattern = /\[IMAGE:(\/[^\]]+\.(jpg|jpeg|png|gif|webp))\]/gi;

  // 패턴 2: 일반 파일 경로 (outputs, captures 폴더 내 이미지)
  const filePathPattern = /(\/[^\s]+\/(outputs|captures)\/[^\s]+\.(jpg|jpeg|png|gif|webp))/gi;

  // 패턴 3: 마크다운 이미지 ![alt](path)
  const markdownImagePattern = /!\[[^\]]*\]\((\/[^)]+\.(jpg|jpeg|png|gif|webp))\)/gi;

  let text = content;

  // [IMAGE:path] 패턴 추출 및 제거
  let match;
  while ((match = imageTagPattern.exec(content)) !== null) {
    images.push(match[1]);
  }
  text = text.replace(imageTagPattern, '');

  // 마크다운 이미지 패턴 추출 및 제거
  const mdMatches = [...content.matchAll(/!\[[^\]]*\]\((\/[^)]+\.(jpg|jpeg|png|gif|webp))\)/gi)];
  for (const m of mdMatches) {
    if (!images.includes(m[1])) {
      images.push(m[1]);
    }
  }
  text = text.replace(markdownImagePattern, '');

  // 일반 파일 경로 패턴 추출
  const pathMatches = text.match(filePathPattern);
  if (pathMatches) {
    for (const path of pathMatches) {
      if (!images.includes(path)) {
        images.push(path);
      }
    }
  }

  return { text: text.trim(), images };
}

// 메시지 내용 컴포넌트
export function MessageContent({ content }: { content: string }) {
  const parsed = parseImagePaths(content);

  return (
    <div>
      {/* 이미지 표시 */}
      {parsed.images.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {parsed.images.map((imgPath, index) => (
            <img
              key={index}
              src={`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`}
              alt={`이미지 ${index + 1}`}
              className="max-w-[200px] max-h-[200px] rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity"
              onClick={() => window.electron?.openExternal(`file://${imgPath}`)}
              title="클릭하여 원본 보기"
            />
          ))}
        </div>
      )}
      {/* 텍스트 표시 */}
      {parsed.text && (
        <p className="text-sm whitespace-pre-wrap break-words">{parsed.text}</p>
      )}
    </div>
  );
}
