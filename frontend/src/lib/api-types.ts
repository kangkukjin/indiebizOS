/**
 * api-types.ts - API 클라이언트 공유 타입
 * mixin 파일들이 참조하는 코어 인터페이스
 */

export interface APIClientCore {
  request<T>(endpoint: string, options?: RequestInit): Promise<T>;
}
