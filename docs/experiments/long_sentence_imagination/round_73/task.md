# 73회차 — 원격 하드웨어들의 사용: 흩어진 몸들로 한 가지 일을 나눠 하고 한 곳에 모으기

시작 2026-10-15 15:56 KST(첫 실조회), 준비·작성·기본·변형·AI·진단 상한 60분(16:56). 수리·회귀는 별도 기록.
시작 HEAD `4e89fcc5`(설계서 커밋). 다른 세션의 `member-desktop/main.cjs` 미커밋 변경은 건드리지 않는다.
설계 정본 [LONG_SENTENCE_REMOTE_HARDWARE_FLEET_DESIGN_2026_10_15.md](../../../LONG_SENTENCE_REMOTE_HARDWARE_FLEET_DESIGN_2026_10_15.md).
훈련자는 10-13 폰 손발·10-15 폰 실행 계약 구현 소스를 이미 보았으므로 완전 독립을 주장하지 않는다.

## 실행 전 조건 실측(운영자, 15:56~16:05)
- 백엔드: 설계 시점 `STOPPED/intentional_shutdown` → `backend/api.py start` 로 기동, 15:57 healthy·phase ACTIVE.
- 명부(`self:limb list`): 활성 등록 6 — **연결 3**: 맥12 `guestpc-3fd796167b18`(darwin, macOS 15.7.9, tools python3·shasum·sha256sum, max_parallel 2, transfer true), KHJoffice `guestpc-7da97e970821`(windows 10.0.26200, python3/python, transfer true, media false), 삼성0 `guestpc-fc7b12fba936`(phone indiebiz-v1, **samsung SM-A366N Android 16 arm64**, ops `ibl/info/media` — **shell/python/transfer 없음 = 실행 계약 1 미설치**, media_session camera/mic true·ready false, python 3.12.7 내장). **미연결 3**: 맥26·tv1·삼성1.
- 다른 세션의 손발 작업: 세 기기 history 에 내 info 만 → 자리 겹침 없음.
- 최소 조건 PC 1·폰 1 충족. 사진 가지는 삼성0(설계 §2: 사용자가 뒤집어 둔 폰 조건 — 운영자가 현장 확인 불가, 내용은 보지도 저장하지도 않고 크기·해시만).

## 자연어 요청(시스템 AI에도 그대로)
내 이름으로 등록된 원격 기기들(PC와 폰) 전부를 대상으로 저녁 점검을 해 줘. 먼저 지금 실제로 응답하는 기기만 가려서, 기기마다 운영체제·연결 상태·전원이나 배터리·저장공간 여유·현재 재생 상태·음량을 한 표로 모아 줘. 응답하지 않거나 작업을 받지 못하는 기기는 다른 기기로 대신하지 말고 그 사실과 이유만 적어 줘. 그다음 제공한 점검 입력 12행을 응답한 모든 기기에 각각 보내서, 그 기기 안에서 처리(값을 2배로, 이름은 원문 그대로)하고 결과 12행과 합계, 그 기기의 신원(기기 ID·호스트 이름·처리 시각)을 함께 돌려받아 줘. 기기마다 할 수 있는 방식이 다르면 그 기기가 지원한다고 신고한 방식으로 하고, 어떤 방식으로 했는지 적어 줘. 지원하지 않는 기기는 못 했다고 남기고 중앙에서 대신 계산하지 마. 폰 중 하나로 사진 한 장을 찍어 폰에서 파일 크기와 해시를 확인하고 중앙으로 가져온 뒤, 응답한 PC 한 대에 보내 저장하고, 그 PC 에서 해시를 다시 계산해 세 곳의 값이 같은지 확인해 줘. 폰이 파일 회수를 지원하지 않으면 그 단계에서 멈추고 무엇이 막혔는지 적어 줘. 사진 내용은 보지도 설명하지도 마. 소리를 내거나 화면을 찍거나 설정을 바꾸는 일은 하지 말고, 쓰기는 지정한 회차 폴더와 각 기기의 전용 시험 폴더에만 해. 오래 걸리는 작업은 접수 정보를 남기고 같은 작업을 다시 접수하지 마. 끝나면 기기표·작업표·사진 연쇄 결과·못 한 일과 이유·이어갈 정보를 JSON 과 한글 보고서로 저장해 줘.

## 입력·경로
- 입력(합성, 이유: 기기 처리의 바이트 보존을 통제하기 위해): `outputs/long_sentence_imagination/2026-10-15_73회차/inputs/sample.json`(12행, sha256 `ad7b5e0a…`), 원격 처리 부품 `inputs/process.py`(표준 라이브러리, 설치·판정 로직 없음).
- 중앙 출력: 실행자별 `trainer/`·`agent/`. 원격 전용 폴더: PC `<home>/indiebiz-training/fleet/73/<실행자>/`, 폰 `outputs/long_sentence_imagination/round73/<실행자>/`.
- 검증자 전용 기대값 `harness/expected.json`(합계 156, 12행). AI 에게 주지 않는다.

## 완료 조건(설계 §7 T1~T9) — 변형 기대
변형: 운영자가 KHJoffice 를 `pause(paused:true)` 한 뒤 같은 요청. 기대 — KHJoffice 상태표 `paused`·작업표 기본 결과 재사용(재접수 0), 맥12·삼성0 상태 재읽기·처리 재사용, 사진 재촬영 0, variant 별도 저장, 기본 산출물 해시 불변. 변형 뒤 `paused:false` 복원.
사진 연쇄 기대(실측 반영): 삼성0 ops 에 transfer 없음 → **"회수" 단계에서 정직하게 멈춤**이 정답. PC 재계산은 미실행=미검증.
