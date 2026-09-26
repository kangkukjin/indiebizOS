# 등록만(always_on=0) 관용구 정리 — 2026-09-26

## 실측한 문제

라이브 원장 `data/ibl_usage.db`의 이름 붙은 행 62개(상시 7 + 등록만 55)를 등록 관문·참조 스캔·
이름 채널 검색으로 훑었다.

- 등록만 55개 중 **실행 0·참조 0이 21개** — 대부분 09-04~06 자동 증류 잔재(`--promote` 이전 시대).
  수동 등록본과 뜻이 같은 쌍이 여덟(`DB표보고조회하기↔표보고조회하기`, `원장에검색결과누적하기↔원장에누적`,
  `큰원문스필로덜어요약하기↔덜어내고요지만` …). 이름 채널(`search_aliased`)은 Top-2뿐이라 어휘 항만으로
  재보면 죽은 이름이 산 이름을 밀어냈다("원장에 새 결과 누적 저장" → 잔재 0.80 > 정본 0.60).
- `retire_frozen_aliases.py`는 "얼어붙은 사건"(슬롯 0·6+·경로 리터럴)만 골라 2건밖에 못 잡았다.
- 등록 경로가 둘이고 관문이 달랐다. `register_idiom.py`(판본 1: 이름≤12자·when·슬롯·개정 이력)와
  `register_webapp_idioms.py`(판본 2: `check_source`만). **판본 1 스크립트는 판본 2 본문을 아예 못 읽어**
  판본 2 관용구 14개 전부 `--update/--refresh/--promote --when`이 불가였다.
- 가이드가 판본 2 흐름 안에서 부르는 판본 1 관용구(미처리만고르기·직전보고서찾아읽기·고치고확인하기 …)는
  legacy-envelope 다리로 실행돼 `results`·`final_result` 문자열까지 봉투 전체를 돌려줬다(실측
  `[fn:미처리만고르기]` 판본 2 호출 → 1.2KB 봉투, 값은 `.items`).
- 09-25 언어 개정(91448265)으로 catch한 외부 실패도 `source_complete:false`가 되자, 09-23의
  `ibl_v2_learning.record_functions`(`success and source_complete`)가 "자료 하나 빠지면 한계를 적고 완료"하도록
  설계된 보고서 관용구에 설계대로 동작한 턴마다 `fail_count`를 더했다(AI동향준비읽기 1/1·검색묶음추리기 1/1·
  웹앱검사하기 2/2). `test_ai_tips_report.py`의 한 시험이 옛 규약을 단언한 채 실패 중이었다.

## 변경

1. **이름 회수 26건** — 본문·이력은 그대로, `alias=''`·`tags+=retired_2026_09_26`. 백업
   `data/_backups/2026-09-26_등록만관용구정리/`(DB `.backup` + `stripped_aliases.json`, 되돌림
   `backend/retire_frozen_aliases.py --restore`). 대상: 자동 증류 잔재·동의어 쌍의 죽은 쪽 21,
   선정집 demote 사유가 결함을 적시한 채 실행 0인 4(`표보고조회하기`·`띄우고기다리기`·`행마다붙이기`·`모아서추리기`),
   `뉴스모아선별산문쓰기`(가이드가 기본 경로 아님이라 명시, 실행 0). 상시 7개와 판본 2 14개는 손대지 않았다.
   판정 근거로 남긴 두 예외: `찾아서각각읽기`(실행 3이나 상시 `좁혀서읽기`와 같은 서명·뜻),
   `패키지설치상태확인하기`(실행 1, 건축 패키지 일회성).
2. **판본 2 이식 7건** `data/idioms/legacy_port_seeds.json` — 미처리만고르기·중복빼고추리기·묶어순위내기·
   직전보고서찾아읽기(`줄수=160` 기본, `{found,path,text,candidates}`)·고치고확인하기(`{confirmed,matches,total,message}`)·
   고치고시험돌리기(`{ok,items}`)·원장에누적(`{path,count,added}`). 판본 2 호출자는 `ibl_v2_store.definitions`가
   같은 이름의 판본 2를 우선 해소하므로 다리를 타지 않는다. 판본 1 행은 판본 1 호출자를 위해 남긴다.
   실제 실행기 시험 `backend/test_legacy_port_idioms.py` 8건.
3. **`record_functions`** — 함수 성적은 함수가 값을 돌려줬는가(`event["success"]`)로 센다. 원천 불완전은
   봉투의 `source_complete`가 따로 말한다. 회귀 `test_ibl_input_abstraction.py::test_function_that_handles_external_failure_counts_as_success`.
   `test_ai_tips_report.py`의 해당 시험은 현 언어 규약(완료 + `source_complete:false` + limitations)을 단언하도록 고쳤다.
   09-25 이후 쌓인 위 관용구들의 fail_count는 소급 정정하지 않았다(어느 턴이 이 원인인지 원장만으로는 확정 못 함).
4. **`scripts/register_idiom.py` 판본 인지** — `#!ibl edition=2` 본문은 `_gates_v2`(정의 이름 일치·`check_source`·
   이름≤12자·when≥10자·필수 슬롯 0/6+ 관문; 기본값 있는 인자는 세지 않음). `--update/--refresh/--promote`는 새 본문과
   같은 판본의 행을 고르고(`_find`, 판본 2 우선), `--list`에 판본 열. `retire_frozen_aliases.py --stale-days N`은
   실행 0·참조 0·등록 N일 경과 이름도 고른다(정리 전 스냅샷에서 24/26 재현).
5. 가이드: `ai_trend_report.md`(직전보고서찾아읽기 판본 2 계약, 뉴스모아선별산문쓰기 언급 삭제),
   `webapp.md`(고치고확인하기 반환 Record).

## 남은 것 · 결정 필요

- ✅ **판본 2 이식 7건 라이브 등록 완료**(맥, 같은 날 뒷처리): id 4884~4890, 호출 용례 7건 포함 의미 색인 14,
  always_on=0, 백업 `data/_backups/2026-09-26_175432_판본2이식관용구`. 첫 적용은 호출 용례 7줄이 `category:"phrase"`
  (alias 없음)로 적혀 원장 입구가 거절했다 — 다른 시드와 같이 `composition`으로 고쳐 재적용(멱등). 라이브
  `/ibl/execute`로 `직전보고서찾아읽기`가 판본 2 정의로 해소돼 `{found,path,text,candidates}`를 돌려줌을 확인.
- 이름 채널이 상시 7개를 후보에서 빼지 않는다(이미 프롬프트에 있는 이름이 Top-2를 먹을 수 있음).
  `set_phrase_recall`을 증류 관문·귀속이 읽어서 단순 필터로 끝나지 않아 손대지 않았다.
- 같은 이름의 판본 1·2 행(`열추려보기`·`정렬해추리기`·`AI팁보고서쓰기`)은 판본별 카운터가 갈린다. `AI_TIPS_REPORT_IDIOM.md`가
  레거시 행 보존을 명시해 두었다.
- ✅ `backend/test_idiom_expansion_2026_09_09.py` 5건(3ded991b 이후 실패) 수리: 스크립트를 일반 인증하지 않고
  `판정관용구`의 모델 없는 op(`urls`·`finish`)만 본문 계약에 허용, 판정 op(`prepare`·`select`)는 계속 불허. 18 통과.
- `홈페이지갱신검토자료`는 `git log --since-as-filter`(git ≥ 2.37)를 요구한다 — 타 PC 설치 시나리오의 함정.
- 남은 등록만 판본 1 컷(각각읽고요약·잘라각각종합·덜어내고요지만·최신파일읽기·위치마다읽기·최신범위읽기)은 선정집
  demote 사유대로 명시 호출 호환용이다. 실행 0이 이어지면 다음 정리 대상.

시험: `test_legacy_port_idioms.py` 8 · 보고서 3종·웹앱·홈페이지·코드조사 85(환경상 git 버전 1건 제외) ·
`test_ai_tips_report.py` 34 · register/curate 관련 153 · 관용구 계열 333 통과(리눅스 셸, 시스템 python + requirements-core).
