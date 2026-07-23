# guest-helper — USB 손발(게스트 PC 헬퍼)

낯선 PC 에 **USB 를 꽂아** 그 PC 에서 셸·파일 작업을 시키는 얇은 손발 시스템.
두뇌·신원은 내 몸(허브)에 남고, USB 엔 허브 비밀번호가 아니라 **limb key 하나**만 실린다.

## 어휘

- `[self:limb]{op: issue/list/revoke/approve}` — 손발 자격 원장. `issue` 는 USB 페이로드
  (`outputs/limb_issue/<alias>/`)를 만든다.
- `[limbs:guestpc]{op: shell/read/write/list/info}` — 붙은 손발 조작(허브에서 하달).

## 흐름

```
발급  [self:limb]{op:issue}  → USB 페이로드(주소+키+헬퍼)
실행  그 PC 에서 헬퍼 더블클릭 → 허브에 아웃바운드 접속(승인 대기)
승인  [self:limb]{op:approve}  → 몰래 실행 방어
명령  [limbs:guestpc]{op:shell,...} → 그 PC 에서 실행 → 결과 회신
폐기  [self:limb]{op:revoke}   → USB 분실 시 이 키만 폐기
```

## 배관

- 수신 API: `backend/api_limb.py` (`/limb/connect·poll·result`, limb key 자체 인증).
- 자격 원장: `backend/limb_keys.py` (`data/limb_keys.json`, 무-flock 원자쓰기 = 윈도우 안전).
- 중계 큐: `backend/phone_jobs.py` 재사용(폰 LTE 푸시와 같은 롱폴). 큐엔 IBL 이 아니라
  셸 봉투 JSON 을 싣는다 — 손발은 IBL 엔진 없는 얇은 몸.
- 헬퍼 소스: `helper/` (Go 단일 파일, 크로스컴파일 → win/mac/linux).

## 경계

- **눈 없음(1단계)**: 셸/파일만. GUI 전용 앱·화면 확인은 미지원(후속 op).
- 손발은 신뢰 원장 이웃으로 자동 등록되지 않는다 — 인가는 limb key + 승인뿐(고권한 방어).
- 허브가 켜져 있고 터널이 살아 있어야 한다(본체 의존).

자세한 사용법: `data/guides/guest_helper.md`.
