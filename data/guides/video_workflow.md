# 동영상 제작 가이드 — 강의 덱이 영상의 원본이다

**동영상을 만드는 길은 하나다: 강의 덱 → `[self:deck]{op: "video"}`.**
(2026-08-05 정리 — 옛 engines:html_video(HTML 씬 합성)·engines:remotion(React/TSX 렌더)은 은퇴.
슬라이드가 HTML 이던 시절의 어휘였고, 지금 슬라이드의 정본은 강의 워크스페이스다.
합성 파이프라인(TTS→씬 길이 맞춤→FFmpeg)은 deck video 의 엔진으로 잔류한다.)

## 흐름 — "동영상 만들어줘" 의 결정론 경로

1. **덱 준비** — 이미 있는 강의를 쓰거나, 원고에서 새로 만든다:
   - `[self:lecture]{op: "create", title, thesis, audience}` → `[self:material]{op: "add"}`(원고·자료)
   - `[self:slide]{op: "create", instruction, content}` × N — 장마다 **스피커 노트(나레이션 초안)가 자동 시드**된다.
   - 나레이션을 다듬으려면 강의 창에서 노트를 편집(사용자 편집은 보존됨).
2. **렌더** — `[self:deck]{op: "video", lecture_id}`:
   - 슬라이드 PNG + 장별 스피커 노트 → TTS → **나레이션 길이에 씬 길이 자동 맞춤** → FFmpeg 합성.
   - 기본 **백그라운드**(즉시 반환, 수 분 소요) — 진행·결과는 `video_state.json`, 같은 op 재호출로도 확인. `wait: true` = 동기.
   - 옵션: `engine`(기본 **gemini** / `edge`=무과금) · `voice`(gemini 기본 **Charon**, `Sulafat`·`Achird` 등 / edge 는 `ko-KR-SunHiNeural` 등) · `style`(gemini 전용 자연어 연기 지시) · `rate`(edge 전용) / `transition`(fade 기본) / `bgm_path` / `output_filename`.
   - **나레이션 비용**: 기본 gemini 는 문자 수 과금이라 장수가 많은 덱은 그만큼 든다. 시험 렌더는 `engine: "edge"` 로 돌리고 최종만 gemini 로 굽는 게 싸다.
   - 노트 없는 장 = 무나레이션 씬(기본 길이). 결과의 `missing_notes` 로 확인.
3. **산출물** — `outputs/lectures/<id>/video/lecture_video.mp4` (h264+aac).

## 원칙

- **품질은 덱에서 나온다** — 슬라이드 큐레이션(slides.md §1)과 스피커 노트 퇴고가 영상 품질의 전부다. 렌더는 결정론.
- 실패한 렌더는 `video_state.json` 의 error 를 읽고 원인(TTS 실패·PNG 누락 등)을 고친 뒤 재호출.
- BGM·음성 톤 변경 = 같은 op 재호출(덱 불변, 렌더만 다시).
