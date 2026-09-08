# AI 팁 보고서 프로그램 재작성 — 문법 검사까지만

2026-09-09. [프로그램](program.ibl) · [검사 기록](validation.json).

사용자 지시대로 보고서 프로그램을 작성하고 구문·정적 검사까지만 수행했다. 검색, 자막 요청, 보고서용 AI 호출, 보고서 생성, 원장 갱신은 실행하지 않았다. 엔진·관용구·스케줄·운영 가이드도 변경하지 않았다.

## 범위와 입력

이전 [일괄 실행 실험](../../AI_TIPS_ONEPASS_EXPERIMENT_2026_09_08.md)의 전체 프로그램을 새 문법으로 다시 썼다. 기준일 2026-09-08, 180일 컷오프 2026-03-12, 주제 디버깅, 검색어 다섯 개를 유지했다. 오늘 발행할 호의 주제 선정은 이번 작업 범위가 아니다.

실행 시 출력 위치는 `~workspace/outputs/experiments/ai_tips_rewrite_2026_09_09/`이다. 이전 프로그램처럼 그 폴더에 `_covered_videos.json`과 `db/tips.json` **입력 복사본을 미리 준비하는 조건**이다. 이번에는 복사하지 않았다. 정확한 전후 실행 비교에는 동일한 갱신 전 스냅샷이 필요하며, 이미 실행을 마친 09-08 실험 폴더는 초기 상태가 아니다. `~workspace`는 실행 프로젝트가 정본 저장소일 때 그 경로를 가리킨다.

완주할 경우 복사본 원장·DB → 로컬 md → 로컬 HTML을 만든다. 공유창고 등재와 알림은 이전 실험과 같이 포함하지 않는다. 품질 관문 미달이면 실패 상태를 반환한다. 외부 자료 실패·AI 품질 판단·산출물의 정확성은 아직 확인하지 않았다.

## 무엇이 단순해졌는가

- 다섯 검색 문장 대신 질의 목록과 `each` 본문 하나. 공통 경로·날짜·주제는 변수로 참조한다.
- 기존 영상 제외는 `anti`, 선정 집합과의 교집합은 `semi`로 표현한다. 상세 팁을 확인할 때 같은 열이 `_2`로 복제되지 않는다.
- 조회 원장의 팁 건수는 `left join + defaults`로 한 번에 붙인다. 원장 행마다 팁 목록을 다시 검색하지 않는다.
- `select`의 구조 투영으로 팁 DB의 `source` 객체를 직접 만든다. `팁행source중첩` 스크립트와 평탄 중간 파일을 제거했다. HTML 변환은 기존 `보고서HTML`만 사용한다.
- 집계·반환 객체를 직접 구성하고, 반복문은 문자열 `do` 대신 코드 블록으로 쓴다. 조회 실패 행의 선택적 필드 정규화는 명시적으로 남겼다.

이전 실행의 자막 직렬화 실패도 반영했다. 구간 통화를 `[MM:SS] 본문`으로 모아 텍스트로 저장하고 두 번의 근거 추출이 같은 원문을 읽게 했다. `grounded`, `known`, `criteria`와 제목 선별 후 상세 추출 순서는 유지했다. 원장 기록 수·누락 ID, 장편 수, 시도 후보 수, HTML 제거 줄·링크 수 검사도 프로그램에 포함했다. HTML 계수는 실제 스크립트 반환 계약인 `items.0`에서 읽는다.

## 크기와 검사 결과

| 항목 | 이전 | 재작성 |
|---|---:|---:|
| 문자 수(주석·공백 포함) | 13,797 | 10,357 |
| UTF-8 바이트 | 17,481 | 14,608 |
| 소스의 액션 표기 수 | 81 | 65 |
| 줄 수 | 101 | 143 |

문자 수는 **24.93% 감소**했다. 긴 문자열 안에 들어 있던 코드를 여러 줄로 펼쳤으므로 줄 수는 늘었다. 액션 표기 수는 정적 소스상의 개수이며 반복 횟수·AI 내부 재시도 수가 아니다. 경로 변수화·검색 데이터화·지시문 편집도 포함된 차이이므로, 전부 이번 언어 확장의 효과라고 해석할 수 없다. 결과 품질·실행 시간·토큰 절감량은 측정하지 않았다.

- 로컬 파서, 코드 IR 컴파일, IR JSON 직렬화 왕복: 통과.
- 정적 통화·필드 검사: 오류 0, 경고 23. 검사기의 기권 없이 통과했다. 경고는 `selected`, `tip`, `how`, `tools`, `hype`, `timestamp`, `implication`, `try_candidate`, `language`처럼 AI가 생성하는 열을 정적으로 확정하지 못한 자리이며 반복 진단을 포함한다. 해당 열의 실제 존재는 실행 때 확인해야 한다.
- 실제 앱의 `POST /ibl/validate`: HTTP 200, `valid:true`, `typecheck.ok:true`. AI 액션 여섯 자리의 비용 고지는 실행 사실이 아니다.
- 보고서 프로그램 실행·보고서용 모델 호출: **0회**.

이번 작문에서 여러 줄 목록 할당과 다음 줄 머리의 `??`가 거절됐다. 목록 할당·폴백은 같은 줄로 바꾸고, 반복 몸통의 외부 목록 참조는 `items:"${선정팁.items}"`로 써 현재 검수기가 읽도록 했다. 이 표기는 목록을 문자열로 바꾸지 않고 실행 시 원형 값으로 전달한다. 엔진을 추가로 고치거나 검사 조건을 완화하지 않았다.

정본 저장소 루트에서 실행 없는 로컬 검사를 재현할 수 있다:

```sh
PYTHONPATH=backend:scripts .venv/bin/python - <<'PY'
import boot_paths
import json
from pathlib import Path
from ibl_code_ir import compile_code, pack, unpack
from api_ibl import validate_code
code = Path('docs/experiments/ai_tips_rewrite_2026_09_09/program.ibl').read_text()
unpack(json.loads(json.dumps(pack(compile_code(code)), ensure_ascii=False)))
check = validate_code(code)
assert check['valid'] and check['typecheck']['ok']
assert not check['typecheck'].get('abstained')
print(json.dumps(check['typecheck']['issues'], ensure_ascii=False, indent=2))
PY
```
