# lecture_workspace — 강의 만들기 워크스페이스

강의 슬라이드를 한 장씩 협업으로 만드는 도구. 채팅 한 줄로 데크 전체를 한 번에 생성하던 방식의 한계(매 턴 컨텍스트 재구축, 데크 수동 조작 불가, 강의자 호흡 무시)를 영구 상태 + UI 패널로 해결한다.

## 핵심 아이디어

파워포인트가 잘 하는 일을 채팅 인터페이스가 못 하는 이유는 슬라이드 데크가 **외부화된 영구 상태**가 아니기 때문이다. 이 패키지는:

1. **강의별 영구 폴더** — `indiebizOS/outputs/lectures/{lecture_id}/` 안에 `deck.json` + `materials/` + `slides/`. 닫고 다시 열어도 그대로.
2. **안정적 슬라이드 ID** — `s001`, `s002` ... 재배열은 `slide_order` 배열만 갱신 (파일 안 건드림).
3. **누적 메모** — 강의자가 거부한 톤·채택한 메타포·결정사항이 `deck.cumulative_memo`에 쌓여 다음 라운드에 반영.
4. **3패널 워크스페이스 (Step 2)** — 별도 Electron 창에서 재료/데크/AI 한 화면.
5. **가벼운 슬라이드 AI (Step 3)** — 시스템 AI 키·모델을 빌린 인지 파이프라인 우회 인스턴스.

## 저장 구조

```
indiebizOS/outputs/lectures/
└── {lecture_id}/                    # 예: harness-1bu, ganggukjinui-mulrihak-ipmun
    ├── deck.json                    # 메타·순서·누적메모
    ├── materials/                   # 원고·노트·이미지
    │   ├── 하네스_원고.docx
    │   └── notes.md
    └── slides/                      # 슬라이드별 spec + 렌더된 PNG
        ├── s001.json
        ├── s001.png
        ├── s002.json
        └── s002.png
```

`lecture_id`는 한글 제목의 자동 슬러그(한글 자모 → 로마자 약식 변환). 충돌 시 `-2`, `-3` 자동 부여.

## deck.json 스키마 (version 1)

```json
{
  "version": 1,
  "lecture_id": "haneseuran-mueotinga-1bu",
  "title": "하네스란 무엇인가? 1부",
  "audience": "일반인",
  "thesis": "AI 시대 인간의 새로운 정체성은 하네스이다",
  "duration_minutes": 60,
  "design_system": "vintage_book",
  "created_at": "2026-05-23T19:00:00",
  "updated_at": "2026-05-23T19:00:00",
  "slide_order": ["s001", "s002"],
  "slides": {
    "s001": {
      "id": "s001",
      "title": "표지",
      "layout": "hero_illustration",
      "spec_file": "slides/s001.json",
      "png_file": "slides/s001.png",
      "created_at": "...",
      "updated_at": "..."
    }
  },
  "cumulative_memo": {
    "tone_preferred": ["능동형 표현", "한 장 한 메타포"],
    "tone_rejected": ["일반 명제"],
    "metaphors_adopted": ["햄릿의 배우와 연출가"],
    "decisions": ["막간은 마지막에 배치"]
  },
  "materials": [
    {"file": "materials/하네스_원고.docx", "type": "docx", "added_at": "..."}
  ]
}
```

## IBL 액션 (Step 1: 데이터 레이어)

| 액션 | 용도 |
|------|------|
| `[self:lecture]{op: "list"}` | 모든 강의 요약 목록 |
| `[self:lecture]{op: "create", title, audience?, thesis?, duration_minutes?, design_system?}` | 새 강의 생성 |
| `[self:lecture]{op: "load", lecture_id}` | 강의 데이터 전체 로드 |
| `[self:lecture]{op: "delete", lecture_id, confirm: true}` | 강의 삭제 (확인 필수) |
| `[self:lecture]{op: "open", lecture_id?}` | 강의 만들기 창 열기 (Step 2에서 IPC 연결) |
| `[self:deck]{op: "reorder", lecture_id, order: [...]}` | 슬라이드 순서만 갱신 |
| `[self:slide]{op: "delete", lecture_id, slide_id}` | 슬라이드 삭제 |
| `[self:material]{op: "add", lecture_id, file_path \| (text + filename)}` | 재료 추가 |
| `[self:material]{op: "remove", lecture_id, filename}` | 재료 삭제 |

## 로드맵

- ✅ **Step 1** — 백엔드 데이터 레이어 + IBL 액션 9개
- ⏳ **Step 2** — Electron BrowserWindow + 3패널 React UI (재료 / 데크 / AI 채팅) + IPC 연동
- ⏳ **Step 3** — 슬라이드 생성 AI (시스템 AI 설정 빌린 가벼운 인스턴스) + slide_shadcn 연동: `slide_create`, `slide_edit` 액션 추가

## 모듈 구조

- `lecture_store.py` — 데이터 레이어 (deck CRUD, 슬러그, 슬라이드/재료 조작, 누적 메모)
- `handler.py` — ToolContext 디스패처. 도구 이름 분기 + 입력 검증 + JSON 응답
- `ibl_actions.yaml` — IBL 액션 매핑 (`self:` 노드)
- `tool.json` — 패키지 메타 + 도구 스키마
