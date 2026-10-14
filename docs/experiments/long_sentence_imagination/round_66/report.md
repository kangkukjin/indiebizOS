# 66회차 — 원격폰 기능 활용·준비 상태·파일 왕복

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 훈련과 소스 수리. 중앙 적용 확인,
삼성1용 arm32 APK 빌드 성공. **폰 쪽 출처 전달 수정은 APK 설치 대기**다.
현재 설치본의 카메라·마이크 등을 실제 가동한 검증과 모든 하드웨어 지원은 주장하지 않는다.

## 과제와 경계

[자연어 과제](task.md): USB 없이 삼성1의 실제 info·라디오/음악 상태 조회, 12용도 근거 판정,
폰 전용 폴더에 합성12행 저장·재독·중앙 회수, JSON/한국어 보고서 저장·재독.
변형은 없는 대상 추가·행 역순·메모 변경이며 기본 결과를 보존한다. 추가 수리 검증은
CRLF·조합형 한글·이모지·역슬래시·인용문을 넣은 새12행이다.
촬영·녹음·위치·재생/알림/진동·전화·문자·설정 변경을 하지 않았다.

훈련자는 이미 읽은 구현의 영향을 받으므로 완전 독립을 주장하지 않는다. 시스템 AI에는
자연어와 합성 입력/별도 출력 경로만 전달했고 trainer/harness/정답 열람을 금했다.
변형에서는 자기 직전 결과의 재사용을 허용했다. 수리 후 재실행 역시 같은 rehearsal 문맥이므로
차가운 시작 비교가 아니다. 외부 사실 검색이 필요한 과제가 아니며 실기기 응답이 근거다.

## 실행과 판정

- 08:08 KST 시작 → 08:57:04 훈련 종료(49분). 준비·접속 승인 대기를 포함한다.
  최초 describe 08:09:34, 실제 AI 기본 실행 08:43:12. 승인 대기와 작성 시간을 분 단위로
  정확히 분해하지 못했으며 활성 과제 실행 구간은 약14분이다. 60분 훈련 상한 안에서 종료했다.
- 기본·변형 AI 종료/자식0과 원격37건 전부 종료(성공33/실패4)를 회수한 뒤 제품을 수정했다.
  이후 08:57~09:12 수리·회귀·APK 빌드·추가 검증 약15분, 뒤의 커밋 관문 시간은
  별도다. 훈련시간에 수리 시간을 숨겨 넣지 않았다.
- [초안](base_v0.ibl)은 join 인자 순서 오류. [v1](base_v1.ibl)은 기본32.075초/변형28.888초로
  원격 왕복과 중앙 재독 성공. 사람용 보고서의 신원·권한 원문 누락과 지원 과해석을
  [v2](base_v2.ibl)에서 보완: 기본15.703초/변형33.956초. JSON 근거는 v1부터 보존됐다.
- 수리 후 같은 v2 기본31.198초/변형28.455초/새 변형22.312초. 모두 실제 폰12행 전건 일치,
  없는 대상의3개 probe는 접수 전에 거절(task_ref 없음), 기존 base 산출물 해시 불변.
  소요시간은 요청~응답 벽시계이며 작성/검수 시간과 다르다.
- 독립 AI 기본 ep4728: 486.802초, execute_ibl22회+Bash6회. 첫 파일 인용 실패 후 새 파일로
  복구, 최종12행의 id/purpose/note 전건 일치. 본인의 추가 verdict 필드는 비교와 분리했다.
  판본1 read 응답으로 원문을 못 받았다는 기술 판단은 아래 L66-3에서 정정한다.
- 독립 AI 변형 ep4729: 215.194초, execute_ibl5회. 자기 판정을 재사용하되 실제 기기와
  재생 상태/새 파일은 다시 조회했다. 역순·수정 메모12행 일치, 없는 기기 미실행, base 보존.
- 수리 후 AI 재실행: ep4730 314.463초, execute_ibl16회·Bash0회, 자식0으로 완료.
  별도 edition2·json 직렬화를 스스로 선택해 원문664자와12행 모두 일치.
  f문자열에 Python식 {{를 쓴 오류와 get을 목록에 쓴 오류2건은 스스로 복구했다.
  중앙 대조 오류 뒤 이미 끝난 폰 작업을 재실행하지 않고 참조를 재사용했다.
  수정 후 검증 원격16건(성공15/실패1, 최종 교재 예제 포함) 모두 종료. 무오류 작성·문서 변경의 인과 효과는 주장하지 않는다.

실기기는 Android9 Samsung SM-J730K(32비트), Python3.11.10. 연결·IBL·파일 왕복과
라디오 stopped/음악 now_playing=null·queue0 조회는 실제 확인했다. camera/microphone의
지원·권한·ready와 speaker/playback/video_receive/video_playback은 앱의 true 신고다.
화면 송출은 screen:false 신고이며 가속도·Bluetooth·NFC는 조작 계약을 확인하지 못했다.
GPS/TTS/진동은 폰 사전에 어휘가 있으나 이번 훈련에서는 실행하지 않았다.
재실행이 보고한 명함52액션과 패키지 합111의 차이는 같은 분모가 아니다.
capability_card는 always_on 코어를 제외하고 self_can_run을 거른 소개용 내용어를 센다.
package list는 vocabulary_state.inventory의 패키지 귀속 수를 센다. 수치 차이를 결함으로 단정하지 않았다.

## 발견과 수리

| 갭 | 관측·분류 | 수리·확인 |
| --- | --- | --- |
| L66-1 | 중앙 origin=training이 원격 IBL 봉투·폰 localhost 요청·폰 실행 문맥에서 사라짐. 구현 결함 | resident_pcs→limb_client→phone_execution_routes 3경계에 training/test만 전달, user 값은 권한으로 승격하지 않음. 정상·예외 후 문맥 복원. 수리 전 관련20검사 중5실패→수리 후20통과. 실제 중앙 하달 봉투4건의 training 확인. 폰 설치 후 종단 실증은 대기 |
| L66-2 | 카탈로그가 Android 등록 미지원, 교재가 허브 비밀번호·없는 .ok 검사·미구현 transfer collect를 안내. 발견/학습 마찰 | USB 각인과 이후 원격 연결, info·판본2 결과.value, 실패/접수증 보존, 파일/바이너리 경계를 수정. 어휘 추가0, 설명만 변경. 기존 용례80건 검토, 은퇴 문구 관문 등록 |
| L66-3 | AI가 JSON을 중첩 IBL 문자열에 수동 삽입해 escape9개를 소비:1116자1559B 대 원본1125자1568B. 판본1 read를 폰 전체의 한계로 일반화 | 내부 프로그램에 별도 edition2 헤더, json(json(rows)) 직렬화, 폰 소유 참조와 중앙 참조 구분을 교재·카탈로그에 명시. 판본2 self:read.text는 실기기에서 정상. 파서 결함으로 단정하거나 파서를 바꾸지 않음. 원래/새 문자 변형 모두 통과 |
| L66-4 | 훈련자 join 인자 오류와 v1 사람용 보고서 누락·능력 신고 과해석 | 원래 오류 보존, v1/v2 수정 및 재독. 엔진 결함이 아닌 작성·완료 판정 문제로 분류 |

재발 검사는 [test_limb_client.py](../../../../backend/test_limb_client.py)의
`test_phone_ibl_preserves_isolated_origin_across_transport`와
`test_phone_ibl_cannot_turn_transport_metadata_into_user_grant`,
[test_phone_execution_routes.py](../../../../backend/test_phone_execution_routes.py)의
출처 설정/복원·예외·잘못된 메타데이터 검사다.

## 비용과 낭비 검토

| 실행 | input | output | cache_read | cache_create | 내부 청구 usage 이벤트 |
| --- | ---: | ---: | ---: | ---: | ---: |
| AI 기본 | 4,637,099 | 34,499 | 4,292,335 | 336,959 | 6 |
| AI 변형 | 1,917,304 | 16,886 | 1,795,808 | 110,911 | 6 |
| 수리 후 AI 기본 | 2,845,678 | 23,753 | 2,582,275 | 255,546 | 6 |

`trajectory_event.model.usage` 중 accounting=billable_usage만 합산했다. input에 캐시가
포함되므로 캐시 열을 input에 다시 더하지 않는다. 계획·실행·분류·평가를 포함한다.
기본 실행부29라운드/변형7라운드는 도구 호출28회/5회와 구분한다. 자동 압축0,
recall.presented/used 각각1회, training으로 증류 없음. 훈련자 모델 토큰은 미측정이다.
프로그램 내 모델 호출0을 작성자 비용0으로 표시하지 않는다.

실기기 신원·권한·재생 상태와 왕복 전건 대조, 손상된 첫 파일의 보존·재검수는 필요한 비용이다.
중첩 문자열 수동 인용과 판본 혼동으로 생긴 파일 재작성·read 재시도는 줄일 수 있었던 일이다.
별도 json 직렬화/헤더/결과 층 설명으로 재발을 줄이되 한글·따옴표·줄바꿈·빈 문자열 대조는 유지한다.
훈련자 변형은 없는 대상에 info/재생/왕복을 모두 시도했다. 기기 부재 확인 뒤 나머지를
미실행으로 기록하면 접수 전 중복 거절을 줄일 수 있으나 오류 보존은 유지해야 한다.
AI 변형은 기존 판정을 재사용해 중복 해석을 줄였다. 회상/지원 확인의 효용을 호출 수만으로
낭비라 하지 않는다. 실행자·문맥·산출물 상세도가 다르므로 일반적인 시간/토큰 절감률은 주장하지 않는다.

## 검증과 미검증

선택기: 변경8파일·backend2모듈, 전이619/676파일(92%)·resident_pcs 허브 → 전수.
직접 관련24통과, 관련 시스템72통과(106.04초). 최종 일반 backend 종합검사
**10,275통과·1건너뜀·1실패(137.31초)**. 이 실행의 실패는 작업 시작 전부터 있던
미추적 `test_scheduled_visible_fallback_2026_10_14.py`의 __main__ 누락을
`test_single_runner::test_r2_direct_run_delegates_to_pytest`가 검출한 것이다. 그 파일은
다른 작업의 본문이라 커밋하지 않았다. 다만 이것이 커밋 관문도 막아, 기존 본문을
바이트 그대로 보존하고 pytest.main 진입부만 추가했다(로컬 미추적 파일 유지).
그 파일과 단일 러너 관문8검사가 이후 통과했다. 종합 전체는 다시 실행하지 않았으므로
10275/1/1을 최종 전수0실패로 바꾸어 쓰지 않는다. 첫 회귀의 용례 원장 미확인·새 시험 러너 누락은
이번 변경에서 해결했다. 전체 통과로 표현하지 않는다.
IBL 생성물 --check, Android 번들, backend 층, 은퇴 계약 관문 통과.
커밋 전 가이드 예산36000B 초과를 검출해 폰 설명을 remote_phone.md로 분리하고
guide_db 검색·guest_helper 링크를 연결했다. 내용을 삭제해 예산을 맞추지 않았다.
재기동·지도 전수 등의 무관한 system 묶음과 프런트엔드 검사는 미실행.
수정한 교재 예제를 그대로 발췌해 전용 폴더에서 실행:12.392초, 추가 문자 변형12행 전건 일치.

삼성1용 arm32Debug APK 89,774,629B 빌드 성공. 엔진 zip의 limb_client가 정본 수정본과
바이트 일치한다. APK SHA256 `14aa1dc8f3a03beae02219b8677e94cc868913f30ebaba7727e2189d2444f647`.
빌드에는 작업 시작 때 이미 있던 폰 변경도 포함되며 그 파일들은 이번 커밋에서 제외한다.
USB는 미연결이고 현 손발 계약에는 앱 업데이트 경로가 없어 설치하지 않았다.
새 설치본의 실제 origin 종단 보존·센서/소리/영상 출력·외부망/TURN/장시간 안정성은 미검증이다.

## 증거와 재현

로컬 증거 루트 `outputs/long_sentence_imagination/2026-10-14_66회차/`:
`runs/` 요청·응답·시각, `trainer/`·`agent/` 산출물, `ai_*_trace.json`·`ai_*_episode.json`,
`training_closed.json`, `origin_baseline.json`·`origin-after-live.json`, `verification.json`,
`metrics.json`, `runner-repair.xml`·`foreign_test_runner_repair.json`, `origin-before.xml`·`origin-after.xml`·`targeted.xml`·`regression*.xml`·`system-related.xml`.
키·자격 원문은 보고서에 복사하지 않았다. 원래 실패 파일/응답도 보존했다.

새 경로로 재현(현재 활성 삼성1 필요):

```bash
python3 docs/experiments/long_sentence_imagination/round_66/harness/prepare.py replay_base
python3 docs/experiments/long_sentence_imagination/round_66/harness/transport.py replay_base outputs/long_sentence_imagination/2026-10-14_66회차/replay_base.request.json
python3 docs/experiments/long_sentence_imagination/round_66/harness/prepare.py replay_variant --variant
python3 docs/experiments/long_sentence_imagination/round_66/harness/transport.py replay_variant outputs/long_sentence_imagination/2026-10-14_66회차/replay_variant.request.json
```

[harness/verify.py](harness/verify.py)는 실행자가 쓴 성공 표시만 믿지 않고 원격 read의
실제 행을 합성 입력과 비교한다. 고정된 이번 실행 증거를 읽는 oracle이며, 새 replay 결과는
해당 label의 입력·원격 행을 같은 방식으로 비교한다. `prepare.py --new-variant`로 추가 변형을 만든다.
