/**
 * api-ibl.ts - 수동 모드(IBL 컴파일러 프론트엔드) API
 * APIClient mixin: 자연어→IBL 번역, dry-run 검증, 실행, 액션 카탈로그.
 *
 * 모델은 선장이 아니라 컴파일러다 — translate는 번역만, 검수와 주권은 인간에게 남는다.
 */

import type { APIClientCore } from './api-types';

// ===== 타입 =====

export interface IblTranslateResult {
  intent: string;
  ibl_code: string;
  references: string;  // 번역의 근거가 된 과거 용례 (XML) — 리터러시 학습용
  raw: string;
}

export type IblSafety = 'read' | 'write' | 'unknown';

export interface IblValidateStep {
  node: string;
  action: string;
  params: Record<string, unknown>;
  kind: 'action' | 'block';
  effect: string;       // 사람이 읽는 효과 설명 (코드가 아닌 효과 레벨 검수)
  safety: IblSafety;    // 'read'=부작용 없음(되돌릴 필요 없음), 'write'=부작용, 'unknown'=미분류
  valid: boolean;
  error: string | null;
}

export interface IblValidateResult {
  valid: boolean;
  syntax_error: string | null;
  step_count?: number;
  has_side_effect?: boolean;  // 부작용 step이 있으면 실행 전 명시적 확인 필요
  steps: IblValidateStep[];
}

export interface IblCatalogAction {
  description: string;
  target_description: string;
  target_key: string;
  implementation: string;
  keywords: string[];
  group: string;
  ops?: { default?: string; values?: Record<string, string> } | null;
}

export interface IblCatalog {
  nodes: Record<string, { actions: Record<string, IblCatalogAction>; count: number }>;
  total: number;
}

// IBL 건강 점검 결과 — 정적(§1A)·fixture 통화(§1B)·골든 파이프(§1C)
export interface IblHealthEvent {
  node: string;            // __static__ | __ibl_health__
  action: string;          // ibl_consistency | currency | golden_pipes
  success: boolean;
  data_quality: string;
  error_message: string | null;
}

export interface IblHealthResult {
  healthy: boolean;
  events: IblHealthEvent[];
}

// 계기판 상태 — 마지막으로 기록된 IBL 건강(검사 실행 X) + 핵심 vitals
export interface IblHealthStatusItem {
  key: string;
  label: string;
  ok: boolean | null;          // null = 아직 미점검
  detail: string | null;
  checked_at: string | null;
}

export interface DashboardStatus {
  ibl_health: {
    checked_at: string | null;
    healthy: boolean | null;   // null = 미점검
    stale: boolean;            // 마지막 점검이 48h 초과 — 초록 배지를 바래게
    items: IblHealthStatusItem[];
    action_count: number;
  };
  services: Record<string, boolean>;
  disk_free_gb: number | null;
}

// 조종실 '기억 회상 검증' — 0단계 연상 묶음(해마+심층+포식+디스크골격) 미리보기
export interface RecallSection {
  key: string;
  label: string;
  present: boolean;
  content: string;
}

export interface RecallPreviewResult {
  top_score: number;    // 해마 최고 점수 (≥0.85 = Reflex 경로)
  top_code: string;
  total_chars: number;  // 실제 주입될 전체 문자 수
  sections: RecallSection[];
}

export function applyIblMethods<T extends APIClientCore>(client: T) {
  return Object.assign(client, {

    /** 자연어 의도 → IBL 코드 번역 (실행 안 함). 경량 모델 + 해마 용례. */
    async translateToIBL(intent: string, allowedNodes?: string[]) {
      return client.request<IblTranslateResult>('/ibl/translate', {
        method: 'POST',
        body: JSON.stringify({ intent, allowed_nodes: allowedNodes ?? null }),
      });
    },

    /** 조종실 '기억 회상 검증' — 이 명령에 0단계 연상이 주입할 기억 묶음을 실행 없이 미리 본다. */
    async recallPreview(message: string) {
      return client.request<RecallPreviewResult>('/system-ai/recall-preview', {
        method: 'POST',
        body: JSON.stringify({ message }),
      });
    },

    /** dry-run: IBL 코드를 파싱·검증만 하고 효과를 미리 본다 (실행 안 함). */
    async validateIBL(code: string) {
      return client.request<IblValidateResult>('/ibl/validate', {
        method: 'POST',
        body: JSON.stringify({ code }),
      });
    },

    /** 검수를 마친 IBL 코드를 실제 실행한다. projectId로 표면별 프로젝트 컨텍스트를 지정. */
    async executeIBL(code: string, projectId?: string, projectPath = '.') {
      return client.request<unknown>('/ibl/execute', {
        method: 'POST',
        body: JSON.stringify({ code, project_id: projectId ?? null, project_path: projectPath }),
      });
    },

    /** 전체 노드/액션 카탈로그 (자동완성·문법·둘러보기용). */
    async getIblCatalog() {
      return client.request<IblCatalog>('/ibl/actions/catalog');
    },

    /** 성공한 실행을 해마에 증류(학습). top_score는 번역 시 해마 최고 참조 점수. */
    async distillIBL(intent: string, code: string, topScore = 0) {
      return client.request<{ distilled: boolean; reason?: string }>('/ibl/distill', {
        method: 'POST',
        body: JSON.stringify({ intent, code, top_score: topScore }),
      });
    },

    /** IBL 건강 점검 동기 실행 — 정적+fixture 통화+골든 파이프 (AI 0). 수십 초 걸린다. */
    async runIblHealthCheck() {
      return client.request<IblHealthResult>('/world-pulse/ibl-health-check', { method: 'POST' });
    },

    /** 계기판 상태 — 마지막 IBL 건강 + 핵심 vitals (검사 실행 X, 즉각). */
    async getDashboardStatus() {
      return client.request<DashboardStatus>('/world-pulse/dashboard');
    },
  });
}
