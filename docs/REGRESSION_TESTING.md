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
| 봉인 세대 교체·부팅 실패 복구·제어 기반 인계(실제 프로세스) | `backend/test_restart_generation_process.py` |
| IBL 파서·타입·실행·값/와이어·어댑터·스크립트·권한 | `backend/test_python_libraries.py` |
| 어휘 계약·레지스트리·설치/배포·활성화·시딩·캐시 무효화 | `backend/test_vocabulary_archive.py`, `backend/test_vocabulary_bundle_split.py` |
| v2 런타임·원장·읽기 재사용·렌더(긴문장 회차 전체 프로그램 재생) | `backend/test_long_sentence_round6_tasks.py`, `backend/test_long_sentence_round15_repairs.py::test_original_round15_full_program_recovers_without_recollecting`, `backend/test_long_sentence_round3_repairs.py::test_full_report_and_six_source_reuse` |
| 수리 스테이징·apply 수명(실 pytest 자식 배터리) | `backend/test_repair_staging.py` |
| async 본문·블로킹 호출·사용자 경로 효과(저장소 전수 스캔 관문) | `backend/test_event_loop_gate.py::test_repo_has_no_blocking_calls_in_async_bodies`, `backend/test_imagination_round74_residual.py::test_user_path_effects_gate_is_clean_on_live_tree` |
| 관용구 카탈로그·제작자 예시(현행 정의 대조) | `backend/test_corpus_current_idiom_teaching.py::test_current_call_examples_compile_against_current_definitions`, `backend/test_idiom_exposure_levers_2026_09_09.py` |

예를 들어 언어 변경은 종합 회귀 뒤 `test_python_libraries.py`를 실행한다. 재기동
장애 주입까지 같은 변경의 대기 시간에 넣지는 않는다.
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

### 도구 로더의 선택 공급자 복원 (2026-11-11)

일반 병렬 회귀의 한 워커에서 발생한 로더 오류 26건은 테스트 순서에 따른
캐시 오염이었다. `test_program_runtime`의 도구 로더 시험은 캐시를 비우고,
뒤의 `test_member_defaults_and_delivery` 회원 IBL 시험은 `vocabulary_state.read_state`를
임시 교체했다. `active_paths`는 교체된 공급자로 패키지를 걸렀지만,
`tool_loader`의 캐시 기준은 모듈 import 때 붙든 원래 `read_state`를 호출했다.
축소된 46개 매핑을 원래 131개 선택의 결과로 저장해, 공급자를 복원해도 캐시가
적중했다. 법령 액션의 인자 계약과 주식 핸들러 조회 등 후속 소비자들이 실패했다.

캐시 기준의 `read_state`를 호출 시점에 같은 소유 모듈에서 가져오도록 수정했다.
시험마다 캐시를 무조건 지우거나 실패 검사를 제외하지 않는다. 소유자의 임시 상태를
관측하고 복원 후 다시 원래 선택으로 돌아오는 계약을 `backend/test_tool_loader.py`의
`test_mapping_and_selection_use_same_state_provider_after_restore`가 확인한다.
캐시가 빈 경우와 이미 채워진 경우, 도구 스키마·실제 핸들러 접근을 함께 검증한다.

축소 재현 순서는 다음과 같다. 전체 원인 검증에서는 마지막 두 파일 대신 최초에
실패한 26개 node ID를 같은 프로세스에서 실행했다. 수정 전 **26 실패·선행 2 통과**,
수정 후 같은 순서 **28 통과**다. 새 회귀 2건도 수정 전 각각 실패함을 확인했다.

수정 후 관련 로더·회원·프로그램 검사 51건이 통과했다. 시스템 검사를 포함한
`pytest backend/ -n auto --dist loadfile` 전수는 **13,010 통과·24 건너뜀·실패 0**
(449.69초)이며, `build_ibl_nodes.py --check`도 통과했다.

```bash
.venv/bin/python3 -m pytest \
  backend/test_program_runtime.py::test_existing_tool_loader_uses_new_submodules_without_cache_reset \
  backend/test_member_defaults_and_delivery.py::test_real_member_ibl_write_uses_member_device_and_rejects_hub_target \
  backend/test_tool_radio.py::test_favorite_play_uses_only_available_identifier \
  backend/test_stock_history_fallback.py
```

## 시험 파일의 자리 (2026-10-04)

재발을 막는 시험은 **모듈명 파일**(`backend/test_<모듈>.py`)에 둔다. 회차·에피소드·날짜 이름
파일(`test_*_round*_repairs.py`·`test_episode*.py`·`test_*_2026_*.py`)은 그 회차의 증거를 잇는
자리이지 계약의 집이 아니다. 2026-10-04 실측: 시험 파일 547개 중 225개가 사건 이름이었고,
v2 엔진 핵심(`ibl_v2_adapters`·`ibl_v2_compile`·`ibl_v2_runtime`)은 모듈명 시험 파일 없이
회차 파일 37개에 흩어져 있었다. 시험 함수는 08-15 90개에서 10-04 4,822개로 늘었다(주당 약
1,000건 수집 증가). 사건 파일에 쌓이면 선택기도 사람도 영향 범위를 좁히지 못한다.

새 시험을 쓸 때: 해당 모듈명 파일이 있으면 거기에, 없으면 만든다. 회차 보고서는 그 node ID를
링크한다. 단순 이동은 본문·파라미터·assertion을 보존한다. 계약 변경·중복 정리에서는
현행 계약과 대체 검사로 근거를 확인한 뒤 수정·통합·삭제할 수 있다. 과거 검사 수를 보존하기
위해 폐기된 동작이나 구현 모양을 유지하지 않는다.

일반 시험은 `python -m pytest`로 실행하고 `__main__`은 선택 사항이다. 직접 실행 진입점을
제공한다면 pytest로 위임한다. 순찰·CI 등 자동 호출자는 pytest의 종료 상태와 수집 범위를
확인한다. 수집 0건은 통과가 아니며 직접 파일 실행의 rc 0을 검증 영수증으로 쓰지 않는다.

## 검사 유지·통합·폐기

기능을 변경할 때 관련 검사가 지키는 **현재 계약과 실제 소비자**도 함께 확인한다.
실패한 기대값을 새 구현에 무조건 맞추거나, 오래됐다는 이유만으로 삭제하지 않는다.
다음 근거를 기존 커밋에 남기며 별도의 상시 검사 관리 시스템은 만들지 않는다.

- 계약이 유지되면 입력·결과·효과·권한·복구의 행동 검사를 보존한다.
- 같은 계약·소비자의 반복은 입력 사례를 합친다. 본문이 같아도 장치·권한·실패 경계가 다르면 유지한다.
- 폐기된 계약은 소비자가 사라졌는지 확인한 뒤 제거한다. 지원하는 저장 데이터·호환 경로의 검사는 남긴다.
- 과거 코드 조각·이름의 금지 목록은 현재의 행동·소유권 검사로 대체한다. 정확한 문구 자체가 공개 계약이 아니라면 문자열 존재만으로 기능을 입증하지 않는다.
- 검사 이름·주석·대역의 범위를 실제 assertion과 맞춘다. 인자 전달 검사는 실행 의미의 검증으로 보고하지 않는다.
- 통합 시 사례 보존을 비교하고, 강화한 검사는 의도적으로 잘못된 입력·선언을 넣었을 때 실패하는지 확인한다.

### 2026-11-04 정리 범위

기준 `deb1e0a2`의 추적 시험 파일 870개를 AST로 조사했다. 같은 스코프의 동명 시험 덮어쓰기와
동일한 리터럴 파라미터 중복은 없었고, 본문 동일 후보 6쌍을 수동 대조했다. 이는 전체 시험의
의미적 유효성 인증이 아니다. 동적 데이터·fixture·대역의 모든 실행 경로는 전수 의미 감사를 하지 않았다.

| 판단 | 반영 |
| --- | --- |
| 숫자 순서 43·44회차는 같은 소비자·assertion이고 입력만 다름 | 기존 `test_value_semantics_convergence.py`로 합침. 16개 숫자 행과 백분율·비유한수 10건 보존, 회차 파일 2개 제거 |
| 동등성의 스칼라·구조 행렬이 같은 세 소비자를 검사 | `test_value_semantics_consumer_contract.py`의 한 행렬로 16개 입력 모두 보존 |
| 값 의미론의 과거 함수명·코드 문자열 금지 검사 2개 | 제거. 현행 AST 값 판정 관문, 실제 공통 export·위임 및 횡단 행동 검사는 유지 |
| 나머지 동일 본문 후보: 서로 다른 정적 관문, PC/Chrome, 명령/환경변수, 수리 보호 책임 | 입력·대상 경계가 달라 유지. 본문 일치만으로 삭제하지 않음 |
| 필수 code 검사가 이름 존재만 확인 | 공개 schema의 required와 REST·MCP 실제 모델의 누락 거절 검사로 교체. 빈 문자열은 계속 허용 |
| 순찰 직접 실행이라는 옛 전제와 가이드 문구 존재 검사 | 선택 진입점 위임과 실제 순찰의 pytest 호출·rc 1/5 거절로 교체 |
| 앱 템플릿 시험 머리말에 판본 1·치환·노드 지정의 과거 설명 잔류 | 이미 바뀐 현재 assertion에 맞춰 설명 수정 |

검사 수 자체의 감소를 성과로 삼지 않는다. 이번 정리는 필요한 사례를 보존하면서 중복 소유와
낡은 구현 제약을 제거하고, 기존 검사 이름이 약속한 행동 검증을 보완하는 범위다.

검증: 관련 163개 통과. 통합 전후의 숫자 16개 행·추가 10건과 동등성 16개 행은 입력과
assertion AST의 동일성을 확인했다. 도구 schema·REST·MCP에서 code의 필수 선언을 각각
제거한 3개 변이는 강화한 검사가 모두 검출했다. 직접 진입점이 없는 pytest 모듈과 정상
위임은 허용하고, 시험 없이 통과만 출력하는 진입점은 거절하는 것도 확인했다.
선택기는 7/868개(1%)를 골랐지만 시험 러너 계약을 바꿨으므로 system 포함 전수를 실행했다:
`.venv/bin/python3 -m pytest backend/ -n auto --dist loadfile` → **12,530 통과·24 건너뜀·실패 0**,
453.55초. 대상 묶음은 133→132개, 추적 시험 파일은 870→868개다. Android 번들 재생성 및
IBL 정합 검사도 통과했다. 실제 모델·Windows·명시적 로컬 엔진 등 건너뛴 인수는 별도다.

## 분리 판단의 근거 (2026-10-04 추가)

10-03 기본 종합 회귀 기록: 8,624개·799초(13분 19초). 직렬이었고 12코어 중 1개를 썼다.
같은 집합을 8워커 `--dist loadfile`로 돌린 실측: 8,786개 통과·1 건너뜀·**197초(3분 17초)**.
시간은 긴 꼬리에 몰려 있었다. 10초 이상 8개가 156초(20%), 1초 이상 160개가 443초(55%),
나머지 92%는 합쳐 100초 남짓이다. 가장 큰 덩어리는 긴문장 6회차 원장 전체 재생 3개(85초)로
09-29 분리 다음 날 추가됐다.

이번에 `system`으로 옮긴 12개는 실제 프로그램 전체 재생·실 프로세스 재기동·저장소/데이터
전수 스캔이다(위 표). 본문·파라미터·assertion은 바꾸지 않았고 마커만 더했다. 기본 집합
8,774개와 system 128개의 합은 수집 8,902개와 같다. 삭제할 시험은 이번에도 찾지 못했다.

## 설치 관용구를 쓰는 시험의 준비 비용 (2026-10-28)

`installed_functions`는 워커마다 세션 시작 후 처음 필요할 때 배포 원문을 실제
`prepare`/`publish` 관문으로 한 번 설치한다. 그 카탈로그·인증 판본의 불변 바이트만
보관하고 시험마다 별도 임시 저장소에 복사한다. 각 복사본은 같은 설치 판본의 복제이며,
파일·변경 세대·추가 게시·훼손은 다른 시험과 공유하지 않는다. 하드링크나 이전 실행의
디스크 캐시는 쓰지 않는다. pytest를 새로 실행하면 현재 원문으로 다시 검사·설치한다.
설치·재인증 자체를 검증하는 시험은 여전히 실제 게시 관문을 직접 호출한다.

기존 준비는 모든 소비 시험마다 설치 전체를 다시 검사했다. 12워커 `loadfile` 전수
1,033.74초 중 PC 제어 파일 하나가 누적 1,023.29초로 마지막 워커를 붙잡았다.
이 파일은 같은 143개 항목을 유지한 관련 재검사에서 누적 21.87초가 됐다.
관련 147개 통과·1개 건너뜀, 38.76초. 격리 회귀는 `backend/test_conftest.py`에 있다.

같은 12워커 명령의 후속 **전체 검사(system 포함)는 451.14초(7분 31초)**,
11,441 통과·22 건너뜀·종료 코드 0이었다. 기존 1,033.74초보다 **56.36% 단축**됐다.
JUnit 항목 대조: 기존 시험 누락 0, 건너뜀 항목 동일, 격리 회귀 3개만 추가.
전수끼리 비교한 PC 제어 파일 누적 시간은 1,023.29 → 33.60초다. 검사 전후
추적 파일 지문은 모두 같았다. 전후 각 1회 실측이므로 기기 부하에 따른 변동은 남는다.
전체 실행 증거·파일별 시간은 [성능 기록](experiments/regression_performance_2026_10_28.json)에 있다.

## 반복 해석과 커밋 후속 관문의 비용 (2026-11-02)

관용구 설치 준비 재사용 이후에도 실행 경계마다 같은 YAML을 다시 해석하고,
Python 배포판 메타데이터를 이름 정렬·이름 읽기·버전 읽기에서 세 번 파싱했다.
`yaml_content.load_yaml`은 정확히 같은 원문만 프로세스 안에서 재사용하고 매번
깊은 복사본을 준다(최대 32개, 100만 문자 초과는 비보관). 기존 파일 읽기·판본
지문 검사·활성 필터는 유지한다. 파일명이나 수정 시각을 키로 새 캐시를 만들지
않으며 파손·변경·호출자 수정이 다른 관측에 숨지 않는다. Python 환경 지문은
조회마다 배포판 메타데이터를 한 번 읽으며 다음 조회에는 다시 읽는다.

전체 회귀가 끝나도 커밋 훅의 정합성·몸 번들·정적 관문은 별도 검사다.
`build --check`의 도구 인덱스는 한 빌드 범위에서 한 번 만들고 각 소비자에게
독립된 복사본을 준다. 빌드 종료·예외 때 범위를 닫고 다음 빌드에서는 다시 만든다.
앱 템플릿은 같은 원문·레지스트리·관용구의 컴파일 진단을 그 검사 안에서만
재사용하되 모든 원래 위치에 오류·경고를 보고한다. 컴파일 예외는 재사용하지 않는다.

커밋 훅은 IBL 정합성 검사를 나머지 관문과 병행한다. 통과 결과를 다음 커밋에
재사용하지 않으며, 정합성 자식의 종료 코드까지 확인해야 커밋을 허용한다.
다른 관문의 실패·중단 때는 미완료 자식을 종료·회수한다. 개별 관문의 내부 순서와
기존 선택 조건은 유지한다. 전수 시험 수와 필수 관문을 줄인 변경이 아니다.

원문 신선도·별칭/복사 격리·환경 지문은 `test_yaml_content.py`,
`test_python_environment_lock.py`, `test_ibl_dependencies.py`에서,
빌드 범위·출처 보존은 `test_iblbuild_v2.py`, 훅의 병행·실패·중단 처리는
`test_precommit_checks.py`에서 확인한다. 실측은
[성능 기록](experiments/regression_performance_2026_11_02.json)에 남긴다.

같은 12워커 `loadfile` 전수(system/local 포함)에서 **464.66초 → 402.43초**로
62.23초(13.39%) 줄었다. 11,866 통과·24 건너뜀에서 11,888 통과·24 건너뜀이며,
기존 항목 누락 0·건너뜀 집합 동일·추가 회귀 22개다. PC 제어·Android·계약 대조의
준비/실행 비용이 줄었지만 실제 프로세스 수명을 재는 검사 시간은 남는다.
전후 각 1회 측정이고, 라이브 HTTP 건강검사 전체 시간과 커밋 훅 전체 단축률은
이번 기록에서 측정하지 않았다. 프로파일링 시간과 일반 전수 시간을 혼용하지 않는다.

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

## GitHub Actions 실행 환경

`Seam Guards`의 전체 pytest는 macOS에서 실행한다. 실제 자기수리·코딩 쓰기 검사는
Seatbelt를 사용하고, 문서 변환 회귀에는 macOS의 textutil 경로가 포함된다. Linux에서
이 검사를 성공한 것으로 흉내 내거나 제외하지 않는다. AST·공개 라우트 등 나머지
관문은 Ubuntu에서, `Portability (3 OS)`는 Windows·Linux·macOS에서 계속 실행한다.
브라우저·PDF·차트 회귀에는 Playwright와 Chromium, matplotlib·plotly·kaleido를 설치한다.
브라우저는 설치·실행 모두 저장소의 ms-playwright를 쓰며 전체 검사 전 실제 PNG 렌더로
확인한다. 문서·시트 인수 검사를 위해 npm 의존성과 프론트엔드 빌드도 먼저 준비한다.
코드 분석 회귀는 실제 Pyright·TypeScript 서버를 사용한다. 새 checkout에서는
`npm ci --ignore-scripts --no-audit --no-fund --prefix data/code_analysis`로 잠금 파일의
서버를 설치한다. CI도 같은 명령을 실행하며 서버 선언·잠금 파일 변경을 검사 입력에 포함한다.

새 checkout에는 개인 프로젝트의 outputs, 반환 모양 관측, 관용구 DB가 없다. 회귀는
필요한 디렉터리와 관측을 fixture로 만들고, 관용구는 추적된 시드를 격리 DB에 넣는다.
`Fresh Clone Check`의 최소 빌드 의존성은 PyYAML과 실행 영수증 모듈의 filelock이다.
병렬 작업자는 부모의 임시 경로를 상속해도 각자 새 런타임 루트를 소유한다. 시스템
메모리 DB도 이 경로를 사용해 테스트 수집 중 최초 SQLite 초기화가 서로 충돌하지 않는다.
접수증 검수에는 pypdf가 필요하다. 브라우저의 새 탭 사건은 클릭 영수증보다 늦을 수
있으므로 수리 예제는 실제 탭 목록을 한정 재관측한다. 타임아웃 소유권 검사는 해제
신호까지 코루틴을 유지하고, 일회성 Git fixture는 비동기 자동 정비를 끈다.
격자 편집기는 통합문서 생성과 첫 렌더 완료를 구분한다. 브라우저 인수 시험은 초기
CPU를 느리게 해, 스크롤 컨트롤러가 서기 전에 이름 상자 입력을 받던 경합을 재현한다.

## 시간과 보고

pytest는 기본으로 느린 setup/call/teardown 상위 항목과 전체 시간을 표시한다.
`-q`는 설정에 있으므로 호출에서 다시 붙이지 않는다. 전수 시간 자체의 최적화는
이 실측을 바탕으로 한다. 단순히 느리다는 이유로 검사를 삭제·skip하거나 assertion을
약화하지 않는다. 테스트 격리를 확인하지 않은 일괄 병렬화도 하지 않는다.

결과에는 실행 범위와 통과·실패·건너뜀, 남은 미검증을 밝힌다. 관련 검사만 통과했다면
그 범위를 적는다. 선택기로 골랐다면 선택기의 요약 줄(변경 수·선택 비율·허브)을 함께 적는다.
"전체 backend 회귀 N passed"는 전수를 실제로 돌린 때만 쓴다. 캐시·이전 커밋·다른 세션의 결과를 현재 변경의 전수 통과로 대신하지 않는다.

## 키체인·대화형 승인이 필요한 검사

일반 회귀시험은 실제 로그인 키체인의 개인키를 사용하지 않는다. Mac 서명 경로는
`backend/test_helper_mac_signing.py`에서 가짜 `security`·`codesign`·빌드 도구로 검사한다.
인증서가 있다는 이유로 실제 서명 시험을 자동 활성화하지 않는다. 실서명은 사람이 연
터미널에서 `bash helper/build.sh --sign`으로 따로 수행하며, 자동 수리/pytest/비대화형
호출은 도구 실행 전에 종료 코드 77(`AUTHORIZATION_REQUIRED`)로 멈춘다.
승인 대기를 테스트 실패로 보고 반복 실행하지 않는다. 인증서 신뢰 검사 통과는 개인키의
무인 접근 가능성을 입증하지 않는다. 실서명·대상 Mac 권한·배포 미검증은 별도로 보고한다.
