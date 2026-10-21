# TV 컨트롤 — 손발 등록·앱·AI 공용 스크립트

TV 전원·입력·음량·앱·DLNA 재생을 제어할 때 읽는다. 앱 모드의 **TV 컨트롤**과 AI가
등록 스크립트 `TV제어`를 함께 사용한다. 계약 조회는 `[self:script]{op:"list",id:"TV제어"}`다. 장치 소개의 `control_guide`가
이 파일을 가리킨다. 현재 문맥에 계약이 있으면 다시 읽거나 같은 코드를 새로 만들지 않는다.

## 대상과 등록

조종실 **손발 → 네트워크 기기 등록 · 삼성 TV**에서 이름·IPv4 주소를 등록한다.
TV에 IndieBiz OS나 PC 헬퍼를 설치할 필요가 없다. 현재 드라이버는 Samsung Tizen이며,
다른 제조사 TV가 자동으로 호환되는 것은 아니다. TV 컨트롤 앱은 사용자의 설정에 따라 **거실TV**로 고정되어 별도 대상 선택 없이 버튼을 누른다. 앱 선언의 `target:"거실TV"`는 손발 원장의 등록 이름으로 해석된다.

- 켜기에는 유선/무선 MAC과 해당 LAN 브로드캐스트 주소가 필요하다. TV의 네트워크 대기·원격 켜기 설정 및 망에 따라 동작이 다르다.
- 최초 제어 전에 TV를 켜고 앱의 **TV 연결 허용·페어링**을 눌러 TV 화면에서 허용한다. 기존 토큰이 있으면 등록 시 재사용할 수 있다.
- 앱 ID는 모델별로 다를 수 있다. 등록 폼의 앱 ID를 확인한다. PC 입력 위치는 TV 입력 메뉴의 왼쪽부터 1로 세며 입력 목록 변화 후 다시 확인한다.
- 이름·위치·연결된 PC는 설명 데이터다. TV와 연결된 Windows PC는 각각 별도 `device_id`다. TV 입력 전환이 PC의 유튜브 재생이나 그래픽 재설정을 수행하지 않는다.
- 목록·일시 중지·해제는 기존 `[self:limb]`와 손발 패널을 쓴다. `adapter:"network-api"`, `kind:"tv"`, `os:"tizen"`이다. 이 기기에 `guestpc shell/python/info`를 보내지 않는다.
- 주소·MAC·페어링 토큰은 허브의 비공개 `network_hardware.json`에 저장한다. 앱/AI 공개 목록에는 연결 설정·토큰을 싣지 않는다. 등록 해제는 저장된 연결 설정을 삭제한다. TV 자체의 허용 기기 목록은 TV 설정에서 별도로 관리한다.

## 작업에 맞는 기기 선택

“TV에 유튜브”는 TV 자체 앱 실행과 연결된 PC의 브라우저 재생이 다르다. 장치 소개의 이름·설명·OS·adapter를 확인해 사용자가 가리킨 기기를 고른다. TV 자체 앱이면 이 가이드의 `launch`, Windows PC이면 `pc_control.md`의 **기존 재생 교체** 공용 스크립트(`youtube_replace`)를 사용한다. PC 크롬의 일반 탭·창(유튜브 영상 아닌 페이지 열기·전환·닫기)은 `pc_control.md`의 **Windows Chrome 창·탭**(`chrome_*`, 전용 프로필)이다. 영상 URL·제목·길이를 전달하고 본영상 시간 진행과 기존 재생 정지 검증이 통과한 뒤 완료로 보고한다. 광고 화면·URL 입력만으로 재생 성공이라고 하지 않는다. 일반 `open_url`로 유튜브 영상을 추가하지 않는다. PC 화면을 TV에 보여줘야 하는 경우에만 등록된 두 기기에 각각 PC 실행과 TV 입력 전환을 수행한다. 연결 관계가 설명에 없으면 추측하지 않는다. 두 경우 모두 요청 전달과 실제 영상 재생 확인을 구분한다.

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
$r = [self:script]{id:"TV제어",args:{target:$target,op:"status"},timeout:90}
assert $r.success == true, "TV 요청 실패. 변경 명령을 반복하지 말고 상태를 확인하세요.", {result:$r}
return $r
```

`target`을 유지하고 아래 인수로 `args`를 바꾼다.

| op | 추가 인수 | 확인하는 것 |
| --- | --- | --- |
| status | 없음 | power·앱 running/visible + UPnP 음량·음소거·DLNA 재생/위치, 지원 시 입력. 선택 SmartThings 마지막 보고값 |
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
먼저 상태를 조회한다. 아래 항목별 관측이 미지원·미확인이면 사용자 또는 별도 관측이 필요하다.
`launch`가 성공해도 사용자가 원한 영상의 재생·전체 화면·소리까지 성공했다고 보고하지 않는다.

## 음량·입력·재생 상태 읽기

기존 `status` 한 번으로 조회한다. 추가 키 입력·앱 실행·음량 변경 없이 읽는다.
꺼진 TV를 켜서 확인하는 요청이면 기존 `on`을 먼저 사용한다. `status` 자체는 켜지 않는다.
전원 확인용 내부 조회는 가벼운 기존 경로를 유지해 WOL 재확인마다 전체 조회를 반복하지 않는다.

결과의 `observations`는 항목별 `{value,state,verified,source,scope,observed_at}`이다.
최상위 `verified`는 기존 **전원 확인** 의미(`verification_scope:power_only`)이며 전체 항목의
성공이 아니다. `local_observations`·`cloud_observations`에는 각 경로의 원래 증거가 남는다.
로컬 관측이 있으면 우선하고, 없는 항목만 클라우드 보고로 보완한다.

| 항목 | 조회 수단·의미 |
| --- | --- |
| volume | UPnP RenderingControl `GetVolume`, 0~100. 0도 실제 값 |
| mute | UPnP `GetMute`, Bool. false는 조회 실패가 아니라 음소거 해제 |
| input_source | TV의 `/dmr`가 MainTVAgent2와 `GetCurrentExternalSource`를 광고할 때 조회. 그 외에는 선택 SmartThings `mediaInputSource.inputSource` |
| dlna_transport | AVTransport `GetTransportInfo`의 상태. **DLNA 재생기만** 대상으로 함 |
| dlna_position | `GetPositionInfo`의 위치·길이·트랙. 한 번의 위치 조회이며 시간 진행을 입증하지 않음 |
| media_playback | 선택 SmartThings `mediaPlayback.playbackStatus`의 마지막 보고. 해당 TV가 제공해야 함 |

`observed`는 로컬 API에서 읽은 값, `reported`는 클라우드 마지막 보고다.
`unsupported`는 **해당 조회 경로**에 서비스·액션·속성이 없다는 뜻이다.
`unavailable`(연결/일시 실패), `unauthorized`(인증/권한), `invalid_response`(잘못된 응답),
`not_configured`(선택 연동 없음)는 구분한다. 미확인 값은 null이며 0·false로 대체하지 않는다.

DLNA의 `NO_MEDIA_PRESENT`·`STOPPED`가 TV 전체의 재생 중단을 뜻하지 않는다.
HDMI로 연결된 TV1의 유튜브는 `PC제어`의 `youtube_status`로 PC 브라우저 쪽에서 확인한다.
그 결과 역시 TV의 현재 입력·패널 표시·물리적 소리를 입증하지 않는다.
TV 자체 유튜브의 영상 진행을 모든 모델에서 원격 조회할 수 있다고 주장하지 않는다.

### 선택 SmartThings 연결

로컬 음량·음소거·DLNA 조회에는 계정이나 토큰이 필요 없다. 로컬에서 제공하지 않는 입력·
재생 보고를 보완하려면 TV가 등록된 SmartThings 계정의 **기기 읽기 권한** 액세스 토큰과
기기 ID가 필요하다. 주인 등록 API `POST /remote-pcs/hardware`의 기존 수정 계약에서
`target`을 지정하고 `connection.smartthings:{device_id,token}`을 추가한다.
기존 IP·MAC·앱 등 전체 연결 설정을 유지한다. 토큰은 허브 비공개 원장(0600)에만 저장하고
가이드·코드·대화·공개 기기 목록에 넣지 않는다. 수정 시 smartthings 생략은 기존 설정 유지,
명시적 null은 연결 해제다. 다른 SmartThings 기기와 자동으로 매칭하지 않는다.

클라우드는 읽기 전용 GET 한 번이며 자동 새로고침 명령·재생 명령을 보내지 않는다.
`reported_at`은 SmartThings가 보고한 마지막 변경 시각(누락이면 null)이고,
`observed_at`은 허브가 응답을 받은 시각이다. 오래된 보고를 현재 실측으로 바꾸지 않으며
클라우드 항목의 verified는 false다. 토큰 만료·권한 부족은 unauthorized로 표시한다.
TV 모델이 해당 capability를 제공하지 않으면 연결해도 조회할 수 없다.

구현 근거: [UPnP RenderingControl 표준](https://upnp.org/specs/av/UPnP-av-RenderingControl-v1-Service.pdf),
[AVTransport 표준](https://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf),
[Samsung 로컬 UPnP 구현](https://github.com/ollo69/ha-samsungtv-smart/blob/master/custom_components/samsungtv_smart/api/upnp.py),
[MainTVAgent2 패킷 관측](https://github.com/casperboone/homey-samsung-smart-tv/blob/master/samsung.md),
[SmartThings 상태 API](https://developer.smartthings.com/docs/service-integrations/query-and-list-devices).

2026-10-21 실기 관측: 등록된 KU70UA8070FXKR에서 WOL 후 전원 on, 음량 0·음소거 false,
DLNA NO_MEDIA_PRESENT·위치 0:00:00을 확인했다. `/dmr`에는 MainTVAgent2가 없었고
7676 연결도 실패했다. SmartThings 실계정 조회·TV 자체 앱의 영상 진행 확인은 미검증이다.

DLNA는 직접 미디어 주소용이다. 유튜브 웹페이지 주소는 미디어 주소가 아니며 TV 내 유튜브 앱
실행과 구분한다. KT 편성표(`tv_epg.py`)는 공개 정보의 날짜별 캐시이며 현재 셋톱 채널을
읽거나 전환하지 않는다. 지역 편성과 실제 채널은 다를 수 있다.

## 연결 설정 수정·앱 보강

소유자 API `POST /remote-pcs/hardware`는 `{alias,driver:"samsung-tizen",context,connection}`으로
등록한다. 같은 요청에 `target:device_id`를 주면 수정한다. `connection`은 `ip` 필수,
`mac,broadcast,token,client_name,apps,pc_input_index,smartthings` 선택이다. 수정 시 빈 페어링 토큰은 기존 토큰을 유지한다.
기존 값을 포함한 전체 연결 설정을 보내며 공개 목록에서 토큰을 얻으려 하지 않는다.
`POST /remote-pcs/state`와 `PUT /remote-pcs/context`는 기존 대상 ID를 그대로 사용한다.

새 동작은 공용 스크립트·선언형 `living_tv.yaml`·이 가이드·회귀 검사를 함께 갱신한다.
개별 TV 이름·주소·입력 위치는 등록 데이터로 둔다. 새 IBL 낱말이나 TV용 상주 서버는 필요 없다.
