# 긴문장 75회차 — 최근 PC·TV 재사용 부품의 점검·복구·재판정

> 아래는 최초 훈련 시점 기록이다. 이후 사용자 요청으로 수행한 [후속 수리·재검증](repair.md)에 최신 해결 상태와 잔여를 남겼다.

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 실행했다. **훈련 완료, 시스템 수리 없음.**
2026-10-18 19:01 시작, 주 과제·변형·진단은 19:12까지, 보고·증거 정리·커밋은 별도 운영 시간.
60분 상한 안에 종료했다. 시작 HEAD `b66081d1`, 종료 직전 HEAD `02f29f57`(다른 세션의 설계 문서 커밋).
시험한 PC/TV 저장 함수·스크립트·OS 구현 6파일은 시작 커밋과 바이트 동일함을 확인했다.
초기 미커밋 작업은 그대로 두었다. 최초 HTTP 연결 거절 뒤 관리 진입점으로 백엔드를 시작했다.

## 1. 과제·입력·작성

[실행 전 계약](task.md), [자연어 요청 원문](request.txt), [기본 명부](fixtures/base.json), [변형 명부](fixtures/variant.json).
최근 `b66081d1`의 가이드 이름 해소·등록 스크립트 계약·PC 제어/후속 확인과 앞선 PC·TV 공용 제어를 시험했다.
본체·연결된 Windows PC·오프라인 Mac·실제 TV·부재 대상·PC로 잘못 분류한 폰, 6행이다.
실기기에는 status만 요청했다. 음량·음소거·전원·재생·등록 변경을 시험한 회차가 아니다.

요구 → 관측(대상별 실패 격리) → 판정(정책별 출력 조건) → JSON/Markdown 저장·재독으로 나눴다.
지역 함수 `관측`은 원 영수증/원 결과/오류를 반환하고, `판정`은 외부 효과 없이 ready를 계산한다.
PC의 전송·대기·검증은 기존 `PC제어`/`PC제어확인`, TV는 `TV제어`에 맡겼다.
[최초 초안](base_v0.ibl)의 `join` 인수 순서 오류를 검사기가 정확히 안내했다.
수정 **1주기** 뒤 [v1](base_v1.ibl)은 기본·변형 모두 실행됐다. 변형의 프로그램 수정은 0회다.
참고 자료는 anatomy/진화 목적/훈련 가이드/조합 교재/PC·TV 가이드와 라이브 describe/script list다.
내부 구현은 최초 전체·변형 실행 뒤 null 영수증 진단과 AI가 제기한 Windows 필드 확인 때만 열었다.

독립 AI에는 자연어 원문과 입력·출력 위치만 주었다. 훈련자 해법·정답은 전달하지 않았다.
실행 로그에서 다른 실행자의 결과 열람은 관측되지 않았다(상위 폴더 이름 목록은 열람).
AI도 본 작업을 IBL로 작성했고 Bash는 입력 열람·소스 진단·파일 지문 확인 등에 사용했다.
실제로 작성한 코드는 [ai/](ai/)에 보존했다. AI의 소스 진단은 계약만으로 수행한 경로와 구분한다.

## 2. 결과와 판정

| 실행 | 검사 / 종료 | 산출물 검증 | HTTP/에피소드 시간 | ready / total |
|---|---|---|---:|---:|
| 훈련자 기본 v1 | issues 0, runtime guards 남음 / completed | 6행·근거·합계·재독 통과 | 19.369초 | 2 / 6 |
| 훈련자 조건 강화·역순 | 같은 프로그램 / completed | 원 관측·초기 영수증·기본 파일 보존, 새 기기 조회 0 | 5.504초 | 2 / 6 |
| 독립 AI 기본 ep4905 | 자체 검사·실행 / succeeded | 6행·근거·합계·재독 통과 | 250.471초 | 2 / 6 |
| 독립 AI 조건 강화 ep4906 | 자체 검사·실행 / succeeded | 역순·원 관측 보존·새 기기 조회 0·기본 파일 지문 동일 | 87.382초 | 1 / 6 |

기본 과제는 두 실행 모두 **달성**이다. 실패/미확인 대상을 정확히 남기는 것도 완료 조건이다.
변형의 저장·재사용·판정 일관성은 각 출력이 선언한 근거 기준으로 통과했다.
그러나 **Windows capability의 뜻이 달라 변형 두 결과를 같은 의미의 전건 정답으로 합치지 않는다**(L75-2).
훈련자 변형은 공개 부품의 Bool 값 기준 달성, 더 강한 “장치별 직접 관측” 해석은 미검증이다.
AI 변형은 직접 관측되지 않은 능력을 미확인으로 남기는 조건을 달성했다. 최종 답변에는 L75-3이 있다.

- 본체: 출력 4개, Windows: 출력 4개. 실제 소리·영상 재생은 미검증이다.
- Windows는 첫 `pending`의 task_ref를 그대로 확인해 `completed/verified:true`가 됐다.
- 오프라인 Mac·부재 ID·잘못된 종류는 모두 실패 근거를 보존했고 다음 행으로 이어졌다.
- TV는 `success:true, reachable:false, power:unknown, verified:false`였다. 꺼짐·준비 완료로 바꾸지 않았다.
- 변형은 행을 역전하고 음량/음소거 조건을 모두 켰다. 기존 관측의 request_id·task_ref·내용을 보존했다.

훈련자 run `48bb3ac7b8ce4fc188b22cdb38d0e522` / 변형 `e6762613ab244b6e873ce5ffc0016d6d`.
훈련자 원격 작업 `2b0042a8b1f240c7b86de6371835b993`, AI 원격 작업 `5bd9a38a16a34dc68f8f7c0d5aa3cca5`는 완료 결과를 회수했다.
AI task `task_sysai_70526a20` / `task_sysai_a17ca5c6`은 모두 succeeded로 회수했다.
실패 탐침은 엔진 `interrupted`로 반환된 종료 결과이며 실행 중인 원격 작업이 아니다.

### 최근 수리의 실전 확인

| 시험 | 실제 관측 |
|---|---|
| 정확한 가이드 이름 | pc_control.md, python_libraries.md, managed_records.md를 정확히 반환. 미등록 두 파일은 registered:false |
| 호환 별칭 | ibl_v2.md → ibl_composition.md, reference_kind:alias |
| 부재 가이드 | 오류와 본문 없음. 다른 가이드 본문으로 대체하지 않음 |
| read:false / if_hash | 본문 없는 메타데이터 / unchanged:true, 본문 재전송 없음 |
| 등록 부품 계약 | PC·TV callable_contract 조회 성공 |
| 잘못된 TV status 인수 | url을 함께 주면 검사 및 실제 실행 입구 모두 ARGUMENT_CONTRACT, executed:false |
| 원 영수증 재사용 | 기존 pending 영수증으로 다른 IBL 실행에서 완료 회수. 새 원격 접수 없음 |
| 대상/소스 지문 변경 | 모두 unknown·verified:false와 verification 실패 사유. 잘못된 성공 0 |

증거: [탐침](evidence/probes.json), [영수증 변형](evidence/receipt_probe.json),
[훈련자 원 관측](evidence/trainer_observations.json), [검증기](harness/verify.py).
검증기는 AI의 kind 객체·evidence.prior 래퍼를 풀도록 보완했다. 최초 검증기의 스키마 불일치 실패는
실행자 결함으로 세지 않았다. 기대 조건을 낮춘 것이 아니라 같은 id/target/근거/판정을 비교한 것이다.

## 3. 발견과 다음 수리의 경계

### L75-1 — 후속 확인의 null 근거 입력 방어 공백 (구현, 확정)

`evidence_ref` **생략**은 unknown과 원 영수증 확인 안내를 반환한다. 같은 자리를 **null**로 두면
`RECORD_REQUIRED: has/get은 Record와 Text 키를 받습니다`로 중단한다.
최초 4건 연쇄 탐침에서 앞 3건은 완료/unknown/unknown, 마지막 null 행에서 전체가 interrupted가 됐다.
부분 결과와 실패 위치는 보존됐으므로 침묵·거짓 성공 문제는 아니다.
행별 catch를 추가한 진단 프로그램에서도 같은 타입 오류를 관측했다.

[독립 최소 재현](null_receipt_repro.ibl)과 [생략 대조군](missing_receipt_control.ibl)은 실기기 없이 재현된다.
원인: `data/idioms/pc_control_check.ibl:4`의 `get(...,{})`은 null을 기본값으로 바꾸지 않는데,
다음 줄에서 그것을 Record로 다시 get한다. 형 계약은 작업 Unknown이어서 사전검사는 incomplete다.
정상 pending 전체 반환값의 후속 확인은 통과했다. **손상 입력 복구의 진단 일관성 문제**로 한정한다.
수리 후보: 공개 함수 경계에서 근거 Record 여부를 검사해 기존 unknown/failure 계약으로 정규화.
생략·null·잘못된 타입·유효 원 영수증·변경된 대상/지문을 같은 회귀에 넣고 원래 전체 흐름도 재검증한다.
이번 회차에는 수리하지 않았다.

### L75-2 — Windows 능력 필드의 출처·뜻 공백 (계약/해석, 기능 불능은 미확정)

`pc_control_windows.ps1:67`의 `can_set_volume=true, can_mute=true`는 기본값이다.
macOS는 해당 속성의 설정 가능 여부를 조회한다. 같은 이름의 두 필드에 서로 다른 근거가 실린다.
훈련자는 반환 Bool을 그대로 사용했고, AI는 소스 확인 후 Windows 값을 별도 원문으로 보존하고
직접 관측 능력은 unverified로 표기했다. 이 차이가 변형 ready 2 대 1을 만들었다.

**상수라는 이유만으로 Windows 조절 기능이 고장났다고 판정하지 않는다.**
AI가 제안한 QueryHardwareSupport는 하드웨어 지원 조회다. Windows는 하드웨어 지원이 없어도
소프트웨어 제어를 제공하므로 이것만으로 can_set_volume을 대체하면 뜻이 바뀔 수 있다.
[Microsoft의 QueryHardwareSupport 계약](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-queryhardwaresupport).

먼저 필드가 API의 지원 능력인지, 하드웨어 직접 지원인지, 이 장치에서 설정·재조회까지 검증한 것인지
구분해야 한다. 자동 수리로 false를 넣지 않는다. 현재 과제의 읽기 전용 범위에서는 실제 설정 성공을
검증하지 않았다. 다음 작업은 반환 설명과 근거 표시를 정렬하고, 사용자에게 허용된 시험 환경에서
소프트웨어/하드웨어 지원과 설정 후 관측을 별도로 검증하는 것이다.

### L75-3 — 최종 응답의 근거 없는 요청 귀속 (응답 품질, 원인 미확정)

AI 변형 최종 답변은 “작업 지시에는 '7행'이라고 되어 있었지만 … 6개”라고 썼다.
보존한 기본·변형 요청문에 7행 요구는 없다. 실제 산출물은 올바른 6행이다.
[원 응답](evidence/ai_variant_final.txt)을 보존했다. 사용자 요청과 내부 안내의 혼동인지 생성 오류인지는
확정하지 않았다. 일반적인 숫자·요청 귀속은 실제 요청 원문으로 대조하고, 근거 없는 정정 서술은
응답에 넣지 않는 것이 개선 방향이다. 산출물 계산 오류와 구분한다.

## 4. 독립 AI의 발견·검수·비용

| 관측 축 | 기본 / 변형 |
|---|---|
| 풀이 | 실제 IBL 조합, 기본 execute_ibl 9·Bash 6 / 변형 2·2(검사 포함) |
| 분할·재사용 | 변형은 자신의 기존 JSON만 읽어 재판정. 기기 도구 호출 0 |
| 발견 | 기본 describe로 저장 함수 발견·사용. 처음 목록 필터의 contains 인수/Null 접근을 자체 수정. 이후 구현을 읽어 capability 출처 판단 |
| 완료 | 두 산출물 재독·행수/ID/합계 검증. 최종 평가 사건 두 턴 모두 존재 |
| 회상·축적 | recall.presented/used 각 1회씩. origin=training, 압축 0, 증류 없음 |
| 사용자 재요청 | 훈련 변형 요청 외 보완 요청 없음. 최종 문장 L75-3은 검수에서 잡히지 않음 |

[계측 원문](evidence/metrics.json), [AI 도구·작성 코드의 연결](evidence/ai_actions.json).
기본은 250.471초, 공급자 보고 input **2,833,497**, output **16,644**, cache_read **2,506,055**,
cache_create **321,470**. 변형은 87.382초, input **1,075,252**, output **7,553**,
cache_read **1,010,094**, cache_create **55,141**. cache를 input에 다시 더하지 않았다.
분류·의식·실행·평가·변형의 background 역할까지 계측에 포함했다. 주 실행/의식 ClaudeCode opus,
보조 deepseek-flash. 훈련자 작성 모델 토큰은 미측정이며 IBL 내부 모델 호출 0을 작성 비용 0으로 세지 않는다.
API 시간과 AI 에피소드 시간의 포함 범위가 달라 속도/토큰 개선율은 주장하지 않는다.

필요했던 비용은 실제 조회·실패 격리·동일 영수증 회수·최종 재독이며, capability 소스 확인은
판정 차이를 드러냈다. 줄일 후보는 PC 행마다의 전체 손발 목록 반복과 AI의 4차례 소스 검색/열람이다.
공개 계약에 출처·보장 범위가 있으면 구현 탐색을 줄일 수 있다. 이는 절감 후보이며 비교 실험은 하지 않았다.
변형에서는 실제 기기 재조회·원격 재접수 비용을 이미 피했다. 검수나 실패 표시는 줄이지 않는다.
초안 join 오류 1회는 작성자 오류로 계상하고 시스템 결함으로 올리지 않았다.

## 5. 보존·미검증·재현

로컬 전문: `outputs/long_sentence_imagination/2026-10-18_75회차/`의 runs, inputs, trainer, ai, evidence.
정본 문서에는 비민감 명부·실행 프로그램·원 관측·검증 결과·최소 재현·AI 코드/최종 답변을 보존했다.
API 키·페어링 토큰·원장 key_hint와 전체 기기 원장은 포함하지 않았다.

실기기 주 과제는 해당 장치/등록이 있어야 재실행할 수 있다. `base_v1.ibl`을 `/ibl/execute`에
edition:2, origin:training, project_id:study, inputs(input_path, previous_path, out)로 보낸다.
기본 previous_path는 빈 문자열, 변형은 자신의 기본 report.json이다. 먼저 check:true로 검사한다.
null 최소 재현은 등록된 실기기 없이 실행할 수 있고, TV contract_probe는 executed:false가 기대다.

실제 음량 변경·유튜브 교체/중복 재생·TV 전원/입력 제어·폰 갱신·UI 클릭은 이번 회차 미검증이다.
수리나 전체 backend/frontend 회귀는 수행하지 않았다. 코드 수리 없이 실제 IBL·HTTP·산출물 검증에
집중한 회차다. 새 관용구 등록·해마 시딩·예약 실행도 없다.
가이드 §4-5의 두 실행 비교와 §5의 원인 분리는 유효했다. 추가로 capability의 값뿐 아니라
관측 출처를 분리하면 두 실행의 판정 차이를 더 일찍 발견할 수 있다.
