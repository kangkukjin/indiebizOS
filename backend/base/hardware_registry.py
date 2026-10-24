"""Network appliances in the limb registry, without PC credentials or heartbeats.

The private connection stays on the controlling hub. Public rows join the same
device picker as PC/phone registrations; they are never compute-routing nodes.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
import threading
from filelock import FileLock
import ipaddress
import re
import secrets
import time

import limb_keys


_lock = threading.RLock()


def _store_path():
    # Same private data root as limb credentials, separate file so script status
    # writes cannot overwrite a simultaneous PC/phone credential update.
    return limb_keys._store_path().with_name("network_hardware.json")


@contextmanager
def _store(write=False):
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, FileLock(str(path) + ".lock", timeout=10):
        rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(rows, dict):
            raise ValueError("네트워크 기기 원장 형식 오류")
        yield rows
        if write:
            tmp = path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as stream:
                os.chmod(tmp, 0o600)
                json.dump(rows, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)



def _resolve(target, rows):
    if not isinstance(target, str) or not target:
        raise ValueError("기기의 device_id를 지정하세요")
    if target in rows:
        return rows[target]
    matches = [r for r in rows.values() if r["alias"] == target
               and r["state"] != "removed"]
    # Do not let an appliance alias hide a PC/phone with the same name.
    others = [r for r in limb_keys.list_keys(include_revoked=False)
              if r.get("alias") == target and not r.get("expired")]
    if len(matches) != 1 or others:
        raise ValueError("기기 이름이 없거나 중복입니다. device_id를 지정하세요")
    return matches[0]


def contains(target):
    with _store() as rows:
        return any(target in (r["device_id"], r["alias"]) for r in rows.values())


def _public(rec):
    observed = rec.get("observation") or {}
    current = time.time() - observed.get("at", 0) < 90
    return {
        "device_id": rec["device_id"], "alias": rec["alias"],
        "revoked": rec["state"] == "removed", "expired": False,
        "approved": rec["state"] == "active" and not rec["paused"],
        "connected": observed.get("reachable") if current else None,
        "observed_at": observed.get("at"), "expires_at": None,
        "last_used": observed.get("at"), "last_host": None,
        "env": {"os": rec["platform"]},
        "registration": {
            "kind": rec["kind"], "adapter": "network-api", "driver": rec["driver"],
            "state": rec["state"], "paused": rec["paused"], "context": rec["context"],
            "capabilities": {"os": rec["platform"]},
            "observations": deepcopy(rec.get("observations") or []),
        },
    }


def devices():
    with _store() as rows:
        return [_public(r) for r in rows.values()]


def connection(target):
    """Private driver access. Removed/paused targets cannot be executed."""
    with _store() as rows:
        rec = _resolve(target, rows)
        if rec["state"] != "active" or rec["paused"]:
            raise PermissionError("기기 등록이 해제되었거나 제어가 중지되었습니다")
        return deepcopy(rec)


def _validate_connection(value):
    if not isinstance(value, dict):
        raise ValueError("connection 객체가 필요합니다")
    allowed = {"ip", "mac", "broadcast", "token", "client_name", "apps", "pc_input_index", "smartthings"}
    if set(value) - allowed:
        raise ValueError("지원하지 않는 연결 설정입니다")
    cfg = deepcopy(value)
    # A literal address prevents URL/path injection and accidental DNS targets.
    for field in ("ip", "broadcast"):
        if field == "broadcast" and not cfg.get(field):
            continue
        addr = ipaddress.IPv4Address(cfg.get(field, ""))
        if addr.is_loopback or addr.is_multicast or addr.is_unspecified:
            raise ValueError("TV 네트워크의 IPv4 주소를 입력하세요")
        cfg[field] = str(addr)
    if cfg.get("mac"):
        mac = re.sub(r"[:-]", "", str(cfg["mac"]))
        if not re.fullmatch(r"[0-9a-fA-F]{12}", mac):
            raise ValueError("MAC 주소를 확인하세요")
        cfg["mac"] = ":".join(mac[i:i + 2] for i in range(0, 12, 2)).lower()
    token = cfg.get("token", "")
    if not isinstance(token, str) or (token and not re.fullmatch(r"[a-zA-Z0-9_-]{1,256}", token)):
        raise ValueError("페어링 토큰 형식이 올바르지 않습니다")
    cfg["client_name"] = str(cfg.get("client_name") or "IndieBiz")[:80]
    apps = cfg.setdefault("apps", {})
    if (not isinstance(apps, dict) or len(apps) > 50 or
            any(not isinstance(k, str) or not isinstance(v, str) or
                not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", v) for k, v in apps.items())):
        raise ValueError("앱 이름과 앱 ID 매핑을 확인하세요")
    if "pc_input_index" in cfg:
        index = cfg["pc_input_index"]
        if type(index) is not int or not 1 <= index <= 12:
            raise ValueError("PC 입력 위치는 1~12 정수입니다")
    cloud = cfg.get("smartthings")
    if cloud is not None:
        if (not isinstance(cloud, dict) or set(cloud) != {"device_id", "token"} or
                not isinstance(cloud.get("device_id"), str) or
                not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", cloud["device_id"]) or
                not isinstance(cloud.get("token"), str) or
                not re.fullmatch(r"[a-zA-Z0-9_.~+/-]{1,4096}=*", cloud["token"])):
            raise ValueError("SmartThings 기기 ID와 읽기 권한 토큰을 확인하세요")
    return cfg


def register(alias, connection_config, *, context="", driver="samsung-tizen", target=None):
    if driver != "samsung-tizen":
        raise ValueError("현재 등록을 지원하는 드라이버는 samsung-tizen입니다")
    alias = str(alias or "").strip()
    if not alias or len(alias) > 80:
        raise ValueError("기기 이름을 1~80자로 입력하세요")
    cfg = _validate_connection(connection_config)
    with _store(write=True) as rows:
        if target:
            rec = _resolve(target, rows)
            if rec["state"] != "active":
                raise ValueError("해제된 기기는 새로 등록하세요")
            # Empty token on editing means keep the existing pairing.
            if not cfg.get("token"):
                cfg["token"] = rec["connection"].get("token", "")
            # Old registration clients do not know the optional cloud observation settings.
            # Omission preserves them; explicit null disconnects the cloud observer.
            if "smartthings" not in cfg and "smartthings" in rec["connection"]:
                cfg["smartthings"] = deepcopy(rec["connection"]["smartthings"])
        else:
            if any(r["state"] == "active" and r["connection"]["ip"] == cfg["ip"] for r in rows.values()):
                raise ValueError("이미 등록된 주소입니다. 기존 기기를 수정하세요")
            rec = {"device_id": "hardware-" + secrets.token_hex(6), "state": "active", "paused": False}
        if any(r["device_id"] != rec["device_id"] and r["state"] == "active"
               and r["connection"]["ip"] == cfg["ip"] for r in rows.values()):
            raise ValueError("이미 등록된 주소입니다. 기존 기기를 수정하세요")
        rec.update(alias=alias, kind="tv", driver=driver, platform="tizen",
                   context=str(context or "")[:2000], connection=cfg, observation={})
        rows[rec["device_id"]] = rec
        return _public(rec)


def update(target, *, remove=False, paused=None, context=None, observations=None):
    with _store(write=True) as rows:
        rec = _resolve(target, rows)
        if remove:
            rec.update(state="removed", connection={}, observation={})
        elif rec["state"] != "active":
            raise ValueError("이미 등록 해제된 기기입니다")
        if paused is not None:
            rec["paused"] = bool(paused)
        if context is not None:
            rec["context"] = str(context)[:2000]
        if observations is not None:
            # 제어 관측 칸 — 병합·검증은 control_observations 가 맡고 여기는 목록 모양만 지킨다.
            if not isinstance(observations, list) or len(observations) > 500:
                raise ValueError("관측 칸은 500행 이내 목록이어야 합니다")
            rec["observations"] = deepcopy(observations)
        return _public(rec)


def observe(target, reachable):
    with _store(write=True) as rows:
        rec = _resolve(target, rows)
        if rec["state"] == "active":
            rec["observation"] = {"reachable": bool(reachable), "at": time.time()}


def save_token(target, token, *, expected_connection=None):
    with _store(write=True) as rows:
        rec = _resolve(target, rows)
        if rec["state"] != "active" or rec["paused"]:
            raise PermissionError("기기 등록이 해제되었거나 제어가 중지되었습니다")
        if expected_connection is not None and rec["connection"] != expected_connection:
            raise PermissionError("연결 설정이 변경되어 이전 연결 토큰을 저장하지 않았습니다")
        cfg = _validate_connection({**rec["connection"], "token": str(token)})
        rec["connection"] = cfg
