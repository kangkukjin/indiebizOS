# 핸드오프 — 폰-자아 능력 확장 후속 (다음 세션)

작성 2026-06-14. 이번 세션은 "폰-자아를 더 완전한 독립 자아로" 만드는 빌드 묶음이었다.
커밋 3개: `842e1f8`(상주 스케줄러) · `f5a269e`(자율주행 드릴다운) · `ab8a7a6`(의료기록 동기화 +
runs_on 정직성 + 폰 액션 이식 + 사적 기억/파일). 먼저 읽기: 이 문서 → MEMORY.md.

## 0. 관통하는 원칙 (이번 세션에서 정립 — 후속에도 적용)

1. **runs_on 정직성**: 액션은 `anywhere`(각 몸 로컬) / `mac_only`(폰→맥 포워드) / `phone_only`
   (맥→폰 포워드) 셋 중 하나로 *정직하게* 태그돼야. `anywhere`인데 패키지 폰 미번들이면 silent-forward
   (태그 거짓) → `build_ibl_nodes.validate_phone_reachability`가 이제 적발한다(self-check 합류).
2. **라이브러리=비계, API=몸** ([[architecture_body_vs_absorbable]]): 폰서 못 도는 게 *무거운
   라이브러리*면, 그게 감싸는 HTTP API를 경량 도구(requests/feedparser)로 직접 부르면 이식 가능.
   arxiv·shopping이 증명. 흔한 함정="모듈레벨 네이티브/무거운 import가 순수 API op까지 가둠"→지연 import.
3. **기억의 두 부류**: *사용자 세계-데이터*(연락처·비즈니스·일정·의료기록=객관)=공유·동기화 /
   *자아의 주관적 기억*(memory·해마·대화·자기상태=그 자아의 마음)=자아별 사적·동기화 안 함.
4. **self 노드 = 자기 몸**: self 액션은 자기 하드웨어에 작용(파일=자기 fs, 시계=자기 시계).

## 1. 후속 작업 (우선순위 순)

> (제외됨 — 사용자 결정 2026-06-14: ①media_producer 폰 이식 ②폰 해마 증류 ③폰 심층기억 시맨틱
>  검색(폰은 키워드로 충분) ④캘린더 동기화 = 불필요. 이미지·tts 생성·캘린더는 맥 포워드로 충분.)

### A. 의료기록 삭제 경로 (CRDT 빈자리) — ✅ 완료 (커밋 4ae628b, 2026-06-14)
~~`health-record/storage.py`에 delete 함수 0, handler에 delete op 0 → 사용자가 의료기록 *삭제 불가*~~
soft_delete_record + health_op delete op 신설. ★부수 버그픽스: 조회 11쿼리에 deleted=0 필터
누락이었음(없으면 soft-delete 무의미). 조회 출력에 (#id) 표시, 한국어 record_type 별칭, 해마 5용례
+hippo 재export(폰 semantic 0.880). build --check + /ibl/execute 종단(measurement/symptom) 검증.
stdlib만이라 폰 import 위험0 → 다음 APK 빌드 자동 번들. 액션 125 유지.

### B. 반응형→능동 층 후속 (이전 핸드오프 잔여)
- **channel 트리거("Y 메시지 오면 X") — ① 맥 발화 경로 ✅ 완료(커밋 다음, 2026-06-14)**:
  ★핸드오프 전제가 틀렸었음 — "channel_poller 폰 번들만 필요"가 아니라 **발화 경로가 맥에서도 미존재**였음.
  `_create_trigger`(type:channel)는 event_triggers.json 저장만, channel_poller는 event_triggers 를 전혀
  안 읽었음(소유자명령→시스템AI + 이웃→자동응답 두 경로뿐). schedule 은 calendar_manager 폴링이 발화
  엔진이지만 channel 은 발화 엔진이 없었음. → channel_poller `_save_message_to_db`(Gmail/Nostr 3수신
  경로 공통 깔때기)에 `_check_channel_triggers` 훅 신설: enabled channel 트리거를 config(channel/from/
  keyword)로 필터→매칭 시 `_fire_channel_pipeline`(데몬스레드 execute_pipeline, 메시지를 _prev_result
  주입, calendar_actions 레거시 직접실행과 동형). 격리+통합 검증(매칭/비매칭/채널필터/dedup/컨텍스트주입).
  **⚠️ 라이브 백엔드 poller는 재시작 전까지 구 코드** — 실 메시지 발화는 백엔드 재시작 후.
- **② 폰 번들링 — 미착수(더 무겁고 별도)**: channel_poller + auto_response + business_manager 폰 번들 +
  ★Nostr 수신을 pynostr(채널_poller 모듈레벨 try-import) → `nostr_phone_bridge`(Kotlin, indienet `_ON_PHONE`
  경로) 로 적응 필요. Gmail 폴링 폰 경로도. build.gradle 주석이 명시적으로 deferred. **사용자와 substrate
  접근 결정 필요**(채널_poller 통째 vs 폰 전용 경량 poller).
- "그만할 때까지 받아쓰기"(연속 스트리밍) = `sense:listen` 연속 모드(트리거 의미 밖, 새 메커니즘). 미착수.
- 본문: [[project_phone_standing_jobs.md]](폰 상주 스케줄러는 schedule 타입 완료, channel ①맥 완료/②폰 잔여).

## 2. 소소한 빈자리

- **write→read 경로 비대칭**(기존, 내 변경 아님): `system_essentials/handler.py:161-166` write가 bare
  파일명을 `outputs/`로 리다이렉트하는데 read는 안 함 → write→read 어긋남(맥·폰 공통, 응답 redirected_to
  표시). read도 outputs/ 폴백하거나 redirect를 끄면 일치. 고칠지 결정.
- **youtube search_youtube**: yt-dlp extract_info — 키 없는 가벼운 검색 API 대체 없어 mac 유지가 맞음
  (arxiv 패턴 적용 불가 확인됨).
- **메모리 정합**: 이번 세션이 메모리 다수 갱신(home_only→mac_only 일괄 포함). `consolidate-memory`
  스킬 1회 권장.

## 3. 빠른 시작 (콜드 스타트)
```
cd /Users/kangkukjin/Desktop/AI/indiebizOS
git log --oneline -5                          # 842e1f8·f5a269e·ab8a7a6 이번 세션
python3 scripts/build_ibl_nodes.py --check    # 어휘·runs_on 정합·포크가드·매니페스트
curl -s localhost:8765/health                 # 맥 백엔드(dev 상시)
adb devices && adb forward tcp:8799 tcp:8765  # 폰 A36 USB
curl -s localhost:8799/launcher/instruments   # 폰 앱모드(HTTP 200·유효 JSON까지 — 비어있지않음≠정상!)
```
⚠️ **온디바이스 검증 의무**: 폰 작업은 HTTP 200+유효 JSON까지 직접 확인(사용자에게 떠넘기지 말 것).
3p 라이브러리 폰 이식은 **모듈레벨 스캔만으론 못 믿음** — A36 대표 액션 실행으로 import 확정(지연 import
3p가 실행 시 터질 수 있음). 폰 변경 시: `cd phone-companion && ./gradlew assembleDebug &&
adb install -r app/build/outputs/apk/debug/app-debug.apk` 후 force-stop+재시작.

현재: 폰 패키지 22, runnable 95 (세션 시작 11/67). runs_on 분포 anywhere/mac_only/phone_only.

## 4. 핵심 메모리 (읽기 순서)
1. `project_indiebizos_phone_native`(이번 세션 후속 다수 기록 — 맨 뒤 항목들) · `project_body_proprioception_detection`(두-자아 진실).
2. `architecture_body_vs_absorbable`(라이브러리=비계/API=몸 — 이식 원칙) · `architecture_substrate_superstructure_seam`(헌법 1조).
3. `project_business_db_sync`(동기화 패턴 — health/calendar 미러 본) · `project_phone_mac_routing_plan`(라우팅·빌림).
4. `project_phone_standing_jobs`(반응형→능동 잔여).
