# 관용구 노출 실험 증거

실행일: 2026-09-09. [결과 보고서](/Users/kangkukjin/Desktop/AI/indiebizOS/docs/IBL_IDIOM_EXPOSURE_RESULT_2026_09_09.md), [생성 전 계획](/Users/kangkukjin/Desktop/AI/indiebizOS/docs/IBL_IDIOM_EXPOSURE_PROTOCOL_2026_09_09.md).

## 자료 구분

| 파일 | 내용 |
|---|---|
| manifest.json | 생성 전 과제·순서·모델·제한·프롬프트/소스 해시 |
| registry.json | 두 조건에 공통으로 등록한 운영 DB의 관용구 본문·서명 |
| exposure_delta.txt | 두 프롬프트 사이의 실제 차이, 앞 구분 줄바꿈 포함 |
| compact_trials.json | 54개 과제 실행의 전체 시도 코드·사용량·판정·결과; 파싱 실패 응답도 보존 |
| trial_metrics.csv | 과제 단위 비용·호출·초기 오라클 점수; 사후 감사 점수는 audit_summary.json |
| summary.json | 초기 오라클 기준 전체/과제/종류/관용구 집계와 짝 비교 |
| audit_summary.json | 실행 관문 재생 비교와 사후 요구 충족 판정 |
| oracle_difference_examples.json | 초기/사후 판정이 다른 11개 시도의 코드·실행 결과·실제 파일 |
| composition_contract_audit.json | 최신범위읽기 이름 호출/정확한 몸 전개/명시적 반환값 추출의 비교 |
| grep_probe.json | 별도 탐색적 진단 3회; 계획 수정 시점·소스·코드·결과 포함 |
| validation.json | 기준 코드·잘못된 코드·감사 대조·회귀 검사 결과 |
| frozen_sources.json | 생성에 사용한 당시 study/cases/worker 소스; 서식 정리 이전 |
| audit_sources.json | 실행 관문·요구 충족 감사의 당시 소스 |
| execution_source_hashes.json | 생성 시 참조한 실행 소스 해시 |
| integrity_after_generation.json | 모델 생성 완료 후 소스·프롬프트·엔진 드리프트 검사 |
| formatting_equivalence.json | 서식 정리 후 생성 관련 3개 소스의 AST 동등성 |

## 수치를 읽을 때

- `first_ok`/`final_ok`는 **초기 오라클**이다. 결과물 기준 사후 평가는 `audit_summary.json`의 `first_requirement_ok`/`final_requirement_ok`다. 원점수를 덮어쓰지 않았다.
- `first_raw_named`는 응답 원문에서 이름 호출을 작성한 시도다. `first_named`는 바깥 응답 파싱을 통과한 코드의 호출, `first_executed_named`는 실행에서 관측한 호출이다. 원문만 있는 호출은 수동으로 확인했다.
- 세 비노출 수리의 사용량이 시간 초과로 없다. 수리 포함 합계는 `summary.json → groups → all → attempt_usage`의 `known_sum_lower_bound`/`exact_total`을 사용한다. 단순 과제 통계의 `output_tokens.sum`은 일부 사용량이 없는 과제 전체를 제외하므로 전체 소비량으로 인용하면 안 된다.
- 첫 생성 54회는 사용량이 모두 알려져 있다. 사고는 출력 토큰에 이미 포함된다. 입력 합계에는 신규·캐시 생성·캐시 읽기를 포함하며 주·보조 모델을 합친다. 원시 토큰 합계는 결제 금액이 아니다.
- 첫 `first_wall_s`는 모델 프로세스 시간이다. 수리 포함 `wall_s`에는 모델과 IBL 실행 시간이 들어간다.
- 실패와 미사용도 포함한 배정 조건 전체를 비교한다. 성공한 호출만 골라 비교하지 않는다.
- 과제별 재표집 구간은 과제 틀이 적을 때 퇴화할 수 있다. 보고서의 일반화 한계에는 전체 9개 과제 틀을 묶어 재표집한 구간을 사용했다.

## 재현 범위

전체 원본은 `/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/idiom_exposure_2026_09_09_v1/`, 보조 진단은 `/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/idiom_exposure_2026_09_09_grep_probe/`에 있다. 저장소에는 검토에 필요한 코드를 포함한 축약 증거를 넣었고, 큰 운영 프롬프트와 원본 CLI 응답 전체는 로컬 원본에 남겼다. 프롬프트 해시만으로 원문을 복원할 수는 없다.

현재 `scripts/idiom_exposure_{cases,worker,study,report}.py`는 당시 실험 전용 도구다. 생성 후 Python 서식만 정리했으며, 당시 소스는 JSON 안에 보존했다. 감사 소스는 당시 고정 소스를 기준으로 동작한다. 수리 피드백을 이미 제공한 뒤 판정 오류를 발견했으므로, 사후 감사로 수리 횟수·비용을 다시 산출하지 않는다. 과거의 초기 오라클을 향후 범용 품질 검사로 그대로 채택해서는 안 된다.

이 자료를 집계·검토하는 데 모델 호출은 필요 없다. 새 생성 실험은 추가 사용량을 소모하며 같은 출력의 재현을 보장하지 않는다. 운영 엔진·언어·노출 설정에는 이번 실험의 수정 사항이 없다.
