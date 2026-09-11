/** 채팅·관리자 메시지의 이미지 표기 해석. 일반 계기의 첨부 경로 파서는 별도 계약이다. */
// 이미지 경로 패턴 감지 및 변환
export function parseImagePaths(content: string): { text: string; images: string[] } {
  const images: string[] = [];

  // 패턴 1: [IMAGE:/path/to/file.jpg] 형식
  const imageTagPattern = /\[IMAGE:(\/[^\]]+\.(jpg|jpeg|png|gif|webp))\]/gi;

  // 패턴 2: 일반 파일 경로 (outputs, captures, charts 폴더 내 이미지)
  const filePathPattern = /`?(\/[^\s`'"\n]+\/(outputs|captures|charts)\/[^\s`'"\n]+\.(jpg|jpeg|png|gif|webp))`?/gi;

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

  // 파일 경로 패턴 추출
  const pathMatches = [...text.matchAll(filePathPattern)];
  for (const m of pathMatches) {
    if (!images.includes(m[1])) {
      images.push(m[1]);
    }
  }
  text = text.replace(filePathPattern, '');

  return { text: text.trim(), images: images.filter(img => img && img.trim() !== '') };
}

