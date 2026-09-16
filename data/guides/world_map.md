# 세계의 지도 — 지식으로 가는 카탈로그

지도는 분야·개념·방법·도구의 이름과 연결에서 알고 있는 지식을 회상하거나 검색하는 입구다.
지식 본문을 저장하는 백과사전이 아니다. 이미 적절한 접근을 돕는다.
새로운 관점·대안 제시가 의무는 아니다. 학습·연구 목적의 직접 구현과 명시 제약을 존중한다.
설치 상태·권한·현재 API는 지도 등재와 별개로 확인한다.

## 전체 어휘 조회

```ibl
[self:script]{op:"run", id:"세계지도", args:{op:"browse"}}
[self:script]{op:"run", id:"세계지도", args:{op:"browse", path:["인문"]}}
[self:script]{op:"run", id:"세계지도", args:{op:"browse", path:["인문","글쓰기","퇴고"]}}
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
path는 편집 분류 경로, broader는 별도로 검토한 직접 일반화 관계다.
근거와 확인일을 고치고 검토한 로컬 문서의 SHA-256을 evidence.content_hash에 기록한다.
문서가 변경되면 관계는 stale로 자동 확장에서 빠지고 색인 재생성도 재검토 전 거부한다.
외부 웹 변경을 자동 감지하는 기능은 없으므로 현재 계약은 사용 시 원문으로 확인한다.

```bash
.venv/bin/python3 scripts/build_knowledge_catalog.py
.venv/bin/python3 scripts/build_knowledge_catalog.py --check
.venv/bin/python3 scripts/evaluate_world_map.py
```

틀린 관계를 발견하면 해당 ID·근거·정정 내용을 데이터에 반영한다. 자동 주입 사건에는
revision·context_digest·seed·관계 ID·생략 이유·추정 토큰·지연이 남는다.
토큰은 UTF-8 바이트/2 추정이며 실제 모델 청구 토큰과 다르다.
