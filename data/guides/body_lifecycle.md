# 몸의 명사 생애주기 — 런처 항목·에이전트·채팅방·스위치·창고·채널·미디어 (2026-10-05)

매니저·폴더 창·휴지통·멀티채팅·창고·설정 창이 REST 로만 하던 일을 어휘로 연다. 구현은 **조종실 라우트와 같은 서비스 함수**(한 벌)이고,
쓰기 op 는 사전의 `requires`(주인 전용 · 영구 삭제·설정 변경은 사람 승인 토큰)가 실행기 관문에서 집행한다. 설계 정본 `docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md` §1-⑩.

## 낱말 지도
| 명사 | 낱말 | op |
|---|---|---|
| 런처 프로젝트 | `[self:project]` | list · templates · create · rename · copy · move(폴더로) · trash · delete(승인) |
| 런처 폴더 | `[self:folder]` | list · create · items · rename · move · trash |
| 런처 휴지통(프로젝트·폴더·스위치·채팅방 공통) | `[self:trash]` | list · restore(item_id+item_type) · empty(승인) |
| 스위치 | `[self:switch]` | list · run(접수증) · info · create · update · rename · copy · trash · delete(승인) |
| 에이전트 | `[others:agents]` | list · info · create · update · delete(승인) · start · stop · role · note |
| 채팅방(멀티채팅) | `[others:chat_room]` | list · candidates · create · info · participants · add · remove · messages · say · clear · trash · delete(승인) |
| 이웃 창고 피드 | `[others:warehouse]` | neighbors · poll · feed · browse · search · like · retweet · score · memo · forget(승인) |
| 내 창고 | `[self:warehouse]` | list · add · remove(휴지통) · move · mkdir · trash · restore · purge(승인) |
| 채널 설정·폴러 | `[others:channel]` | list · detail · set(승인) · poll · status |
| 미디어 파일 | `[self:media]` | probe · transcode(접수증) · hls(접수증) · subtitles · subtitle |
| 즐겨찾기 사이트 | `[limbs:launch]` | open_ui · list · add · remove |

## 규칙
- **휴지통 먼저**: 프로젝트·폴더·스위치·채팅방·내 창고 항목의 `trash`/`remove` 는 되돌릴 수 있다. 영구 삭제(`delete`·`empty`·`purge`)만 사람 승인 토큰이 필요하다 — 자율 턴에서는 거절되므로 휴지통으로 보내는 것으로 끝내고 보고하라.
- **접수증**: `[self:switch]{op:"run"}`·`[self:media]{op:"transcode"|"hls"}` 는 즉시 접수증(`task_ref`)을 돌려준다 → `[self:task]{op:"wait", ref: $r.task_ref}`.
- **이름 규칙**: 런처 폴더(`self:folder`)는 바탕화면의 묶음이고 디스크 폴더는 `self:mkdir`·`self:list`. 내 창고 관리는 `self:warehouse`, 이웃 창고는 `others:warehouse`. 채널 읽기·보내기는 `others:channel_read`·`others:channel_send`, 설정은 `others:channel`.
- **에이전트 지정**: `agent_id: "프로젝트/에이전트id"` 또는 `project_id` + `agent_id`. 스위치 `create` 는 그 프로젝트의 역할·허용 노드를 복사해 얼린다(모델은 얼리지 않음).
- **회원 주체**: 이 낱말들의 쓰기 op 는 전부 주인 전용(`requires.principal: owner`). 프로젝트·휴지통·내 창고·채널은 읽기도 주인 전용.

## 예
```
$p = [self:project]{op: "create", name: "시장조사"}
[others:agents]{op: "create", project_id: "시장조사", name: "조사원", role: "자료를 찾아 정리한다", allowed_nodes: ["sense"]}
$sw = [self:switch]{op: "create", name: "아침 뉴스", command: "오늘 뉴스 요약", project_id: "시장조사", agent_name: "조사원"}
$r = [self:switch]{op: "run", switch_id: $sw.switch.id}
[self:task]{op: "wait", ref: $r.task_ref, timeout: 240}
```
