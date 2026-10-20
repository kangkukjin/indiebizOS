# L84-3 답변 언어 추적 — 실제 모델 입력·공급자 전달·재현 (2026-10-20)

84회차(`3c7f08ff`, [report §4 L84-3](experiments/long_sentence_imagination/round_84/report.md))에서 프로젝트 에이전트 EXECUTE 경로(ClaudeCode 공급자, opus)가 한국어 발화·역할·자료에 대해 7턴 중 6턴 채팅 답변을 영어로 썼다. 이 문서는 **규칙이 실제로 모델에 전달됐는지, 어디에 놓였는지, 공급자가 어떻게 넘기는지**를 코드와 기록으로 확정하고, 세 가설을 판정하며, 수리안을 제안만 한다(수리는 사용자 판정 뒤).

## 1. 결론

- **규칙은 전달됐다.** `base_prompt_v6.md`의 "사용자가 쓰는 언어로 응답하라"는 실제 시스템 프롬프트의 **마지막 절(우리 본문) 6행, 179자째**에 그대로 실렸다. CLI 자체 절에는 영어로 답하라는 지시가 없고, 우리 본문이 CLI 절보다 **뒤**에 놓인다. 따라서 "공급자 전달 순서·위치" 가설(①)은 **기각**.
- **전달이 같아도 결과는 회차마다 다르다.** 같은 CLI(2.1.299)·같은 모델(claude-opus-5-5)·같은 12절 구조·같은 규칙 위치에서 L81 은 16건 중 14건 한국어, L83 은 24건 중 17건, L84 는 14건 중 0건이었다. 원인은 결정적 전달 결함이 아니라 **CLI 하네스의 영어 맥락(영어 페르소나 절·영어 system-reminder) 아래에서 '작업 보고' 문체가 영어로 기우는 확률적 선택**이다. 재현에서도 같은 세션이 "#execute 테스트"에는 한국어로, 바로 다음 한국어 요약 요청에는 영어로 답했다.
- **파일/채팅 단계 분리(③)는 코드상 없다.** Write 도구 호출과 채팅 텍스트는 같은 CLI 세션의 같은 응답 루프에서 나온다(`claude_code.py` 스트림 파서가 text 블록을 그대로 답으로 넘김). 관측된 분리는 "독자가 한국어인 산출물"과 "하네스에 보내는 보고"의 분리다.
- **수리안(제안만)**: 프롬프트 문장을 늘리지 않고, ClaudeCode 공급자 어댑터가 이미 넘기는 `--settings` JSON에 CLI 자체 스위치 `language` 를 싣는다. 값은 사용자 발화에서 파생(데이터). CLI가 `# Language / Always respond in …` 블록을 자기 책임으로 주입하며(실측), 영어 요청에도 한국어로 답했다. 소유 위치·재검증 조건은 §6.

## 2. 증거 경로

| 무엇 | 경로 |
| --- | --- |
| 84회차 에피소드·궤적(5058~5069) | `outputs/long_sentence_imagination/2026-10-20_84회차/evidence/ai_execute_t1/{events,episode,calls}.json`, `store_0/` (spill 사본) |
| spill 원본 | `data/spill/supervision/921a9c237a5d42d1ab072054d343738e/events.jsonl` (T1) |
| **실제 전달된 시스템 본문**(공급자가 쓴 파일) | `/var/folders/dj/…/T/claude_code_sys_agent_ab8150f3_t31c157000.txt` (T1, 88,498B = 49,639자) — 스레드별 고정 경로, 호출마다 덮어씀 |
| **CLI 가 기록한 실제 시스템 프롬프트**(12절) | `~/.claude/projects/-Users-kangkukjin-Desktop-AI-indiebizOS-projects-L84-training/3839d4b6-642b-4202-b343-424635223831.jsonl` 의 `attachment.type=prompt_snapshot` (ai_execute), `6c125a1a-….jsonl` (ai_probe) |
| 세션 매핑 | `data/claude_code_sessions.json` — `L84_training:agent_ab8150f3@rehearsal#b4576914 → 3839d4b6…` |
| 재현 1건(ep5072)+부수 턴(ep5071) | `outputs/long_sentence_imagination/2026-10-20_84회차/repro_L84-3/` (`summary.json`, `*_events.json`, `system_prompt_as_passed.txt`, `cli_transcript_new_rows.json`); 요약 사본 [evidence/L84-3_repro.json](experiments/long_sentence_imagination/round_84/evidence/L84-3_repro.json) |
| CLI 언어 스위치 실측 | `~/.claude/projects/-private-tmp-…-scratchpad-cliprobe/*.jsonl` (haiku 원샷 2~3회, 합계 0.001 USD 미만) |

## 3. 확정 사실 — 코드

**조립** (`backend/cognition/prompt_composition.py` 에이전트 변형, 374행~): 절 순서 = 현재 시점 → **기본 프롬프트(base_prompt_v6)** → 시스템 구조 → Git → 위임 → IBL 환경 → 프로젝트 포식 기억 → Role → Notes → … . 언어 규칙은 두 번째 절 `<purpose>` 안 한 문장이다.

**전달** (`backend/providers/cli_provider.py` 1245행 `_write_system_prompt_file`, `backend/providers/claude_code.py` 531~538행 `_build_command`):
1. `self.system_prompt`(조립 결과 48,419자) + ClaudeCode 전용 `TOOL_POLICY`(1,220자) 를 `<tmp>/claude_code_sys_<agent_id>_t<thread>.txt` 에 쓴다.
2. 명령줄에 `--append-system-prompt-file <그 파일>` 로 넘긴다(윈도우 argv 상한 회피). `--settings`(네이티브 훅)·`--tools`·`--allowed-tools`·`--mcp-config` 동반. `--setting-sources ""` 는 원샷·의식·감독 역할에만 붙으므로 EXECUTE 경로는 사용자 설정·cwd 상위 CLAUDE.md 를 읽는다.
3. 유저 프롬프트는 stdin 으로, resume 이면 현재 메시지만(이력은 CLI 세션), fresh 면 직렬화 이력을 앞에 붙인다.

**기록의 한계**: `trajectory_event` 의 `model.input` 은 `accounting: input_shape_only` — `system_chars`(48,419 = TOOL_POLICY 제외 글자 수)·`message_chars` 만 남고 본문은 없다(`backend/base/model_call_context.py:124`). 본문 정본은 (a) 공급자 임시 파일(덮어씀), (b) CLI 트랜스크립트의 `prompt_snapshot`(벤더 기록) 둘뿐이다.

**같은 루프**: 파일 쓰기(Write)와 채팅 텍스트는 `claude_code.py` 의 stream-json 파싱(614행 `text` 블록)에서 한 세션·한 라운드 열 안에 나온다. 별도의 "채팅 요약 단계"는 없다.

## 4. 확정 사실 — 기록

**T1(ep5058, fresh) 의 실제 시스템 프롬프트** (`prompt_snapshot`, 12절 56,057자):

| 절 | 글자 | 내용 | 한글 |
| --- | --- | --- | --- |
| 0 | 1,603 | CLI 자체: "You are an agent working with the user…" + Harness 규칙 | 0 |
| 1~10 | 4,815 | CLI 동적 절: 코드 스타일·대명사·되돌리기 어려운 행동 확인·세션 안내·Memory·Environment·Context management·행동 지침·total_tokens | 0 |
| **11** | **49,639** | **우리 본문** = 공급자 파일 그대로(바이트 동일 확인). 6행 179자째 "사용자가 쓰는 언어로 응답하라", 맨 끝 `# 도구 정책` | 18,728 |

- CLI 절 0~10 전문을 읽었다: 응답 언어에 관한 지시는 **없다**. CLI 의 출력 언어 설정(`language`)은 `~/.claude/settings.json` 에 **미설정**이다(바이너리에 "Always respond in ${e}" 기능은 존재하나 켜져 있지 않음).
- 유저 턴은 `<turn_context>`(실행기억·판결·세계 지도, 한국어 6~10K자) 뒤에 한국어 명령이 온다. CLI 는 여기에 영어 system-reminder(auto mode, environment, `/Users/kangkukjin/Desktop/AI/CLAUDE.md` 5,069자, AutoMem `MEMORY.md` 1,463자, date 등)를 덧붙인다(트랜스크립트 `attachment` 행).
- 답변: ai_execute 8건·ai_probe 6건 텍스트 블록 **전부 영어**(파일 본문은 한국어). 첫 텍스트는 해시 대조 직후 "Hashes match the manifest. Writing the draft now."

**회차 간 비교**(같은 CLI 2.1.299·claude-opus-5-5·12절 구조·규칙 위치 동일):

| 회차 | 텍스트 블록 | 한국어 | 영어 | 영어의 성격 |
| --- | --- | --- | --- | --- |
| L81 | 16 | 14 | 2 | "Unchanged. Writing the result." 류 진행 보고 |
| L83 | 24 | 17 | 7 | 진행 보고(다나와 탐색 중간 보고) |
| L84 | 14 | 0 | 14 | 진행 보고·최종 답·확인 질문 전부 |

**재현(ep5072, 2026-10-20 11:39:55, origin training, 같은 에이전트 ai_execute, resume 세션)**: 요청 "방금까지 저장한 FAQ 초안과 개선 실험안의 핵심을 채팅으로 세 줄만 요약해 주세요. 파일은 새로 만들지 말고 채팅 답변만 주세요." → 답변 **영어**(자료 인용어 "내 강의실" 만 한국어). 전달된 시스템 본문 88,524B/49,652자, 규칙 179자째·6행, 끝은 도구 정책(`repro_L84-3/system_prompt_as_passed.txt`). 도구 호출 0, 파일 없음 → "파일 단계가 영어 요약을 만든다"는 ③ 의 기제 없이도 영어다.
**부수 턴(ep5071, 11:38:12)**: 접수 확인 호출이 실제 접수돼 "#execute 테스트" 가 실행됐다(의도치 않음, 무해) → 답변 **한국어** "테스트 메시지 잘 받았습니다. 다음 작업을 말씀해 주세요." 같은 세션·같은 시스템 본문에서 90초 사이에 한국어→영어가 갈렸다. 그 직전 타 세션 턴(ep5070, "한국어 한 문장으로 답하세요")도 한국어였다 → 트랜스크립트의 영어 습관 고착(resume) 만으로는 설명되지 않는다.

**CLI 언어 스위치 실측**(haiku 원샷, `--settings '{"language":"Korean"}'`): CLI 가 `attachment.type=language` 로 `<system-reminder># Language\nAlways respond in Korean. Use Korean for all explanations, comments, and communications with the user. Technical terms and code identifiers should remain in their original form. …</system-reminder>` 를 **세션 시작 시 유저 측 메타 메시지**로 주입했고, 영어 요청 "Say hello in one short sentence." 에 "안녕하세요!" 로 답했다. 바이너리 문자열상 주입 시점은 `session_start`·`compaction`·`settings_sync`·`policy_refresh` 이며, 설정 해제 시 "The language preference was cleared. Match the user's language." 를 보낸다. (resume 세션에 설정을 **나중에** 붙였을 때도 주입됨 — §8 실측.)

## 5. 가설 판정

| 가설 | 판정 | 근거 |
| --- | --- | --- |
| ① CLI 자체 시스템 지시(영어)가 뒤에 붙어 우선 | **기각** | CLI 절은 앞(0~10), 우리 본문이 마지막(11). CLI 절에 언어 지시 없음. `language` 설정 미사용. |
| ② 48K 안 한 줄 규칙의 위치가 약함 | **위치는 기각, 세기는 부분 채택** | 규칙은 우리 본문 첫 6행(전체의 12% 지점)에 있고 L81·L83 은 같은 위치로 대부분 한국어였다. 위치를 옮겨도 근거상 달라질 이유가 없다. 다만 "한 문장 vs CLI 의 영어 페르소나·영어 리마인더" 경합에서 **작업 보고 문체일 때** 영어로 기우는 것은 사실이다(L81·L83 의 영어도 전부 진행 보고). |
| ③ 파일 작성(한국어)과 채팅 요약(영어)이 다른 단계 | **구조적으로 기각** | 같은 세션·같은 루프. 재현에서 파일 없이도 영어. 관측 패턴의 올바른 서술 = "한국어 독자용 산출물 vs 하네스 상대 보고". |

**원인 확정**: 전달 결함이 아니라 **공급자 하네스 맥락에서의 모델 선택**이다. ClaudeCode 공급자는 CLI 의 영어 페르소나(절 0 "You are an agent working with the user…")·영어 system-reminder 들 위에 우리 한국어 본문을 덧붙이는 구조이며, 이 구조에서 "사용자가 쓰는 언어로" 한 문장은 보고 문체를 안정적으로 묶지 못한다. 회차·턴마다 0~100% 로 흔들리는 확률 현상이므로 **프롬프트 문장을 보태는 수리는 원인(경합)에 맞지 않고**, 벤더 하네스가 제공하는 같은 층의 스위치로 묶는 것이 맞다.

## 6. 수리안 (제안만 — 사용자 판정 뒤 구현)

**R1(권고). CLI 자체 출력 언어 스위치를 공급자 어댑터에서 켠다.**
- 소유 위치: `backend/providers/claude_code.py` `_build_command` — 이미 `--settings json.dumps(self.native_hook_settings())` 를 넘기는 자리(507행). `native_hook_settings()` 결과에 `"language": <값>` 한 키를 합친다. 프롬프트 파일·`TOOL_POLICY`·`base_prompt_v6` 는 손대지 않는다(새 문장 0, 새 어휘 0, 다른 공급자 영향 0).
- 값의 출처(데이터): 이번 턴 사용자 명령 텍스트의 지배 문자(한글이면 `"Korean"`; 영문이면 생략 → CLI 기본 "Match the user's language"). 이름 사전(언어 목록)은 `frontend/i18n/catalog.json` 의 `languages`(ko/en) 가 이미 있으니 그 키를 재사용한다. 판정 불가(혼합·짧음)면 키를 **생략**한다 — 잘못 고정하는 것이 더 나쁘다. 사용자 프로필에 언어 항목이 생기면 그것이 우선(현재 백엔드에는 locale 설정이 없다 — UI 언어는 프론트 localStorage 에만 있다).
- 왜 이 층인가: 증상은 ClaudeCode 공급자에만 있는 "하네스 페르소나와의 경합"이고, 그 하네스가 같은 목적의 스위치를 자기 책임으로 제공한다. 모델이 바뀌어도 CLI 가 주입하므로 모델 교체를 살아남는다. 비용은 턴당 리마인더 ~120 토큰.
- 재검증 조건:
  1. `backend/test_claude_code.py` 에 `_build_command` 의 `--settings` JSON 이 한국어 명령에서 `language=Korean`, 영어·혼합 명령에서 키 없음을 확인하는 시험.
  2. L84 T1(fresh)·T4("재참여율?")·재현 요청을 ai_probe 급 새 에이전트에서 각 3회 → 채팅 텍스트 한국어 비율 100%, 파일 본문 변화 없음.
  3. resume 세션에서도 블록이 들어가는지(§7 실측 결과에 따라 — 안 들어가면 세션 키에 언어를 포함해 fresh 로 끊는 `tool_policy_fingerprint` 와 같은 선례 적용).
  4. 트랜스크립트 `attachment.type=language` 존재 + `prompt_snapshot` 12절 구조 불변 확인.
  5. 원샷(tools_mode)·의식 경로는 `--setting-sources ""`·`--settings` 없음 → 같은 증상이 관측되면 별도 판정(이번 증거는 EXECUTE 경로만).

**R2(비추천).** `base_prompt_v6` 문장을 강화하거나 위치를 옮긴다 — 증거상 위치는 무관하고, 규칙 증식·모든 공급자 공통 프롬프트 변경이라 범위가 크다.

**R3(선택, 증거 보존).** `model.input` 에 시스템 본문의 sha256·경로를 남긴다(`model_call_context.py`). 본문 저장은 아니며 카운터도 아니다 — 다음 추적 때 "전달된 본문" 을 공급자 임시 파일·벤더 트랜스크립트에 의존하지 않게 하는 출처 표식. 이번 조사에서 본문 정본이 우리 기록 밖에만 있었던 점이 근거.

## 7. 부수 관측 (수리 범위 밖, 후속 후보)

- **상위 CLAUDE.md·AutoMem 누출**: EXECUTE 경로는 `--setting-sources` 를 주지 않아 CLI 가 cwd(`projects/L84_training`) 상위의 `/Users/kangkukjin/Desktop/AI/CLAUDE.md`(5,069자, "하네스 전용 뷰") 와 `~/.claude/projects/-Users-kangkukjin-Desktop-AI-indiebizOS/memory/MEMORY.md`(1,463자) 를 프로젝트 에이전트의 첫 유저 턴에 싣는다(트랜스크립트 `attachment.type=instructions`). 훈련 에이전트가 사용자 워크스페이스 지침·기억 색인을 읽는 셈이며 토큰도 든다. 언어 원인은 아니다(둘 다 한국어).
- resume 세션 + 나중에 붙인 `language` 설정 실측: §8 — 주입됨.
- 이 조사가 쓴 턴: ep5071(의도치 않은 "#execute 테스트"), ep5072(재현). 다른 세션이 같은 에이전트에 ep5070 을 보내고 있었다(공유 노트에 기록).

## 8. 실측 추가 — resume 세션의 언어 블록 주입

haiku 원샷으로 설정 없이 세션을 만든 뒤(첫 턴은 CLI 측 도구 호출 파싱 오류로 답 없음), 같은 세션을 `--resume` + `--settings '{"language":"Korean"}'` 로 이어 영어 요청 "Now say one more short sentence about the weather." 를 보냈다 → 트랜스크립트에 `attachment.type=language` 가 resume 시점(02:44:36Z)에 기록됐고 답변은 "오늘은 가을 하늘이 높고 맑아서 산책하기 좋은 날씨예요." 였다. 즉 **설정이 나중에 붙은 resume 세션에도 블록이 주입된다**(1회 실측, 세션 `aa56fe43…`). R1 재검증 3 은 이 실측으로 1차 충족이며, 구현 때 EXECUTE 경로의 실제 resume 세션에서 한 번 더 확인한다.
