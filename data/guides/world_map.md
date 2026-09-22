# 세계의 지도 — 지식으로 가는 카탈로그

지도는 분야·개념·방법·도구의 이름과 연결에서 알고 있는 지식을 회상하거나 검색하는 입구다.
지식 본문을 저장하는 백과사전이 아니다. 이미 적절한 접근을 돕는다.
새로운 관점·대안 제시가 의무는 아니다. 학습·연구 목적의 직접 구현과 명시 제약을 존중한다.
설치 상태·권한·현재 API는 지도 등재와 별개로 확인한다.

## 전체 어휘 조회

```ibl
[self:script]{op:"run", id:"세계지도", args:{op:"browse"}}
[self:script]{op:"run", id:"세계지도", args:{op:"browse", path:["인문"]}}
[self:script]{op:"run", id:"세계지도", args:{op:"browse", path:["인문","글쓰기와 편집"]}}
[self:script]{op:"run", id:"세계지도", args:{op:"search", query:"3차원"}}
[self:script]{op:"run", id:"세계지도", args:{op:"open", id:"blender"}}
[self:script]{op:"run", id:"세계지도", args:{op:"neighbors", id:"problem.arch_visual"}}
[self:script]{op:"run", id:"세계지도", args:{op:"ancestors", id:"method.scene_render"}}
```

query를 생략한 search는 전체 목록이다. limit은 1..50(기본 10), offset은 0부터다.
browse는 해당 경로 바로 아래의 분류와 그 경로에 놓인 어휘를 함께 반환한다.
item_type=category는 하위 분류이며 entry_count는 그 아래 전체 어휘 수다. 그 행의 browse를
다음 args로 사용한다. item_type=entry는 어휘다. path는 파일 경로가 아닌 정확한 분류명 배열이다.
이름·검색어를 모르면 최상위부터 내려간다. search 0건에서도 응답의 browse로 탐색할 수 있다.
정확한 분류명만 검색하고 어휘 일치가 없으면 그 분야 항목을 반환한다. 일반 문장의 주제어만으로 확장하지 않는다.
응답의 next를 다음 args로 쓰면 revision이 고정된다. stale_revision이면 처음부터 다시 조회한다.
open은 어휘·직접 관계·근거를, neighbors는 관계별 이웃과 방향·상태를 반환한다.
ancestors는 검토된 일반화 관계의 상위 어휘·깊이·경유 경로를 반환한다.
원문은 반환된 source.path 또는 evidence.path를 self:read로 열고 공식 URL을 확인한다.

## 자동 전달

두 길로 온다. `<method_map>` = 이름·별칭을 실제로 말했을 때 글자 일치로 잡은 어휘와 검토된 관계. `<world_map>`+`<world_memory>` = 표현이 달라도 닿는 의미 채널 — 가지 사전(`data/knowledge_catalog/branches.yaml` 의 찾는 말)으로 가지를 먼저 고르고 그 안 2건 + 밖 1건을 `분류 경로: 이름` 으로 준다. 기계가 고른 후보이니 관련 없으면 무시하고, 모자라면 `<world_map>` 의 분야에서 browse 로 내려간다.

기본으로 모든 작업 에이전트에 적용한다. 설정을 만들지 않아도 structure 모드다.
시스템·프로젝트·회원·위임 에이전트가 공통 인지 경로에서 관련 어휘를 한 번 선택하고,
이름과 핵심 관계의 같은 조각을 의식과 실행에 전달한다.
Reflex·포식 등 강제 역할·문맥 갱신에서도 적용한다. 개인 기억과 실행 권한은 별도 경계를 유지한다.
과거 에이전트 허용 목록은 주입을 제한하지 않는다. 전체 진단용 enabled=false만 명시적으로 끈다.
names는 분류와 이름만 전달하는 모드로 선택할 수 있다.

전체 지도의 크기와 자동 주입량은 별개다. 지도는 계속 확장하고, 질문에 맞는 작은 조각만 추출한다.
문자·토큰 상한은 추출 결과의 팽창을 막는 장치다. 뜻·출처·해시·조회 명령·반복 안내는 주입하지 않는다.
상세는 open에서 확인한다. 내부 검증과 근거 원장은 그대로 보존한다.
문제↔방법↔도구를 양방향 조회하며 필수 조건의 이름과 명시 적용 범위를 전달한다. 충족 여부 미확인은 내부에 보존한다.
사용자의 말만으로 설치·적용 가능·권한을 단정하지 않는다.

## 갱신

정본은 data/knowledge_catalog/world.yaml과 fragments다. kind 미검토 기존 항목은 term이다.
분야 골격은 `data/knowledge_catalog/outline.yaml`, 검색용 가지 사전은 `branches.yaml`이다.
전 분야의 어휘는 `atlas/*.yaml`·`foundation/*.yaml`·`concepts/*.yaml`에 나뉘며 모두 같은 검색을 쓴다.
`outline.yaml`의 `subfields`는 세부 주제의 골격이다. browse와 항목 벡터는 전체 경로를
쓰며, 자동 회상의 가지 선택은 앞 두 단에서 한다. 트리 전체를 프롬프트에 넣지 않는다.
골격을 먼저 검토하고 기존 어휘를 배치한 뒤 빈 가지를 채운다. 현재 분류 경로는 browse에서
확인한다. 항목 ID는 분류가 옮겨져도 유지한다.
같은 개념의 번역·약어는 별칭으로 합치고, 새 개념만 새 ID를 부여한다.
편집 초안과 외부 근거의 확인 범위는 각 항목의 source에서 확인한다.
path는 편집 분류 경로, broader는 별도로 검토한 직접 일반화 관계다.
근거와 확인일을 고치고 검토한 로컬 문서의 SHA-256을 evidence.content_hash에 기록한다.
문서가 변경되면 관계는 stale로 자동 확장에서 빠지고 색인 재생성도 재검토 전 거부한다.
외부 웹 변경을 자동 감지하는 기능은 없으므로 현재 계약은 사용 시 원문으로 확인한다.
파일 내용 바이트로 파싱을 재사용하며 내용이 바뀌면 다시 읽는다. mtime이나 파일 크기만으로
갱신을 판단하지 않는다. 검색어 정규식 캐시도 제한된 개수만 보관한다.

```bash
.venv/bin/python3 scripts/build_knowledge_catalog.py
.venv/bin/python3 scripts/build_knowledge_catalog.py --check
.venv/bin/python3 scripts/evaluate_world_map.py
```

틀린 관계를 발견하면 해당 ID·근거·정정 내용을 데이터에 반영한다. 자동 주입 사건에는
revision·context_digest·seed·관계 ID·생략 이유·추정 토큰·지연이 남는다.
토큰은 UTF-8 바이트/2 추정이며 실제 모델 청구 토큰과 다르다.
