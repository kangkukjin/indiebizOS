# guest-helper — 상주 PC·휴대 USB 손발

중앙 허브의 명령을 원격 PC에서 실행하는 Go 헬퍼다. 신규 등록은
`[self:limb]{op:"register"}` 또는 조종실 손발 (USB)의 공용 폴더 준비로 시작한다.
폴더를 USB에 복사해 대상 PC에서 이름을 정하고 설치한다. 로그인 시 자동 시작하며
USB를 빼도 연결을 유지한다. 기존 `issue` 휴대형·회원 모드는 별도로 유지한다.

- `[limbs:guestpc]`: 셸·파일·화면·입력, 상주형 파일 전송·재생·깨우기·기록·취소.
- `[self:limb]`: 목록·등록·새 작업 일시 중지·명시적 제거·기존 키 관리·사용자 요청의 헬퍼 업데이트(`op:update`, `target` 필수).
- 상주형은 작업별 cwd/env 분리, request_id 중복 방지, GUI mode:interactive 필수다.
- 긴 작업은 접수증을 보존해 self:task로 확인한다. 실패 원문은 history에 남는다.
- detach는 휴대형 프로세스 종료만 허용한다. 상주형 제거는 self:limb remove이며
  removal_pending과 기기의 실제 removed 확인은 다르다.

배관: backend/surface/api_resident_pcs.py 및 api_limb.py,
backend/services/resident_pcs.py, backend/base/resident_store.py·limb_keys.py·phone_jobs.py.
헬퍼 소스·빌드: helper/README.md, helper/build.sh.

반복 절차는 data/idioms/guestpc_*.ibl의 등록 함수 아홉 개를 쓴다.
사용법·입력·재개·한계의 정본은 data/guides/guest_helper.md다.
