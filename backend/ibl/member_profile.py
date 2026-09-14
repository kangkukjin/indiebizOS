"""member_profile.py — 회원 프로파일: 부재(카탈로그)·권한(실행 직전 관문)·골격.

정본: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-4·§3-5·§3-6 (2026-09-14, 1단계).

두 층을 각각 집행한다:
- 부재(visible): 회원 주체에서는 `data/member_manifest.json`(빌드 파생 — lands_on 선언 액션)에 있고
  회원 프로파일에 열린 묶음의 액션만 카탈로그에 선다. 나머지는 거절이 아니라 부재.
- 권한(gate): ibl_engine 의 잎마다 실행 직전에 같은 판정 + hub 는 감사 지문 대조 + body 는 몸 바인딩.
  선언 없음=거절(fail-closed). 주인 주체에는 None(무영향).

판정 축은 이름이 아니라 선언(lands_on·limb_op·path_audited·side_effect·회원 활성 원장)이다.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

PROFILE = "member"
_cache = {"path": None, "mtime": None, "data": None}


def _root() -> Path:
    from runtime_utils import get_base_path
    return Path(get_base_path())


def manifest(root: Path = None) -> dict:
    """빌드 파생 회원 매니페스트(mtime 캐시). 없으면 빈 매니페스트(=회원에게 어휘 없음)."""
    p = Path(root or _root()) / "data" / "member_manifest.json"
    try:
        st = p.stat()
    except FileNotFoundError:
        return {"version": 1, "actions": {}}
    if _cache["path"] == str(p) and _cache["mtime"] == st.st_mtime_ns:
        return _cache["data"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 1, "actions": {}}
    _cache.update(path=str(p), mtime=st.st_mtime_ns, data=data)
    return data


def is_member_principal() -> bool:
    try:
        import principal
        return principal.current().kind == principal.KIND_MEMBER
    except Exception:
        return False


def entry(node: str, action: str, root: Path = None) -> Optional[dict]:
    return (manifest(root).get("actions") or {}).get(f"{node}:{action}")


def handler_fingerprint(pkg_dir: Path) -> str:
    """scripts/iblbuild_derive.handler_fingerprint 와 같은 계산 — 시험이 일치를 고정한다."""
    h = hashlib.sha256()
    for p in sorted(Path(pkg_dir).rglob("*.py")):
        if "__pycache__" in p.parts or p.name.startswith("test_"):
            continue
        h.update(p.relative_to(pkg_dir).as_posix().encode()); h.update(b"\0"); h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()[:16]


def _package_dir(package_id: str, root: Path = None) -> Optional[Path]:
    try:
        from vocabulary_state import package_path
        return Path(package_path(package_id, root)) if package_id else None
    except Exception:
        return None


def fingerprint_ok(e: dict, root: Path = None) -> bool:
    """hub 액션의 감사 지문이 현재 구현과 같은가 — 옛 표식으로 바뀐 코드를 자동 개방하지 않는다."""
    pa = e.get("path_audited") or {}
    pkg = _package_dir(e.get("package"), root)
    if not pa.get("impl") or pkg is None:
        return False
    return handler_fingerprint(pkg) == str(pa.get("impl"))


def _package_open(e: dict, node: str, action: str, cfg: dict, root: Path = None) -> bool:
    from vocabulary_state import is_active, action_owner
    pkg = e.get("package") or action_owner(node, action, cfg, root)
    if not pkg:
        return False   # 코어(패키지 없음) 액션은 1단계에서 회원에게 열지 않는다 — 지문 대상이 없다
    return is_active(pkg, root, profile=PROFILE)


def visible(node: str, action: str, cfg: dict, root: Path = None) -> bool:
    """부재 층 — 회원 주체가 아니면 항상 True(무영향)."""
    if not is_member_principal():
        return True
    e = entry(node, action, root)
    if not e:
        return False
    if not _package_open(e, node, action, cfg or {}, root):
        return False
    if e.get("lands_on") == "hub" and not fingerprint_ok(e, root):
        return False
    return True


def gate(node: str, action: str, cfg: dict, root: Path = None) -> Optional[dict]:
    """권한 층 — 실행 직전. 회원 주체에서 통과 못 하면 거절 봉투, 아니면 None."""
    if not is_member_principal():
        return None
    q = f"{node}:{action}"
    e = entry(node, action, root)
    if not e:
        return {"success": False, "error_type": "permission",
                "error": f"[{q}] 은(는) 회원 세션에 없는 낱말입니다(주인이 개방하지 않음)."}
    if not _package_open(e, node, action, cfg or {}, root):
        return {"success": False, "error_type": "permission",
                "error": f"[{q}] 의 묶음이 회원 프로파일에 잠들어 있습니다."}
    if e.get("lands_on") == "hub":
        if not fingerprint_ok(e, root):
            return {"success": False, "error_type": "permission",
                    "error": f"[{q}] 의 감사 표식이 현재 구현과 다릅니다 — 재감사 전에는 열리지 않습니다."}
        return None
    import principal
    if e.get("lands_on") != "body" or not e.get("limb_op"):
        return {"success": False, "error_type": "permission", "error": "회원 실행 선언 불완전"}
    from member_bridge import connected
    if not principal.current().device_id or not connected(principal.current().device_id):
        return {"success": False, "error_type": "no_body", "error": "회원 기기가 연결되어 있지 않습니다"}
    return None


def skeletonize(code: str) -> str:
    """사전에 실재하는 액션 이름만 남긴다. 슬롯 이름·fn 이름·주석도 사적일 수 있다."""
    if not code:
        return ""
    from ibl_registry import load_nodes_installed
    nodes = (load_nodes_installed() or {}).get("nodes", {})
    public = {f"{n}:{a}" for n, cfg in nodes.items() for a in (cfg.get("actions") or {})}
    return " >> ".join(f"[{q}]" for q in re.findall(r"\[([A-Za-z_]+:[A-Za-z_]+)\]", code) if q in public)
