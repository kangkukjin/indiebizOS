"""구형 인텔 맥(macOS 10.15~11)용 레거시 헬퍼 트랙 (2026-10-09).

Go 1.25+ 로 구운 mac-amd64 는 최소 macOS 12 라 Catalina 에서 dyld 가
_SecTrustCopyCertificateChain 을 못 찾고 꺼진다. Go 1.22 + go.legacy.mod 로 구운
indiebiz-helper-mac-amd64-legacy 를 빌드·발급 묶음·사용법이 함께 실어야 한다.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: F401,E402

HANDLER = ROOT / "data/packages/installed/tools/guest-helper/handler.py"
LEGACY = "indiebiz-helper-mac-amd64-legacy"


def _load_handler():
    spec = importlib.util.spec_from_file_location("guest_helper_handler_legacy_t", HANDLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def issued(tmp_path, monkeypatch):
    import limb_keys
    dist = tmp_path / "helper" / "dist"
    dist.mkdir(parents=True)
    for name in ("indiebiz-helper-mac-arm64", "indiebiz-helper-mac-amd64", LEGACY,
                 "indiebiz-helper-win.exe", "indiebiz-helper-linux"):
        (dist / name).write_bytes(b"bin")
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    monkeypatch.setattr(limb_keys, "mint", lambda alias, ttl_days=0, **k: {
        "alias": alias, "device_id": "guestpc-test", "key": "limb_testkey0000", "expires_at": None})
    h = _load_handler()
    monkeypatch.setattr(h, "_hub_address", lambda: ("https://hub.example", None))

    def run(os_name):
        return h._issue({"alias": "구형맥", "os": os_name})
    return run


@pytest.mark.parametrize("os_name", ["mac", "macos", "darwin", ""])
def test_mac_issue_includes_legacy_binary(issued, os_name):
    r = issued(os_name)
    assert r["success"]
    assert LEGACY in r["binary_included"]
    assert (Path(r["payload_dir"]) / LEGACY).is_file()


def test_readme_routes_old_intel_mac_to_legacy(issued):
    r = issued("mac")
    text = (Path(r["payload_dir"]) / "사용법.txt").read_text(encoding="utf-8")
    assert LEGACY in text
    assert "macOS 11 이하" in text and "Catalina" in text
    assert "xattr -d com.apple.quarantine" in text
    cfg = json.loads((Path(r["payload_dir"]) / "indiebiz-helper.json").read_text(encoding="utf-8"))
    assert cfg["key"] == "limb_testkey0000"


def test_win_issue_does_not_carry_legacy(issued):
    assert LEGACY not in issued("win")["binary_included"]


def test_build_script_has_legacy_track():
    sh = (ROOT / "helper/build.sh").read_text(encoding="utf-8")
    assert "GOTOOLCHAIN=go1.22" in sh and "-modfile=go.legacy.mod" in sh and LEGACY in sh
    mod = (ROOT / "helper/go.legacy.mod").read_text(encoding="utf-8")
    assert "\ngo 1.22" in mod
    assert (ROOT / "helper/go.legacy.sum").is_file()


@pytest.mark.skipif(not shutil.which("otool"), reason="otool 없음(macOS 전용 검사)")
def test_built_legacy_binary_targets_catalina():
    b = ROOT / "helper/dist" / LEGACY
    assert b.is_file()
    load = subprocess.run(["otool", "-l", str(b)], capture_output=True, text=True, check=True).stdout
    minos = [l.split()[1] for l in load.splitlines() if l.strip().startswith("minos")]
    assert minos, load[:500]
    major, minor = (int(x) for x in minos[0].split(".")[:2])
    assert (major, minor) <= (10, 15)
    syms = subprocess.run(["nm", "-u", str(b)], capture_output=True, text=True).stdout
    assert "SecTrustCopyCertificateChain" not in syms
    if shutil.which("go"):
        ver = subprocess.run(["go", "version", str(b)], capture_output=True, text=True).stdout
        assert "go1.22." in ver


def test_issue_root_uses_runtime_root_without_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("INDIEBIZ_BASE_PATH", raising=False)
    monkeypatch.setattr("runtime_utils.get_base_path", lambda: tmp_path)
    h = _load_handler()
    assert h._issue_root() == str(tmp_path)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
