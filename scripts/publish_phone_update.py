#!/usr/bin/env python3
"""Publish a signed phone APK to the central resident artifact store (no device I/O).

Build with ./gradlew :app:assembleArm64Debug -PphoneVersionCode=N, then pass
--apk PATH. Each ABI has its own channel. Keys and APKs are never committed.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401

import phone_updates


def inspect_apk(apk, build_tools):
    apk = Path(apk).resolve()
    tools = Path(build_tools)
    signed = subprocess.run([str(tools / "apksigner"), "verify", "--print-certs", str(apk)],
                            check=True, text=True, capture_output=True).stdout
    certs = re.findall(r"Signer #\d+ certificate SHA-256 digest: ([a-fA-F0-9]{64})", signed)
    if len(certs) != 1:
        raise ValueError("exactly_one_apk_signer_required")
    badging = subprocess.run([str(tools / "aapt"), "dump", "badging", str(apk)],
                             check=True, text=True, capture_output=True).stdout
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", badging, re.M)
    minimum = re.search(r"^sdkVersion:'(\d+)'", badging, re.M)
    native = re.search(r"^native-code: (.+)$", badging, re.M)
    abis = re.findall(r"'([^']+)'", native[1]) if native else []
    if package is None or minimum is None or len(abis) != 1:
        raise ValueError("single_abi_apk_required")
    return phone_updates.validate_manifest({"package": package[1], "version_code": int(package[2]),
        "version_name": package[3], "min_sdk": int(minimum[1]), "abi": abis[0],
        "signer_sha256": certs[0].lower(), "sha256": phone_updates.digest(apk), "size": apk.stat().st_size})


def publish(apk, build_tools):
    manifest = inspect_apk(apk, build_tools)
    directory = phone_updates.releases_root() / manifest["abi"]
    directory.mkdir(parents=True, exist_ok=True)
    # Serialize publishers across processes; immutable files survive active transfers.
    from filelock import FileLock
    with FileLock(str(directory / ".publish.lock")):
        pointer = directory / "current.json"
        if pointer.exists():
            previous = json.loads(pointer.read_text())
            if previous["sha256"] == manifest["sha256"]:
                return previous
            if previous["signer_sha256"] != manifest["signer_sha256"]:
                raise ValueError("phone_release_signer_changed")
            if previous["version_code"] >= manifest["version_code"]:
                raise ValueError("phone_release_version_must_increase")
        with tempfile.TemporaryDirectory(dir=directory) as tmp:
            staged = Path(tmp) / "update.apk"
            shutil.copyfile(apk, staged)
            if phone_updates.digest(staged) != manifest["sha256"]:
                raise ValueError("apk_changed_during_publish")
            os.replace(staged, directory / (manifest["sha256"] + ".apk"))
            index = Path(tmp) / "current.json"
            index.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            os.replace(index, pointer)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True)
    parser.add_argument("--build-tools", help="Android SDK build-tools directory containing aapt and apksigner")
    args = parser.parse_args()
    path = args.build_tools
    if path is None:
        sdk = Path(os.environ.get("ANDROID_HOME") or Path.home() / "Library/Android/sdk")
        candidates = sorted((sdk / "build-tools").glob("*"), key=lambda p: tuple(int(n) for n in re.findall(r"\d+", p.name)))
        path = next((str(p) for p in reversed(candidates) if (p / "apksigner").is_file()), None)
    if path is None:
        parser.error("--build-tools 또는 ANDROID_HOME을 설정하세요")
    print(json.dumps(publish(args.apk, path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
