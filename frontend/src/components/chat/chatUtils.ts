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

// 문서 파일 확장자 목록 (.pages, .docx, .pdf)
export const DOCUMENT_EXTENSIONS = ['.pages', '.docx', '.pdf'];

// 문서 파일인지 확인
export function isDocumentFile(file: File): boolean {
  const fileName = file.name.toLowerCase();
  return DOCUMENT_EXTENSIONS.some(ext => fileName.endsWith(ext));
}

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

// 스트림 데이터 타입
export interface StreamData {
  url: string;
  name?: string;
  type?: string;  // "hls" 등
  source?: string;
  lat?: number;
  lng?: number;
  playable?: boolean;  // 백엔드가 HLS 재생가능 판정한 결과 (있으면 프론트가 재-스니핑 없이 신뢰)
}

// 스트림 데이터 패턴 감지 및 파싱
export function parseStreamData(content: string): { text: string; streams: StreamData[] } {
  const streams: StreamData[] = [];
  let text = content;

  // [STREAM:{...}] 패턴 찾기
  const streamStart = '[STREAM:';
  let startIdx = text.indexOf(streamStart);

  while (startIdx !== -1) {
    const jsonStart = startIdx + streamStart.length;
    let braceCount = 0;
    let jsonEnd = -1;
    let inString = false;
    let escaped = false;

    for (let i = jsonStart; i < text.length; i++) {
      const char = text[i];
      if (escaped) { escaped = false; continue; }
      if (char === '\\' && inString) { escaped = true; continue; }
      if (char === '"') { inString = !inString; continue; }
      if (inString) continue;
      if (char === '{') braceCount++;
      else if (char === '}') {
        braceCount--;
        if (braceCount === 0 && text[i + 1] === ']') {
          jsonEnd = i + 2;
          break;
        }
      }
    }

    if (jsonEnd !== -1) {
      const jsonStr = text.substring(jsonStart, jsonEnd - 1);
      try {
        const streamData = JSON.parse(jsonStr) as StreamData;
        if (streamData.url) {
          streams.push(streamData);
        }
      } catch { /* 파싱 실패 시 무시 */ }
      text = text.substring(0, startIdx) + text.substring(jsonEnd);
      startIdx = text.indexOf(streamStart);
    } else {
      break;
    }
  }

  return { text: text.trim(), streams };
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
