# 원격 하드웨어 — 기존 헬퍼 가이드 입구

## 빠른 호출

장치 소개의 이름·OS·접속 관측으로 대상을 고르고 device_id를 유지한다. `registration`이 있으면 상주형, 없으면 휴대형이다. 오프라인·마지막 권한 관측은 현재 실행 가능의 증거가 아니다. `[self:limb]{op:"list"}`에서 설치 세대·부품·관측 판본·업데이트 상태와 관측 기록을 확인한다.

| 작업 | 소유 가이드와 조회할 절 |
| --- | --- |
| PC 음량·앱·전원·화면·재생 | `pc_control.md`의 빠른 호출과 해당 조작면 |
| Android 제어 | `android_control.md`의 빠른 호출; 실행·파일은 `remote_phone.md` |
| TV | `tv_control.md`의 빠른 호출. network-api는 허브 실행이며 guestpc 대상이 아님 |
| 원격 셸·접수증·전송·취소 | `remote_pc_execution.md`의 빠른 호출, 재관측과 전송 재시도, 작업 종료·출력·확인 자리 |
| 설치 전 준비·등록·권한·교체·제거 | `remote_pc_installation.md`의 빠른 호출과 해당 절 |
| IndieBiz OS 본체 설치·빌드·remote_steps | `remote_pc_installation.md`의 IndieBiz OS 본체 설치 → 원격 PC 설정 검증 문서 |

현재 제공된 빠른 호출 범위는 바로 사용한다. 부족한 동작·인자만 `read_guide(query="remote_pc_execution.md",section="빠른 호출")` 또는 `execute_ibl(code="",describe=["fn:외부PC작업실행"])`으로 확인한다. 가이드 전문이나 무관한 설치 절을 반복해서 읽지 않는다.

원격 실행의 접수와 완료는 다르다. 원 반환값·task_ref·요청ID를 보존하고 `외부PC작업확인` 또는 `self:task`로 이어본다. 대기 종료·통신 단절 뒤 변경을 다시 보내지 않는다. 상주 작업의 마무리는 등록 해제가 아니며, remove는 명시 요청 때만 한다. UAC 보안 화면 승인은 현지 사람이 한다.
