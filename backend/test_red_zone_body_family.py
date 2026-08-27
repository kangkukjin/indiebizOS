"""RED 관문의 몸-가족 판정 회귀 — 48회차 별건 (2026-08-27)

48회차 상상훈련의 별건 실측(ep2146): 격리 워크트리에서 전수 회귀를 돌리다
test_emitter_output_path::test_P11 이 워크트리의 frontend/index.html 을 **실제로
덮어썼다**. RED 구역 판정이 판정자(로드된 게이트 사본)의 집(_REPO_ROOT)에 고정돼
있어서 — 라이브 게이트에게 `.worktrees/…/frontend/` 는 RED 가 아니었다. 수리 중
거울상도 발견됐다: 워크트리 게이트에게는 본체의 backend/ 가 RED 가 아니었다.

수리 = 기준 루트를 과녁 경로에서 유도(red_zone_family.body_root_of). 본체와 그
git 워크트리는 한 가족(같은 본체 .git), 남의 저장소는 가족이 아니다 — 이 배터리는
그 네 방향(본체 RED·워크트리 RED·거울상·남의 저장소 허용)을 못박는다.

실행: .venv/bin/python -m pytest backend/test_red_zone_body_family.py
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG = os.path.join(_ROOT, "data", "packages", "installed", "tools", "system_essentials")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def handler():
    return _load("_rzf_handler", os.path.join(_PKG, "handler.py"))


@pytest.fixture
def body(tmp_path):
    """가짜 본체 + 그 git 워크트리 + 남의 저장소. 전부 realpath 로 통일(macOS /tmp 심링크)."""
    home = os.path.realpath(str(tmp_path / "home"))
    wt = os.path.join(home, ".worktrees", "repair-x")
    foreign = os.path.realpath(str(tmp_path / "someone_else"))
    for root in (home, wt, foreign):
        os.makedirs(os.path.join(root, "backend"), exist_ok=True)
        os.makedirs(os.path.join(root, "frontend"), exist_ok=True)
    os.makedirs(os.path.join(home, ".git", "worktrees", "repair-x"))   # 본체 .git = 디렉토리
    os.makedirs(os.path.join(foreign, ".git"))                          # 남의 .git = 자기 것
    with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as f:    # 워크트리 .git = 파일
        f.write(f"gitdir: {os.path.join(home, '.git', 'worktrees', 'repair-x')}\n")
    return {"home": home, "wt": wt, "foreign": foreign}


# ── ① 가족 판정(순수 함수) ──────────────────────────────────────────────

def test_F1_본체와_워크트리는_한_가족(body):
    fam = _load("_rzf_family", os.path.join(_PKG, "red_zone_family.py"))
    assert fam.principal_root(body["wt"]) == body["home"]
    assert fam.principal_root(body["home"]) == body["home"]
    assert fam.body_root_of(os.path.join(body["home"], "backend", "a.py"), body["home"]) == body["home"]
    # 안쪽 루트가 먼저 — 워크트리 경로는 본체가 아니라 워크트리 기준
    assert fam.body_root_of(os.path.join(body["wt"], "backend", "a.py"), body["home"]) == body["wt"]
    # 거울상: 집이 워크트리여도 본체 경로를 가족으로 본다
    assert fam.body_root_of(os.path.join(body["home"], "backend", "a.py"), body["wt"]) == body["home"]
    assert fam.body_root_of(os.path.join(body["foreign"], "backend", "a.py"), body["home"]) is None
    assert fam.body_root_of("/tmp/rzf_nowhere/a.py", body["home"]) is None


# ── ② 게이트 종단(네 방향) ──────────────────────────────────────────────

def _gate(handler, monkeypatch, home):
    from pathlib import Path
    monkeypatch.setattr(handler, "_REPO_ROOT", Path(home))
    return handler._red_zone_violation


def test_F2_본체_RED는_여전히_막힌다(handler, monkeypatch, body):
    gate = _gate(handler, monkeypatch, body["home"])
    assert gate(os.path.join(body["home"], "frontend", "index.html")) is not None
    assert gate(os.path.join(body["home"], "data", "x.yaml")) is None  # data/ 는 RED 아님


def test_F3_워크트리_RED가_이제_막힌다(handler, monkeypatch, body):
    """48회차 별건의 재현 그대로 — 라이브 게이트가 워크트리 frontend/ 를 판정한다."""
    gate = _gate(handler, monkeypatch, body["home"])
    err = gate(os.path.join(body["wt"], "frontend", "index.html"))
    assert err is not None, "라이브 게이트가 격리 워크트리의 RED 를 또 놓쳤다(48회차 별건 재발)"
    assert gate(os.path.join(body["wt"], "backend", "core.py")) is not None
    # 정적 자산 면제도 과녁 루트 기준으로 따라온다
    assert gate(os.path.join(body["wt"], "backend", "static", "a.css")) is None


def test_F4_거울상_워크트리_게이트가_본체_RED를_막는다(handler, monkeypatch, body):
    gate = _gate(handler, monkeypatch, body["wt"])
    assert gate(os.path.join(body["home"], "backend", "core.py")) is not None, \
        "격리 안에서 절대경로 하나로 살아있는 기질을 덮어쓸 수 있다(거울상 구멍)"


def test_F5_남의_저장소는_종전대로_허용(handler, monkeypatch, body):
    """RED 는 '이 몸의 기질'이지 저장소 일반이 아니다 — 과잉 차단은 다른 결함이다."""
    gate = _gate(handler, monkeypatch, body["home"])
    assert gate(os.path.join(body["foreign"], "frontend", "index.html")) is None
    assert gate(os.path.join(body["foreign"], "backend", "app.py")) is None


def test_F6_게이트_자신은_격리_사본도_보호(handler, monkeypatch, body):
    gate = _gate(handler, monkeypatch, body["home"])
    rel = "data/packages/installed/tools/system_essentials/handler.py"
    for root in (body["home"], body["wt"]):
        target = os.path.join(root, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        err = gate(target)
        assert err is not None and "게이트 자신" in err, (root, err)


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    raise SystemExit(pytest.main([__file__, "-q"]))
