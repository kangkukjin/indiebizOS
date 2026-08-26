# 검수 비용 계층화 핸드오프 (2026-08-27 설계 → **같은 날 집행 완료**)

> **집행 결과**: Phase 1~6 전부 완료. render 전 op 행에 `prescreen`(html: 콘솔 오류·페이지
> 예외·요청 실패·잉크율 / pdf·svg: 잉크율 / xlsx: +수식 오류 표식) + 봉투 `prescreen_flagged` ·
> critic `prescreen` 단락(키 검사 앞, tier=prescreen/vision 구분) · 화면검수 배선 · 어휘 2표면
> 갱신+`--check` GREEN · 계약 배터리 **7건** GREEN(오탐 금지=깨끗한 페이지 빈 문자열 포함,
> 인접 배터리 22건 회귀 GREEN) · 시드 3건(+distilled 827) · 라이브 종단: 콘솔 오류 페이지를
> 화면검수로 — 두 뷰포트 모두 0층 단락, **each 단계 8ms = 비전 호출 0회 실증**.
> 잔여: ⏳실사용 관찰(0층 오탐 등장 여부 — 잉크율 임계 0.1%) · 풀 재학습 대기열 합류(시드 3).

> 목적: 검수 파이프(`render >> each critic`)가 첫 수부터 유료 비전 호출을 쓰는 구조를
> **0층(공짜 기계 관측) → 1층(유료 비전 심사)** 계층으로 바꾼다. 상용 하네스 대조에서
> 배울 것으로 판정된 항목("싼 텍스트 검사를 먼저, 비싼 픽셀은 마지막").
> 원칙: **파이프 모양 불변** — 계층화는 문장이 아니라 이음매(행 필드 + critic 단락)에 산다.

## 0. 설계 결정 3가지 (탐사 근거)

1. **0층의 자리 = render 의 행 필드.** Playwright 가 이미 페이지를 열고 있으므로 콘솔
   오류·페이지 예외·요청 실패 수집은 **한계비용 0** 이다. PNG 잉크율·xlsx 수식 오류
   표식(재계산 PDF 텍스트)도 로컬 연산뿐. 각 행에 `prescreen`(문자열 — 비었으면 깨끗,
   차 있으면 사실 문장들 "; " 연결)을 동봉한다.
   - **헌법 정합**: prescreen 은 관측의 기계 요약(결정론)이지 판단(취향)이 아니다 —
     `truncated`·`scan_truncated` 와 같은 정직층 부류. 합격/불합격 **판정**은 critic 층의 몫.
   - 문자열 하나인 이유: `[table:each]` 의 `$it.필드` 치환이 문자열에서 안전하다(실측 —
     ibl_exec_each `_each_substitute`). 목록/불리언이면 치환 자리가 깨진다.
2. **1층 단락의 자리 = critic 의 `prescreen` param.** `image_read{op:"critic", prescreen:
   '$it.prescreen'}` — 비어 있지 않으면 Gemini 를 **호출하지 않고** 즉시 실패 verdict
   (`tier: "prescreen"`, issues=관측 사실들)를 같은 모양(summary+verdict_json)으로 반환.
   API 키 검사보다 **앞**에 두어 키 없이도 돈다. 깨끗하면 기존 비전 경로(`tier: "vision"`).
   - 분기·필터·[if] 를 쓰지 않는 이유: 파이프 모양이 불변이라 기존 문장·시드·화면검수가
     전부 재사용되고, 더러운 행도 verdict 행으로 남는다(필터로 떨구면 침묵 유실).
3. **op 별 0층 관측 범위** (없는 것은 안 하는 것으로 정직하게 — 가이드에 명기):
   - html: 콘솔 오류 / 페이지 예외(pageerror) / 요청 실패(requestfailed) / PNG 잉크율(빈 화면)
   - pdf·svg: PNG 잉크율만
   - xlsx: PNG 잉크율 + 재계산 PDF 텍스트의 수식 오류 표식(#REF!·#DIV/0!·#VALUE!·#NAME?·#N/A·#NULL!·#NUM!)
     — criteria/sheet.yaml forbidden 의 0층 선행판(비전은 백업 그물이 된다)

## 집행 항목

- Phase 1 — render_artifact.py: html 루프에 이벤트 수집, `_ink_ratio`(pymupdf Pixmap 표본),
  xlsx 후처리(페이지별 텍스트 표식 스캔), 전 op 행에 `prescreen` 필드(깨끗=""), 봉투에
  `prescreen_flagged` 수.
- Phase 2 — gemini_vision.py: critic 진입부(키 검사 앞) prescreen 단락, 정상 경로 verdict 에
  `tier: "vision"` 부여.
- Phase 3 — ibl_actions.yaml: image_read params 에 `prescreen`, 두 액션 desc·achievement 갱신.
  build `--check`.
- Phase 4 — workflows/화면검수.yaml do 문장에 `prescreen: '$it.prescreen'` 추가.
- Phase 5 — 계약 배터리 backend/test_render_prescreen_contract.py: 콘솔 오류 포집 / 깨끗한
  페이지 = 빈 문자열 / 빈 화면 잉크율 / 페이지 예외 / critic 단락이 **키 없이** 실패 verdict /
  단락 없을 때 정상 경로 보존 / xlsx 표식(soffice 없으면 skip) / 워크플로우 통과 배선.
- Phase 6 — 시드(관문 통과분만 비전 문형), guides(sheet.md·web_builder.md), changelog,
  백엔드 재기동(서브모듈), 라이브 종단(양 뷰포트가 0층에서 걸리는 페이지 = API 비용 0 실증).

## 곁가지(범위 밖)

- 잉크율 임계 미세조정·뷰포트별 차등: 실사용 오탐 등장 시.
- 0층 관측을 별도 어휘로 승격: 기각 — 행 필드가 조합 가능성을 이미 준다(반-어휘-증식).
