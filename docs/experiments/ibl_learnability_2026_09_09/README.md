# 작성 규칙 정리 후 AI 팁 보고서 예제

2026-09-09. [프로그램](program.ibl) · [정적 검사 기록](validation.json) · [언어 변경 설명](../../IBL_LEARNABILITY_2026_09_09.md).

이전 [재작성본](../ai_tips_rewrite_2026_09_09/README.md)의 기준일·검색어·품질 기준을 유지했다. 이번 프로그램은 실행하지 않았다. 검색·자막 요청·보고서용 모델 호출·보고서 생성·원장 갱신은 0회다.

변경은 여러 줄 질의 목록, 다음 줄의 폴백, 반복문 안 외부 목록의 직접 참조, 일반 `$return=[{...}]`로 원장·DB 객체 구성, 자막 원문의 JSON 보존, AI 결과의 schema 선언이다. 자막을 `[MM:SS]` 텍스트로 조립하던 reduce를 없앴다. schema의 필드 존재 검사는 코드가 맡으며 의미 품질의 criteria는 유지했다.

| 항목 | 앞 재작성본 | 이번 예제 |
|---|---:|---:|
| 문자 수(공백·주석 포함) | 10,357 | 10,459 |
| 줄 수 | 143 | 156 |
| 정적 오류 | 0 | 0 |
| 정적 경고 | 23 | 0 |

102자 늘었다. 새 필드 선언과 일반 참조 표기도 포함된 수치다. 이번 목적은 짧게 압축하는 것이 아니라, 같은 표기로 값을 만들고 검사할 수 있게 하는 것이다. 경고 0은 이 예제에 명시된 필드 계약을 검사기가 읽었다는 뜻이며, 실제 자료와 AI 출력의 품질을 검증했다는 뜻은 아니다.

구문 파싱·코드 IR 컴파일·JSON 직렬화 왕복과 로컬 검수기를 통과했다. 검사기 기권은 없다. 재현은 정본 저장소 루트에서 아래처럼 한다. 실제 앱의 `/ibl/validate`도 HTTP 200, valid/typecheck.ok가 true이며 오류·경고 0이었다.

```sh
PYTHONPATH=backend:scripts .venv/bin/python - <<'PY'
import boot_paths
from pathlib import Path
from api_ibl import validate_code
code = Path('docs/experiments/ibl_learnability_2026_09_09/program.ibl').read_text()
result = validate_code(code)
assert result['valid'] and result['typecheck']['ok']
assert not result['typecheck']['issues']
assert not result['typecheck'].get('abstained')
PY
```

나중에 실행하려면 `~workspace/outputs/experiments/ibl_learnability_2026_09_09/`에 갱신 전 `_covered_videos.json`과 `db/tips.json` 입력 복사본을 준비해야 한다. 이번에는 준비하거나 실행하지 않았다. 완주 시 그 복사본과 로컬 Markdown·HTML만 갱신하는 기존 실험 범위를 유지했다. 운영 발행·공유창고·알림은 포함하지 않는다.
