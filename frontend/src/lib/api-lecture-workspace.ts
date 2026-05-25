/**
 * api-lecture-workspace.ts - 강의 만들기 워크스페이스 API
 * APIClient mixin: 강의 CRUD, 데크 조작, 재료 관리, 누적 메모.
 */

import type { APIClientCore } from './api-types';

// ===== 타입 =====

export interface LectureSummary {
  lecture_id: string;
  title: string;
  audience: string;
  slide_count: number;
  updated_at: string;
  error?: string;
}

export interface SlideMeta {
  id: string;
  title: string;
  layout: string;
  spec_file: string;
  png_file: string;
  created_at: string;
  updated_at: string;
}

export interface CumulativeMemo {
  tone_preferred: string[];
  tone_rejected: string[];
  metaphors_adopted: string[];
  decisions: string[];
}

export interface MaterialEntry {
  file: string;
  type: string;
  added_at: string;
  source?: string;
}

export interface Deck {
  version: number;
  lecture_id: string;
  title: string;
  audience: string;
  thesis: string;
  duration_minutes: number;
  design_system: string;
  created_at: string;
  updated_at: string;
  slide_order: string[];
  slides: Record<string, SlideMeta>;
  cumulative_memo: CumulativeMemo;
  materials: MaterialEntry[];
}

export interface LectureLoadResponse {
  deck: Deck;
  slides_dir: string;
  materials_dir: string;
  lecture_dir: string;
}

export interface LectureCreateInput {
  title: string;
  audience?: string;
  thesis?: string;
  duration_minutes?: number;
  design_system?: string;
}

export interface DeckMetaUpdate {
  title?: string;
  audience?: string;
  thesis?: string;
  duration_minutes?: number;
  design_system?: string;
}

/** 디자인 시스템 6종 — media_producer/shadcn_slides.py와 일치 */
export const DESIGN_SYSTEM_OPTIONS: Array<{
  value: string;
  label: string;
  description: string;
}> = [
  { value: 'vintage_book',    label: '빈티지북',         description: '베이지 종이 + 청·적갈 잉크 · 책 강의·인문' },
  { value: 'academic_paper',  label: '학술 논문',        description: '미색 + 진남 + 진홍 강조 · 연구·논문' },
  { value: 'sf_blueprint',    label: 'SF 블루프린트',    description: '다크 네이비 + 시안 HUD · NotebookLM 양식' },
  { value: 'tech_minimal',    label: '테크 미니멀',      description: '다크 + 시안 네온 · 개발자·테크' },
  { value: 'magazine_modern', label: '잡지 모던',        description: '흰·검·적색 · 편집·홍보' },
  { value: 'default',         label: '기본 (없음)',      description: '디자인 시스템 없음 — 색 테마만' },
];

export interface SlideCreateResponse {
  success: boolean;
  slide_id: string;
  slide: Record<string, unknown>;
  png_file: string;
  spec_file: string;
  reasoning?: string;
  speaker_note?: string;
  memo_signals?: Partial<CumulativeMemo>;
  mode: 'create' | 'edit';
}

export function applyLectureWorkspaceMethods<T extends APIClientCore>(client: T) {
  return Object.assign(client, {

    // ============ 강의 CRUD ============

    async listLectures() {
      return client.request<{ lectures: LectureSummary[]; lectures_root: string }>('/lectures');
    },

    async createLecture(data: LectureCreateInput) {
      return client.request<{ lecture_id: string; deck: Deck; lecture_dir: string }>('/lectures', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    async loadLecture(lectureId: string) {
      return client.request<LectureLoadResponse>(`/lectures/${encodeURIComponent(lectureId)}`);
    },

    async deleteLecture(lectureId: string) {
      return client.request<{ deleted: string; path: string }>(
        `/lectures/${encodeURIComponent(lectureId)}`,
        { method: 'DELETE' }
      );
    },

    async updateDeckMeta(lectureId: string, patch: DeckMetaUpdate) {
      return client.request<Deck>(
        `/lectures/${encodeURIComponent(lectureId)}`,
        { method: 'PATCH', body: JSON.stringify(patch) }
      );
    },

    // ============ 데크 조작 ============

    async reorderDeck(lectureId: string, order: string[]) {
      return client.request<{ lecture_id: string; slide_order: string[] }>(
        `/lectures/${encodeURIComponent(lectureId)}/reorder`,
        { method: 'POST', body: JSON.stringify({ order }) }
      );
    },

    async deleteSlide(lectureId: string, slideId: string) {
      return client.request<{ deleted: string; remaining: string[] }>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}`,
        { method: 'DELETE' }
      );
    },

    // ============ AI 슬라이드 생성/편집 ============

    async createSlide(
      lectureId: string,
      instruction: string,
      insertAt?: number,
      layout?: string,
    ) {
      const body: Record<string, unknown> = { instruction };
      if (insertAt !== undefined) body.insert_at = insertAt;
      if (layout) body.layout = layout;
      return client.request<SlideCreateResponse>(
        `/lectures/${encodeURIComponent(lectureId)}/slides`,
        { method: 'POST', body: JSON.stringify(body) }
      );
    },

    /**
     * 슬라이드의 현재 spec을 가져옴 (직접 편집 모달용).
     */
    async getSlideSpec(lectureId: string, slideId: string) {
      const url = `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/spec`;
      const response = await fetch(url);
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err));
      }
      return response.json() as Promise<Record<string, unknown>>;
    },

    /**
     * 슬라이드 spec 필드를 직접 patch + PNG 재렌더. AI 호출 없음.
     * PowerPoint식 직접 편집 — patch에 없는 필드는 그대로 보존.
     */
    async patchSlideSpec(
      lectureId: string,
      slideId: string,
      patch: Record<string, unknown>,
    ) {
      return client.request<{
        success: boolean;
        slide_id: string;
        mode: 'patch';
        spec: Record<string, unknown>;
        png_file: string;
        patched_keys: string[];
        design_system: string;
      }>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/patch`,
        { method: 'POST', body: JSON.stringify({ patch }) }
      );
    },

    /**
     * 슬라이드 spec 변경 없이 PNG만 재렌더.
     * design_system 변경 후 같은 내용으로 새 톤 적용 시 사용. AI 호출 없음.
     */
    async rerenderSlide(lectureId: string, slideId: string) {
      return client.request<{
        success: boolean;
        slide_id: string;
        mode: 'rerender';
        design_system: string;
        png_file: string;
        title: string;
      }>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/rerender`,
        { method: 'POST' }
      );
    },

    async editSlide(
      lectureId: string,
      slideId: string,
      instruction: string,
      layout?: string,
    ) {
      const body: Record<string, unknown> = { instruction };
      if (layout) body.layout = layout;
      return client.request<SlideCreateResponse>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/edit`,
        { method: 'POST', body: JSON.stringify(body) }
      );
    },

    // ============ 내보내기 ============

    async exportDeck(
      lectureId: string,
      format: 'pdf' | 'pptx' | 'pptx_image' | 'pptx_editable',
    ) {
      // 파일 생성 후 메타 반환
      return client.request<{
        success: boolean;
        format: 'pdf' | 'pptx';
        mode?: 'image' | 'editable';
        path: string;
        slide_count: number;
        skipped?: number;
        editable_count?: number;
        fallback_image_count?: number;
        filename: string;
      }>(
        `/lectures/${encodeURIComponent(lectureId)}/export?format=${format}`,
        { method: 'POST' }
      );
    },

    /** 내보낸 파일의 다운로드 URL (브라우저에서 a[href]로 사용). */
    exportFileUrl(lectureId: string, filename: string): string {
      return `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/export/file?filename=${encodeURIComponent(filename)}`;
    },

    /** 슬라이드 PNG의 HTTP URL — <img src>에 직접 사용. file://보다 안정. */
    slidePngUrl(lectureId: string, slideId: string): string {
      return `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/png`;
    },

    /** 재료 파일의 HTTP URL. */
    materialFileUrl(lectureId: string, filename: string): string {
      return `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/materials/${encodeURIComponent(filename)}/file`;
    },

    // ============ 재료 관리 ============

    async addMaterialText(lectureId: string, text: string, filename: string) {
      return client.request<MaterialEntry>(
        `/lectures/${encodeURIComponent(lectureId)}/materials/text`,
        { method: 'POST', body: JSON.stringify({ text, filename }) }
      );
    },

    async addMaterialPath(lectureId: string, filePath: string) {
      return client.request<MaterialEntry>(
        `/lectures/${encodeURIComponent(lectureId)}/materials/path`,
        { method: 'POST', body: JSON.stringify({ file_path: filePath }) }
      );
    },

    async uploadMaterial(lectureId: string, file: File): Promise<MaterialEntry> {
      // multipart 업로드는 request<T> 표준 헬퍼를 쓰지 않고 직접 fetch
      const url = `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/materials/upload`;
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch(url, { method: 'POST', body: formData });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
      }
      return response.json();
    },

    async removeMaterial(lectureId: string, filename: string) {
      return client.request<{ removed: string; deleted_from_deck: number }>(
        `/lectures/${encodeURIComponent(lectureId)}/materials/${encodeURIComponent(filename)}`,
        { method: 'DELETE' }
      );
    },

    // ============ 누적 메모 ============

    async patchMemo(lectureId: string, patch: Partial<CumulativeMemo>) {
      return client.request<CumulativeMemo>(
        `/lectures/${encodeURIComponent(lectureId)}/memo`,
        { method: 'PATCH', body: JSON.stringify(patch) }
      );
    },

    // ============ 워크스페이스 창 열기 (다른 창에서 호출용) ============

    async openLectureWorkspace(lectureId?: string) {
      return client.request<{ success: boolean; lecture_id: string | null }>(
        `/lectures/open-workspace`,
        { method: 'POST', body: JSON.stringify({ lecture_id: lectureId || null }) }
      );
    },
  });
}
