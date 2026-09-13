# 내 어휘 메뉴 이동과 독립 폴더 창

2026-09-13. 내 어휘 진입점을 모드 선택기에서 안경 메뉴의 설정 바로 아래로 옮겼다. 기존 `indiebiz_launcher_mode=vocabulary` 저장값은 자율주행으로 돌아가므로 제거된 모드가 렌더링되지 않는다. 모바일 모드 바도 같은 경계를 따른다.

내 어휘 바탕과 폴더는 기존 도구 창 생성기를 공유한다. `/vocabulary/:folderId`를 초기 렌더 전에 해소하고 해당 폴더만 표시한다. 폴더별 창 참조를 관리해 재열기는 기존 창을 복원·포커스하고 다른 폴더는 별도 창으로 만든다. 부모 창·모달 관계가 없으며 OS 제목줄로 이동, 테두리로 크기 조절이 가능하다. 런처 안에서만 움직이던 `useFolderWindowMotion`과 고정 크기 CSS는 제거했다.

`VocabularyView`는 한 창에 한 폴더를 렌더한다. 상위 폴더 열기, 저장고 가져오기, 묶음 설명·단어소개, 분류·우클릭 작업을 유지한다. 내용이 창보다 크면 스크롤한다. 없어진 폴더를 열린 창에서 발견하면 상위 폴더로 돌아갈 수 있도록 안내한다.

마우스는 HTML 드래그 데이터를 전달해 창 사이에서 묶음을 이동한다. 터치는 같은 화면의 포인터 드래그를 유지한다. 변경 후 기존 `vocabulary-changed` 이벤트를 Electron IPC(웹은 BroadcastChannel)로 중계하며, 수신 이벤트를 재방송하지 않는다. 폴더 이름 변경은 열린 창의 제목에도 반영된다. 실제 분류·활성 변경은 기존 백엔드 API가 계속 검증한다.

## 검증

`frontend/scripts/test-vocabulary-windows.mjs`는 실제 Electron 창 생성기·preload·React 화면을 사용한다. 별도 프로필과 가짜 API 데이터로 실행하므로 사용자 활성 원장·배치는 건드리지 않는다. main.js의 백엔드·예약작업 수명도 시작하지 않는다. Vite 실행 상태에서 `node scripts/test-vocabulary-windows.mjs`로 재현한다.

- 다른 창 바깥으로 이동·크기 조절, 동일 폴더 중복 열기 방지.
- Chromium 마우스 드래그로 폴더에 넣기, 서로 다른 렌더러의 DataTransfer 전달과 양쪽 목록 갱신.
- 폴더 이름 변경의 제목 동기화, 바탕 창 종료 후 폴더 유지, 상위 폴더 재열기.
- 안경 메뉴의 설정 바로 아래 위치, 모드 선택기 제거, 웹 폴더 이동과 뒤로가기.

| 검증 | 결과 |
|---|---|
| `node scripts/test-vocabulary-windows.mjs` | 위 Electron·메뉴·웹 경로 검사 통과, 렌더러 오류 없음 |
| `npx tsc -p tsconfig.app.json` | 통과 |
| `npx vite build` | 통과 |
| `.venv/bin/python -m pytest backend/ -o addopts='' -q` | 4,198 통과, 1 건너뜀 (380.04초) |

작은 창에서의 스크롤과 안경 메뉴 배치도 스크린샷으로 확인했다. 창을 가로지르는 마우스의 OS 제스처 자체는 합성하지 않고, 출발 렌더러의 실제 dragstart에서 만든 DataTransfer를 다른 렌더러의 drop으로 전달해 검사한다. Electron 메인·preload 변경은 앱 재시작 후 적용된다.
