# 상상훈련 10~17회차 회귀 재검 결과 (2026-09-29, 읽기 전용)

라이브 백엔드 정상 응답(/health healthy). 모든 execute 는 body `project_id:"컨텐츠", origin:"training"`.
파일 쓰기는 전부 `scratchpad/regress/tmp/r10_17/out/` 로 바꿔서만 실행. 트리거·goal·스케줄·워크플로 등록·발신·노트북 add·즐겨찾기 add 는 validate 만 했다.
원자료: `scratchpad/regress/tmp/r10_17/res/*.json` (문장별 validate+execute 원응답), 케이스 정의 `cases.py`·`cases2.py`·`cases3.py`.

## 1. 회차별 요약

| 회차 | 재검 표현 | 정상 | 문법변화(정상) | 여전히 오류 | 검수만(부작용) |
|---|---|---|---|---|---|
| 10 | 5 | 2 (Y1, B9) | 2 (Y2, Y5) | 0 | 1 (Y3) |
| 11 | 15 | 13 | 0 | 0 | 2 (I7, I10) |
| 12 | 23 | 19 | 2 (J4, J11) | 0 | 2 (J15/F18, J16) |
| 13 | 14 | 12 | 0 | 0 (K7은 아래 R15-F15-1 항목에 합침) | 2 (K5, K12) |
| 14 | 15 | 12 | 1 (I4a) | 0 | 2 (V14-1 add, F14-3) |
| 15 | 14 | 11 | 0 | 1 (F15-1 부분 — if/else) | 2 (I6 chart, I10) |
| 16 | 15 | 11 | 2 (F16-2, T8) | 0 | 2 (T6, T12) |
| 17 | 17 | 13 | 0 | 1 (F17-3) | 2 (T5 등록, T10) |

## 2. 여전히 오류

### R17-F17-3 — 17회차 F17-3: bare `$변수` 치환이 결과 봉투를 통째로 문자열화
- 원래 증상: `$주석 = [self:folder_note]…` 뒤 `[self:write]{content:"$주석"}` 를 하면 파일에 `{"success": true, "annotations": []}` 가 저장되어 배관 키가 들어갔다. 수리(R-F17-3, `_v4_var_payload`)는 message/items 를 우선하도록 바꿨다.
- 이번에 돌린 문장(`op:"get"` 은 은퇴해 `detail` 로 고쳐 씀):
```
$주석 = [self:folder_note]{op: "detail", path: "<scratch>/out"} ; [self:write]{path: "<scratch>/out/주석.md", content: "$주석"}
```
- validate: valid:true / execute: success:true. 저장된 파일 전문은 `{"success": true, "annotations": [], "items": [], "count": 0}` 이다.
- 대조군: `$목록 = [self:webapp]{op:"list"}` 처럼 items 가 비어 있지 않으면 items JSON 만 저장된다. 이 경우는 정상이다.
- 원인(코드 읽기, `backend/ibl/workflow_binding.py` `_v4_var_payload`): `items_nonempty = isinstance(items, list) and bool(items)` 조건 때문에 **items 가 빈 목록이면 통화로 인정되지 않고** 폴백 `return raw`(봉투 원형)로 떨어진다. 이제 folder_note 도 `items:[]` 를 함께 내는데, 0건이면 여전히 success·count 가 파일에 저장된다.
- 분류: 원 결함 재현(0건 경로). 17회차 부록은 "무 message·무 items 봉투는 봉투 유지"를 한계로 기록했지만, 이번 봉투에는 items 가 **실존**(빈 목록)하므로 그 한계와는 다른 경우다.

### R15-F15-1 (R13-K7, R16-T5, R17-T4 공통) — 15회차 F15-1: 조건 블록이 좌변 실측값을 보고하지 않음
- 원래 증상: if/case 결과가 `{"result": …}` 뿐이어서 어느 분기를 탔는지, 좌변 값이 얼마였는지 알 수 없었다.
- 현재 상태: `matched`·`matched_value` 가 추가됐다. case 는 완전히 보고한다(예: `matched:"100~160", matched_value:157.34`). if 의 **참 분기**도 값을 싣는다(`matched_value: 5.2`). 그러나 **else 분기로 떨어지면 좌변을 실제로 측정했는데도 `matched_value: null`** 이다.
- 돌린 문장 예:
```
[if: sense:host{op: "status"}.disk_percent > 90]{[self:time]} [else]{[self:time]}
[if: sense:crypto{coin: "bitcoin"}.data.current_price_usd > 100000]{[self:time]}
[else]{[self:time]}
```
- execute: `{"result": "...", "matched": "else", "matched_value": null}`. 같은 좌변을 `< 90` 으로 뒤집으면 `matched_value: 5.2` 가 실린다.
- 분류: 원 결함 부분 재현. else 경로에서는 "조건이 왜 거짓이었는지(값)"를 여전히 볼 수 없다. 15회차에 이 항목은 "판정 요청"이었고, 요청은 `matched`/`value` 동반이었다.

## 2-b. 판단 불가 (참고)
- **validate 최상위 `valid:true` 인데 typecheck 가 error 인 문장**: R12-J4(`[sense:book]{op:"detail"}`), R17-F17-3b(`[self:folder_note]{op:"get"}`), R13-F13-2(병렬 뒤 rename→merge). 이 셋은 execute 에서 "실행 전 통화 검사 거절"로 즉시 막히고, 거절 사유는 validate 응답의 `typecheck.issues` 에 들어 있다. 13회차 F13-2 의 "검수 사각"은 정보 차원에서는 해소됐지만, 최상위 `valid` 필드만 보는 소비자에게는 여전히 "valid 인데 실행 거절"로 보인다. 설계상 두 필드를 분리한 것인지는 판단할 수 없어 기록만 남긴다.

## 3. 문법 변화로 정상 처리된 항목
- R10-Y2 중첩 each(옛 do 문자열) → `#!ibl edition=2` 의 `[{a:1},{a:2}] >> [table:each]{ … [table:each]{ … } }`: 2×2 중첩 결과가 정확하다.
- R10-Y5 `[self:time]@phone` → `@폰-9f2b`: `@phone` 은 "노드를 찾을 수 없습니다. 지금 연결된 노드: 맥, 폰-9f2b"로 정직하게 거절됐다. 실제 노드명으로 쓰면 두 몸이 동시에 실행된다(`_forwarded_to: phone(push)`).
- R12-J4 `[sense:book]{op:"detail"}` → `{op:"search"} >> take >> write`: 파일에 스텁이 아닌 items 데이터가 저장된다(W-정련 정상).
- R12-J11 / R16-T8 `[engines:render_html]{html,output_path}` → `[engines:render]{op:"html", html, output_path}`: PNG 가 생성된다. T8 의 `$카드.message` 여러 줄 HTML 바인딩도 정상이다.
- R14-I4a `sense:world{}.economy.usd_krw > 1400` → `.economy.usd_krw.price`: economy 가 이제 `{price, change_pct, data_date}` 구조다. 옛 경로는 "dict 과 int 비교 불가"로 정직하게 실패한다. B14-1(economy 공백)은 해소됐다(7지표 수집).
- R16-F16-2 `groupby{agg:"sum:amount"}` → `agg:{합계:["sum","amount"]}`: 옛 스칼라 표기는 "agg 는 dict" 정직 오류로 거절된다. dict 표기로는 완주한다.
- R17-F17-3b `folder_note{op:"get"}` → `op:"detail"`: 이름만 바뀐 경우다. 치환 결과 문제는 §2 에 적었다.

## 정상 확인된 주요 수리(회귀 없음)
B9(분 단위 cron 거절, 지금은 `30 * * * *` 도 정직 거절) · B10 if/case 판정 불능 보류와 필드 힌트 · case null→default · F1 union 모양 경고 · write message 추출(devdocs) · F14(storage 문구) · B11 download path · F15 폰 전용 어휘 안내 · F16 messages inbox 안내 · F17 빈손 each/flatten · F18 id 별칭 · V13-1 goal/storage items · G13-1 괄호 분기(단·이중) · F13-3 order:"desc" · F14-1 each 치환 정직화(한글 필드·as 유령 변수) · F14-2 flatten keep · F14-4 structure ai_call 표시 · notebook ask ai_call · B15-1 거울 키(trigger list take/filter, host resources) · B15-2 since 첫 검침 note(peek) · V15-1 host resources→filter free_gb · F16-1 if 몸 중괄호 누락 시 형태 힌트("if 블록 헤더가 닫히지 않았습니다 — 형태: [if: 조건]{...}". 진단 문구 자체는 헤더를 탓해 부정확하지만 형태 힌트는 준다) · F16-3 script last_status · F16-4 book title · V16-1/V16-2 lecture/material list · F17-1 patch project_id 경고 소멸, body project_id 로 each 안 write 완주 · F17-2 `_branch_errors`/`_fallback_used` · V17-1 self_check results · 직접 경로 기본 신원(channel_read 무신원 완주).

## 4. 재검 못 한 항목과 이유
- 부작용이라 validate 만 함: R10-Y3(goal 블록 — `[goal:]` 블록 validate valid), R11-I7·R12-J16·R13-K5·R17-T5(트리거 create, cron 해소는 `_cron_to_config` 직접 호출로 확인), R11-I10·R16-T12(피드 게시), R12-J15(이벤트 delete id 별칭), R13-K12(`others:ask ?? notify`), R14-V14-1(radio_favorite add), R14-F14-3(notebook add 상대경로 — 노트북 생성이 필요해 경로 해석 실측 불가), R15-I6(health→chart, 파일 산출), R15-I10(workflow save;run), R16-T6(schedule do 안 brief → has_ai_call true 확인), R17-T10(폰 클립보드 — 맥 사전에 없음 정직 안내).
- 실행하지 않음: 15회차 I1·I2(since 기준선 저장 = 상태 쓰기 → peek 로 대체), 16회차 차단기(3연속 실패 유발 필요), 17회차 T12(전수 자가점검 실행, 수 분·부작용 → V17-1 results 로 대체).
- 외부 원천 관찰(수집 대상 아님): R17-F17-2a 둘째 가지가 CoinGecko 429(한도). 폴백 전멸 보고는 정상이었다.
- 데이터 관찰(오류 아님): finance 지출 28건의 category 가 전부 빈 문자열이라 groupby 결과가 1그룹이다. 음수 금액(환불) 행도 합계에 포함된다.
