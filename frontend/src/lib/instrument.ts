/**
 * 앱 모드 계기(instrument) 공용 헬퍼 — 커스텀 계기가 IBL/AI 를 부르는 **정본 경로**.
 *
 * 계기마다 손으로 fetch 를 짜다 보면 `project_id:'앱모드'` 를 잊어 "활성 프로젝트 경로
 * 확보 불가"로 실패한다(실제 사고 이력). 그 컨텍스트를 헬퍼에 박아 **실수를 구조적으로
 * 불가능**하게 한다 — 저자는 이 함수만 부르면 항상 맞는다.
 *
 * raw fetch + 절대 API base 를 쓰는 이유: 계기는 Electron(file://)·원격 등 다양한
 * 오리진에서 뜨는데, 상대경로 api 클라이언트는 백엔드에 안 닿을 수 있다(기존 계기 관습).
 */

const API = 'http://127.0.0.1:8765';

/** 앱 모드 시스템 프로젝트 컨텍스트 — 앱 모드엔 활성 프로젝트가 없어 `[self:*]` 상대경로가
 *  풀리지 않는다. 상대경로는 이 컨텍스트에서 `projects/앱모드/<경로>` 로 해소된다. */
export const APP_PROJECT_ID = '앱모드';

/**
 * 앱 모드에서 IBL 코드를 실행하고 결과 payload 를 견고하게 언랩한다.
 * `project_id:'앱모드'` 를 자동으로 실어 보낸다(저자가 잊을 수 없음).
 *
 * 응답 언랩: 단일 액션이면 결과가 최상위, 합성(`>>`) 다단계면 `final_result` 에 온다.
 * 문자열이면 JSON 파싱을 시도한다(실패 시 문자열 유지).
 */
export async function iblExecuteApp(code: string): Promise<unknown> {
  const res = await fetch(`${API}/ibl/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, project_id: APP_PROJECT_ID }),
  });
  const d = await res.json();
  let r: unknown =
    d?.final_result ??
    (d && typeof d === 'object' && 'result' in d ? (d as { result: unknown }).result : d);
  if (typeof r === 'string') {
    try { r = JSON.parse(r); } catch { /* keep string */ }
  }
  return r;
}

/**
 * 시스템 AI에게 **동기 대화**를 요청한다(맥락+지시를 message 에 담아). 응답 텍스트를 돌려준다.
 *
 * ★전체 인지 파이프라인(의식→실행)을 타므로 느릴 수 있다(수십 초~분). 대신 시스템 AI의
 * **도구 접근**이 있어 "PDF로 저장" 같은 도구 필요 지시가 실제로 된다.
 *
 * 언제 무엇을:
 *  - 가벼운 변환/조회  → `iblExecuteApp` (빠름)
 *  - 지금 답을 이 패널에 → `askSystemAI` (동기 대화, 이 함수)
 *  - "가서 이 일을 해"(산출물 생성) → 대화가 아니라 `[others:delegate]{scope:"system"}` (선언형, 코드 0)
 */
export async function askSystemAI(message: string): Promise<string> {
  const res = await fetch(`${API}/system-ai/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  const d = await res.json();
  return String(d?.response ?? '');
}

/**
 * **원샷 AI 질문** — `[self:ask]` 어휘 경유(raw fetch·엔드포인트 아님). 답 텍스트를 돌려준다.
 * 도구 없이 가볍고 빠르다: 요약·개선·설명·번역·답변·변환. **AI 호출의 기본값.**
 *
 * `askSystemAI`(도구 쓰는 무거운 에이전트 대화)와 다르다. 무언가를 *만들거나* 여러 단계가
 * 필요하면 대화가 아니라 `[others:delegate]{scope:"system"}` (에이전트 작업, 비동기)로.
 *
 * @param prompt  지시/질문 (필수)
 * @param context 판단 대상 텍스트/데이터 (선택)
 */
export async function askAI(prompt: string, context?: string): Promise<string> {
  const parts = [`prompt: ${JSON.stringify(prompt)}`];
  if (context != null) parts.push(`context: ${JSON.stringify(context)}`);
  const r = await iblExecuteApp(`[self:ask]{${parts.join(', ')}}`);
  if (r && typeof r === 'object') {
    const o = r as { result?: unknown; text?: unknown };
    return String(o.result ?? o.text ?? '');
  }
  return typeof r === 'string' ? r : '';
}
