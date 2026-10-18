# PC 제어 — 앱과 AI의 공용 호출

macOS·Windows PC의 출력 장치·음량·음소거·주소 열기·잠금과 Windows 유튜브 제어를 한다.
앱의 PC 컨트롤과 AI는 저장 함수 `PC제어`·`PC제어확인`을 함께 쓴다.
`execute_ibl`의 `describe:["fn:PC제어","fn:PC제어확인"]`으로 서명을 조회한다.
내부 스크립트 계약은 `[self:script]{op:"list",id:"PC제어부품"}`에 있다.

## 대상 선택

`[self:limb]{op:"list"}`의 device_id·이름·설명·OS·연결 상태를 읽어 사용자가 가리킨
PC를 고른다. 본체는 `__local__`을 명시한다. 출력 장치 ID와 PC ID는 서로 다르다.
PC가 한 대여도 자동 선택하지 않는다. 중지·해제·미접속·미지원 OS는 실행 전에 거절한다.
OS와 실행 파일·전송 명령은 부품이 해소하며 호출자가 지정하지 않는다.

다음은 자리표 골격이다. 대상 ID와 출력 ID는 조회한 실제 값으로 고쳐 쓰는 것이 정상이다.

```ibl
#!ibl edition=2
$PC = "선택한 device_id"
return [fn:PC제어]{대상:$PC,요청:{action:"status"}}
```

상태 결과의 `result.devices`에서 사용할 출력의 ID와 can_set_volume·can_mute를 확인한다.

```ibl
#!ibl edition=2
return [fn:PC제어]{대상:"선택한 device_id",요청:{action:"volume",device_id:"조회한 출력 ID",value:30}}
```

| action | 추가 요청 인수 | 관측 범위 |
| --- | --- | --- |
| status | 없음 | OS의 출력 장치·음량·음소거 |
| volume | device_id, value:0~100 정수 | 지정 출력의 음량 재조회(오차 ±1) |
| mute | device_id, enabled:Bool | 지정 출력의 음소거 재조회 |
| open_url | url:HTTP(S) | 브라우저 열기 요청. 페이지 표시·영상 재생 보장 아님 |
| lock | 없음 | 잠금 요청. 잠금 화면의 실재 확인 아님 |
| youtube_status | 없음 | Windows 브라우저의 기존 유튜브 탭 |
| youtube_replace | url,title,duration_seconds,fullscreen:Bool | 기존 재생 정지·탭 수 유지·본영상 재생·요청한 전체화면 |
| youtube_stop | 없음 | 기존 재생 정지·탭 수 유지 |

## 유튜브 영상 선택

Windows의 Chrome·Edge·Brave에서 기존 재생 탭을 교체한다. 영상 검색 결과의 URL·전체 제목·
길이를 사용하며 길이는 **초** 단위 정수다. 생방송은 지원하지 않는다. 광고가 재생 중이거나
본영상 시간을 확인하지 못하면 검증 실패다. `open_url`로 새 유튜브 영상 플레이어를 추가하지 않는다.
macOS의 브라우저 교체는 지원하지 않는다. TV 자체 앱 실행은 [TV 제어](tv_control.md)의 launch다.

## 완료와 후속 확인

반환은 status·target·verified·result·task_ref·verification·evidence_ref·failure다.
`completed`는 호출 처리 종료이며, `verified:false`를 목표 달성으로 보고하지 않는다.
OS 음량 관측은 물리 스피커에서 소리가 나는지 확인한 것이 아니다.

`pending`이면 **전체 반환값**을 보존해 다음처럼 확인한다. 변경 요청은 다시 보내지 않는다.

```ibl
#!ibl edition=2
$작업 = [fn:PC제어]{대상:"선택한 device_id",요청:{action:"status"},대기:0}
return [fn:PC제어확인]{작업:$작업,대기:60}
```

대기는 기본 60초, 유튜브는 150초이고 0~240초로 조절한다. 장치 실행 제한은 별도로
기본 30초·유튜브 120초다. pending을 failed로 바꾸거나 자동 재전송하지 않는다.
`unknown`은 접수·관측·원 근거가 불확실한 경우다. 실패에는 단계와 다음 확인 방법이 있다.

후속 확인은 준비·접수의 원래 실행 영수증과 대상·요청 ID·OS·소스 지문을 대조한다.
verification을 임의 수정하면 검증하지 않는다. 검증기 코드가 바뀌거나 영수증이 만료되면
unknown으로 남긴다. 최신 코드를 다시 보내 과거 결과를 대신 만들지 않는다.
값을 잃었으면 execute_ibl의 기존 `result_ref.read_args`로 원 반환을 회수한다. 접수 응답 자체를
잃은 경우 원 실행의 resume·실행 기록과 guestpc history로 확인하고 새 요청을 만들지 않는다.

## 설치와 수리

배포 정의의 정본은 `data/idioms/pc_control*.ibl`, 구현은 `data/scripts/pc_control.py`다.
설치 목록 `data/idioms/installed.json`이 첫 부팅에도 정의를 제공한다. 같은 이름의 다른 개인
정의는 충돌로 신고한다. 임베딩 색인 등록은 `register_webapp_idioms.py --seed-file pc_control_seeds.json`을 사용한다.
구현은 prepare→guestpc→task→검증을 소유한다. 정상 호출에서 이 연결을 다시 작성하지 않는다.
