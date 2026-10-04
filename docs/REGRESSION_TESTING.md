# 회귀 검사 — 개발 피드백과 최종 검증

목적은 변경이 깨뜨린 계약을 빨리 찾고, 필요한 범위의 신뢰를 확보하는 것이다.
작은 수정마다 backend 전수를 반복하지 않는다. 수집·실행은 기존 pytest 하나를 쓴다.
재발을 막는 시험은 기본 수집 경로 `backend/test_*.py`에 두고, 회차별
`docs/experiments/`에는 증거와 시험 링크를 남긴다. 문서 폴더에만 둔 시험은 기본 회귀에 포함되지 않는다.

## 개발 중

변경한 계약의 테스트와 직접 소비자·경계 테스트를 먼저 고른다. 파일 이름 일치만으로
영향 범위를 판단하지 않는다. 파서 변경이면 타입 검사·실행·저장 프로그램 소비자까지 본다.

고르는 일은 기계가 먼저 한다(2026-10-04). `scripts/select_tests.py`가 변경 파일에서 backend
import 그래프의 전이 소비자와, 변경 경로를 문자열로 가리키는 시험 파일을 모아 pytest 인수로
낸다. 선택이 시험 파일의 40%를 넘으면 `backend/`(전수)를 내고 허브 모듈을 stderr에 이름 부른다.

```bash
.venv/bin/python3 -m pytest $(.venv/bin/python3 scripts/select_tests.py --explain) -n auto --dist loadfile
```

기본은 작업 트리의 미커밋 변경이고 `--commit REV`·`--range A..B`·`--files`로 바꾼다. 선택은
영향 분석의 하한이다. 언어·격리·부트스트랩 변경은 아래 '모든 검사'를 따른다.

```bash
.venv/bin/python3 -m pytest backend/test_대상.py backend/test_관련경계.py --ff -x
```

`--ff`는 이전 실패를 먼저 실행하고 나머지도 검사한다. `-x`는 첫 실패에서 멈춘다.
관련 검사를 고르고 있는 단계에서는 전수 실행을 동시에 시작하지 않는다.

## 실패 수정

실패한 node ID를 출력에서 그대로 골라 재실행한다. 매 수정마다 전수로 돌아가지 않는다.

```bash
.venv/bin/python3 -m pytest 'backend/test_대상.py::test_실패한항목' -x
```

같은 작업의 실패 캐시를 쓸 때는 검사 범위를 명시한다.

```bash
.venv/bin/python3 -m pytest backend/test_대상.py backend/test_관련경계.py --lf --lfnf=none -x
```

`--lfnf=none`은 실패 캐시가 없을 때 전체 실행으로 바뀌는 것을 막는다. 이때 pytest는
검사 0건으로 종료 코드 5를 낸다. 검증한 것이 아니므로 위의 명시 node ID 또는 관련
파일을 실행한다. 캐시는 통과 증명이나
변경 영향 분석이 아니다. 동시 세션이 캐시를 공유한다면 명시 node ID를 우선한다.
실패 항목을 고친 뒤에는 선택했던 관련 검사 전체를 통과시킨다.

## 종합 회귀와 시스템 검사

관련 검사만으로 부족한 공통 기능 변경은 아래 종합 회귀를 실행한다. `system`으로
분리한 검사는 실제 프로세스 장애·작업자 연동·패키지 배포·대규모 데이터 전수 감사다.
분리의 이유는 느리다는 사실만이 아니라, 확인하는 계약과 변경 대상이 구분된다는 데 있다.

```bash
.venv/bin/python3 -m pytest backend/ -m "not system" -n auto --dist loadfile --ff
```

`-n auto --dist loadfile`은 pytest-xdist 병렬이다(2026-10-04 채택, `backend/requirements-dev.txt`).
`loadfile`은 한 파일을 한 워커가 통째로 맡아 모듈 범위 fixture와 파일 안 순서를 지킨다.
`pytest.ini`의 addopts에는 넣지 않는다. 관련 검사 몇 개를 돌릴 때는 워커 기동이 검사보다 길다.

다음 변경에는 해당 시스템 묶음도 실행한다. 기존 파일의 테스트·파라미터·assertion은
줄이지 않았으며, 마커 없이 파일을 직접 지정하면 모든 항목이 실행된다.

| 변경 대상 | 함께 실행할 파일/항목 |
| --- | --- |
| 재기동·프로세스 소유권·작업 수명·공통 저장소/동시성 | `backend/test_restart_process.py` |
| IBL 파서·타입·실행·값/와이어·어댑터·스크립트·권한 | `backend/test_python_libraries.py` |
| 어휘 계약·레지스트리·설치/배포·활성화·시딩·캐시 무효화 | `backend/test_vocabulary_archive.py`, `backend/test_vocabulary_bundle_split.py` |
| 세계 지도 데이터·검색·문맥 조립·선택 예산 | `backend/test_world_map_atlas.py::test_atlas_names_reach_the_selected_excerpt`, `backend/test_world_map_browse.py::test_every_entry_reachable_by_browsing_without_names` |
| v2 런타임·원장·읽기 재사용·렌더(긴문장 회차 전체 프로그램 재생) | `backend/test_long_sentence_round6_tasks.py`, `backend/test_long_sentence_round15_repairs.py::test_original_round15_full_program_recovers_without_recollecting`, `backend/test_long_sentence_round3_repairs.py::test_full_report_and_six_source_reuse` |
| 수리 스테이징·apply 수명(실 pytest 자식 배터리) | `backend/test_repair_staging.py` |
| async 본문·블로킹 호출·사용자 경로 효과(저장소 전수 스캔 관문) | `backend/test_event_loop_gate.py::test_repo_has_no_blocking_calls_in_async_bodies`, `backend/test_imagination_round74_residual.py::test_user_path_effects_gate_is_clean_on_live_tree` |
| 관용구 카탈로그·제작자 예시(전수 관문) | `backend/test_idiom_exposure_levers_2026_09_09.py::test_validate_catalog_runs_every_producer_example_through_the_gate` |

예를 들어 언어 변경은 종합 회귀 뒤 `test_python_libraries.py`를 실행한다. 재기동
장애 주입과 지도 이름 전수 감사까지 같은 변경의 대기 시간에 넣지는 않는다.
어휘 계약까지 바꿨다면 어휘 묶음도 추가한다. 여러 영역에 걸치면 해당 묶음을 모두 고른다.

## 모든 검사가 필요한 때

영향 범위를 좁힐 근거가 없거나, 테스트 격리/부트스트랩·의존성을 변경했거나,
순서 의존/프로세스 상태 오염이 의심되면 모든 검사를 실행한다. 사용자 요청·CI·릴리스도
전수를 유지한다. `system`은 기본 제외가 아니므로 기존 전수 명령·CI의 수집 범위는 같다.

```bash
.venv/bin/python3 -m pytest backend/ -n auto --dist loadfile --ff
```

문서·출력 설정만의 변경이나 영향이 한정된 기능 수정은 해당 검사와 필요한 관문으로
검증한다. 언어·어휘 변경의 빌드 정합 검사 등 기존 필수 관문은 그대로 따른다.

전수는 실패 목록을 한 번에 모은다. 실패하면 항목별로 수정·재확인하고 관련 검사를
통과시킨 뒤 전수를 다시 실행한다. 실패 하나를 고칠 때마다 전수를 새로 시작하지 않는다.
순서 의존 실패는 실패 항목 단독 통과로 닫지 않고 원래 순서/선행 테스트와 함께 확인한다.
변경·새 실패·미해결 우려가 없다면 이미 통과한 범위를 반복하지 않는다.

## 시험 파일의 자리 (2026-10-04)

재발을 막는 시험은 **모듈명 파일**(`backend/test_<모듈>.py`)에 둔다. 회차·에피소드·날짜 이름
파일(`test_*_round*_repairs.py`·`test_episode*.py`·`test_*_2026_*.py`)은 그 회차의 증거를 잇는
자리이지 계약의 집이 아니다. 2026-10-04 실측: 시험 파일 547개 중 225개가 사건 이름이었고,
v2 엔진 핵심(`ibl_v2_adapters`·`ibl_v2_compile`·`ibl_v2_runtime`)은 모듈명 시험 파일 없이
회차 파일 37개에 흩어져 있었다. 시험 함수는 08-15 90개에서 10-04 4,822개로 늘었다(주당 약
1,000건 수집 증가). 사건 파일에 쌓이면 선택기도 사람도 영향 범위를 좁히지 못한다.

새 시험을 쓸 때: 해당 모듈명 파일이 있으면 거기에, 없으면 만든다. 회차 보고서는 그 node ID를
링크한다. 기존 사건 파일을 옮기는 일은 계약 단위로 하되 본문·파라미터·assertion은 바꾸지 않는다.

## 분리 판단의 근거 (2026-10-04 추가)

10-03 기본 종합 회귀 기록: 8,624개·799초(13분 19초). 직렬이었고 12코어 중 1개를 썼다.
같은 집합을 8워커 `--dist loadfile`로 돌린 실측: 8,786개 통과·1 건너뜀·**197초(3분 17초)**.
시간은 긴 꼬리에 몰려 있었다. 10초 이상 8개가 156초(20%), 1초 이상 160개가 443초(55%),
나머지 92%는 합쳐 100초 남짓이다. 가장 큰 덩어리는 긴문장 6회차 원장 전체 재생 3개(85초)로
09-29 분리 다음 날 추가됐다.

이번에 `system`으로 옮긴 12개는 실제 프로그램 전체 재생·실 프로세스 재기동·저장소/데이터
전수 스캔이다(위 표). 본문·파라미터·assertion은 바꾸지 않았고 마커만 더했다. 기본 집합
8,774개와 system 128개의 합은 수집 8,902개와 같다. 삭제할 시험은 이번에도 찾지 못했다.

## 시험의 실 저장소 쓰기 (2026-10-04 스윕)

병렬 1회 뒤 `data/scripts/registry.yaml`이 재직렬화돼 있던 원인을 스윕으로 찾았다. 저장소
트리로 향하는 모든 쓰기(open w/a/x/+, os.replace, os.rename)를 시험 nodeid와 함께 기록하는
임시 플러그인으로 기본 집합을 돌렸다. 결과와 수리:

- 추적 파일 쓰기 1건: `test_pipe_currency_failures::test_p17_script_list_preflight`가 실
  `data/scripts/registry.yaml`·`data/scripts.json`에 시험 항목을 등록했다가 스냅샷으로 되돌렸다.
  재직렬화 외에, 되돌리기가 그 사이 라이브 몸이 등록한 항목을 덮어쓸 수 있었다. 원장 앵커를
  `tmp_path`로 돌렸다.
- `data/spill` 쓰기 1,659 경로·46MB(1회분, 66개 시험 파일). 실 스필 112K 파일·9.8GB의 최근분
  대부분이 시험 산물이었다. 스필 루트 시임은 `common/spill.py`의 `_root` 하나다(순수 코어라 `get_base_path`를 import할
  수 없어 파일 상대 앵커 유지, 층 관문). 직접 경로를 짓던 세 곳(`ibl_v2_experience`·`conscious_supervisor`·`supervision_store`)을
  `spill_dir()` 시임으로 돌리고, `conftest.py`의 autouse fixture가 시험마다 스필 루트를 `tmp_path`로
  보낸다(시험이 `get_base_path`를 돌렸으면 그 아래 `data/spill`, 회원 사설 스필은 그대로).
  ContextVar가 아니라 모듈 함수를 바꾸는 이유: 작업자 스레드는 ContextVar를 물려받지 않는다.
- 수리 뒤 재스윕: 추적 파일 쓰기 0, `data/spill` 쓰기 0. 종합 회귀 8,779 통과.
- 2차 스윕(같은 날)에서 남은 런타임 저장소 쓰기를 전부 시임으로 돌렸다. 시임은 두 종류다.
  **루트 함수**(프로세스 안에서만 쓰는 저장소): 실행 영수증 `ibl_run_journal.runs_root`, 수리 세션
  잠금·계속 기록 `repair_continuation.state_root`, 워크플로우 `workflow_store._get_workflows_path`,
  스크립트 작업공간 `script_workspace.storage_root` — `conftest.py`의 `isolated_runtime_stores`가
  시험마다 `tmp_path`로 바꾸되, 시험이 `get_base_path`를 돌렸으면 그 아래 `data/…`를 따른다.
  **환경변수 `INDIEBIZ_RUNTIME_STATE_DIR`**(프로세스를 넘는 저장소): 완료 대기 채널(CLI 어댑터와 MCP
  대기자가 다른 프로세스 — 함수 patch는 `test_long_completion` 2건이 깨졌다), 스크립트 실행 원장
  `data/script_runs`·`data/scripts.json`(패키지 `script_ops`, 정의 원장과 본문은 그대로), 쓰기 원장
  `write_ledger`, 그리고 위 루트 함수들도 이 변수가 있으면 그 아래를 본다(자식 프로세스 상속). 회상
  색인은 기존 `INDIEBIZ_RECALL_INDEX_DIR`. 환경변수는 `pytest_configure`가 워커(프로세스) 단위로
  한 번 두고(시험이 끝난 뒤에 쓰는 작업자 스레드 — 회상 색인 동기화 등 — 도 실 저장소가 아니라 여기로
  온다), `isolated_runtime_stores`가 시험 단위로 새 디렉터리를 덮는다. 시험이 모듈 전역(`_LEDGER_PATH`·
  `script_ops._STATE` 등)을 직접 바꿨으면 그 값이 환경변수보다 앞선다.
- 실행 영수증 `data/ibl_runs`는 실 저장소 957MB·37K 파일 중 매 회귀 수십 디렉터리가 시험 산물이었고,
  자식 프로세스(MCP 대기자)가 만든 sqlite까지 환경변수 시임이 걷는다.
- 남긴 것: `data/runtime/python-environment.lock`(환경 임대 잠금 파일, 데이터 아님),
  `data/guide_dates_cache.json`(가이드 날짜 캐시의 재생성, 내용 동일), `.hypothesis/`(예시 DB),
  `outputs/ibl-replay-test-*`(TemporaryDirectory, 자동 삭제).

스윕은 상설 도구다. `INDIEBIZ_TEST_WRITE_SWEEP=<로그파일>`을 주면 `conftest.py`가 저장소 트리로
향하는 모든 쓰기(open w/a/x/+, os.replace, os.rename)를 `nodeid<TAB>종류<TAB>경로`로 기록한다.
xdist에서 해시 변화를 본 시험은 쓴 시험이 아니므로 반드시 이 기록으로 주인을 찾는다. 자식
프로세스의 쓰기는 잡지 못하니 실행 뒤 `find data -newermt`로 잔존물도 본다.

```bash
INDIEBIZ_TEST_WRITE_SWEEP=/tmp/sweep.log .venv/bin/python3 -m pytest backend/ -m "not system" -n auto --dist loadfile
cut -f3 /tmp/sweep.log | grep '^data/' | sed -E 's#^(data/[^/]+).*#\1#' | sort | uniq -c | sort -rn
```

새 런타임 저장소를 만들 때는 루트 함수(또는 프로세스를 넘는 저장소면 환경변수)를 하나 두고
`isolated_runtime_stores`에 한 줄 더한다. `conftest.py`의 세션 훅이 세션 전후의 추적 파일
변경(`git status --porcelain`)을 대조해 새로 바뀐 추적 파일이 있으면 세션을 실패로 끝낸다.
병렬 실행 뒤 `git status`에 data/ 변경이 남으면 먼저 이 훅의 메시지를 본다.

## 분리 판단의 근거 (2026-09-29)

로컬 전수 JUnit 기록 7,636건·747.426초를 읽고 함수 본문 중복 후보와 고비용 검사를
검토했다. 이 실행에는 실패 2건·건너뜀 1건이 있으므로 통과 기준선은 아니다.
재기동 파일 138.21초, Python 라이브러리 42.67초, 어휘 아카이브 25.02초,
어휘 분리 배포 24.21초, 지도 이름 전수 검색 한 항목 49.754초였다.
95개 합계 약 280초(전수 벽시계의 약 37%)가 분리 대상이다.

분리 후 실제 기본 종합 회귀: **7,540 passed, 1 skipped, 95 deselected, 457.09초
(7분 37초)**. 당일 전수 기록 12분 27초보다 약 4분 50초 짧다. 검사 범위가 다른
실행의 대기 시간 비교이며 같은 전수 검사를 더 빨리 실행했다는 뜻은 아니다.
관련 시스템 검사(Python 라이브러리 전체·재기동 대표) 49개도 44.58초에 통과했다.
마커 추가 뒤 시스템 95개 전체를 새로 재실행한 것은 아니다.

수집 대조에서 기본 7,540개와 시스템 95개의 교집합은 없고, 합집합은 기존 수집
7,635개와 일치했다(모듈 수준 건너뜀 1건 별도). 다섯 시험 파일의 AST를 대조해
마커 이외의 실행 본문·파라미터·assertion 무변경을 확인했다.

삭제할 근거는 확인하지 못했다. 재기동의 before/after·상태별 장애는 서로 다른 복구
경계를 보호한다. 본문이 같은 숫자 순서 테스트도 작은 숫자 표기와 정밀도 경계라는
다른 입력을 보호하므로 중복으로 삭제하지 않았다. 이번에는 수집 마커만 추가했다.

## 시간과 보고

pytest는 기본으로 느린 setup/call/teardown 상위 항목과 전체 시간을 표시한다.
`-q`는 설정에 있으므로 호출에서 다시 붙이지 않는다. 전수 시간 자체의 최적화는
이 실측을 바탕으로 한다. 단순히 느리다는 이유로 검사를 삭제·skip하거나 assertion을
약화하지 않는다. 테스트 격리를 확인하지 않은 일괄 병렬화도 하지 않는다.

결과에는 실행 범위와 통과·실패·건너뜀, 남은 미검증을 밝힌다. 관련 검사만 통과했다면
그 범위를 적는다. 선택기로 골랐다면 선택기의 요약 줄(변경 수·선택 비율·허브)을 함께 적는다.
"전체 backend 회귀 N passed"는 전수를 실제로 돌린 때만 쓴다. 캐시·이전 커밋·다른 세션의 결과를 현재 변경의 전수 통과로 대신하지 않는다.
