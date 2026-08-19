# 동영상 제작 가이드 — 강의 덱이 영상의 원본이다

**동영상을 만드는 길은 하나다: 강의 덱 → `[self:deck]{op: "video"}`.**
(2026-08-05 정리 — 옛 engines:html_video(HTML 씬 합성)·engines:remotion(React/TSX 렌더)은 은퇴.
슬라이드가 HTML 이던 시절의 어휘였고, 지금 슬라이드의 정본은 강의 워크스페이스다.
합성 파이프라인(TTS→씬 길이 맞춤→FFmpeg)은 deck video 의 엔진으로 잔류한다.)

## 흐름 — "동영상 만들어줘" 의 결정론 경로

0. **원본이 음성 파일일 때** (녹음·강연 m4a/mp3/영상에서 출발) — 먼저 받아쓴다:
   `[self:script]{op:"run", id:"음성받아쓰기", args:{path:"<파일>"}}` → 전사문이
   `outputs/transcripts/<이름>.transcript.txt` 에 남고 경로를 통화로 돌려준다.
   **★`[sense:listen]` 을 쓰지 말 것** — 그건 *마이크 1회 입력*이라 파일에 못 쓴다(2026-08-19 ep1251 의 함정).
   전사문은 요약이 아니라 전문이라 **오프닝·클로징 인사말이 보존된다** — 그대로 첫 장·마지막 장 슬라이드가 된다.
   그다음 `[self:material]{op:"add", lecture_id, file_path}` 로 덱에 붙이면 아래 1번으로 이어진다.
   긴 파일은 `segment_seconds`(기본 300)로 나눠 보낸다. 응답이 잘리면 이 값을 줄인다.

1. **덱 준비** — 이미 있는 강의를 쓰거나, 원고에서 새로 만든다:
   - `[self:lecture]{op: "create", title, thesis, audience}` → `[self:material]{op: "add"}`(원고·자료)
   - `[self:slide]{op: "create", instruction, content}` × N — 장마다 **스피커 노트(나레이션 초안)가 자동 시드**된다.
   - 나레이션을 다듬으려면 강의 창에서 노트를 편집(사용자 편집은 보존됨).
2. **렌더** — `[self:deck]{op: "video", lecture_id}`:
   - 슬라이드 PNG + 장별 스피커 노트 → TTS → **나레이션 길이에 씬 길이 자동 맞춤** → FFmpeg 합성.
   - 기본 **백그라운드**(즉시 반환) — **별도 프로세스**라 백엔드가 리로드돼도 렌더는 계속된다. `wait: true` = 동기.
   - **진행 확인은 `[self:deck]{op:"video", lecture_id, check: true}`** — 렌더를 새로 걸지 않고 상태만 묻는다.
     `stage`·`index`/`total`(씬 몇 장째)이 하트비트로 갱신되고, 렌더가 죽으면 pid 로 판정해 **`interrupted`** 로 확정된다.
     즉 `building` 은 "지금 살아서 돌고 있다"는 뜻이다 — 죽은 렌더를 기다리는 일은 없다.
   - 소요: 정지 슬라이드 덱은 **장당 수 초**(12장 ≈ 1분). 프레임을 장마다 수백 장 찍지 않고 한 장을 늘여 인코딩한다.
   - 옵션: `engine`(기본 **gemini** / `edge`=무과금) · `voice`(gemini 기본 **Charon**, `Sulafat`·`Achird` 등 / edge 는 `ko-KR-SunHiNeural` 등) · `style`(gemini 전용 자연어 연기 지시) · `rate`(edge 전용) / `transition`(fade 기본) / `bgm_path` / `output_filename`.
   - **나레이션 비용**: 기본 gemini 는 문자 수 과금이라 장수가 많은 덱은 그만큼 든다. 시험 렌더는 `engine: "edge"` 로 돌리고 최종만 gemini 로 굽는 게 싸다.
   - 노트 없는 장 = 무나레이션 씬(기본 길이). 결과의 `missing_notes` 로 확인.
   - **★내 목소리로 굽기**: 렌더 전에 `[self:script]{op:"run", id:"나레이션생성", args:{lecture_id}}` 를
     한 번 돌리면 장별 스피커 노트가 사용자 본인 목소리로 구워져 `narration/<slide_id>.wav` 에 쌓인다.
     그다음 이 op 를 평소대로 부르면 된다 — **그 장에 wav 가 있으면 TTS 대신 그 파일을 쓴다**(engine·voice 무관).
     장별로 섞여도 된다(어떤 장은 내 목소리, 나머지는 TTS). 결과의 `preset_narration` 이 쓰인 장 수.
     **낭독 속도는 0.9x(10% 느리게)가 표준**이라 스크립트가 알아서 적용한다 — 그만큼 씬이 길어지고
     씬 길이는 나레이션에 맞춰지므로 타임라인은 자동으로 다시 맞는다(2026-08-17 사용자 판정).
     시험 렌더는 `engine:"edge"` 로 싸게 돌리고 **최종만 내 목소리**로 굽는 게 시간·과금 모두 유리하다
     (목소리 복제는 문장당 40~60초). 상세·함정·레퍼런스 교체 = `voice_narration.md`.
3. **산출물** — `outputs/lectures/<id>/video/lecture_video.mp4` (h264+aac).

## 원칙

- **품질은 덱에서 나온다** — 슬라이드 큐레이션(slides.md §1)과 스피커 노트 퇴고가 영상 품질의 전부다. 렌더는 결정론.
- 실패한 렌더는 `check: true` 의 error 를 읽고 원인(TTS 실패·PNG 누락 등)을 고친 뒤 재호출.
  `interrupted` = 렌더가 끝나기 전에 끊긴 것(프로세스 사망) — 원인 로그는 `video/render.log`, 그냥 다시 부르면 된다.
- **폴링은 상태 파일을 직접 긁지 말고 `check: true` 로** — 파일만 보면 죽은 렌더의 `building` 을 그대로 믿게 된다
  (2026-08-17 실사고: 리로드에 죽은 렌더를 20분간 '진행 중'으로 오독).
- BGM·음성 톤 변경 = 같은 op 재호출(덱 불변, 렌더만 다시).
