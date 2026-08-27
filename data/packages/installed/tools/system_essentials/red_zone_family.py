"""red_zone_family.py — RED 구역 판정의 기준 루트를 **과녁 경로**에서 유도한다.

★왜 (48회차 별건, 2026-08-27 실측 ep2146): RED 판정이 판정자(로드된 게이트 사본)의
집(`_REPO_ROOT`)에 고정돼 있었다. 그래서

  · 라이브 게이트에게 `.worktrees/…/frontend/` 는 RED 가 아니었다 — 격리 워크트리에서
    돌던 회귀 시험이 워크트리의 frontend/index.html 을 **실제로 덮어썼다**
    (test_emitter_output_path::test_P11). 격리 사본은 [self:patch]{op:"apply"} 로
    라이브가 될 원본이라, 여기가 오염되면 '검증 통과한 척'하는 코드가 라이브로 간다 —
    자기개조 안전장치(Floor #2)의 창고가 정작 무방비였다.
  · 거울상(이번 수리에서 발견): 워크트리 게이트에게는 본체의 backend/ 가 RED 가
    아니었다 — 격리 안에서 도는 코드가 절대경로 하나로 살아있는 기질을 그랜트 없이
    직접 덮어쓸 수 있었다.

수리 = 구역의 기준 루트를 **과녁이 속한 몸**에서 찾는다. 본체와 그 git 워크트리
(`.git` 파일의 gitdir 가 본체 `.git/worktrees/` 를 가리킴)는 한 가족 — 어느 사본의
게이트가 판정하든 같은 답이 나온다. 남의 저장소(backend/frontend 이름만 같은 폴더 —
HomePages 류 일반 웹 프로젝트가 이 모양이다)는 가족이 아니므로 종전대로 허용한다
(과잉 차단 금지 — RED 는 '이 몸의 살아있는 기질'이지 저장소 일반이 아니다).

★잎 모듈(형제 import 없음). 게이트의 일부이므로 게이트 자신과 같은 보호를 받는다
(handler 의 `_GATE_RELS` — 어느 사본이든 그랜트 없는 IBL 쓰기 금지 + 워치독 스모크).
"""
import os


def principal_root(root: str) -> str:
    """root 가 git 워크트리면 그 본체 루트, 아니면 자신."""
    try:
        gitp = os.path.join(root, ".git")
        if os.path.isfile(gitp):
            with open(gitp, encoding="utf-8", errors="ignore") as f:
                head = f.read(4096).strip()
            if head.startswith("gitdir:"):
                gitdir = os.path.realpath(head.split(":", 1)[1].strip())
                wt_dir = os.path.dirname(gitdir)           # …/.git/worktrees
                dot_git = os.path.dirname(wt_dir)          # …/.git
                if (os.path.basename(wt_dir) == "worktrees"
                        and os.path.basename(dot_git) == ".git"):
                    return os.path.dirname(dot_git)
    except Exception:
        pass
    return root


def body_root_of(real: str, home: str):
    """과녁 실경로가 속한 **이 몸**(home 의 가족)의 저장소 루트. 밖이면 None.

    저장소 모양 탐지는 게이트의 `_find_repo_root` 와 같은 신호(backend+frontend 동시
    존재)를 쓴다 — 설치 위치·경로 깊이에 안 흔들린다. 안쪽 루트가 먼저 잡히므로
    `.worktrees/<x>/backend/…` 는 본체가 아니라 워크트리 `<x>` 기준으로 판정된다.
    """
    home = os.path.realpath(home)
    p = os.path.dirname(real)  # 쓰기 과녁은 항상 루트 아래 — 자신이 루트일 수 없다
    while True:
        if (os.path.isdir(os.path.join(p, "backend"))
                and os.path.isdir(os.path.join(p, "frontend"))):
            break
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent
    if p == home or principal_root(p) == principal_root(home):
        return p
    return None
