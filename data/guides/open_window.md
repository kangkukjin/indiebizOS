# 런처 창 열기 가이드

`[limbs:open_window]` 단일 액션으로 IndieBiz OS Electron 런처의 7개 메인 작업창을 연다. **app 분기**가 핵심.

`[limbs:os_open]`(OS 기본 앱) · `[limbs:show_map]`(지도) · `[limbs:explorer]`(파일 탐색기)와 다름. 이 액션은 **IndieBiz OS 자체의 작업공간**만 다룬다.

---

## 7개 작업창 — 무엇이 무엇인가

| app | 무엇 | 언제 여는가 |
|---|---|---|
| `project` | 특정 프로젝트의 에이전트 대화 창 | 사용자가 "프로젝트 X 열어줘", "투자 프로젝트 가자" |
| `system_ai` | 시스템 AI(IndieBiz 관리자) 대화 창 | "시스템 AI", "설정", "전체 점검" |
| `messenger` | 사적 통신 — 이웃과의 DM 스레드·연락처 (채널 통합 Gmail/Nostr, 옛 이웃관리) | "메신저 확인", "메일 봐줘", "OO에게 온 메시지" |
| `community` | 공개 통신 — IndieNet(Nostr) 팔로잉 피드·게시판 (옛 IndieNet 창의 후신) | "인디넷 열어", "커뮤니티", "피드 봐줘" |
| `business` | 비즈니스 관계·이웃·연락처·메시지 | "이웃 관리", "비즈니스", "거래처 메모" |
| `multichat` | 여러 에이전트와의 동시 대화방 | "멀티 채팅", "팀 회의실", 협업 대화 |
| `folder` | 사용자 지정 폴더(연락처·프로젝트·메모 등) 빠른 접근 | "즐겨찾기 폴더", "구매 폴더" |

이 7개가 IndieBiz OS의 **메인 작업공간 진입점** 전부다. 그 외 화면(슬라이드·라디오·캘린더 등)은 *프로젝트 창 안*에서 다룬다.

> 통신 두 창의 구분: **수신자가 특정인(주소 지정)이면 메신저, 공개(방송·구독)면 커뮤니티.** DM은 메신저 소관.

---

## 파라미터 (app별로 다름)

| app | 필수 | 옵션 | 동작 |
|---|---|---|---|
| `project` | `project_id` | `project_name`, `agent_name` | 프로젝트 작업창. agent_name 주면 그 에이전트 활성화 상태로 |
| `system_ai` | — | — | 단일 창. 옵션 없음 |
| `messenger` | — | — | 단일 창. 옵션 없음 |
| `community` | — | — | 단일 창. 옵션 없음. (레거시 별칭: `indienet`) |
| `business` | — | — | 단일 창. 옵션 없음 |
| `multichat` | `room_id` | `room_name` | 특정 멀티채팅 방. room_id 없으면 빈 창 |
| `folder` | `folder_id` | `folder_name` | 특정 폴더 화면. folder_id 없으면 폴더 목록 |

> 단일 창인 system_ai/messenger/community/business는 이미 열려 있으면 포커스만. 새 인스턴스 안 만듦.

---

## 표준 사용

### 1) 프로젝트 작업 시작
```
[limbs:open_window]{app:"project", project_id:"투자"}
```
agent_name까지 주면 바로 그 에이전트로:
```
[limbs:open_window]{app:"project", project_id:"투자", agent_name:"포트폴리오 매니저"}
```

### 2) 시스템 AI 대화
```
[limbs:open_window]{app:"system_ai"}
```

### 3) 외부 메시지 점검 (DM·이메일)
```
[limbs:open_window]{app:"messenger"}
```

### 3-b) 커뮤니티 (피드·게시판)
```
[limbs:open_window]{app:"community"}
```
(레거시 `app:"indienet"`도 커뮤니티 창으로 라우팅됨 — 옛 IndieNet 창의 후신)

### 4) 비즈니스/이웃 관리
```
[limbs:open_window]{app:"business"}
```

### 5) 멀티채팅 방 열기
```
[limbs:open_window]{app:"multichat", room_id:"daily_briefing"}
[limbs:open_window]{app:"multichat"}    # 방 목록부터
```

### 6) 폴더 즐겨찾기
```
[limbs:open_window]{app:"folder", folder_id:"구매_2026"}
```

---

## 사용자 의도 매핑 (RAG 힌트)

자연어 표현 → 어느 app이 맞는지 자주 헷갈리는 경우:

| 사용자 말 | app |
|---|---|
| "투자 프로젝트 가자" / "법률 작업 시작" | `project` (project_id로 분기) |
| "전체 설정", "내 IndieBiz 점검" | `system_ai` |
| "메일 확인", "OO에게 온 메시지", "외부 메시지" | `messenger` |
| "인디넷", "커뮤니티 피드", "게시판 봐줘" | `community` |
| "이웃 연락", "거래처 정리", "비즈니스 관계" | `business` |
| "팀 회의실", "여러 명이랑 대화", "에이전트 협업방" | `multichat` |
| "자주 보는 폴더", "구매 폴더" | `folder` |
| "강의 만들기 창" | `[self:lecture]{op:"open"}` — 이 액션 아님 |
| "캘린더", "일정 보기" | 앱 모드의 `calendar` 계기 — 이 액션 아님 |

`lecture_open`이 별도 액션인 이유: 강의 워크스페이스는 일반 메인 창과 다른 전용 UI(slide 데크 + 재료 + AI 명령 3패널)라 lecture_workspace 패키지가 자체 윈도우 생성을 관리.

---

## 자주 하는 실수

- **app 오타**: `project` / `system_ai` / `messenger` / `community` / `business` / `multichat` / `folder` 정확히. `projects`(X), `mail`(X), `chat`(X). (`indienet`=`community` 레거시 별칭으로 동작)
- **`project`에 project_id 누락**: 빈 창 열리고 사용자가 다시 선택해야 함. project_id 주는 게 자연스러움.
- **system_ai/messenger/business에 파라미터 줌**: 무시됨. 단일 창.
- **lecture 창과 혼동**: 강의 만들기 창은 `[self:lecture]{op:"open"}`. 이 액션의 app 목록에 없음.
- **Launcher WS 미연결**: Electron 런처가 실행 중이고 WebSocket 연결돼 있어야 동작. 백엔드만 켜진 상태에선 "Launcher WS 미연결" 에러. dev 모드에선 보통 문제 없음.

## 관련

- `[self:lecture]{op:"open"}` — 강의 워크스페이스 (별도 윈도우)
- `[limbs:os_open]` — OS 기본 앱(브라우저/Finder)으로 URL/파일 열기. IndieBiz 작업창 아님.
- `[limbs:explorer]` — 파일 탐색기 열기
