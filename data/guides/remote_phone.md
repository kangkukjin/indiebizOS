# 원격폰 기능 활용 — 등록·상태·IBL·파일 왕복

## 등록과 연결

Android 폰은 `setup_phone.sh --limb 삼성1`로 설치·등록한다. 허브가 만든 1회용 자격을
USB 물리 접근으로 전달하며 허브 로그인 비밀번호는 요구하지 않는다. 등록 뒤에는 폰이
허브에 원격으로 접속하므로 **USB 미연결만으로 폰을 사용할 수 없다고 판단하지 않는다.**
먼저 `[self:limb]{op:"list"}`의 활성 등록과 연결 상태를 확인한다. `adapter:"indiebiz-v1"`이면
폰 자체 IBL 엔진에 `op:"ibl"`을 보내며, 헬퍼 PC의 셸·파일 봉투와 구분한다.
여러 등록에 같은 별칭이 남아 있으면 현재 활성 등록의 device_id를 사용한다.

- **현재 상태**: `[limbs:guestpc]{op:"info",limb:"삼성1"}`. 동기 결과의 `$r.result`는 폰이
  응답한 정보다. `.capabilities.media_session`에 지원·권한·준비 상태가 있다면 그 값을 사용한다.
  `camera:true`는 촬영 성공이 아니고 `speaker:true`는 TTS 음성 출력 성공이 아니다.
  신고에 없는 기능은 미확인으로 남긴다. 파일 경로·기능 지원과 실제 출력 확인을 구분한다.
- **하달 판본과 결과**: `code`는 별도 프로그램이다. 현재 문법은 그 문자열 안에도
  `#!ibl edition=2` 헤더를 넣는다. 바깥 프로그램의 판본이 문자열 안에 자동 적용되지는 않는다.
  동기 guestpc 응답의 `.result`는 원격 실행 봉투, **`.result.value`가 판본 2의 업무 값**이다.
  `info` 결과에는 이 `.value` 층이 없다. 실행 실패는 `[try]…[catch]`로 받고 원문과
  `$error.details.task_ref`를 보존한다. 존재하지 않는 `.ok` 필드로 실패를 검사하지 않는다.
- **긴 일**: `background:true`로 접수하고 `[self:task]{op:"wait",ref:$ticket.task_ref}`로
  같은 작업을 회수한다. 성공한 wait의 `.result`는 폰 응답이므로 판본 2 업무 값은
  **`.result.value`**다. `timed_out:true`면 같은 ref로 계속 확인한다. 폰 IBL의 실행 중 취소는
  지원하지 않고 전달 전 취소만 가능하다. 결과가 늦다고 재접수하지 않는다.
- **훈련 출처**: 호출 메타데이터의 `origin:"training"`은 허브 봉투→폰 클라이언트→폰 실행기로
  전달한다. 이 경로는 출처 전달을 지원하는 새 설치본에서 적용된다. 표식은 기기 제어를
  차단하는 샌드박스가 아니므로 훈련의 별도 실행 범위는 그대로 지킨다.

### 작은 텍스트·JSON 파일을 원격에서 작성하고 회수하기

폰의 `op:"read"`·`op:"write"`·`op:"shell"`은 헬퍼용이므로 거절된다. 폰의 IBL 안에서
`self:write/read`를 조합한다. 문자열에 JSON 원문을 직접 끼우거나 백슬래시를 손으로
치환하지 말고 **내용을 JSON 문자열 리터럴로 한 번 더 직렬화**한다. 다음 예제의 `rows`는
명시 입력 목록이며, 작업별 고유 시험 경로를 사용한다. IBL의 f문자열은 `${…}`만
보간한다. 코드의 보통 `{…}`는 그대로 쓰며 Python식 `{{…}}`로 바꾸지 않는다.

```ibl
#!ibl edition=2
$inner=f"""#!ibl edition=2
$s=[self:write]{path:"outputs/phone-check/checklist.json",content:${json(json($rows))}}
$d=[self:read]{path:$s.path}
return {path:$s.path,items:$d.data.items,text:$d.text}
"""
$r=[limbs:guestpc]{op:"ibl",limb:"삼성1",code:$inner,timeout:60}
return $r.result.value
```

폰의 `result_ref`·`resume`는 **그 폰 저장소의 참조**다. 중앙 실행기의 read_result에 그대로
넣지 않는다. 필요한 값·원문을 원격 프로그램에서 반환하고 중앙의 `self:write`로 보존한다.
큰 사진·녹음 파일은 경로만으로 회수된 것이 아니다. 현재 폰 손발이 신고하는 ops에 transfer가
없으면 헬퍼용 `transfer collect`를 호출해도 해결되지 않는다. 작은 텍스트 왕복과 바이너리
파일 전송의 지원 범위를 구분한다.

### 소리·미디어·등록 수명

- 소리: `[limbs:radio]{op:"play",station_id:"…"}`를 하달하면 폰 스피커에서 재생한다.
  상태는 `op:"status"`, 정지는 `op:"stop"`이다. 방송국 ID는 먼저 조회한다.
  음악의 읽기 전용 상태는 `[limbs:music]{op:"queue"}`다. 상태 조회 성공은 재생 실증이 아니다.
- 영상·마이크·스피커 연결은 [미디어 세션 가이드](media_session.md)의 기존 스크립트를 사용한다.
  지원 신고와 권한·대기 모드, 실제 프레임/음성 출력은 각각 확인한다.
- 등록 해제는 `[self:limb]{op:"remove",target:"삼성1"}`, 자격 폐기는 `op:"revoke"`다.
  단순 조회·작업 종료 때 등록을 해제하지 않는다.

