# 내 어휘 묶음 분리 — 2026-09-13

기준 조사: [묶음 경계 감사](VOCAB_BUNDLE_BOUNDARIES_AUDIT_2026_09_13.md).
학술·문화·쇼핑이라는 넓은 분류 안에 함께 들어 있던 독립 기능을 실제 배포·활성 선택 단위로 분리했다.

| 이전 묶음 | 지금 선택하는 묶음 | 소유 IBL 액션 |
|---|---|---|
| study | 논문·연구자 (`study`) | `sense:paper`, `sense:researcher` |
| study | 개체 식별 (`entity-lookup`) | `sense:entity` |
| study | 세계은행 통계 (`world-statistics`) | `sense:world_bank` |
| culture | 공연·전시 (`culture`) | `sense:performance`, `sense:exhibit` |
| culture | 책·고전 (`books`) | `sense:book`, `sense:classic` |
| shopping-assistant | 상품·중고 (`shopping-assistant`) | `sense:search_shopping`, `sense:used` |
| shopping-assistant | 외주 서비스 (`freelance-services`) | `sense:freelance` |

전체 보유 묶음은 46→50개, 어휘는 165개로 유지된다. 다른 묶음의 경계는 이번에 변경하지 않았다.

## 구현과 호환

- 액션 선언과 구현을 새 폴더로 함께 옮겼다. 새 묶음은 원본 패키지의 핸들러를 호출하는 래퍼가 아니다. 책 공급자 모듈 다섯 개와 외주 공급자 모듈 하나는 내용 변경 없이 이동했다.
- 인증·HTTP·응답 포맷의 공통 기반은 계속 공유한다. 문화 응답의 HTML 엔티티·날짜 표시 정규화만 기존 공통 모듈 `backend/common/response_formatter.py`로 추출했다.
- IBL 이름·op·기존 예제·앱 정의는 유지한다. 기존 구현이 이미 받던 책의 `page`와 개체 검색의 `name` 별칭을 새 묶음 선언에 명시해 독립 배포 검증을 통과시켰다.
- `data/vocabulary_policy.yaml`의 `bundle_splits`와 `vocabulary_state.py`가 원본의 활성 선택과 폴더·쓰레기통 복원 정보를 한 번 계승한다. 이미 새 묶음을 선택한 기록은 보존한다. 파일이 뒤늦게 도착한 경우에도 실제 액션 소유권을 확인한 뒤 계승한다. 이관 선언이 없는 사전은 기존 선택을 그대로 읽는다.
- 로컬 활성 원장은 백업 후 이관했다. 기존 묶음의 선택은 그대로이며, 분리된 묶음은 각 원본의 상태를 이어받았다. 백업은 `data/_backups/2026-09-13_vocab_split/`에 있다.
- 해마 DB의 기존 IBL 코드에는 이름 변경이 필요 없다. 묶음 하나를 잠재우면 그 묶음의 액션과 해당 코드를 소유 어휘로 보는 판정만 꺼진다. ZIP으로 새 묶음을 다른 사전에 가져오는 경우에는 기존 등록·용례 시딩 경로를 사용하며 처음에는 잠든 상태다.

## 검증

분리 회귀는 `backend/test_vocabulary_bundle_split.py`에 둔다. 선택·폴더·쓰레기통 이관, 늦은 파일 도착, 기존 선택 보존, 원본 없이 ZIP 등록과 독립 프로세스 실행, 응답 통화, 액션 소유권과 폰 지원 범위를 검사한다. 외부 응답은 스텁으로 고정해 공급자 가용성과 구조 회귀를 분리한다.

| 검증 | 결과 |
|---|---|
| `.venv/bin/python -m pytest backend/ -o addopts='' -q` | 4,179 통과, 1 건너뜀 (383.56초) |
| 분리·정책 호환·관용구 노출·단일 러너 관련 7개 테스트 파일 | 93 통과 (전체 회귀에도 포함) |
| `python3 scripts/build_ibl_nodes.py --check` | 어휘·도구·폰 목록·core·배포 필터·문서 파생 정합 통과 |
| `python3 scripts/build_body_bundle.py android --check` | 엔진 번들 일치 |
| `python3 scripts/check_backend_layers.py` | 층 가드 통과 |
| 변경 전후 대조 | 165개 IBL 이름·전체 앱 정의·기존 활성 선택·기존 아이콘 위치 동일 |

이동한 기능 함수의 AST 본문도 대조했다. 실행 진입점과 공통 모듈로 추출한 표시 정규화를 제외하면 원본 함수 본문과 같다.

폰 실행 가능 액션 목록(119개), IBL fixture, 앱 정의는 분리 전과 동일하다. 폰 패키지 목록과 빌드 산출물은 새 소유권으로 재생성했다. 이번에는 연결된 Android 기기가 없어 실기기 설치·실행은 검증하지 않았다. 형제 모듈의 경로가 바뀌었으므로 변경된 배치는 백엔드 시작 시 읽힌다.
