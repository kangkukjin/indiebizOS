# 몸 변화 회상 — [self:body]

내 몸(indiebizOS 저장소)의 파일들이 **언제 어디서 생기고, 바뀌고, 옮겨졌는지**를 git 원장에서 읽는 어휘. 원장은 git 이 이미 쓰고 있다 — 이 어휘는 쓰지 않는 **회상 통로**다(전 op 읽기 전용).

배경: 2026-08-05 백엔드 층 분리 같은 "몸 개조"가 회상 불가능해, 몸을 만지는 도구의 낡은 가정이 몇 주씩 잠복했다(grep 방언 사건). 몸이 바뀌면 몸에 대한 가정이 깨진다 — 변화 자체가 연상 가능한 기억이어야 한다.

## op 5종

| op | 무엇 | 주요 파라미터 |
|----|------|--------------|
| `changes` (기본) | 최근 **파일 단위** 변화 — 미커밋 작업분 포함 | `days`(기본 7) · `path`(스코프) · `limit` |
| `log` | **커밋 단위** 이력 — "무슨 일을 했나" | `days` · `path` · `limit` |
| `file` | **한 파일의 일생** — 생성·수정·이동을 `--follow` 로 관통 | `path`(필수) · `limit` |
| `writes` | **런타임 쓰기 원장** — git 밖 층(data/·outputs/)의 쓰기를 행위자(agent·task·출처)와 함께 | `days` · `path` · `limit` |
| `diff` | **실제 바뀐 줄** — 파일별 items(추가·삭제·diff 본문). 기본=미커밋 작업분(HEAD 대비) | `commit`(한 커밋) · `ref`(구간 ref..HEAD) · `path` · `lines`(파일당 본문 줄, 기본 200) · `limit`(파일 수, 기본 50) |

```
[self:body]{}                                          # 최근 7일 몸 변화
[self:body]{days: 30, path: "backend/cognition"}       # 인지층 한 달 변화
[self:body]{op: "log", days: 7}                        # 이번 주 커밋들
[self:body]{op: "file", path: "backend/ibl/ibl_parser.py"}  # 이 파일 일생 (이동 포함)
[self:body]{op: "diff", path: "backend/ibl"}             # 지금 미커밋 변경의 실제 줄
[self:body]{op: "diff", commit: "a8fd28b", lines: 60}   # 그 커밋이 바꾼 줄
[self:body]{op: "diff", ref: "HEAD~3"}                  # 최근 3커밋 구간
```

## 통화·조합

items 행: changes=`{파일, 상태, 영역, 시각, 요지, 커밋}` (이동이면 `이전경로` 동반) / log=`{커밋, 시각, 요지, 파일수}` / file=changes 와 동형. `영역` 열=층(backend/cognition, data/packages 등) — 집계 축.

```
[self:body]{days: 30, limit: 1000} >> [table:groupby]{by: "영역"}     # 층별 변경 분포
[self:body]{days: 7} >> [table:filter]{where: {상태: "이동"}}          # 최근 이사한 파일만
[self:body]{op: "log", days: 7} >> [table:take]{n: 5}
```

```
[self:body]{op: "writes", days: 2}                     # 최근 이틀 런타임 쓰기 — 누가 뭘 썼나
[self:body]{op: "writes", path: "data"} >> [table:groupby]{by: "행위자"}
```

## 함정·경계

- **★`writes`=부분 기록**: 쓰기 관문(safe_store·`[self:write]`)을 지난 쓰기만 원장(`data/write_ledger.jsonl`)에 남는다 — 핸들러가 직접 open() 으로 쓰면 원리적으로 미기록. 결과 text 가 이 부분성을 항상 광고한다. 코드 층 전수는 `changes`(git)가 정답. `작업` 열=task_id → 주행기록(episode)과 조인하면 "왜 바뀌었나"까지.
- **pc_only** — 폰 몸엔 git 이 없다. git 저장소 밖이면 정직 거절(빈 결과 아님).
- `file` op 의 미추적 파일=이력 0 이 정상("아직 커밋된 적 없음"으로 구분 보고). 경로 오타와 구분됨.
- `limit` 상한 1000 — 초과 요청은 **신고 후** 상한 적용(침묵 클램프 아님). `truncated`/`total` 로 절단 정직 신고.
- 미커밋 행은 `상태: "미커밋"`, 시각·커밋 빈값 — 시각 정렬 시 유의.
- **경계**: 시스템의 *현재 상태*(CPU·디스크)는 `[sense:host]` / *실행 이력*(무슨 명령이 돌았나)은 주행기록(episode) / **파일(몸)의 변화 이력**이 이 어휘. 파일 *내용*은 `[self:read]`, 파일 *찾기*는 `file_find`.
