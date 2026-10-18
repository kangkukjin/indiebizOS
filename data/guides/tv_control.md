# TV 컨트롤 — 손발 등록·앱·AI 공용 스크립트

TV 전원·입력·음량·앱·DLNA 재생을 제어할 때 읽는다. 앱 모드의 **TV 컨트롤**과 AI가
`~workspace/data/instruments/tv_control.py`를 함께 사용한다. 장치 소개의 `control_guide`가
이 파일을 가리킨다. 현재 문맥에 계약이 있으면 다시 읽거나 같은 코드를 새로 만들지 않는다.

## 대상과 등록

조종실 **손발 → 네트워크 기기 등록 · 삼성 TV**에서 이름·IPv4 주소를 등록한다.
TV에 IndieBiz OS나 PC 헬퍼를 설치할 필요가 없다. 현재 드라이버는 Samsung Tizen이며,
다른 제조사 TV가 자동으로 호환되는 것은 아니다. TV 컨트롤 앱은 상단 **제어할 TV 선택 → 거실TV 등 대상 선택** 뒤에 버튼을 누른다. 선택 전에는 제어 명령을 보내지 않는다. TV가 한 대여도 대상 선택은 필요하다.

- 켜기에는 유선/무선 MAC과 해당 LAN 브로드캐스트 주소가 필요하다. TV의 네트워크 대기·원격 켜기 설정 및 망에 따라 동작이 다르다.
- 최초 제어 전에 TV를 켜고 앱의 **TV 연결 허용·페어링**을 눌러 TV 화면에서 허용한다. 기존 토큰이 있으면 등록 시 재사용할 수 있다.
- 앱 ID는 모델별로 다를 수 있다. 등록 폼의 앱 ID를 확인한다. PC 입력 위치는 TV 입력 메뉴의 왼쪽부터 1로 세며 입력 목록 변화 후 다시 확인한다.
- 이름·위치·연결된 PC는 설명 데이터다. TV와 연결된 Windows PC는 각각 별도 `device_id`다. TV 입력 전환이 PC의 유튜브 재생이나 그래픽 재설정을 수행하지 않는다.
- 목록·일시 중지·해제는 기존 `[self:limb]`와 손발 패널을 쓴다. `adapter:"network-api"`, `kind:"tv"`, `os:"tizen"`이다. 이 기기에 `guestpc shell/python/info`를 보내지 않는다.
- 주소·MAC·페어링 토큰은 허브의 비공개 `network_hardware.json`에 저장한다. 앱/AI 공개 목록에는 연결 설정·토큰을 싣지 않는다. 등록 해제는 저장된 연결 설정을 삭제한다. TV 자체의 허용 기기 목록은 TV 설정에서 별도로 관리한다.

## 작업에 맞는 기기 선택

“TV에 유튜브”는 TV 자체 앱 실행과 연결된 PC의 브라우저 재생이 다르다. 장치 소개의 이름·설명·OS·adapter를 확인해 사용자가 가리킨 기기를 고른다. TV 자체 앱이면 이 가이드의 `launch`, Windows PC이면 `pc_control.md`의 **기존 재생 교체** 절차를 따른다. 일반 `open_url`로 유튜브 영상을 추가하지 않는다. PC 화면을 TV에 보여줘야 하는 경우에만 등록된 두 기기에 각각 PC 실행과 TV 입력 전환을 수행한다. 연결 관계가 설명에 없으면 추측하지 않는다. 두 경우 모두 요청 전달과 실제 영상 재생 확인을 구분한다.

## 상태 조회부터 실행

```ibl
#!ibl edition=2
return [self:limb]{op:"list"}
```

목록에서 확인한 TV의 `device_id`를 `$target`에 넣는다. 별칭이 겹칠 수 있으므로 ID를 쓴다.
아래 코드는 **허브**에서 실행한다. 스크립트는 `INDIEBIZ_BASE_PATH`로 허브 원장을 찾으며
요청 인수에 IP·토큰·설정 파일 경로를 받지 않는다. 앱도 동일한 경로로 실행한다.

```ibl
#!ibl edition=2
$target = "등록된 TV의 device_id"
$s = [self:read]{path:"~workspace/data/instruments/tv_control.py"}
$f = [self:write]{path:"~turn/tv_control.py",content:$s.text}
$r = [self:script]{path:$f.path,args:{target:$target,op:"status"},timeout:90}
assert $r.success == true, "TV 요청 실패. 변경 명령을 반복하지 말고 상태를 확인하세요.", {result:$r}
return $r
```

`target`을 유지하고 아래 인수로 `args`를 바꾼다.

| op | 추가 인수 | 확인하는 것 |
| --- | --- | --- |
| status | 없음 | API 응답과 보고된 power, 등록 앱의 running/visible |
| on | 없음 | WOL 후 power=on 재조회. 실패는 success=false |
| off | 없음 | on일 때만 전원 키 1회. off/standby 관측 때만 verified=true |
| volume | `steps:1` 또는 `steps:-1` (최대 ±10) | 상대 음량 키 전달, verified=false |
| mute | 없음 | **음소거 토글**, verified=false. 명시적 켜기/끄기 아님 |
| key | `keys:["KEY_HOME"]` 등 최대 40개 | 리모컨 키 전달, verified=false |
| launch | `app:"youtube"` / `"netflix"` / 앱 ID | 앱 visible=true 재조회. 영상 재생 검증 아님 |
| to_pc | 없음 | 등록된 입력 메뉴 위치로 이동하는 키 전달, verified=false |
| pair | 없음 | TV 연결 승인. 사용자가 TV 화면에서 허용해야 함 |
| dlna_play | `url:"https://…/video.mp4"` | TV에 접근 가능한 미디어 주소 전달, verified=false |
| dlna_stop | 없음 | DLNA 정지 요청 전달, verified=false |
| epg_now | `page:1`, 선택 `channels:[번호]`, `refresh:true` | KT 공개 편성표. TV 상태와 별개 |
| epg_channel | `channels:[번호]` | 해당 채널 하루 편성표 |
| epg_scan | 없음 | KT 채널 원장 재수집. timeout:300 권장 |

## 결과와 재시도

`success:true`는 요청 처리 성공이다. `verified:false`는 결과를 직접 관측하지 못했다는 뜻이다.
`status`가 성공해도 `reachable:false,power:"unknown"`이면 전원·네트워크가 미확인이다.
미응답을 전원 꺼짐으로 바꾸지 않는다. 손발 목록의 `connected`는 최근 90초 관측만 표시하며
시간이 지나면 null(미확인)이다. 상시 연결·TV 전원 상태를 뜻하지 않는다.

음량 증감·음소거·전원 키·입력 전환은 자동 재시도하지 않는다. 시간 초과·연결 종료 후에는
먼저 상태를 조회한다. 상태 조회로 읽을 수 없는 음량·화면·입력은 사용자 또는 별도 관측이 필요하다.
`launch`가 성공해도 사용자가 원한 영상의 재생·전체 화면·소리까지 성공했다고 보고하지 않는다.

DLNA는 직접 미디어 주소용이다. 유튜브 웹페이지 주소는 미디어 주소가 아니며 TV 내 유튜브 앱
실행과 구분한다. KT 편성표(`tv_epg.py`)는 공개 정보의 날짜별 캐시이며 현재 셋톱 채널을
읽거나 전환하지 않는다. 지역 편성과 실제 채널은 다를 수 있다.

## 연결 설정 수정·앱 보강

소유자 API `POST /remote-pcs/hardware`는 `{alias,driver:"samsung-tizen",context,connection}`으로
등록한다. 같은 요청에 `target:device_id`를 주면 수정한다. `connection`은 `ip` 필수,
`mac,broadcast,token,client_name,apps,pc_input_index` 선택이다. 수정 시 빈 토큰은 기존 토큰을 유지한다.
기존 값을 포함한 전체 연결 설정을 보내며 공개 목록에서 토큰을 얻으려 하지 않는다.
`POST /remote-pcs/state`와 `PUT /remote-pcs/context`는 기존 대상 ID를 그대로 사용한다.

새 동작은 공용 스크립트·선언형 `living_tv.yaml`·이 가이드·회귀 검사를 함께 갱신한다.
개별 TV 이름·주소·입력 위치는 등록 데이터로 둔다. 새 IBL 낱말이나 TV용 상주 서버는 필요 없다.
