#!/usr/bin/env python3
"""소유자가 요청한 Mac 배포본을 기존 인증서로 빌드·검증·게시한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def owner_release_boundary():
    # Explicit owner release may be noninteractive. Test/self-repair execution
    # must never touch a real private key, even if it has a terminal.
    if os.environ.get("INDIEBIZ_REPAIR_CHILD") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
        raise PermissionError("AUTHORIZATION_REQUIRED: 시험·자동 수리는 개인키 배포를 실행하지 않습니다.")


def run(args, *, cwd=None, env=None, timeout=120):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} 실패: {(result.stderr or result.stdout)[-1500:]}")
    return result.stdout + result.stderr


def verify(path, identifier, certificate):
    run(["codesign", "--verify", "--strict", str(path)])
    requirement = run(["codesign", "-d", "-r-", str(path)])
    expected = f'identifier "{identifier}" and certificate leaf = H"{certificate.lower()}"'
    if expected not in requirement:
        raise ValueError(f"기존 식별자·인증서 요구사항과 다릅니다: {path.name}")


def verify_pair(folder, manifest, policy):
    binary, worker = folder / "indiebiz-helper", folder / "indiebiz-screen"
    if manifest.get("certificate_sha1") != policy["certificate_sha1"]:
        raise ValueError("배포 인증서 불일치")
    for path, key, identifier in ((binary, "sha256", "helper_identifier"),
                                  (worker, "worker_sha256", "worker_identifier")):
        if digest(path) != manifest[key]:
            raise ValueError("배포 파일 해시 불일치")
        verify(path, policy[identifier], policy["certificate_sha1"])
    if worker.read_bytes() not in binary.read_bytes():
        raise ValueError("서명한 화면 도우미가 헬퍼에 포함되지 않았습니다.")


def publish(releases, build, folder, manifest):
    """Immutable artifacts first; a single atomic pointer makes them available."""
    target = releases / build
    target.mkdir(parents=True, exist_ok=True)
    version = target / manifest["sha256"]
    if not version.exists():
        staging = Path(tempfile.mkdtemp(prefix=".publish-", dir=target))
        try:
            for name in ("indiebiz-helper", "indiebiz-screen"):
                shutil.copy2(folder / name, staging / name)
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            staging.rename(version)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    elif any(digest(version / name) != digest(folder / name)
             for name in ("indiebiz-helper", "indiebiz-screen")):
        raise ValueError("기존 불변 배포 파일이 손상되었습니다.")
    with tempfile.NamedTemporaryFile(mode="w", dir=target, prefix=".current-", delete=False) as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
        temporary = Path(f.name)
    temporary.replace(target / "current.json")
    return version


def release(build, *, root=ROOT):
    owner_release_boundary()
    helper = root / "helper"
    policy = json.loads((helper / "mac_signing.json").read_text())
    certificate = policy["certificate_sha1"]
    if not re.fullmatch(r"[A-F0-9]{40}", certificate):
        raise ValueError("인증서 SHA-1 형식 오류")
    arch = "arm64" if build == "mac-arm64" else "amd64"
    native_arch = "arm64" if arch == "arm64" else "x86_64"
    env = dict(os.environ, GOOS="darwin", GOARCH=arch, CGO_ENABLED="0")
    if build.endswith("-legacy"):
        env["GOTOOLCHAIN"] = "go1.22.12"
    with tempfile.TemporaryDirectory(prefix="indiebiz-mac-release-") as temp:
        stage = Path(temp)
        # Only source inputs: no dist/native binaries from a development build.
        for p in helper.iterdir():
            if p.is_file() and ((p.suffix == ".go" and not p.name.endswith("_test.go"))
                                or p.name in ("go.mod", "go.sum", "go.legacy.mod", "go.legacy.sum")):
                shutil.copy2(p, stage / p.name)
        native = stage / "desktop_native"
        (native / "bin").mkdir(parents=True)
        shutil.copy2(helper / "desktop_native/mac.m", native / "mac.m")
        # Generate the embedded member shell from its current source, in isolation.
        run([sys.executable, str(root / "scripts/build_member_shell.py"),
             "--output", str(stage / "member_app.html")], cwd=root)
        toolchain = {"go": run(["go", "version"], env=env).strip(),
                     "clang": run(["clang", "--version"]).strip(),
                     "sdk": run(["xcrun", "--show-sdk-version"]).strip()}
        inputs = {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob("*")) if p.is_file()}
        inputs["release_script"] = digest(root / "scripts/release_mac_helper.py")
        source_hash = hashlib.sha256(json.dumps({"inputs": inputs, "toolchain": toolchain,
                                                "build": build, "policy": policy}, sort_keys=True).encode()).hexdigest()
        releases = helper / "releases"
        pointer = releases / build / "current.json"
        if pointer.exists():
            old = json.loads(pointer.read_text())
            if old.get("source_sha256") == source_hash:
                verify_pair(pointer.parent / old["sha256"], old, policy)
                return {**old, "reused": True}
        keychain = os.environ.get("INDIEBIZ_MAC_SIGN_KEYCHAIN", str(Path.home() / "Library/Keychains/login.keychain-db"))
        identities = run(["security", "find-identity", "-v", "-p", "codesigning", keychain])
        if certificate not in identities:
            raise PermissionError("기존 서명 인증서·개인키를 사용할 수 없습니다. 다른 인증서로 대체하지 않았습니다.")
        worker = stage / "indiebiz-screen"
        minimum = "11.0" if arch == "arm64" else "10.15"
        run(["clang", "-arch", native_arch, f"-mmacosx-version-min={minimum}", "-O2", "-fobjc-arc",
             "-Wno-deprecated-declarations", "-framework", "AppKit", "-framework", "ApplicationServices",
             str(native / "mac.m"), "-o", str(worker)])

        def sign(path, identifier):
            # A native Keychain authorization prompt may appear. Never alter ACLs,
            # unlock the keychain, or retry a denied/timed-out private-key access.
            run(["codesign", "--force", "--sign", certificate, "--keychain", keychain,
                 "--identifier", identifier, "--timestamp=none", str(path)], timeout=90)
            verify(path, identifier, certificate)

        sign(worker, policy["worker_identifier"])
        shutil.copy2(worker, native / "bin" / ("mac-" + native_arch))
        binary = stage / "indiebiz-helper"
        command = ["go", "build", "-trimpath", "-ldflags=-s -w", "-o", str(binary)]
        if build.endswith("-legacy"):
            command += ["-modfile=go.legacy.mod", "-tags=legacy"]
        run(command + ["."], cwd=stage, env=env, timeout=300)
        sign(binary, policy["helper_identifier"])
        manifest = {"schema": 1, "build": build, "source_sha256": source_hash,
                    "sha256": digest(binary), "worker_sha256": digest(worker),
                    "certificate_sha1": certificate, "toolchain": toolchain}
        verify_pair(stage, manifest, policy)
        publish(releases, build, stage, manifest)
        return {**manifest, "reused": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", choices=("mac-amd64", "mac-arm64", "mac-amd64-legacy"), required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(release(args.build), ensure_ascii=False, indent=2))
    except (PermissionError, subprocess.TimeoutExpired) as exc:
        print(f"서명 배포를 중단했습니다: {exc}. macOS 키체인 승인 상태를 확인하세요. 자동 재시도하지 않습니다.", file=sys.stderr)
        return 77
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
