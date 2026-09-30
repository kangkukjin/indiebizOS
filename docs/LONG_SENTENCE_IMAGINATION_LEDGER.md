# 긴문장 상상훈련 — 회차 요약과 갭 원장

절차 정본: [긴문장 상상훈련 가이드](../data/guides/long_sentence_imagination.md).
이 문서는 git에 남는 누적 기록이다. `outputs/long_sentence_imagination/`의 원자료·로그·
산출물은 로컬 실행 증거이며 이 원장의 요약과 판정 근거를 대신하지 않는다.

## 기록 규칙

- 시작할 때 다음 회차 번호로 항목을 만들고 날짜·과제·상한·진행 상태를 적는다.
  완료·중단한 번호도 재사용하지 않는다. 종료 시 같은 항목을 갱신한다.
- 회차별로 자연어 과제와 완료 조건, 자료·모델·작성 조건, 최초/도움 뒤 시도,
  검사·실행·달성 판정, 변형 결과, 비용·종료 이유·남은 문제를 간단히 기록한다.
- 근거는 실행 id·소스 버전·관측 결과와 함께 적는다. 로컬 경로만으로 판정을 설명하지 않는다.
  비민감 최소 재현과 합성 입력은 이 문서나 `docs/experiments/long_sentence_imagination/round_N/`에 둔다.
- 갭 ID는 `L<회차>-<순번>`이다. 재발견은 같은 ID에 증거를 더하고 다른 훈련의 관련 ID도 연결한다.
  원인 분류와 상태는 별도로 기록한다. 수리됨은 커밋과 원래 전체 프로그램·새 변형의 검증 근거로 닫는다.
- 민감 자료·토큰·개인 원문은 커밋하지 않는다. 생략으로 재현이 제한되면 필요한 조건을 밝힌다.

## 회차 요약

가이드 작성·등록 검증은 훈련 회차로 세지 않는다.

| 회차·날짜 | 과제·완료 조건 | 작성 조건·상한 | 검사/실행/달성·변형 | 비용·종료 이유 | 갭·근거·다음 과제 |
| --- | --- | --- | --- | --- | --- |
| 1 · 2026-09-29 (완료, 훈련만·수리 없음) | 워크숍 견적 3곳(CSV·JSON 혼합, 합성) 비교 보고서. 조건: 3곳 전부·필수 합계 정확·빠진 가격 0 취급 금지·완비+예산 이내 최저가 추천·질문·파일 저장 후 재읽기 | 기본 조건(교재·계약 조회만, 소스 미열람; 개발 세션이라 내부 지식 분리 불가). 60분·수정 3회. 모델 호출 0. HEAD `9dc6f380` | 원래: v3 통과/정상/**부분**(파일에 합계 표 누락 — 훈련자 누락) → v5 **달성**(`39cae3b8…`). 변형(인원 50+C 파일 없음): v3 정직한 실패(coverage·partial) → v5+reuse **달성**(추천 없음, C 재송부 요청, source_complete false, 읽기 3건 복원) | ~20분(20:30~20:50). 수정 3회 소진(v2 보간 따옴표, v3 null 우회, v5 filter 좁힘 우회). check 응답 40KB 중 guards 30KB | L1-1~L1-7. 다음: `table:ai` 가 낀 긴 흐름·재개, 웹 원천 조사 과제, 100행+ 규모 check 비용 |
| 2 · 2026-09-29 (완료, 훈련만·수리 없음) | 송년회 장소·날짜 제안서(설문 120행 CSV·장소 4곳 JSON·후기 4파일, 합성). 조건: 날짜별 확정·미정·식단 집계, 9안 판정·사유, 확정 최다 날 우선 상위 2안, 불가 날 사유, 모델 후기 요약(우려), 채식·알레르기 질문, 저장 후 재읽기 | 기본 조건(교재·describe 만, 소스 미열람; 내부 지식 분리 불가). 60분. 모델 = table:ai 7회(토큰 미상). HEAD `4ae76728` | 원래: v3 부분(12-12 불가 사유 누락 — 훈련자) → v4 **달성**(`c56f4e01…`). 변형 A(V2 후기 없음, 견고성): v3·v4 **달성**(source_complete false, 추천 불변). 변형 B(미정 절반, 입력만 변경): v3 부분("67.0명" 표시) → v4 **달성**. v3→B reuse 읽기 6건 중 0 복원 | ~8분(23:46~23:54, 보고서 별도). 수정 4회(v1 삼항 파이프, v2 내장 인자 파이프·ceil, v3 sorted 목록 키, v4 누락 사유·round). 실패 check 51KB | L2-1~L2-8. 다음: 웹 원천 조사 과제, each 안 행별 모델 호출, 계산/저장 분리로 reuse 재측정 |
| 3 · 2026-09-30 (완료, 훈련만·수리 없음) | 세계 지리 수치 논쟁 학습 자료(실웹 위키 ko/en 6원천: 에베레스트·만리장성·나일). 조건: 6원천 읽음/실패 명시, 8,848.86 m(ko·en 일치 표시), 21,196·8,850 km 정의 차이, 나일 6,650 km·아마존 최장 논쟁, 모든 수치에 문단 근거·원문에 없는 수치 금지(코드 검사), 확인 못 한 부분 절, 저장 후 재읽기 | 기본 조건(교재·describe·관측 실행 2건, 소스 미열람; 내부 지식 분리 불가). 60분. 모델 = table:ai(Codex gpt-6-astra:high) 원천별 6회+해설 1회. HEAD `556ee4c9`, 훈련 중 재기동 1회 | 원래: v3 BUDGET → v4 preserve_rows 실패 → v5b·v6 NUMBER_REQUIRED → v7 **부분**(묶기·논쟁 설계 누락, 훈련자) → v8b **부분**(`f3e9bb16…`, ①②③⑤⑥⑦ 충족·④ 아마존 문단 ¶265 논쟁 미추출). 변형 A(ko 만리장성 404, 견고성): **달성**(원천 1/2·실패 사유·source_complete false). 변형 B(영미 단위·퀴즈, 변경 용이성): 수정 0회 성공이나 **부분**(원천 오기 이상값이 퀴즈 정답) · **reuse 0/1**, 크롤 6건·모델 7회 재실행 | ~28분(09:20~09:48, 보고서 별도, 재기동 대기 ~3분). 수정 8주기. 모델 8실행 합 47요청·입력 814,155·출력 38,168(성공 1회 123,249) — 모델 뒤 순수 계산 버그마다 모델 전량 재지불 | L3-1~L3-11. 다음: 모델 원출력 보존(L3-6 규명), `$ref` 로 나눈 조사 파이프라인 작성 비용, sense:search 로 원천 찾기부터 |
| 4 · 2026-09-30 (완료, 훈련만·수리 없음) | 파이썬 3.13·3.14 변경점 공부 노트 — 공식 What's New 를 검색으로 찾기, PEP 변경 버전별·분류 4종, 3.13 실험→3.14 정식, 문단 근거·원문에 없는 PEP 금지, 확인 못 한 부분, 저장 후 재읽기. P1 수집→P2 모델 추출→P3 렌더 `$ref` 3프로그램 | 기본 조건(교재·가이드·describe·관측 1건, 소스 미열람; 3회차 수리 요약을 앎). 60분. 모델 = table:ai(ClaudeCode opus) 덩이별 7회. HEAD `0c5f47f2` | 원래: P1 v3(검색 변동·hatena 오인 수정 뒤)·P2 첫 판 성공·P3 v3 **달성**(`2630888f…`; 703 실험→정식, 779 는 따로). 변형 A(3.99 추가, 견고성): **달성**(찾지 못함·3.99 모델 0·reuse 크롤 1/3). 변형 B(업그레이드 체크리스트, 변경 용이성): P3 만 수정 0회 **달성**, 모델 0 | ~12분(10:57~11:09, 보고서 별도). 수정 7주기(P1 3·P3 4). 모델 합 14요청·입력 95,806·출력 23,285. P3 수정·변형 6회 전부 모델 0·1초 미만(단계 분할 효과) | L4-1~L4-4. 다음: 링크 따라가기 크롤의 예산(변형 A P1 61,830단계), model_output_ref 실제 실패 검증, 표·PDF 원천 |
| 5 · 2026-09-30 (훈련 완료·후속 수리 §8~9) | 법인카드 경비 정산 — 영수증 PDF 12장(R11 글자 층 없음·R12 손상)×카드 CSV 13행. 조건: 12장 상태, 정상 짝 8, R03 금액 불일치, R07 카드 없음, A1009 중복 청구, 영수증 없음(못 읽은 영수증 단서), 결재 R05·R08, 합계 506,000/435,400, md·json | 기본 조건(소스 미열람). 60분. P1 table:ai(opus) 추출 / P2 table:judge 가맹점 동일성, `$ref` 2프로그램. HEAD `54dd7758`+다른 세션의 L4 수리 미커밋(라이브 반영) | 원래: P1 v1·P2 v2 **달성**(`2d19ab60…`). 변형 A(R09 사본 R13·R14 추가, 견고성): **달성** — 사본을 빼 중복 청구 유지. 변형 B(결재 4만·CSV, 변경 용이성): P2 만 수정 **달성**, 모델 추출 0 | ~8분(11:55~12:03, 보고서 별도). 수정 4주기. 모델 6요청·입력 27,776·출력 2,156 | L5-1~L5-6. 후속: judge null·OCR 수리, 모델 자동 reuse 구현. 잔여 후보: threshold 작성·수천 행 대조 예산 |
| 6 · 2026-09-30 (훈련 완료·후속 수리 §8) | 2025년 가계부 연간 결산 — 월별 CSV 12개(2,698행)·규칙·고정지출. 조건: 규칙+AI 분류(출처 표시), 월별·분류별 표, 중복 결제, 고정지출 빠짐·금액 다름, 튄 달(2배), 구독 겹침(judge), 환불 분리, 못 읽은 파일·금액 명시, md·json | 기본 조건(소스 미열람). 60분. P1 table:ai(opus) / P2 table:judge(Jev), `$ref` 3프로그램. HEAD `bc4925e6`+다른 세션 L5 수리 미커밋(라이브, 훈련 중 재기동 6회) | 원래: P1 v2·P2 v2·P3 v0 **달성 7/8**(구독 겹침 부분 — judge 21쌍 중 미결정 10, 노출). 변형 A(07월 없음·금액 오류): 수정 전 부분(없는 달 미대조) → P2 v3 **달성**, 모델 추출 0. 변형 B(상위 3 가게 표·CSV): P2 v4+P3 v2 달성, 읽기 8/9·judge 재사용, 모델 0. 변형 B2(규칙 추가): reuse 1/16 | 원래 부분 달성까지 14분(재기동 대기 ~3분 포함). 수정 P1 2·P2 2(+A 1)·P3 0(+B 1). 모델 과제 opus 3(17,862/1,415)·Jev 3(7,611/1,242), 재현 opus 4·Jev 9. P1 v0 BUDGET(2,291행에서 10만 단계) | L6-1~L6-9. 다음: 1만 행+ 분할 작성 비용, 재기동 뒤 reuse 격리, judge questions/score, self:script 경계, 상상행동 모드 |

6회차 상세: [round_6/report.md](experiments/long_sentence_imagination/round_6/report.md) — 예산 단위·judge 배치 의존·reuse 무사유 0건·재현 30종·비용 표.

5회차 상세: [round_5/report.md](experiments/long_sentence_imagination/round_5/report.md) — 최초 훈련 기록과 §8의 L5-1~6 후속 수리·전체/변형 검증.

4회차 상세: [round_4/report.md](experiments/long_sentence_imagination/round_4/report.md) — 최초 훈련은 수리 없이 종료. 후속 요청에 따른 L4-1~4 수리와 원본·변형 검증은 §8.

3회차 상세: [round_3/report.md](experiments/long_sentence_imagination/round_3/report.md) — 최초 초안~v8b·변형 B·재현 27개·비용 표.

2회차 상세: [round_2/report.md](experiments/long_sentence_imagination/round_2/report.md) — 최초 초안~v4·재현 16개·실행 요약.

1회차 상세: [round_1/report.md](experiments/long_sentence_imagination/round_1/report.md) — 최초 초안·수정본·재현 16개·실행 요약 포함.
시범 회차 가이드 소견(도움 된 절·모호·빠진 지침)은 보고서 §7. 최초 훈련 당시 사용자 지시("수리는 하지 마")로 가이드 다듬기를 보류했다. 후속 수리·검증은 보고서 §8에 기록한다.

상세 설명이 필요하면 이 표 아래에 회차별 절을 둔다. 1회차에는 가이드에서 실제로 도움이 된 절,
모호하거나 불필요했던 절과 빠진 지침도 기록한다.

## 갭 원장

예시 ID를 실제 발견으로 등록하지 않는다.

| ID | 원인 분류·막힌 연결 | 최소 재현·관측 근거 | 상태·다음 조치 | 수리 커밋·전체/변형 검증 |
| --- | --- | --- | --- | --- |
| L1-1 | 문법·값 계약 공백 — 정적 검사기 null 좁힘 없음(삼항·`[if]`+return·변수 보간) | `$it.a == null ? "-" : text($it.a)` → TYPE; `[if:…==null]{return}` 뒤 `text()` → TYPE; `f"${v}"` → FORMAT_TYPE. 우회 `json()` (`round_1/repro/narrow_*`) | 수리됨 | `674d65ee` · v2·v4 검사, null 삼항·조기 반환·보간, 전체·누락 변형 통과
| L1-2 | 문법·값 계약 공백 — filter 판별 술어 뒤 합집합 레코드 좁힘 없음 | collect 결과를 `not $v.ok` 로 거른 뒤 `$it.error` → MISSING_FIELD error. 우회 `get(…,"")` (`round_1/drafts/v4.ibl` 93행) | 수리됨 | `674d65ee` · v4 error 직접 접근, 전체·누락 변형·읽기 3건 reuse 통과
| L1-3 | 구현 결함+계약 공백 — `self:read .data` 형식별 불선언·CSV 는 구판 봉투 누수·observed_returns 가 내용 키로 오염 | CSV `.data`={success,items,message,path,count}(본문 3중), JSON `.data`=파싱 값(미문서), target_description null, observed keys=`version,run,config,root,snapshot…` (`repro/read_*`) | 수리됨 | `674d65ee` · JSON·CSV/TSV·회원 읽기·내용 키 차단, 새 인용/빈칸/0 변형 통과
| L1-4 | 작성·발견 마찰 — 보간 안 이름 해석 불일치·따옴표 오류 문구 오도 | `${len(x.a)}` → BUILTIN "알 수 없는 내장 함수: x"(`${x.a[0]}` 는 성공); `${join(", ",$x.a)}` → SYNTAX "닫는 }가 없습니다" (`repro/interp_*`). 09-16 ep 감사 "따옴표 중첩"과 같은 계열 | 수리됨 | `674d65ee` · 보간 이름 6형 및 다른/삼중 따옴표 통과, 중첩 따옴표 처방 확인
| L1-5 | 과도한 비용 — 성공 check 응답의 76%가 information RUNTIME_GUARD(일부 전부 Unknown) | 100줄 프로그램 check 40,242자 중 guards 30,597자·24건 (`runs/v3_check.json`) | 수리됨 | `674d65ee` · 동일 v3 40,238→9,945자, 48개 상세 가드 재조회 확인
| L1-6 | 작성·발견 마찰(경미) — 파일 없음이 `TOOL`+원시 `[Errno 2]` | `repro/missing_file_code.ibl` → code TOOL | 수리됨 | `674d65ee` · NOT_FOUND·원인 details·부분 결과, 라이브 누락 변형 통과
| L1-7 | 작성·발견 마찰(경미) — describe 6개 상한이 교재에 없음 | 7개 요청 → "1~6개 배열입니다" | 수리됨 | `674d65ee` · 조합 교재 1~6개 명시·교재 예산 검사 통과
| L2-1 | 계약 공백+과도한 비용 — reuse 가 쓰기 앞의 읽기를 쓰기 자원과 무관하게 전부 제외 → "계산→저장" 프로그램은 복원 0. 모델 호출도 같은 입력으로 재호출 | `round_2/repro/reuse_after_write_*` 0/0 vs `reuse_no_write_*` 1/1. 원래 v3→변형 B: 읽기 6건 중 0 복원, table:ai 재호출 ~17s. 교재 381행의 문서화된 동작. 열린 "model 효과 재사용 판정"과 연결 | 수리됨 | 자원 충돌 없는 입력 6건 복원. 후속 구현으로 table:ai/brief/judge의 같은 입력·설정 성공 결과도 자동 reuse. 2회차 계산 변경은 모델 재호출 0. round_5/report.md §9. |
| L2-2 | 문법·값 계약 공백 — table:ai schema 가 정적 결과형에 투영되지 않음(describe 는 "정적 검사 공용"이라 적음) | `repro/ai_schema_typo.ibl`: `$it.conz` check 통과 → 모델 6.2s 뒤 MISSING_FIELD | 수리됨 | 공통 schema_fields로 선언 이름 투영. conz를 실행 전 MISSING_FIELD로 거절; 값 타입 추측 없음. |
| L2-3 | 과도한 비용 — 실패(invalid) check 는 정보 가드를 접지 않음, 생략분에 guards_ref 없음 (L1-5 의 남은 가지) | `round_2/runs/v1_check.json` 51,008자 중 guards 26,090(24건 표시·58 생략·ref 없음). 성공 check 13,422자 | 수리됨 | invalid check도 상세 가드 ref 보존. v1 응답 51,008→25,960자(오류·경고 유지). |
| L2-4 | 과도한 비용(저장) — 실행 저장본에 식 노드 단위 증거가 행당 ~1.45KB 선형. **6회차 재발견**: 도구 위주 P2 저장본 996KB(value 15KB, 67배, events 3,788), P1 1.87MB(value 310KB) | 원래 v3 값 ~5KB, result_ref 1,255,621자(evidence 1.09M·10,488건). `repro/evidence_scale.ibl` 100행 147K / 1,000행 1.45M | 수리됨 | 동일 구문·근거의 성공 식 DAG 합침. 1,000행 저장 1,452,346→8,395자; 도구·실패·복구 사건 유지. |
| L2-5 | 문법·값 계약 공백 — 같은 수가 리터럴/inputs 출처에 따라 "6"/"6.0" 표시, `//` 결과 정수 표시 보장 없음(문법 전문 114행과 불일치) | `repro/floordiv_display.ibl` "-6" vs "-6.0", `==` true. 변형 B 제안서 "67.0명" | 수리됨 | JSON 소수도 공통 십진 산술·반올림; // 정수 반환, 정수값 보간 통일. v3 비율 0.5의 67명 확인. |
| L2-6 | 작성·발견 마찰(경미) — 삼항 가지 안의 호출이 PURE_EXPRESSION 대신 "`:`가 필요" SYNTAX | `repro/ternary_pipe.ibl` | 수리됨 | 삼항 참 가지 파이프를 PURE_EXPRESSION과 앞 변수/if 처방으로 거절. |
| L2-7 | 작성·발견 마찰(경미) — 정적으로 목록인 sorted 키를 check 가 통과, 실행에서 UNORDERED | `repro/sorted_list_key.ibl` | 수리됨 | 람다 반환형의 확정된 비순서 값을 check에서 UNORDERED로 거절. 필드 이름 정렬의 기존 버킷 규칙 유지. |
| L2-8 | 과도한 비용(관측 불가) — 프로그램 안 모델 호출의 토큰·모델·기어가 실행 봉투·저장본에 없음 | 원래 v3 usage `{steps,rows,elapsed_ms}` 뿐, table:ai 녹화 evidence 비어 있음 | 수리됨 | 청구 원장에서 실행별 usage.model 집계. 실제 모델·선택 출처·입출력/캐시와 미측정 구분; resume 비용 중복 없음. |
| L3-1 | 계약 공백+과도한 비용 — 효과 미상(`effects:unknown`) 호출 하나가 프로그램 전체 reuse 를 0 으로. 크롤 설명이 권하는 `fn:본문에서찾기`(순수 검색, 스필 파일만 기록)가 원인 | `round_3/repro/reuse_lambda_*` 1/1 vs `reuse_find_*` 0/0(`read_calls 0`·`state_change_possible true`). 변형 B: candidates 1·reused 0, 크롤 6건·모델 7회 재실행. L2-1 "자원 미상=전체" 규칙과 결합 | 수리됨 | 명시 순수 계약의 단순 구판 전달 함수와 크롤 URL 읽기 자원 선언. 보고서 쓰기 뒤에도 라이브 크롤 6/6 복원. 복잡한 미상 함수의 보수성 유지. |
| L3-2 | 과도한 비용 — 모델 뒤 순수 계산 실패마다 모든 모델 호출 재지불; partial 로 앞 단계 변수 구제 불가, 단계 분할 지침 없음 | v5b→v6→v7 각 모델 6~8회·입력 10.2만~13.9만. 회차 합 814,155 중 성공 1회 123,249. L2-1 "모델 재사용 미지원"·열린 model 효과 재사용 판정과 연결 | 수리됨 | 단계 반환/$ref는 다른 작업으로의 전달에 유지. 후속 구현으로 성공 모델 결과 자동 reuse. 3회차 원천별 추출·판정 7건을 형식·퀴즈 수정에서 재사용하는 회귀 통과. round_5/report.md §9. |
| L3-3 | 작성·발견 마찰+계약 공백 — 웹 규모(6쪽 ~6,300문단) 람다 필터가 기본 실행 예산 초과; BUDGET 진단에 소진 차원·소비·한도·처방 없음, 한도는 교재에 없음 | v3 steps 100,002. `repro/budget_filter.ibl`(6,000줄) rows 10,001·steps 99,025, details `{row_index,operation}` 뿐 | 수리됨 | BUDGET의 소진 차원·사용/한도·전건 분할 처방. 원 6,000행 재현이 rows 10,001/10,000 명시. 기본 예산 유지. |
| L3-4 | 구현 결함 — table:ai schema 2필드 이상 + 입력이 목록·빈 목록 합집합 → 정적 결과형에서 입력 필드 소실(거짓 MISSING_FIELD). L2-2 투영 인접 | `repro/ai_schema_input_fields_9/10/12` 실패 vs 1필드 8·11·단일 입력 1~7 통과. 실과제 v8 에서 schema 필드 하나 추가로 발생 → `get` 우회 | 수리됨 | 빈 목록 가지를 join할 때 정상 원소 타입 보존. schema 재현 12개 통과, 잘못된 열 거절 유지. |
| L3-5 | 문법·값 계약 공백 — `has()` 술어 filter 뒤 좁힘 없음, 처방 문구가 has 를 다시 권함(L1-2 인접) | `repro/has_narrow.ibl` MISSING_FIELD. 우회 `get(…,…,"")` | 수리됨 | has의 참 분기·filter 뒤 필드 존재 좁힘. 비null·값 타입은 추측하지 않으며 형제 경로는 유지. |
| L3-6 | 작성·발견 마찰 — `preserve_rows` 위반 진단에 누락/중복 `_i`·모델 원출력 없음 | v4(T3 ko)·v5b 1차 실패, `details:{}`, v4 실패 호출 입력 15,986·출력 144. 재시도 성공 → 원인 규명 불가 | 수리됨 | 기대/반환 행수·누락/중복/잘못된 색인 및 병합 전 파싱 모델 응답 조회 참조 보존. 재호출 없이 read_result 확인. |
| L3-7 | 계약 공백 — `number()` 해석 불가 = NUMBER_REQUIRED "산술에는…", 입력값 없음, 실패/null 계약 미문서 | `repro/number_unparsable(_try).ibl`. null 추측 수정 1주기(v6)·모델 재지불 10.2만 | 수리됨 | number 입력 미리보기·타입·유한 숫자 기대값과 실패/try-catch 계약 명시. 실제 실패·복구 확인. |
| L3-8 | 작성·발견 마찰(경미) — 괄호 안 여러 줄 식 SYNTAX "식을 읽을 수 없습니다: \n", 처방 없음 | `repro/multiline_lambda.ibl` | 수리됨 | 람다 => 뒤 줄바꿈 허용. 원 reduce 재현의 결과 6. |
| L3-9 | 작성·발견 마찰(경미) — `repeated_ai_batch` 가 input_fields 리터럴을 반복 데이터로 오경고·중복 경고 | `repro/ai_input_fields_warning.ibl` facts argument input_fields | 수리됨 | 실제 pipe_input payload만 반복 배치 분석. 설정 배열 오경고 제거, 진짜 반복 입력 경고 유지. |
| L3-10 | 작성·발견 마찰(경미) — 크롤 404 = TOOL "서버가 HTTP 오류를 반환했습니다", 상태 코드·details 없음(L1-6 웹 판) | `repro/crawl_404.ibl` | 수리됨 | 관측 HTTP 상태·URL·단계 보존 및 404 NOT_FOUND 전달. 원 위키 없는 문서로 라이브 확인. |
| L3-11 | 계약 공백(경미) — `fn:본문에서찾기` describe 매개변수 Unknown·결과 필드 없음·effects unknown, 구판 봉투(final_result 문자열), 개수가 총 적중 수를 자름 | `repro/probe_find.ibl` 관측 실행으로만 `.items` 확인 | 수리됨 | 본문 검색 입력/결과/순수 효과 계약과 match_info 승격. 기존 items/final_result 봉투 보존, 총 적중·생략 직접 확인. |
| L4-1 | 구현 결함 — 입력 값에서 추론한 확정 Null 타입이 null 가드 뒤 가지를 검사해 거절; 같은 프로그램이 입력에 따라 check·실행 거절(견고성 역전). L1-1 인접 | `round_4/repro/null_instance_type(2).ibl`: 이유 전부 null → TYPE, 혼합 → valid. p3_v1 에서 발생, 우회 `json()` | 수리됨 | 불가능한 좁힘을 내부 bottom으로 보존. p3_v1 무수정·실제 추출값과 원천 누락 추가 변형 모두 저장·재읽기 일치, 라이브 API null/혼합 정상. §8 참조. |
| L4-2 | 작성·발견 마찰+과도한 비용 — 식 자리 파이프 하나가 PURE_EXPRESSION 3건(파이프·원천·each), hint 에 순수 대안 없음. 2·3·4회차 연속 최다 작성 실수 | `repro/pure_expr_triple.ibl` 3건. p3_v0 전체 22건(원본 재계수: PURE 18건) | 수리됨 | 최초 위반 식에 한 진단, 변수 문장·reduce 대안 제공. 최소 재현 3→1, 원본 p3_v0 전체 22→9건; 별개 작성 오류 유지. |
| L4-3 | 작성·발견 마찰 — 계약상 `effects:pure` 인 지역 함수도 람다 안에서 "도구 호출은 앞 문장에" 로 거절, 통하는 형태 미안내 | `repro/pure_fn_in_lambda.ibl` | 수리됨 | 함수 호출과 도구 호출 문구 분리, 람다 반환 술어·each 본문 호출 안내. 안내 예제 실제 실행 통과, 문법 경계는 유지. |
| L4-4 | 계약 공백(경미) — sense:search `queries` 배치의 행별 `query` 태그가 observed_returns 에 없어 거짓 UNOBSERVED_FIELD | `repro/search_query_tag.ibl`, `probe_search` 실제 행에 query 있음 | 수리됨 | queries 모양 좌표 선언·동적 인자의 존재 보존. 단일 관측을 배치에 빌려주지 않음. 정적/동적 배치와 라이브 재현 경고 0, 같은 좌표의 오타 경고 유지. |
| L5-1 | 계약 공백+정직성 — PDF 본문에 문서화 안 된 `--- Page N ---` 표지, 글자 층 없는 PDF 가 표지만 든 비어 있지 않은 본문·경고 없음·source_complete true | `round_5/repro/read_pdf_edge.ibl` R11 text="\n--- Page 1 ---\n". p1_v0 가 스캔본을 "읽음"으로 모델에 넘김 | 수리됨 | `7ba5d87d` · PDF 본문 표지 제거·페이지별 글자 수/추출 불가 표지. PARTIAL_SOURCE와 Document partial 보존; 정상/스캔/혼합·선택 페이지 검증. 상세: round_5/report.md §8. |
| L5-2 | 구현 결함(정직성) — 깨진 PDF(페이지 0)가 오류 없이 빈 본문 성공, source_complete true("빈 파일"과 구별 불가) | 같은 재현 R12 text="", total_pages 0 | 수리됨 | `7ba5d87d` · 0쪽·파싱 실패는 TOOL/corrupt. catch 후 원천 실패 보존; 실제 R12 라이브 검증. 상세: round_5/report.md §8. |
| L5-3 | 계약 공백+비용 — `table:judge` 효과 `unknown` → 낀 프로그램 읽기 reuse 0(L3-1 부류) | `repro/judge_reuse_*` 0/0 vs `ai_reuse_*`(table:ai, model) 1/1 | 수리됨 | `7ba5d87d` · judge·brief 효과 model. 원 재현 읽기 1/1 복원; 모델은 재실행 유지. 상세: round_5/report.md §8. |
| L5-4 | 관측 공백(경미) — judge 사용량에 model·tier·source·call_id 없음(provider 만), L2-8 사각 | p2_main usage.model.calls[0] | 수리됨 | `7ba5d87d` · 공통 호출 범위·사용량. 실제 Jev 모델/source/call_id·tier=null, 미측정 실패 검증. 상세: round_5/report.md §8. |
| L5-5 | 문법 함정 — `+` 로 시작하는 줄이 계속이 아니라 버려지는 별개 문장; 숫자면 조용히 틀린 값(valid·결과 1·경고 0), 목록·문자열은 원인 없는 ARITHMETIC/NUMBER_REQUIRED | `repro/leading_plus_{number,list,text}.ibl`. p2_v0 이상 목록 조립에서 발생 | 수리됨 | `7ba5d87d` · 줄 첫 산술은 SYNTAX와 앞줄 끝 연산자 처방. 원 재현 3종·7연산자·음수 경계 검증. 상세: round_5/report.md §8. |
| L5-6 | 작성·발견 마찰(경미) — FORMAT_TYPE 오류에 expected/actual/details 없음 | `repro/format_type_detail.ibl` | 수리됨 | `7ba5d87d` · 기대·실제 타입 보존. Null|Text 재현과 전체 P2 검증. 상세: round_5/report.md §8. |
| L6-1 | 과도한 비용+계약 공백 — 실행 단계 예산이 식 노드당 ~1단계라 행당 레코드 생성 30~37단계 → 10만 단계 = 한 패스 ~3,000행. 2,698행 정규화 한 패스가 예산 밖, P2 도 96%. 교재에 단계 단위·행당 비용·rows 차원 관계 없음, 예산 상향 계약 없음 | `round_6/repro/budget_*.ibl` 1,000행: plain 7,005·fields 33,005·try 35,005·fn 37,006·compute 24,006·filter 4,006·groupby 18·join 21. 실과제 p1_v0 steps 100,001(rows 2,291) | 수리됨 | 명시 요청 예산(steps≤100만·rows≤10만)·교재 비용 단위. 원 정규화 2,698행 및 새 8,094행 과제 검증. 기본 상한 유지. |
| L6-2 | 작성·발견 마찰+계약 공백 — table:ai schema 필드가 input_fields 밖 기존 열과 동명이면 check 통과 → 모델 호출 뒤 TOOL "원본 필드를 변경", 필드 이름·처방 없음(L2-2 투영으로 정적 검출 가능) | `repro/ai_schema_hidden_collision.ibl`, 실과제 p1_v1(6s·6k 토큰 뒤 실패) | 수리됨 | 정적 검사+동적 핸들러에서 모델 호출 전 충돌 거절. 필드명·처방 제공. |
| L6-3 | 계약 공백+정직성 — table:judge 행 판정이 배치 구성에 의존: 같은 지시·행이 21쌍 배치 0.41/0.54/0.46(미결정) vs 6쌍 배치 0.88/0.87(참), 실행 간 변동 ±0.08. 계약에 미문서 | `repro/judge_batch_effect.ibl`, `runs/r_judge_batch21_run1/2`, `r_judge_batch6_run2`, `r_judge_instr_a/b` | 계약 보강 | 배치 문맥 계약·judgment_context·행별 호출 대안과 비용 명시. 실제 확률 안정화는 미검증. |
| L6-4 | 관측 공백 — 성공 실행 usage.steps 에 구간 귀속 없음, check 에 단계 추정 없음(preflight "each 입력 건수 미상"뿐) | p2_main usage steps 95,778 rows 1,686 | 수리됨 | usage.steps_by_span 상위 20곳+steps_other+limits. 병렬 직접 비용 합계 검사. 정적 비용 예측은 미지원. |
| L6-5 | 구현 결함(미확정) — reuse 가 candidates 를 나열하고 0건 복원, 후보별 사유 없음. run f116f1(13:11) 1/16·0/16, run 70c954a9(13:19:35) 0/4; 같은 프로그램 새 쌍 16/16(모델 포함), 재기동을 넘긴 다른 실행은 복원. 다른 세션 재기동 6회와 겹침 | `runs/r_reuse_p1_identical.json`, `varB2_p1.json`, `r_after_restart_*.json`, `r_bisect_D_full_12files_*` | 진단 수리·원인 미확정 | 미복원 이유·후보별 지문 차이 제공. 별도 프로세스 재시작 후 복원 검증. 당시 0/16 원인은 미확정. |
| L6-6 | 계약·정직성(경미) — groupby sum 이 비수치 문자열을 조용히 제외(count 는 셈), 제외 건수 미신고 | `repro/groupby_string_sum.ibl` "1,200원" 행 | 수리됨 | 기존 집계 warning이 .items 투영 뒤에도 execution_notes로 전달되도록 수리. 집계 의미 유지. |
| L6-7 | 작성·발견 마찰(경미) — table:compute target_description 빈칸, set 이 람다→레코드임을 TYPE 오류로만 발견 | `repro/compute_probe1~4.ibl`, `compute_lambda_ok.ibl` | 수리됨 | authoring_hint 데이터 선언으로 현재 람다→Record 예제를 describe에 노출. |
| L6-8 | 계약(경미) — CSV 저장에 인용 도우미 없음, 쉼표 값이 재읽기 TOOL(partial) | `runs/varB_p3v1.json` → p3_v2 인용으로 통과 | 수리됨 | self:write format:csv 직렬화·columns, 로컬/회원 기기 공용. 전체 산출물 행 재읽기 검증. |
| L6-9 | 문서 불일치(경미) — 교재 26행 "모델은 재호출" vs 같은 교재 382행 "table:ai/brief/judge 성공 결과 자동 재사용"(5회차 수리, 미커밋)이 한 문서 안에서 상충. L2-1 "미지원" 도 옛 상태 | `runs/varB_p2v4.json`(judge 확률 21개 동일·usage.model 없음), `r_bisect_C_table_ai_changed.json` | 수리됨 | 교재 첫머리를 현재 자동 모델 reuse 계약과 일치. 과거 미지원 기록은 당시 이력으로 표시. |

상태는 미확정 / 확인됨 / 수리 중 / 수리됨 / 수용된 한계로 구분한다.
원래 과제나 변형이 미검증이면 그 범위를 남기며 전체 수리 완료로 쓰지 않는다.

후속 수리(2026-09-29): L1-1~L1-7 수리 완료. 종합 **7,715 passed·1 skipped·95 deselected**, 관련 시스템 **71 passed**. 라이브 정상·누락 변형과 부분 읽기 3건 재사용 검증 완료. 구현 `674d65ee`; 관측 스윕의 독립 실행 부팅 보강과 최종 검증 기록은 이 원장 갱신 커밋에 포함한다.

후속 수리(2026-09-30): L2-1~L2-8의 공통 경계 수리. 당시 모델 출력 reuse는 미지원 계약 유지(현재는 5회차 §9 구현으로 지원). 종합 **7,775 passed·1 skipped·95 deselected**(516.60초), 관련 시스템 **71 passed**(97.54초). 원 v3/v4·16개 최소 재현·정상/후기 누락/비율 변경·입력 읽기 6건 reuse 및 라이브 모델 비용/resume 확인. 초기 1,000행 기록 1,452,346→8,395자. 실제 내부 모델 4회 입력 63,769·출력 599토큰(작업자 비용 미측정). 구현과 상세 검증은 이 원장 갱신 커밋, `round_2/report.md` §8·`repair_measurements.json`에 보존.

후속 수리(2026-09-30): 3회차 L3-1~L3-11의 구현·계약·진단·작성 경로를 보강. 크롤 6/6 reuse와 단계 참조의 후속 모델 0회 확인. 당시 자동 모델 reuse는 미지원 유지(현재는 5회차 §9 구현으로 지원). 최종 종합 7,849 passed·1 skipped·95 deselected(530.31초), 관련 system 71 passed(97.27초). 원 과제 전체의 새 실웹 모델 품질 비교는 미실시. 상세 `round_3/report.md` §8.


후속 구현(2026-09-30): 앞선 수리에서 유보한 자동 OCR·모델 출력 reuse를 구현했다.
`table:ai/brief/judge`의 같은 입력·설정 성공 결과를 수정 실행에서 자동 재사용하고,
`self:read`는 글자 없는 선택 PDF 페이지를 로컬 OCR한다. 실제 R11에서 날짜·합계 줄 인식,
라이브 Jev 1회 뒤 수정 실행은 신규 모델 0회·읽기/모델 2건 재사용(677→4ms 단일 관측).
기존의 “미지원 유지”는 당시 상태이며 현 계약은 `round_5/report.md` §9와 `system_docs/ibl.md`가 정본이다.

위 후속 구현 최종 검증: 종합 7,931 passed·0 failed·1 skipped·95 deselected(556.62초), 관련 system 71 passed(102.92초). 최종 백엔드 ACTIVE/ready.

6회차 후속 수리(2026-09-30): 공통 예산·소비 위치·schema 충돌 사전 진단·reuse 미복원 사유·집계 경고 전달·compute 설명·CSV 직렬화·교재 수리. 상세와 미검증은 `round_6/report.md` §8. 모델 배치 독립성 자체와 당시 0/16의 원인은 미확정이다.
검증: 종합 7,972 passed·1 skipped·95 deselected(624.20초), 관련 system 71 passed(100.27초), 실패 0. 실제 모델 응답은 대역, 라이브 HTTP는 백엔드 연결 거절로 미검증.
