# 어휘 파일 `.iblpack` 1판

런처 → **내 어휘**에서 **단어묶음 저장고**를 우클릭해 **파일 가져오기**를 누른다. 묶음을 보낼 때는 그 아이콘을 우클릭해 **내보내기**를 고른다.
가져온 묶음은 잠든 상태로 보관된다. 준비가 끝난 묶음의 **깨우기**를 누르면
이 몸의 AI가 사용할 수 있다. **잠재우기**는 파일·설정·용례·벡터를 보존한다.
실행 중인 작업이나 상주 프로세스를 중단하지 않으며 메모리 회수를 보장하지 않는다.

## 파일 계약

ZIP 안에 `manifest.json`, `ibl_actions.yaml`, `handler.py`, `examples.json`이 필수다.
추가 형제 모듈·정적 자원은 상대 경로로 포함할 수 있다. `tool.json`은 동봉할 필요가
없고 어휘 정의의 `tool_json.header`/`tool_json.tools`에서 기존 빌더가 파생한다.
동봉했다면 파생 결과와 같아야 한다. 코드와 용례를 검사한 뒤 등록하며 가져오기 중
핸들러를 import하지 않는다. 깨우기는 코드 실행을 허용하는 사용자의 선택이다.
파일 지문은 무결성 검사이며 제작자의 신뢰성을 보증하는 서명은 아니다.

```json
{
  "format": "iblpack",
  "format_version": 1,
  "id": "my-vocabulary",
  "version": "1.0.0",
  "name": "나의 어휘",
  "description": "이 묶음으로 할 수 있는 일",
  "dependencies": {},
  "requires_modules": [],
  "requires_env": [],
  "files": {
    "ibl_actions.yaml": "파일 바이트의 SHA-256",
    "handler.py": "파일 바이트의 SHA-256",
    "examples.json": "파일 바이트의 SHA-256"
  }
}
```

`files`에는 manifest 자신을 제외한 모든 파일을 선언한다. 제작 시
`vocabulary_archive.pack(manifest, files)`가 목록과 지문을 생성한다. ID는 영숫자·밑줄·
하이픈이며 버전과 의존 버전 조건은 Python packaging의 Version/SpecifierSet 형식이다.
선언된 직접 의존성만 검사한다. 의존 묶음·라이브러리를 자동 설치하거나 깨우지 않는다.
공유 액션은 `router: handler`로 동봉 구현에 연결한다. 새 PC 묶음은 `runs_on: pc_only`를
선언한다. 폰 지원은 기존 몸 검증 규약을 따른다. `execute(tool_input, context)`가
핸들러 진입점이다. 어휘 fragment의 자세한 형식은 `data/system_docs/packages.md` 참조.

`examples.json`은 설명 문서가 아니라 실제 시딩 데이터다.

```json
[
  {
    "intent": "사용자가 이 어휘를 필요로 하는 자연어 의도",
    "ibl_code": "[sense:my_action]{}",
    "nodes": "sense",
    "category": "single",
    "difficulty": 1,
    "tags": "예시,주제"
  }
]
```

배포자가 선정한 용례를 `add_examples_batch(..., owned_vocabulary=True)`로 넣는다.
소유 판정은 잠든 보유 어휘를 허용하며, 실행용 회상은 활성 사전으로 별도 필터한다.
시딩 출처는 묶음 ID와 내용 지문으로 기록한다. 같은 파일은 중복 등록·시딩하지 않고,
같은 ID의 다른 내용/버전은 덮어쓰지 않고 충돌을 알린다. 자동 업그레이드는 1판 밖이다.

## 기존 묶음과 공유 경로

manifest가 없는 기존 묶음은 Python 소스·루트 README/requirements/package.json·어휘
정의만 자동 포장한다. `examples.json`이 없으면 어휘의 공개 fixture를 시딩 용례로
사용한다. 용례가 없는 묶음은 제작자가 보완해야 한다. 코드 외 자원은 제작자가
manifest의 파일 목록에 명시해야 한다. 개인 코퍼스·키·계정 설정을 자동 수집하지 않는다.

새 파일은 최대 20MB, 해제 총량 100MB, 파일 512개다. 경로 탈출·링크·중복 경로·
파일 손상·정의 충돌을 거절한다. 등록 실패 시 이번 파일·사전집·선택·시딩만 회수한다.
프로세스 강제 종료/전원 장애를 넘는 다중 파일 트랜잭션 복구는 구현하지 않았다.

옛 `===PACKAGE_START===` 텍스트는 메모리에서 변환한 뒤 같은 등록 경로로 보낸다.
어휘 정의나 시딩 용례가 부족하면 제작자 보완을 요구한다. 옛 텍스트를 새로 생성하거나
그 안의 설치 설명을 AI에게 실행시키지 않는다. Nostr는 `IBLPACK/1` + Base64로 같은
ZIP을 운반한다. 현재 게시 API의 50,000자 한도를 넘으면 파일 전달을 안내한다.
실제 게시·전송은 사용자가 요청할 때만 한다.

## 구현 경계

보유 정본은 기존 두 폴더의 합집합이다. 사전집은 보유 전체를 담고 활성 선택은
`data/vocabulary/activation.json` 하나다. 최초 이관에서만 폴더 위치를 읽는다.
필수 보호는 `data/vocabulary_policy.yaml`이다. `core_manifest.json`은 배포 출처다.

스위치는 빌드 없이 공통 캐시를 갱신한다. 새 파일 등록은 `scripts/iblbuild_catalog.py`가
기존 빌더의 수집·병합·파생·검증 함수를 재사용한다. Electron 배포에도 이 스크립트들을
포함한다. 폰의 선택은 로컬 원장을 쓰지만, 이 1판의 파일 가져오기 컴파일 경로는 PC용
Python 서브프로세스 기반이다. Android에서 파일 가져오기는 별도 지원이 필요하다.

검증: `backend/test_vocabulary_{policy,state,lifecycle,archive}.py`.
전체 계획과 범위: `docs/VOCAB_LEGO_PLAN_2026_09_13.md`.
