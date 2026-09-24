# IBL 조합 검사기 수리 — 2026-09-25

[실행 조사](IBL_COMPOSITION_AUDIT_2026_09_25.md)에서 확인한 세 결함을 정본에서 수리했다.
정상 문장을 불필요하게 다시 작성하게 만드는 검사기와 실행기의 의미 불일치를 없애는 변경이다.
새 어휘·문법·상시 프롬프트를 추가하지 않는다.

## 변경

- **병렬 결과 타입**: 공통 IR의 `parallel_branches`를 검사기와 실행기가 함께 사용한다.
  연속 `&` 구문은 가지 순서대로 펼치고, 각 가지가 반환한 목록은 한 값으로 유지한다.
  이제 3개 이상의 병렬 결과도 올바른 목록 원소 타입으로 후속 필드 접근·each·flat_map에 연결된다.
  모든 가지 사이의 선언된 쓰기 자원 충돌을 누적 검사하여, 앞·중간·마지막 가지의 중복 쓰기도 차단한다.
- **case의 조기 반환**: `if`와 `case`가 공통 `merge_continuations`로 다음 문장에 도달하는
  경로들의 변수 환경만 합친다. return한 가지에 변수가 없다는 이유로 정상 경로를 거절하지 않는다.
  return하지 않은 경로 중 하나라도 변수가 없으면 계속 `UNBOUND`로 거절한다.
- **try/catch의 조기 반환**: 정상/예외 경로도 같은 합성 규칙을 사용한다.
  catch가 반환한 뒤에는 try의 성공 변수를, try가 반환한 뒤에는 catch의 변수를 후속 문장에서 사용할 수 있다.
  `finally`는 반환 경로도 통과하므로 별도 환경으로 검사하고, 정리 블록의 변수 변경은 후속 환경에 반영한다.
  안쪽 catch가 끝나면 바깥 `$error`의 검사 환경도 복원해 실행기의 스코프와 맞춘다.

실행기의 데이터·반환·예외 의미는 유지한다. 병렬 구문 순회만 공통 함수로 추출했고,
나머지는 컴파일 단계의 타입·변수 분석 수리다. 기존 실패·권한·취소·예산 경계를 우회하지 않는다.

## 검증

새 회귀 파일 `backend/test_ibl_composition_repairs_2026_09_25.py`에 기존 조사 코어 27개와
추가 경계 사례를 넣었다. 최초 48개 테스트는 수리 전 21개 실패/27개 통과했고,
수리 후 기존 코어·작성 지원 회귀와 함께 163개가 통과했다. 이후 each 안의 return 스코프와
바깥 `$error` 복원 사례 2개를 더하여 새 회귀는 총 50개다.

| 검증 | 결과 |
| --- | --- |
| 조사 프로브: 코어 27개 | 27/27 통과 |
| 코어·HTTP·실제 파일·저장 관용구 조합 | **57/57 통과** — 수리 전 37/57 |
| 현재 저장 함수 정적 검사 | 11개 모두 오류 없음; 미확정 도구 경계는 `incomplete` 유지 |
| backend 전체 회귀 | 5,912 통과·1 실패·1 모듈 스킵; 실패는 아래 테스트 진입점 보완으로 해소 |
| 보완 후 영향 범위 재검사 | 러너 규약 4개 + 새 회귀 50개 = **54개 통과** |
| 새 회귀 파일 직접 실행 | **50개 통과** |
| 어휘·도구·문서 파생물 검사 | `build_ibl_nodes.py --check` 통과 |
| 폰 번들 | `build_body_bundle.py android` 재생성; 모듈 구성 변화가 없어 파생 파일 diff 없음 |

전체 검사에서 새 테스트 파일에 `__main__`이 없어 직접 실행 시 테스트를 건너뛸 수 있다는
`test_single_runner` 규약 위반 1건을 발견했다. pytest로 위임하는 진입점을 추가하고
관련 54개 및 파일 직접 실행 50개를 다시 통과했다. 이 보완은 테스트 진입점에만 적용했고,
운영 코드는 전체 검사 이후 변경하지 않았다. 전체 8분 46초 검사를 다시 돌린 것으로 보고하지 않는다.
모듈 스킵 1개는 기존 `test_narration_injection`의 로컬 음성·Playwright 전용 시험이다.

추가 회귀는 2/3/4/8개 가지, 좌우 괄호, 함수가 반환하는 병렬 목록, 모든 위치의 쓰기 충돌,
여전히 미정의인 변수 거절, 중첩 case 반환, 성공/실패 양쪽의 finally 실행,
finally가 바꾼 Record 필드와 바깥 오류 스코프를 확인한다.
실행 중인 백엔드가 재기동된 뒤 HTTP 프로브도 같은 결과를 확인했다.

## 재현

```bash
.venv/bin/python3 -m pytest backend/test_ibl_composition_repairs_2026_09_25.py
.venv/bin/python3 scripts/probe_ibl_composition_2026_09_25.py \
  --live --library --output outputs/composition_repair_2026_09_25/probes.json
.venv/bin/python3 -m pytest backend/ -o addopts='' -q --tb=short \
  --junitxml=outputs/composition_repair_2026_09_25/pytest.xml
.venv/bin/python3 scripts/build_ibl_nodes.py --check
.venv/bin/python3 scripts/build_body_bundle.py android --check
```

증거는 `outputs/composition_repair_2026_09_25/`의 `before.log`, `focused.log`,
`core_probes.json`, `probes.json`, `pytest.log`, `pytest.xml`, `recheck.log`, `recheck.xml`,
`direct.log`, `build_check.log`, `body_build.log`에 남긴다.
HTTP는 합성 입력과 임시 파일을 사용한다. 저장 함수 실행은 정상 영수증·사용 실적을 남긴다.
자연어 작성 품질·외부 AI 응답 품질·전체 토큰/시간 개선·폰 실기기 실행은 이 수리에서 측정하지 않았다.
