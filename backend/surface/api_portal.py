"""api_portal.py — 개인 포털(커뮤니티 홈)·공개 창고 서빙의 **조립 지점**.

공개 Worker(public-files 와 공유)가 `/h/<slug>/...` 와 `/`(창고) 요청을 이 라우터로 끌어온다.
보안: X-Showcase-Secret(Worker 만 보유) + slug 일치. 개인화 응답이라 Worker 는 no-store.
상태·게이트 로직은 community-portal 패키지 portal_core.py 단일 소스(★수정 시 백엔드 재시작).

2026-08-05 감사 부채 ⑨ 분할 — 1903줄 한 파일에 인증 시스템 통째·파일 서빙·방명록·PWA·
오디오 프록시가 같이 살던 것을 관심사별 5모듈로. 이 파일은 라우터 조립만 한다:

    portal_base       공용 기반 — 시크릿 게이트·portal_core/html 로더·뷰어·세션 쿠키
    portal_face       포털의 공개 면(/page) + PWA 설치 자산
    portal_warehouse  노드의 공개 얼굴 = 레벨 창고(/home ·/manifest ·/file) + 방명록
    portal_admin      창고 관리(소유자 전용, /warehouse-admin/*) — ★공개 면 아님
    portal_auth       회원 신원 — 가입·로그인·개인 링크·비밀번호
    portal_gate       계기 페이지 + ★회원 실행 게이트 + 오디오 프록시

★경로는 분할 전과 **완전히 동일**하다(하위 라우터는 prefix 없이 이 라우터에 합류) —
Worker·public_face·is_public_remote_path 가 전부 경로 문자열로 물려 있어 한 글자도 못 바꾼다.
합류 순서는 원본 정의 순서 그대로 둔다(리터럴 첫 마디가 전부 달라 기능상 무관하지만,
읽는 사람이 옛 파일과 대조할 수 있게).

다른 모듈이 쓰던 헬퍼(`_ensure_warehouses`·`_warehouse_dir`·`_accessible_files` 등)는 이제
**진짜 주인 모듈에서 직접** 가져간다 — 여기서 재수출하면 옛 파일이 이름만 남은 채 계속
중앙처럼 보인다(분할의 목적이 그것이다).
"""

from fastapi import APIRouter

import portal_face
import portal_warehouse
import portal_admin
import portal_auth
import portal_gate

router = APIRouter(prefix="/portal", tags=["portal"])

router.include_router(portal_face.router)
router.include_router(portal_warehouse.router)
router.include_router(portal_admin.router)
router.include_router(portal_auth.router)
router.include_router(portal_gate.router)
