# 시스템 탐구 핸드오프 (다음 세션)

작성 2026-06-13. 직전 세션이 폰-자아 호스팅을 크게 바꾸며 길어졌다. **다음 세션의 목적은 빌드가
아니라 *탐구/감사*** — 시스템 전체가 처음 상상대로 얼마나 이뤄졌는지, 지금 무엇을 할 수 있는지,
어휘·앱모드가 건강한지 한 발 물러서서 점검하는 것(사용자 지정). 먼저 읽기 권장: 이 문서 → MEMORY.md.

---

## 0. 직전 세션 상태 스냅샷 (무엇이 살아있고 무엇이 은퇴됐나)

**★ 큰 전환(커밋 fc18d51·9c6c2e5)**: 폰-자아 두뇌를 *맥 claude_code 렌트*에서 **폰-로컬 in-process Gemini**로 바꿈.
- 폰 3티어: 경량=`gemini-3.1-flash-lite`, 중급·본격=`gemini-3.5-flash` (전부 `gemini_http` REST 직결, GEMINI_API_KEY env). `phone_api._ensure_phone_ai_configs` 가 생성/마이그레이션.
- **맥-자아는 claude_code 유지** (맥선 손이 맥에 있는 게 맞음). → 두 자아가 각자 몸-네이티브 두뇌.
- **이유**: 빌린 두뇌(claude_code)는 자기 몸(맥)을 데려옴(네이티브 Bash 가 맥서 동작). Gemini *모델* API 는 폰서 직접 호출 가능. claude_code "프로그램"(Node CLI)만 폰서 못 돎이었고 구독 과금이 그 CLI 에 묶였을 뿐.

**은퇴(제거 완료, fc18d51)**: `claude_code_remote` provider, `phone_self_channel`, `/ws/phone-self`, `remote_turn` 엔드포인트, `route_to_phone_ws`(api_ibl), ClaudeCodeProvider `backend_url`/`route_to_phone`, mcp_server `ROUTE_TO_PHONE`, `phone_ws_client`, websockets pip. → away-case 역방향 장치 전부. (폰이 로컬 추론하니 맥→폰 역방향 도달이 불필요해 증발.)

**폰-자아가 지금 할 수 있는 것**:
- 폰에서 로컬 Gemini 로 인지 파이프라인(분류→의식→실행→평가) 전부 돎. 도구 실행도 폰.
- **폰 네이티브 Python 실행**: `execute_python`(인-프로세스 exec, capability-gate). A36 검증(소수 계산·7배수 합 폰서 직접). `jclass` 브리지가 그 exec 컨텍스트에 살아있음 → 안드로이드 SDK 도달 가능.
- **마이크로 자기인식**: `runtime_utils.detect_local_micros()` → `{escape, local, borrowed}`. 폰=`{escape:python, local:[python,html], borrowed:[node]}`(셸은 python 에 포섭). 프롬프트에 "만능 탈출구=python" 주입.
- **해마**: 맥 `/ibl/embed` 인코더 렌트(outbound) + 폰 로컬 인덱스 brute-force.
- **빌림**: home_only 액션은 `_forward_to_mac`(폰→맥 outbound, NAT 무관). `/embed` 도 outbound.

**유지된 인프라**: `/ibl/embed`(맥, 해마 렌트), `_forward_to_mac`/`_forward_to_phone`(양방향 빌림, 단 _forward_to_phone 은 LAN 한정), business.db 양방향 sync, detect_body, 폰 번들 파이프라인(build.gradle `_ENGINE_MODULES`).

**이번 세션 미완(논의만, 빌드 안 함)** — §4 프런티어 참조.

---

## 1. 탐구 영역 A — IBL 어휘 구조 감사 (사용자 지정)

**질문**: 5노드 125액션 어휘가 코헌런트한가? 명명 헌법을 따르나? 죽은/고아 액션은? 누락은?
- **시작점**: `data/ibl_nodes_src/{sense,self,limbs,others,engines}.yaml`(단일 진실 소스) · `scripts/build_ibl_nodes.py`(빌드/--check/포크가드) · `data/ibl_nodes.yaml`(생성물) · `backend/ibl_access.py`(프롬프트 XML 노출).
- **읽을 메모리**: `architecture_ibl_naming_law`(명명 헌법: 빈도-길이 반비례·변형은 op·한단어한개념) · `architecture_ibl_as_vocabulary` · `architecture_ibl_action_criteria`(4기준+3운영모드) · `architecture_ibl_description_cost`(프롬프트 비용) · `project_ibl_vocab_reform`(**미완: #24 레거시 별칭 ~160개 은퇴 = 대규모 캡스톤**) · `project_ibl_usability_audit`(144액션 전수감사 완료분).
- **할 것**: 노드별 액션 일람 만들고 — (a)명명 헌법 위반, (b)과통합/과분할, (c)코퍼스에 없는 死어휘, (d)#24 레거시 별칭 잔여 현황, (e)runs_on/scope 태그 정합. `build --check`·`world_pulse self-check` 가 잡는 것과 못 잡는 것 구분.

## 2. 탐구 영역 B — 비전 vs 현실 (사용자 지정: "처음 상상대로 얼마나 이뤘나")

**시작점(읽을 메모리)**:
- `project_four_problem_geneses`(발생 구조 4 문제의식 — ④ 하네스 간 소통이 병목, 미테스트) ← **달성도 채점의 척추**.
- `ai-os-philosophy` · `project_indiebizos_identity`("1단계 75%", "키우는 존재") · `project_indiebizos_shape_superapp_autopilot`(슈퍼앱+오토파일럿, L0-L5) · `project_launcher_three_surfaces`(트릴레마: 자율주행/수동/앱) · `architecture_three_tier_cognition`.
- **할 것**: 각 기둥(IBL 신경계 / 3단 인지 / 런처 3표면 / 해마 실행기억 / 두-자아)을 *솔직히 채점* — 견고히 됨 / 부분 / 미완·열망 / 깨짐. ④(노드 간 협력)이 폰-자아·business sync 로 어디까지 갔는지.

## 3. 탐구 영역 C — 현재 능력 인벤토리 (사용자 지정: "지금 뭘 할 수 있나")

**경험적으로**(코드만 읽지 말고 실제로 돌려볼 것):
- 맥 시스템 AI(`/system-ai/chat`, claude_code), 폰-자아(`localhost:8799/system-ai/chat`, gemini, USB), 앱모드 계기들.
- 노드별 대표 액션을 실제 실행해 작동/침묵실패/크래시 분류. `_audit_corpus_extract.py` 등 기존 감사 도구 재사용.
- 맥 vs 폰 능력 차이 표(이미 알려진 비대칭: 맥=shell+pip+네이티브바이너리 열린 프런티어 / 폰=stdlib+번들+jclass SDK + 맥 빌림).

## 4. 탐구 영역 D — 앱 모드 건강 (사용자 지정: "앱모드 잘 작동하나")

**시작점**: `backend/api_launcher_web.py`(`_derive_instruments`, 서빙 HTML) · `frontend/src/ActionDesktop.tsx`+`GenericInstrument.tsx`(데스크탑) · `ibl_nodes_src` 의 `app:` 블록(단일 선언→3표면 파생) · `build_ibl_nodes.py validate_app_blocks`.
- **읽을 메모리**: `project_remote_app_generic_renderer_pending`(완료: app블록 단일소스→데스크탑/원격/폰 파생, OVERRIDES/STATIC_DOMAINS escape 2층) · `project_messenger_community_instruments`(메신저/비즈니스 계기) · `project_phone_render_primitives`(지도/video/calendar 프리미티브).
- **할 것**: 세 표면(데스크탑 Electron / 원격 웹 / 폰 웹앱)에서 계기들이 실제로 렌더·작동하는지. 특히 폰 두뇌 전환(Gemini) 후 앱모드 회귀 없는지. 드리프트(데스크탑=진실소스 원칙) 점검.

## 5. 탐구 영역 E — 보강 (내가 필요하다고 보는 것)

- **회귀 점검(우선)**: 이번 세션이 대량 변경(폰 두뇌 피벗 + 역방향 장치 제거)을 했다. (a)맥 시스템 AI 정상? (b)앱모드 정상? (c)은퇴 코드의 dangling 참조 0?(이미 grep 확인했으나 재점검) (d)`build --check`·pre-commit·self-check 통과 유지?
- **두-자아 코헌런스**: 맥=claude_code·폰=Gemini 두 자아가 *실제로* 코헌런트한가 — business.db 양방향 sync(`project_business_db_sync`), 정체성 분리, 기억 사적/공유 경계(`project_body_proprioception_detection`). 충돌·중복 없는지.
- **반응형-only 갭**: 폰-자아는 *반응형*이다(물으면 한 턴). "그만할 때까지 받아쓰기"·"매일 아침 X"·"Y 오면 알림" 같은 *열린/상주/중단가능 작업*을 못 함(스케줄러·트리거·이벤트·job 레지스트리·stop-신호 폰 미번들). ← **탐구 후 최우선 빌드 후보 1순위로 본다.**
- **메모리 정합**: 이번 세션이 많은 메모리를 건드렸고 일부는 이제 stale(claude_code_remote/WS away-case 가 메모리엔 "완료"로 남아있으나 코드선 은퇴). `project_body_proprioception_detection` 맨 앞 "★★대전환" 절이 현재 진실. `consolidate-memory` 스킬로 1회 정리 권장.

---

## 6. 미결 프런티어 (탐구가 끝나고 *빌드*로 갈 때 후보)

직전 세션에서 논의됐으나 빌드 안 한 것들(우선순위는 탐구 후 재평가):
1. **반응형→능동/백그라운드 층**(위 §5): 폰에 job 레지스트리+stop-신호+스케줄러/트리거. "X 할 때까지/매일/이벤트시" 가능케. (제일 큰 능력 도약.)
2. **jclass 능력 확장 + 안전**: 권한 봉투 확장(자기상에 "SDK 전체 도달" 명시) + **비가역·외향 행위 confirm 게이트**(augmentation-over-autonomy). ⚠️사용자 미결정(위험 자세). ★중요 안전 사실: 루트 없는 샌드박스라 *기기 자체는 폭주로 안 망가짐*(공장초기화 복구), 진짜 위험은 *허가된 권한 내 비가역 현실 행위*(특히 접근성=다른 앱 조작, SMS·통화·삭제·과금). 권한을 얼마나 여느냐가 능력=위험 다이얼.
3. **인-프로세스 exec 안전**: 폰 execute_python 격리 없음(os._exit/segfault·무한루프 강제종료 불가). AST 위험 필터 등(과한 게이팅=무능화 주의).
4. **폰 해마 증류**(폰 사적 경험→폰 인덱스, 현재 정적 읽기전용) · **폰 world_pulse 수집**(현재 정체성/마이크로 폴백만).
5. **데이터 정리**: 해마 `ibl_examples` difficulty 컬럼 오염 50행(boost_limbs_round2_examples.py 컬럼 어긋남 — 소스는 f10eb6a서 수정, 기존 50행 DB 정리 미완, 작업칩 task_db2bfbb0).

---

## 7. 빠른 시작 (콜드 스타트)
```
cd /Users/kangkukjin/Desktop/AI/indiebizOS
git log --oneline -12                         # 이번 세션 커밋들(f48d914~9c6c2e5)
python3 scripts/build_ibl_nodes.py --check    # 어휘 정합·포크가드·매니페스트 상태
curl -s localhost:8765/health                 # 맥 백엔드 살아있나(dev 상시)
adb devices && adb forward tcp:8799 tcp:8765  # 폰(A36 RFKL104C4MM) USB
curl -s localhost:8799/launcher/instruments   # 폰 앱모드 계기(JSON 유효한지 — 비어있지않음≠정상!)
```
⚠️ **온디바이스 검증 교훈(이번 세션 비싼 버그)**: HTTP 200·유효 JSON까지 확인할 것. "비어있지 않음"만 보면 `Internal Server Error` 문자열을 거짓 양성으로 통과시킨다(실제로 그래서 _lw=None 500 버그를 놓쳤음). 폰은 USB 상시 연결, 온디바이스 검증은 직접 할 것(사용자에게 떠넘기지 말 것).
```
cd phone-companion && ./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk   # 폰 변경 시
```

## 8. 핵심 관련 메모리 (읽기 순서)
1. `project_body_proprioception_detection`(폰-자아 현재 진실, 맨 앞 ★★대전환) · `architecture_substrate_superstructure_seam`(헌법 1조) · `project_phone_mac_routing_plan`(라우팅·빌림) · `project_indiebizos_phone_native`(폰 네이티브 인프라).
2. 어휘: `architecture_ibl_naming_law` · `architecture_ibl_as_vocabulary` · `project_ibl_vocab_reform`.
3. 비전: `project_four_problem_geneses` · `project_indiebizos_identity` · `ai-os-philosophy`.
4. 피드백: `feedback_phone_usb_connected` · `feedback_vocab_change_docs` · `feedback_no_temporary_patches`.
