"""Central APK delivery for registered Android hardware, over resident transport.

An accepted job is only an installation request. Completion requires a subsequent
authenticated sync reporting the installed APK digest, never the enqueue receipt.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

PACKAGE = "com.indiebiz.phoneagent"
ABIS = {"arm64-v8a", "armeabi-v7a"}
_lock = threading.Lock()
_bridge_factory = None


def releases_root():
    import resident_pcs
    return resident_pcs.files_root() / "phone-releases"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_manifest(value):
    if not isinstance(value, dict):
        raise ValueError("invalid_phone_release")
    if (value.get("package") != PACKAGE or value.get("abi") not in ABIS
            or type(value.get("version_code")) is not int or value["version_code"] < 1
            or type(value.get("min_sdk")) is not int
            or type(value.get("size")) is not int or not 0 < value["size"] <= 512 * 1024 * 1024
            or not re.fullmatch(r"[a-f0-9]{64}", value.get("sha256", ""))
            or not re.fullmatch(r"[a-f0-9]{64}", value.get("signer_sha256", ""))):
        raise ValueError("invalid_phone_release")
    return value


def release_for(caps):
    abi = caps.get("abi")
    if abi not in ABIS:
        return None
    path = releases_root() / abi / "current.json"
    try:
        release = validate_manifest(json.loads(path.read_text()))
        if release["abi"] != abi:
            return None
        apk = path.parent / (release["sha256"] + ".apk")
        if not apk.is_file() or apk.stat().st_size != release["size"]:
            return None
        return release
    except (OSError, ValueError, TypeError):
        return None


def status(rec):
    reg = rec["registration"]
    caps = (reg.get("capabilities") or {}).get("apk_update") or {}
    if caps.get("contract") != 1:
        return {"state": "bootstrap", "message": "원격 업데이트 지원 APK 최초 설치 필요"}
    release = release_for(caps)
    result = {"state": "unpublished", "current_version": caps.get("version_code"),
              "abi": caps.get("abi"), "can_install": caps.get("can_install", False)}
    if release is None:
        return result
    result.update(latest_version=release["version_code"], sha256=release["sha256"])
    if caps.get("installed_sha256") == release["sha256"]:
        result["state"] = "current"
    elif caps.get("signer_sha256") != release["signer_sha256"]:
        result.update(state="incompatible", message="설치된 앱과 APK 서명이 다릅니다")
    elif (caps.get("sdk", 0) < release["min_sdk"]
          or caps.get("version_code", 0) >= release["version_code"]):
        result.update(state="incompatible", message="기기 버전 또는 APK versionCode 확인 필요")
    else:
        import resident_store
        result["state"] = "available"
        pending = resident_store.pending(rec["device_id"], "phone_update")
        if pending:
            result.update(state="updating", job_id=pending)
        else:
            # Report download/validation/cancellation failures even when native installation
            # never started. The task receipt remains distinct from installation health.
            import phone_jobs
            with phone_jobs._db() as db:
                resident_store.schema(db)
                row = db.execute("SELECT result FROM resident_tasks WHERE device=? AND generation=? "
                                 "AND json_extract(summary,'$.op')='phone_update' "
                                 "AND json_extract(summary,'$.release.sha256')=? ORDER BY created DESC LIMIT 1",
                                 (rec["device_id"], reg["generation"], release["sha256"])).fetchone()
            outcome = json.loads(row[0]) if row and row[0] else {}
            if outcome.get("error") or outcome.get("unknown") or outcome.get("cancelled"):
                result.update(state="failed", message=str(outcome.get("error") or "업데이트 요청 중단"))
        attempt = caps.get("attempt") or {}
        if attempt.get("sha256") == release["sha256"]:
            state = attempt.get("state")
            if state in {"awaiting_permission", "awaiting_confirmation", "failed", "installing", "staged"}:
                result.update(state=state, message=attempt.get("message", ""))
                # An old failure must not hide a newly queued retry.
                if pending and attempt.get("job_id") != pending:
                    result.update(state="updating", job_id=pending, message="")
    return result


def submit(target):
    import resident_pcs as pcs
    from phone_remote_execution import require_owner
    require_owner()
    with _lock:
        rec = pcs.resolve(target)
        if rec["registration"].get("adapter") != "indiebiz-v1":
            raise ValueError("not_registered_phone")
        state = status(rec)
        if state["state"] in {"current", "updating", "installing", "staged",
                              "awaiting_permission", "awaiting_confirmation"}:
            return {"success": True, **state}
        if state["state"] not in {"available", "failed"}:
            raise ValueError(state.get("message") or "phone_update_" + state["state"])
        caps = rec["registration"]["capabilities"]["apk_update"]
        release = release_for(caps)
        if release is None:
            raise ValueError("phone_release_missing")
        source = releases_root() / release["abi"] / (release["sha256"] + ".apk")
        if digest(source) != release["sha256"]:
            raise ValueError("phone_release_hash_mismatch")
        row = pcs.transfer_create(rec["device_id"], "to_pc", "update.apk",
                                  release["size"], release["sha256"])
        offset = 0
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                offset = pcs.transfer_write(row["id"], offset, chunk)["offset"]
        pcs.transfer_commit(row["id"])
        receipt = pcs.submit(rec["device_id"], {"op": "phone_update", "transfer_id": row["id"],
                             "release": release, "timeout": 1800}, uuid.uuid4().hex,
                             allow_phone_update=True)
        return {**receipt, "state": "updating", "sha256": release["sha256"]}


def bridge():
    if _bridge_factory is not None:
        return _bridge_factory()
    try:
        from java import jclass
        return jclass("com.indiebiz.phoneagent.update.ApkUpdater")
    except Exception:
        return None


def capabilities():
    impl = bridge()
    if impl is None:
        return {}
    try:
        return {"apk_update": json.loads(str(impl.capabilities()))}
    except Exception:
        return {}


def busy():
    attempt = capabilities().get("apk_update", {}).get("attempt", {})
    return attempt.get("state") in {"staged", "installing", "awaiting_permission", "awaiting_confirmation"}


def execute(client, job, command, cancelled):
    impl = bridge()
    if impl is None:
        return {"success": False, "error": "phone_update_bootstrap_required"}
    release = validate_manifest(command.get("release") or {})
    from phone_limb_transfer import execute as transfer
    directory = Path(os.environ["INDIEBIZ_USERDATA"]) / "apk-updates"
    path = directory / (release["sha256"] + ".apk")
    downloaded = transfer(client, {"transfer_id": command.get("transfer_id"),
                                  "path": str(path), "timeout": 1800}, cancelled)
    if downloaded["sha256"] != release["sha256"] or downloaded["size"] != release["size"]:
        raise ValueError("phone_release_hash_mismatch")
    if cancelled.is_set() or client.stopped.is_set():
        raise InterruptedError("phone_update_cancelled")
    # Native code validates the installed signer and package, persists before commit,
    # and survives Python/process death via PackageInstaller + MY_PACKAGE_REPLACED.
    return json.loads(str(impl.install(str(path), json.dumps(release), str(job["id"]))))


def recovered(job):
    """A killed install caller is not proof of installation failure or completion."""
    attempt = capabilities().get("apk_update", {}).get("attempt") or {}
    if attempt.get("job_id") == job["id"]:
        return {"success": attempt.get("state") != "failed", "accepted": True,
                "installation": attempt,
                **({"error": attempt.get("message") or "phone_update_install_failed"}
                   if attempt.get("state") == "failed" else {})}
    return {"success": False, "unknown": True, "error": "phone_update_interrupted_before_receipt"}
