"""Owner release is isolated, certificate pinned, reusable and fail closed."""
import boot_paths  # noqa: F401
import importlib
import json
from pathlib import Path
import shutil

import pytest


@pytest.fixture
def release_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("release_mac_helper")


def test_automatic_jobs_stop_before_any_keychain_access(release_module, monkeypatch):
    monkeypatch.setattr(release_module, "run", lambda *a, **kw: pytest.fail("private key access"))
    with pytest.raises(PermissionError):
        release_module.release("mac-amd64")
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    monkeypatch.setenv("INDIEBIZ_REPAIR_CHILD", "1")
    with pytest.raises(PermissionError):
        release_module.release("mac-amd64")


@pytest.fixture
def fake_release(release_module, monkeypatch, tmp_path):
    module = release_module
    helper = tmp_path / "helper"
    (helper / "desktop_native").mkdir(parents=True)
    (helper / "dist").mkdir()
    (helper / "dist/indiebiz-helper-mac-amd64").write_bytes(b"development")
    (helper / "main.go").write_text("package main")
    (helper / "go.mod").write_text("module test")
    (helper / "desktop_native/mac.m").write_text("worker")
    (tmp_path / "scripts").mkdir()
    shutil.copy2(module.ROOT / "helper/mac_signing.json", helper / "mac_signing.json")
    shutil.copy2(module.__file__, tmp_path / "scripts/release_mac_helper.py")
    policy = json.loads((helper / "mac_signing.json").read_text())
    calls = []
    identities = {}

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == module.sys.executable:
            Path(args[-1]).write_text("generated member shell")
        elif args[:2] == ["go", "build"]:
            stage = kwargs["cwd"]
            Path(args[args.index("-o") + 1]).write_bytes(b"helper:" + (stage / "indiebiz-screen").read_bytes())
        elif args[0] == "clang" and "-o" in args:
            Path(args[-1]).write_bytes(b"worker")
        elif args[0] == "security":
            return policy["certificate_sha1"]
        elif args[:2] == ["codesign", "--force"]:
            identities[Path(args[-1]).name] = args[args.index("--identifier") + 1]
            assert args[args.index("--sign") + 1] == policy["certificate_sha1"]
        elif args[:2] == ["codesign", "-d"]:
            name = Path(args[-1]).name
            return f'identifier "{identities[name]}" and certificate leaf = H"{policy["certificate_sha1"].lower()}"'
        return "fake toolchain"

    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    monkeypatch.delenv("INDIEBIZ_REPAIR_CHILD", raising=False)
    monkeypatch.setattr(module, "run", run)
    monkeypatch.setattr(module, "owner_release_boundary", lambda: None)  # fake tools only
    return module, tmp_path, calls


def test_release_then_reuse_without_private_key_and_without_overwriting_dev(fake_release):
    module, root, calls = fake_release
    first = module.release("mac-amd64", root=root)
    assert first["reused"] is False
    assert len([c for c in calls if c[:2] == ["codesign", "--force"]]) == 2
    calls.clear()
    second = module.release("mac-amd64", root=root)
    assert second["reused"] and second["sha256"] == first["sha256"]
    assert not any(c[0] == "security" or c[:2] == ["codesign", "--force"] for c in calls)
    assert (root / "helper/dist/indiebiz-helper-mac-amd64").read_bytes() == b"development"
    folder = root / "helper/releases/mac-amd64" / first["sha256"]
    (folder / "indiebiz-helper").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="해시"):
        module.release("mac-amd64", root=root)


def test_failed_signature_keeps_previous_published_release(fake_release, monkeypatch):
    module, root, calls = fake_release
    module.release("mac-amd64", root=root)
    pointer = root / "helper/releases/mac-amd64/current.json"
    previous = pointer.read_bytes()
    (root / "helper/main.go").write_text("changed source")
    original = module.run

    def denied(args, **kwargs):
        if args[:2] == ["codesign", "--force"]:
            raise PermissionError("denied")
        return original(args, **kwargs)

    monkeypatch.setattr(module, "run", denied)
    with pytest.raises(PermissionError):
        module.release("mac-amd64", root=root)
    assert pointer.read_bytes() == previous


def test_different_certificate_requirement_is_rejected(release_module, monkeypatch, tmp_path):
    monkeypatch.setattr(release_module, "run", lambda *a, **kw:
                        'identifier "com.indiebiz.helper" and certificate leaf = H"different"')
    with pytest.raises(ValueError, match="인증서"):
        release_module.verify(tmp_path / "binary", "com.indiebiz.helper", "A" * 40)


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
