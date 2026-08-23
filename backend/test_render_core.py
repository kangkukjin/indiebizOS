"""공용 렌더 코어 회귀 — 조립된 원격 런처 스크립트를 실제로 실행해 프리미티브를 그려 본다.

기존 뷰-어휘 가드는 "p.type 케이스가 있는가"(선언 대조)만 봤다. 이 테스트는 조립된 <script>
를 최소 DOM 셰임 위에서 돌려 **무엇이 그려지는지**를 잰다 — 템플릿 이스케이프, 파티션,
스파크라인 좌표, 달력 월 산식, 미디어 소스 결정, compose 채널 우선순위까지.

node 가 없으면 skip (CI 우분투/윈도우 러너엔 있다).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
HARNESS = os.path.join(ROOT, "scripts", "test_render_core.js")


def _assembled_script() -> str:
    """원격런처 표면 HTML 에서 <script> 본문을 뽑는다(코어 인라인 포함된 실물)."""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
        import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)
    from launcher_surface_remote import launcher_html

    blocks = re.findall(r"<script>(.*?)</script>", launcher_html(), re.S)
    assert len(blocks) == 1, f"런처 셸의 <script> 블록이 1개가 아님: {len(blocks)}"
    return blocks[0]


def test_remote_renderer_primitives():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음 — 렌더러 실행 검증 생략")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(_assembled_script())
        path = f.name
    try:
        r = subprocess.run([node, HARNESS, path], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"렌더러 회귀 실패:\n{r.stdout}\n{r.stderr}"
    finally:
        os.unlink(path)


def test_core_has_single_definition_per_name():
    """조립된 스크립트에 코어 이름이 정확히 한 번씩만 정의돼 있어야 한다.

    두 번이면 사본이 부활한 것이고(뒤 정의가 이김 = 조용한 드리프트), 0 번이면 코어가
    안 실린 것이다(앱 탭 전체가 undefined 로 죽음).
    """
    from launcher_render_core import EXPORT_MARKER, _CORE_PATH

    with open(_CORE_PATH, encoding="utf-8") as f:
        core = f.read()
    block = core[core.rfind(EXPORT_MARKER):]
    names = [n.strip() for n in re.search(r"export\s*\{([^}]*)\}", block, re.S).group(1).split(",") if n.strip()]
    assert names, "코어 export 이름을 못 읽음"

    src = _assembled_script()
    for n in names:
        defs = len(re.findall(r"\bfunction\s+%s\s*\(" % re.escape(n), src))
        defs += len(re.findall(r"\bvar\s+%s\s*=" % re.escape(n), src))
        assert defs == 1, f"조립된 런처 스크립트에서 `{n}` 정의가 {defs}개 (1개여야 함)"


def test_phone_surface_carries_core():
    """폰네이티브 표면도 같은 코어를 싣는다 — 한쪽만 빠지면 그 몸의 앱 탭이 죽는다."""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    from launcher_surface_phone import phone_html

    html = phone_html()
    assert "function tplWith(" in html
    assert "function calendarModel(" in html


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
