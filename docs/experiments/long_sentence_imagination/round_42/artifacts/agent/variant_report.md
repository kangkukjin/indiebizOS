# 검증 보고서 — 훈련42 입력 실패 변형 (s003 PNG 누락 → 복구)

작성: 2026-10-09 · 덱 `hunryeon42-dogribai-dongne-surigyosil` · 합성 훈련 자료, 공개·발송·예약 없음

## 요약
| | variant_missing.mp4 | variant_recovered.mp4 |
|---|---|---|
| 렌더 종료상태 | `success:true` (예외 없음) **하지만 부분 결과** — `slides:3`, `skipped:["s003"]` | `success:true`, `slides:4`, `skipped:[]` |
| 실제 포함 장면 | **3/4** (opening·learn·closing), **prepare(s003) 누락** | **4/4** opening→learn→prepare→closing |
| 자막 큐 | 6 (prepare 원고 없음) | 8 (네 note 전문과 완전 일치) |
| 길이 | 21.89 s | 27.84 s |
| 판정 | **실패(부분)** — 길이·코덱은 요구를 만족하지만 장면과 원고 하나가 빠져 요구 미충족 | **통과** |

렌더러가 PNG 없는 장을 조용히 건너뛰고 성공으로 끝낸다. 누락은 반환값 `skipped`와 아래 실측으로만 드러난다.

## 1. 누락 재현 — variant_missing
- 호출: `[self:deck]{op:video, engine:edge, voice:ko-KR-SunHiNeural, captions:true, 1280×720, output_filename:variant_missing.mp4, wait:true}` (최초 렌더와 같은 요구).
- 직전 상태: `slides/`에 s001·s002·s004.png만 있었고 s003은 .json(spec)과 .html만 남아 있었다. 덱 slide_order는 4장 그대로다.
- 반환: success true, slides 3, narrated 3, missing_notes [], **skipped ["s003"]**, captions 6, caption_burned true.
- ffprobe: h264 High 1280×720 24fps (21.875 s) + aac LC 44.1 kHz stereo (21.89 s), 각 1개.
- 화면 장면 실측: 0.25초 간격 프레임 88장을 뽑고 상단 75% 영역을 슬라이드 PNG 4장과 비교했다. 결과는 s001 0.12–6.88 s → s002 7.12–13.88 s → **s004 14.12–21.88 s**이고, s003과 맞는 프레임은 0장이다.
- 자막 실측: 큐 6개를 note에 대응하면 opening·learn·closing만 완전 일치한다. prepare 원고("깨끗한 옷 한 벌, …가져오세요.")는 자막에 없다. 렌더러가 장을 통째로 건너뛰었으므로 나레이션에도 prepare가 없다(narrated 3). 다만 이 파일을 STT로 들어서 확인하지는 않았다.
- 산출물: `variant_missing.mp4`, `variant_missing.captions.ass`, `variant_missing.captions.srt`, `frames_variant_missing/`.

## 2. 복구 — s003 PNG만 재생성
- 숨겨 두었을 수 있는 원본 PNG는 찾지 않았다. 이전 턴에 저장해 둔 내 틀 `agent/work/template.html`과 장면 내용 `agent/work/contents.json`을 등록 스크립트 `슬라이드틀적용`에 다시 넘겨 복구했다(모델 호출 0회).
- 스크립트는 장마다 spec 해시와 PNG 해시를 비교한다. s001·s002·s004는 `reused:true`(파일 수정시각 11:17 그대로)였고, **s003만 `reused:false`로 다시 렌더했다**(11:45).
- 복구한 s003.png: 1280×720, 33,039 B, sha256 `635dde26…bf555`. 하단 540–719px에서 배경색과 다른 픽셀은 0개다.
- 덱 상태: slide_order s001→s004, 네 장의 title과 speaker_note가 scenes.json과 문자열로 완전히 같다(4/4).

## 3. 재렌더 — variant_recovered
- 호출은 1절과 같고 output_filename만 `variant_recovered.mp4`로 바꿨다. bgm_path와 rate는 지정하지 않았다(rate 기본값 +0%).
- 반환: success true, slides 4, narrated 4, preset_narration 0, missing_notes [], skipped [], captions 8, caption_burned true.
- ffprobe: 컨테이너 mp4 **27.84 s** / 비디오 1개(h264 High, 1280×720, yuv420p, 24fps, 27.708 s) / 오디오 1개(aac LC, 44.1 kHz, stereo, 27.84 s). sha256 `28376808…f943`.
- 배경음악: 지정하지 않았다. silencedetect(−45 dB, 0.25 s)로 문장 사이 무음 12구간을 찾았다. 배경에 연속음이 없다는 것과 맞는 신호 기반 판단이다.

### 장면 순서·원고·실측 길이
| # | key | slide | 화면 title | note(나레이션·자막 원문) | 구간(s) | 길이(s) | 자막 큐 | 화면 실측(프레임 분류) |
|---|---|---|---|---|---|---|---|---|
| 1 | opening | s001 | 버리기 전에, 함께 고쳐요 | 버리기 전에, 함께 고쳐요. 동네 수리교실에서 작은 수선을 시작합니다. | 0.00–6.77 | 6.77 | 1–2 | s001 0.12–6.88 |
| 2 | learn | s002 | 단추 하나부터 천천히 | 떨어진 단추를 달고, 작은 구멍을 꿰매 봅니다. 처음이어도 괜찮아요. | 6.77–13.63 | 6.86 | 3–4 | s002 7.12–13.88 |
| 3 | prepare | s003 | 가져올 것은 세 가지 | 깨끗한 옷 한 벌, 바느질 도구, 그리고 배우고 싶은 마음을 가져오세요. | 13.63–19.58 | 5.95 | 5–6 | s003 14.12–19.62 |
| 4 | closing | s004 | 토요일 두 시, 가상 마을회관 | 토요일 오후 두 시, 가상 마을회관에서 만나요. 이 영상은 훈련용 가상 행사 안내입니다. | 19.58–27.84 | 8.26 | 7–8 | s004 19.88–27.62 |

장면 구간은 렌더러가 실측 나레이션 길이로 만든 자막 타임라인에서 얻었고, 화면 분류 구간과 0.25초 안에서 일치한다(fade 전환 구간은 분류에서 제외).

## 4. 실제 검수 범위
| 항목 | 방법 | 범위 | 결과 |
|---|---|---|---|
| 스트림·길이 | ffprobe | 두 파일 전체 | missing 21.89 s / recovered 27.84 s, 둘 다 1280×720 h264 + aac 각 1개 |
| 장면 포함·순서 | 0.25 s 간격 프레임 상단 75%를 슬라이드 PNG와 평균 차이로 비교 | missing 88장, recovered 112장 | missing s001→s002→s004 (3장면), recovered s001→s002→s003→s004 (4장면) |
| 자막 원문 | ASS 파싱 → 장면별 공백 1칸 결합 → note와 `==` 비교(정규화 없음) | recovered 큐 8/8 · 장면 4/4, missing 큐 6/6 | recovered 완전 일치. missing은 prepare가 빠진 3장면만 일치 |
| SRT 사본 | SRT를 다시 읽어 ASS 큐 텍스트와 비교 | recovered | 일치 |
| 구운 자막 위치 | 큐 중간 프레임에서 배경과 다른 행·열 측정 | recovered 8/8, missing 6/6 | 자막 박스 y 619–683, x 180–1099 → 전부 y ≥ 540, 화면 안 |
| 제목 표시·겹침·잘림 | `engines:image_read` 육안 판독 | recovered 장면당 1장 = 4장(큐 1·3·5·8) | 네 title이 글자 그대로 보이고 자막은 그 시점 원고와 같다. 겹침·잘림 없음. variant_missing 프레임의 육안 판독은 파일명을 잘못 지정해 실패했고, 픽셀 분류로만 확인했다 |
| 복구 PNG 하단 여백 | 픽셀 비교 | s003.png | 배경과 다른 픽셀 0 |
| 내용(받아쓰기) | `[sense:listen]{op:transcribe}` | recovered 0–27.84 s 전체 | 네 note의 문장이 순서대로 모두 나오고 prepare 문장도 포함된다. 차이는 전사 표기뿐이다(쉼표 일부 누락, "수리 교실", "마을 회관", "오후 2시"). missing은 STT를 하지 않았다 |
| **발음 청취** | — | — | **사람이 듣는 청취 검수는 하지 않았다.** STT 일치는 내용을 알아들을 수 있다는 증거일 뿐 발음·억양의 승인이 아니다. "두 시"가 실제로 어떻게 읽혔는지는 미확인이다 |
| 목소리 | 렌더 인자 | 두 렌더 | edge ko-KR-SunHiNeural, rate +0% 하나, preset_narration 0 |

## 5. 보존·경계
- 기존 agent 폴더의 최종본 3개는 이전 턴에 기록한 sha256과 같다. 따라서 변경되지 않았다: `suri_class_promo.mp4`(177b05e3…), `.captions.ass`(b37fc892…), `.captions.srt`(71832457…).
- 이번 턴에 쓴 곳: agent/variant/ 아래, 그리고 덱 폴더(s003.png 복구, video/variant_*.mp4·.ass 원본 렌더). 이전 렌더 `video/suri_class_promo.*`는 다른 파일명을 써서 건드리지 않았다.
- 다른 실행자의 trainer·drafts·harness·정답·보고서는 열지 않았다. 숨겨진 원본 PNG도 찾지 않았다. 외부 게시·전송·예약 호출은 0건이다.
- 검증 스크립트와 원시 결과는 `work/verify_variant.py`와 `work/verify_variant_result.json`에 있다.
