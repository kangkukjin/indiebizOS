/**
 * 채팅 공통 유틸리티 함수
 */
import type { RouteMapData } from '../RouteMap';
import type { LocationMapData } from '../LocationMap';

// 텍스트 파일 확장자 목록
export const TEXT_EXTENSIONS = [
  '.txt', '.md', '.json', '.yaml', '.yml', '.xml', '.csv', '.log',
  '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.sql',
  '.sh', '.env', '.ini', '.conf', '.toml'
];

// 파일을 base64로 변환
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
  });
}

// 텍스트 파일인지 확인
export function isTextFile(file: File): boolean {
  const fileName = file.name.toLowerCase();
  return TEXT_EXTENSIONS.some(ext => fileName.endsWith(ext)) ||
    file.type.startsWith('text/') ||
    file.type === 'application/json' ||
    file.type === 'application/xml';
}

// 텍스트 파일 읽기
export function readTextFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsText(file, 'UTF-8');
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
  });
}

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

// 지도 데이터 패턴 감지 및 파싱 (route_map, location_map 모두 지원)
export function parseMapData(content: string): { text: string; routeMaps: RouteMapData[]; locationMaps: LocationMapData[] } {
  const routeMaps: RouteMapData[] = [];
  const locationMaps: LocationMapData[] = [];
  let text = content;

  // [MAP:{...}] 패턴 찾기 - JSON 내부의 ]를 피하기 위해 수동 파싱
  const mapStart = '[MAP:';
  let startIdx = text.indexOf(mapStart);

  while (startIdx !== -1) {
    const jsonStart = startIdx + mapStart.length;

    // JSON 끝 찾기: 중괄호 카운팅
    let braceCount = 0;
    let jsonEnd = -1;
    let inString = false;
    let escaped = false;

    for (let i = jsonStart; i < text.length; i++) {
      const char = text[i];

      if (escaped) {
        escaped = false;
        continue;
      }

      if (char === '\\' && inString) {
        escaped = true;
        continue;
      }

      if (char === '"') {
        inString = !inString;
        continue;
      }

      if (inString) continue;

      if (char === '{') {
        braceCount++;
      } else if (char === '}') {
        braceCount--;
        if (braceCount === 0) {
          if (text[i + 1] === ']') {
            jsonEnd = i + 2;
            break;
          }
        }
      }
    }

    if (jsonEnd !== -1) {
      const jsonStr = text.substring(jsonStart, jsonEnd - 1);
      try {
        const mapData = JSON.parse(jsonStr);
        if (mapData.type === 'route_map') {
          routeMaps.push(mapData as RouteMapData);
        } else if (mapData.type === 'location_map') {
          locationMaps.push(mapData as LocationMapData);
        }
      } catch {
        // JSON 파싱 실패 시 무시
      }

      text = text.substring(0, startIdx) + text.substring(jsonEnd);
      startIdx = text.indexOf(mapStart);
    } else {
      break;
    }
  }

  return { text: text.trim(), routeMaps, locationMaps };
}
