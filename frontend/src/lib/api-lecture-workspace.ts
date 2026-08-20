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
  speaker_note?: string;  // 강의 노트(말할 내용) — 선택 시 좌측 하단에 표시/편집
  text_overlays?: TextOverlay[];  // '글자 얹기' — 원본(base.png) 위 합성 문구 목록
}

/** '글자 얹기' 한 건 — x/y(% 좌상단·자유 좌표)가 있으면 position(9방)보다 우선. */
export interface TextOverlay {
  text: string;
  position?: string;   // 9방: top-left … bottom-right
  x?: number;          // 자유 좌표 — 슬라이드 폭의 % (박스 좌상단)
  y?: number;          // 자유 좌표 — 슬라이드 높이의 %
  size?: string;       // small/medium/large
  size_vw?: number;    // 자유 크기 — 슬라이드 폭의 %
  font?: string;       // sans(기본)/serif/gowun/jua/black/pen/brush
  color?: string;      // white/black/#hex
  chip?: boolean;
  shadow?: boolean;    // 글자 그림자 (기본 없음)
  weight?: string;     // 'normal'만 저장 — 기본은 semi-bold(600)
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
  lecture_memo?: string;  // 사용자 메모(왼쪽 항상 표시) — AI 슬라이드 생성에 미사용
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
  lecture_memo?: string;
}

/** 디자인 옵션 — 3그룹:
 *  css = slide_shadcn(CSS, 빠름·무료) / image = slide_image(개념 일러스트, 느림·비용) / auto = AI 자율
 *  값은 백엔드 shadcn_slides.DESIGN_SYSTEMS · slide_styles.STYLES · _IMAGE_DESIGNS와 일치 */
/**
 * 강의 창의 선택은 두 축뿐이다 — **톤**(design tone)과 **렌더 방식**(render).
 * 구조(layout/composition)는 AI가 내용을 보고 고른다.
 *
 * ★목록을 여기 하드코딩하지 않는다. `GET /lectures/design-systems` 가 진실 소스
 *   (media_producer/slide_tones.py)를 그대로 내려준다 — 예전엔 프론트엔드 상수가
 *   백엔드보다 오래 살아남아, 은퇴한 톤을 계속 보여주고 고르면 생성이 실패했다.
 */
export type RenderMode = 'native' | 'image' | 'html';

export interface ToneOption {
  key: string;
  ko: string;
  desc: string;
  renders: RenderMode[];   // 이 톤이 지원하는 렌더 방식
}

export interface RenderOption {
  key: RenderMode;
  ko: string;
  desc: string;
}

export interface DesignMatrix {
  tones: ToneOption[];
  renders: RenderOption[];
  default_tone: string;
  default_render: RenderMode;
}

/** design_system 문자열 ↔ (톤, 렌더). 백엔드 slide_tones.py 와 같은 문법. */
export function buildDesignSystem(tone: string, render: RenderMode): string {
  return render === 'html' ? tone : `${render}_${tone}`;
}

export function parseDesignSystem(design: string): { tone: string; render: RenderMode } {
  const d = (design || '').trim();
  for (const render of ['native', 'image'] as const) {
    for (const sep of ['_', ':']) {
      if (d.startsWith(render + sep)) {
        return { tone: d.slice(render.length + sep.length) || 'vintage_book', render };
      }
    }
    if (d === render) return { tone: 'vintage_book', render };
  }
  return { tone: d || 'vintage_book', render: 'html' };
}

export interface SlideGenOptions {
  /** 이 한 장만 덱 기본과 다른 렌더 방식으로 (혼합 덱). */
  render?: RenderMode;
  /** HTML 구조 강제 — UI 에는 노출하지 않는다(프로그래매틱 전용). */
  layout?: string;
  /** 이미지 품질: 'pro'(고품질·비쌈) / 'fast'(저가·빠름). */
  imageQuality?: string;
  /** 채팅 첨부 — 이 이미지가 '들어간' 슬라이드를 조판. */
  image?: { base64: string; name: string };
}

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

    // ============ 선택지 매트릭스 (톤 × 렌더 방식) ============

    /** 드롭다운 두 개의 선택지. 진실 소스는 백엔드 톤 레지스트리 — 캐시하지 말 것. */
    async designMatrix() {
      return client.request<DesignMatrix>('/lectures/design-systems');
    },

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

    /** 슬라이드의 강의 노트(말할 내용) 저장. 빈 문자열이면 노트 제거. AI 호출 없음. */
    async setSlideNote(lectureId: string, slideId: string, note: string) {
      return client.request<{ slide_id: string; speaker_note: string }>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/note`,
        { method: 'PATCH', body: JSON.stringify({ note }) }
      );
    },

    async deleteSlide(lectureId: string, slideId: string) {
      return client.request<{ deleted: string; remaining: string[] }>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}`,
        { method: 'DELETE' }
      );
    },

    /** 슬라이드 복제 — 같은 내용으로 한 장 더(원본 바로 뒤). 새 슬라이드 메타 반환. */
    async duplicateSlide(lectureId: string, slideId: string) {
      return client.request<SlideMeta>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/duplicate`,
        { method: 'POST' }
      );
    },

    // ============ AI 슬라이드 생성/편집 ============

    async createSlide(
      lectureId: string,
      instruction: string,
      insertAt?: number,
      opts?: SlideGenOptions,
    ) {
      const body: Record<string, unknown> = { instruction };
      if (insertAt !== undefined) body.insert_at = insertAt;
      if (opts?.render) body.render = opts.render;
      if (opts?.layout) body.layout = opts.layout;
      if (opts?.imageQuality) body.image_quality = opts.imageQuality;
      if (opts?.image) { body.image_base64 = opts.image.base64; body.image_name = opts.image.name; }
      return client.request<SlideCreateResponse>(
        `/lectures/${encodeURIComponent(lectureId)}/slides`,
        { method: 'POST', body: JSON.stringify(body) }
      );
    },

    /**
     * 이미 만들어둔 이미지 여러 장을 슬라이드로 한 번에 추가 (AI 생성 없이).
     * 파일 순서대로 데크에 삽입. insertAt 지정 시 그 위치부터.
     */
    async uploadSlideImages(
      lectureId: string,
      files: File[],
      insertAt?: number,
    ): Promise<{ success: boolean; count: number; created: SlideMeta[]; skipped: string[] }> {
      const url = `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/slides/upload-images`;
      const formData = new FormData();
      for (const f of files) formData.append('files', f);
      if (insertAt !== undefined) formData.append('insert_at', String(insertAt));
      const response = await fetch(url, { method: 'POST', body: formData });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
      }
      return response.json();
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

    /**
     * 강의 자료를 읽어 슬라이드 초안(instruction) 목록을 만든다 (일괄 생성 1단계).
     * 반환된 목록을 호출자가 한 장씩 createSlide로 순차 생성한다.
     */
    async outlineLecture(lectureId: string, count?: number) {
      const body: Record<string, unknown> = {};
      if (count !== undefined) body.count = count;
      return client.request<{ success: boolean; slides: { instruction: string }[]; count: number }>(
        `/lectures/${encodeURIComponent(lectureId)}/outline`,
        { method: 'POST', body: JSON.stringify(body) }
      );
    },

    /**
     * 통짜 이미지/이미지 슬라이드 '부분 수정' — 다시 그리지 않고 현재 이미지를 편집.
     * 제목 한 줄 등만 바꿀 때. 구도·그림 보존(완전 픽셀 동일은 아님).
     */
    async imageEditSlide(
      lectureId: string,
      slideId: string,
      instruction: string,
      imageQuality?: string,
    ) {
      const body: Record<string, unknown> = { instruction };
      if (imageQuality) body.image_quality = imageQuality;
      return client.request<{
        success: boolean;
        slide_id: string;
        mode: 'image_edit';
        png_file: string;
        title: string;
      }>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/image-edit`,
        { method: 'POST', body: JSON.stringify(body) }
      );
    },

    /**
     * 결정론 '글자 얹기' — 이미지 모델 없이 현재 슬라이드 PNG 위에 문구만 합성.
     * 그림 픽셀 보존(원본 자동 보존), clear=true 는 얹은 글자 제거·원본 복원.
     */
    async textOverlaySlide(
      lectureId: string,
      slideId: string,
      opts: {
        text?: string;
        position?: string;
        x?: number;
        y?: number;
        size?: string;
        size_vw?: number;
        font?: string;
        color?: string;
        chip?: boolean;
        clear?: boolean;
        overlays?: TextOverlay[];  // 전체 교체 (배치 편집기 저장)
      },
    ) {
      return client.request<{
        success: boolean;
        slide_id: string;
        mode: 'text_overlay';
        overlays: number;
        text_overlays?: TextOverlay[];
        png_file: string;
        title?: string;
        message?: string;
      }>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/text-overlay`,
        { method: 'POST', body: JSON.stringify(opts) }
      );
    },

    async editSlide(
      lectureId: string,
      slideId: string,
      instruction: string,
      opts?: SlideGenOptions,
    ) {
      const body: Record<string, unknown> = { instruction };
      if (opts?.render) body.render = opts.render;
      if (opts?.layout) body.layout = opts.layout;
      if (opts?.imageQuality) body.image_quality = opts.imageQuality;
      if (opts?.image) { body.image_base64 = opts.image.base64; body.image_name = opts.image.name; }
      return client.request<SlideCreateResponse>(
        `/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/edit`,
        { method: 'POST', body: JSON.stringify(body) }
      );
    },

    // ============ 내보내기 ============

    async exportDeck(
      lectureId: string,
      format: 'pdf' | 'pptx' | 'pptx_image' | 'pptx_editable' | 'images',
    ) {
      // 파일 생성 후 메타 반환
      return client.request<{
        success: boolean;
        format: 'pdf' | 'pptx' | 'images';
        mode?: 'image' | 'editable';
        path: string;
        folder?: string; // images 전용 — ZIP 과 나란한 원본 폴더
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

    /** 저장된 실강 녹음 상태 — '동영상 렌더링'이 실녹음/TTS 어느 경로로 갈지의 근거. */
    async getNarrationRecording(lectureId: string): Promise<{
      exists: boolean; duration_sec?: number; created_at?: string; bytes?: number;
      marks?: { slide_id: string; t: number }[];
    }> {
      const url = `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/narration-recording`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`녹음 상태 조회 실패 (${r.status})`);
      return r.json();
    },

    /**
     * 저장된 녹음 오디오의 HTTP URL — '강의 플레이'의 <audio src>.
     * 파일 확장자는 브라우저가 준 mime 에 따라 달라지므로 경로를 여기서 짓지 않는다
     * (timeline.json 의 audio_file 이 정본이고 백엔드가 그걸 보고 고른다).
     * v = created_at 캐시버스터 — 다시 녹음하면 같은 URL 의 내용만 바뀌기 때문.
     */
    narrationAudioUrl(lectureId: string, v?: string): string {
      const base = `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/narration-recording/audio`;
      return v ? `${base}?v=${encodeURIComponent(v)}` : base;
    },

    /**
     * 실강 녹음(오디오 한 덩어리) + 슬라이드 전환 타임라인 저장.
     * ★기존 녹음은 통째로 대체된다 — 녹음 버튼을 다시 누르면 새로 찍는다는 뜻.
     */
    async saveNarrationRecording(
      lectureId: string,
      audio: Blob,
      timeline: { duration_sec: number; marks: { slide_id: string; t: number }[] },
    ): Promise<{ exists: boolean; duration_sec?: number; bytes?: number }> {
      const url = `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/narration-recording`;
      const fd = new FormData();
      // 확장자는 백엔드가 content-type 으로 정한다 — 이 파일명은 표식일 뿐.
      fd.append('audio', audio, 'recording.webm');
      fd.append('timeline', JSON.stringify(timeline));
      const r = await fetch(url, { method: 'POST', body: fd });
      if (!r.ok) {
        const e = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail));
      }
      return r.json();
    },

    /** 녹음 폐기 — 다음 렌더는 다시 스피커 노트 TTS 경로로 간다. */
    async deleteNarrationRecording(lectureId: string): Promise<void> {
      const url = `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/narration-recording`;
      const r = await fetch(url, { method: 'DELETE' });
      if (!r.ok) throw new Error(`녹음 삭제 실패 (${r.status})`);
    },

    /**
     * 동영상 렌더 시작. ★능력은 IBL 어휘가 갖고 있고 여기는 그걸 부르는 다리다
     * (custom_app_instrument.md 철칙0 — 렌더용 REST 를 새로 만들지 않는 이유).
     * 녹음이 있으면 렌더가 알아서 그 녹음+타임라인으로 씬 길이를 정한다.
     */
    async renderLectureVideo(lectureId: string): Promise<unknown> {
      const { iblExecuteApp } = await import('./instrument');
      return iblExecuteApp(`[self:deck]{op: "video", lecture_id: ${JSON.stringify(lectureId)}}`);
    },

    /** 렌더 진행 상태 — 상태 파일을 직접 긁지 말고 check:true 로 (video_workflow.md). */
    async lectureVideoStatus(lectureId: string): Promise<Record<string, unknown>> {
      const { iblExecuteApp } = await import('./instrument');
      const r = await iblExecuteApp(
        `[self:deck]{op: "video", lecture_id: ${JSON.stringify(lectureId)}, check: true}`);
      return (r ?? {}) as Record<string, unknown>;
    },

    /** 슬라이드 PNG의 HTTP URL — <img src>에 직접 사용. file://보다 안정. */
    slidePngUrl(lectureId: string, slideId: string): string {
      return `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/png`;
    },

    /** '글자 얹기' 이전 원본 PNG URL — 배치 편집기의 배경 (얹은 글자 없으면 현재 판). */
    slideBasePngUrl(lectureId: string, slideId: string): string {
      return `http://127.0.0.1:8765/lectures/${encodeURIComponent(lectureId)}/slides/${encodeURIComponent(slideId)}/png?base=true`;
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
