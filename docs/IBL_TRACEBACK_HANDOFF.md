# IBL 트레이스백 — 설계·집행 핸드오프 (2026-08-27)

> 정본. 요지는 `data/system_docs/ibl.md` 엔진 규약 문단, 구현 단일 소스는
> `backend/ibl/ibl_traceback.py`, 회귀는 `backend/test_ibl_traceback.py`.

## 1. 문제 — 왜 트레이스백인가

IBL은 "코딩하는 언어"다. 파이썬으로 코딩할 때 에러가 **어디서** 났는지 찾아주는 것이
핵심 기능이듯, IBL 문장이 실패하면 어디서·왜·무슨 입력으로 죽었는지가 한 형식으로
남아야 한다. 종전의 실패 관측성은 침묵 지점을 발견할 때마다 그 자리만 메운
누적물이었다(파이프 침묵 실패·silent clamp·병렬 침묵 성공 … 각자 다른 키, 다른 모양):

- **프레임 경로 부재** — each·블록·워크플로우·병렬 안의 실패가 위로 올라올 때 산문
  한 줄로 납작해졌다. 실측 결정점: `ibl_exec_each.py` 의 옛
  `errors.append({**base, "_error": res.get("error")})` — 내부 파이프 봉투(res)에
  어느 step·무슨 입력이 다 있는데 문자열 하나만 건지고 버렸다.
- **최상위 오류가 산문** — `error: "Step 3 에러: …"`. 위치가 문자열 안에 있어 파싱 필요.
- **실패 프레임의 입력 부재** — 실패 step 에 들어간 통화가 실패 기록에 없었다
  (파이썬 프레임의 지역변수에 해당하는 자리).
- **파이썬 예외 축소** — 핸들러 예외가 `str(e)` 로 죽어 패키지 안 위치가 유실
  (`ibl_routing._route_handler` 의 포획 지점).

품질 축과의 연결: 원샷 AI 단계는 예외를 던지지 않고 **그럴듯하지만 나쁜 결과를
성공으로 반환**한다. 품질 미달을 "위치 있는 실패"로 만들려면 위치 형식이 먼저 있어야
한다 — 트레이스백이 그 기반이고, `error_type: "quality"` 를 예약해 두었다(후속 배치).

## 2. 형식

모든 실패 봉투(success:false)에 구조화된 `traceback` 하나:

```json
"traceback": {
  "frames": [                                  // 바깥→안쪽
    {"kind": "pipeline", "step": 3, "of": 7, "node": "table", "action": "each"},
    {"kind": "each", "item": 12, "of": 40},
    {"kind": "pipeline", "step": 2, "of": 3, "node": "sense", "action": "crawl"}
  ],
  "error": "원형 오류문",                        // 다이어트 밖 (상한 2000자만)
  "error_type": "tool_error|exception|syntax|binding|quality†",
  "input": {"shape": "items", "count": 40, "columns": [...], "preview": "…"},
  "py_tail": ["media_producer/handler.py:88 in _render", "KeyError: 'fps'"]  // 예외만
}
```

frame kind ∈ `pipeline · parallel(branch) · fallback(attempts) · each(item/of) ·
block(block=try/catch/repeat/branch, matched) · workflow(name)` — 전부 **표준 문법
구조**다. 어휘 이름은 엔진에 들어가지 않는다(헌법: 표준/사전 경계).

## 3. 규약 — 결정 네 가지

1. **경계 규약, 등록 목록 없음** (B48-1). 실패 봉투가 실행기 경계를 넘을 때 넘는 쪽이
   자기 프레임을 앞에 붙인다(파이썬 예외 전파와 같은 방향). 조립 단일 지점은
   `workflow_engine._handle_failure` — tb 를 안 만든 실패 지점(미래 포함)도 여기서
   기본 pipeline 프레임 + input 요약을 얻는다.
2. **예외 없음** (2026-08-27 판정). 초안은 each 행별 실패를 1차에서 빼자 했으나
   기각 — 그 면제 자체가 손 고른 스윕이고, each 는 실패가 가장 잦은 자리다.
   each 행(`errors[]._traceback`)·병렬 가지(`branches_failed[].traceback`, 잎 오류
   포함)·블록·워크플로우 전부 붙는다.
3. **요약기 재사용** (B27-1: 판정기는 하나). `input` 은
   `ibl_envelope.summarize_result` 로만 — 트레이스백과 봉투 요약이 서로를 반박하지
   않게. 트레이스백 자체는 다이어트 대상이 아니다(진단 정보).
4. **반복은 접되 밝힌다** (침묵 클램프 금지). 동일 오류 N행의 무거운 상세
   (py_tail·input)는 첫 발생에만 원형, 이후 `detail_at: <행>` 참조 + 봉투 note.
   frames 는 행당 수십 바이트라 전 행 유지.

승계 방향: 안쪽 트레이스백이 진실 — 바깥은 frames 만 쌓고 error/input/py_tail 을
덮지 않는다(`build_tb(nested=...)`). try·catch 모두 실패 = catch 의 tb 가 바깥으로
(처리 중의 실패가 최종 오류 — 파이썬 규약), try 쪽은 `try_error.traceback` 에 보존.

## 4. 배선 지도 (2026-08-27 집행분)

| 자리 | 파일 | 무엇 |
|---|---|---|
| 단일 소스 | `backend/ibl/ibl_traceback.py` (신설, ibl 층) | build_tb/push_frame/tb_of(사본)/py_tail_of/attach_input/fold_heavy |
| 조립 지점 | `workflow_engine._handle_failure` | 기본 프레임 + input + 실패 step 기록(`results[].traceback`, 다이어트 생존) + 봉투 최상위 |
| 파이프 실패 7지점 | `workflow_engine` | 문법·변수치환·바인딩(binding), 실행/병렬/폴백 예외(exception+py_tail), step 에러(tool_error+nested 승계) |
| 병렬 | `workflow_engine` | 가지별 `branches_failed[].traceback`(잎 오류도 생성) · 전 가지 실패=첫 가지 tb 승계 |
| 폴백 | `workflow_engine` | 전체 실패=마지막 시도 tb 승계 + attempts 수 프레임 |
| each | `ibl_exec_each` | 행별 `_traceback`(do 봉투 승계+each 프레임) · fold_heavy · 전량 실패=첫 행 tb 가 문장 tb |
| 블록 | `ibl_control_blocks` | `_run_body` 승계 · `_block_tb`(try/catch/repeat 프레임, repeat 은 iteration) |
| 분기 | `ibl_executors._attach_branch_meta` | if/case 분기 몸 실패에 block(matched) 프레임 |
| 워크플로우 | `workflow_engine.execute_workflow` | 실패 봉투에 `{kind:"workflow", name}` 프레임 |
| 파이썬 꼬리 | `ibl_routing._route_handler` | 동기·async 핸들러 예외에 씨앗 tb(py_tail) — 유일하게 str(e) 로 죽던 관문 |

층: `ibl_traceback` 은 `check_backend_layers.py` LAYERS ibl 에 등재(잎 모듈,
ibl_honesty 와 같은 위상).

## 5. 남긴 것 (의도적)

- **부분 실패 중간 step 의 다이어트**: each 부분 실패(문장은 성공)가 파이프 *중간*
  step 이면 봉투 다이어트가 그 step 의 errors[] 를 요약으로 접는다 — 정직 표지
  승격(`markers_of`)이 error_count 를 나르고, 원형은 `verbose:true`. 기존 규약 유지.
- **goal 라운드 실행**: goal 본체(비동기 라운드)의 실패 경로는 품질 단계
  (`error_type: "quality"`) 배치에서 GoalEval 과 함께 — 관리 op 의 잎 오류는 파이프
  이음매 기본 프레임으로 충분.
- **표면 렌더**: 조종실이 traceback 을 파이썬 트레이스백처럼 렌더하는 것은 표면
  작업 — 데이터는 이미 봉투에 있다.

## 6. 다음 단계 (품질 축 — 지난 설계 대화의 합의)

1. **단계별 품질 계약**: AI 단계(ai_call: true 액션)에 그 단계의 기대를 선언 →
   미달이 `error_type: "quality"` 로 **같은 트레이스백 형식**의 위치 있는 실패가 된다.
2. **작성 시점 정적 검사**: "이 AI 단계에 품질 계약이 없다"를 지적하는 린트.
3. **학습 회로**: 품질 판정이 붙은 에피소드 → 증류 게이트가 단계 단위 점수를 먹게.
