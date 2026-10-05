"""warehouse_admin.py — 내 창고(공유창고 레벨 0~4) 관리 낱말 `[self:warehouse]` (2026-10-05, 설치 목록 ⑩).

공개면 관리 라우트(portal_admin)의 본문에만 살던 목록·넣기·빼기(휴지통)·옮기기·새 폴더·휴지통 복구·영구 삭제를 여기로
내려 HTTP 와 IBL 이 같은 함수를 부른다. 경로 규칙은 base.warehouse_paths 한 벌. 예외는 ValueError/LookupError —
라우트가 400/404 로 바꾼다.
"""
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import warehouse_paths as WP

ADD_MAX_FILES = 2000


def list_level(level: int = 0) -> dict:
    lv = WP.check_level(level)
    WP.ensure_dirs()
    counts = {l: sum(1 for p in WP.warehouse_dir(l).rglob("*") if p.is_file() and not p.name.startswith(".")) for l in WP.LEVELS}
    d = WP.warehouse_dir(lv)
    files, dirs = [], []
    for p in d.rglob("*"):
        if p.name.startswith("."):
            continue
        if p.is_dir():
            dirs.append(str(p.relative_to(d))); continue
        if not p.is_file():
            continue
        st = p.stat()
        entry = {"name": str(p.relative_to(d)), "bytes": st.st_size, "path": str(p),
                 "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
        if p.name.lower().endswith(".url") and st.st_size <= 4096:
            target, warehouse = WP.parse_urlfile(p)
            if target:
                entry["link"] = target
                if warehouse:
                    entry["warehouse"] = warehouse
        files.append(entry)
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return {"levels": counts, "level": lv, "files": files, "dirs": dirs, "root_path": str(WP.root()), "folder_path": str(d)}


def _copy_folder_into(src: Path, dest_dir: Path):
    src_r = src.resolve()
    if str(dest_dir.resolve()).startswith(str(src_r) + os.sep):
        raise ValueError("이 폴더 안에 창고가 들어 있어요 — 통째로는 넣을 수 없어요")
    files = [p for p in src_r.rglob("*") if p.is_file() and not any(s.startswith(".") for s in p.relative_to(src_r).parts)]
    if not files:
        raise ValueError("빈 폴더예요")
    if len(files) > ADD_MAX_FILES:
        raise ValueError(f"파일이 너무 많아요({len(files)}개, 상한 {ADD_MAX_FILES}개)")
    dest = dest_dir / src_r.name
    n = 2
    while dest.exists():
        dest = dest_dir / f"{src_r.name} ({n})"; n += 1
    shutil.copytree(str(src_r), str(dest), ignore=shutil.ignore_patterns(".*"))
    return dest.name, len(files)


def add(level: int, paths: list, dest: str = "") -> dict:
    lv = WP.check_level(level)
    if not isinstance(paths, list) or not paths:
        raise ValueError("paths required")
    WP.ensure_dirs()
    dest_dir = WP.safe_rel(WP.warehouse_dir(lv), str(dest or "").strip())
    if not dest_dir.is_dir():
        raise ValueError("목적지가 폴더가 아니에요")
    added, skipped = [], []
    for raw in paths[:200]:
        src = Path(str(raw)).expanduser()
        if src.is_dir():
            try:
                name, cnt = _copy_folder_into(src, dest_dir); added.append(f"{name}/ ({cnt}개)")
            except Exception as e:  # noqa: BLE001
                skipped.append({"path": str(raw), "reason": str(e)})
            continue
        if not src.is_file():
            skipped.append({"path": str(raw), "reason": "없는 경로예요"}); continue
        target = dest_dir / src.name
        n = 2
        while target.exists():
            target = dest_dir / f"{src.stem} ({n}){src.suffix}"; n += 1
        try:
            shutil.copy2(str(src), str(target)); added.append(target.name)
        except Exception as e:  # noqa: BLE001
            skipped.append({"path": str(raw), "reason": str(e)})
    return {"ok": True, "level": lv, "added": added, "skipped": skipped}


def remove(level: int, name: str) -> dict:
    """창고에서 빼기 = 휴지통/<레벨>/ 로 이동(파인더식). 파괴적이지 않다."""
    lv = WP.check_level(level)
    if not name:
        raise ValueError("name required")
    src = WP.safe_rel(WP.warehouse_dir(lv), name)
    if not src.exists() or src == WP.warehouse_dir(lv):
        raise LookupError("no such item")
    trash = WP.trash_dir(lv)
    trash.mkdir(parents=True, exist_ok=True)
    dest = trash / src.name
    if dest.exists():
        dest = (trash / f"{src.stem}.{int(time.time())}{src.suffix}" if src.is_file() else trash / f"{src.name}.{int(time.time())}")
    src.rename(dest)
    return {"ok": True, "trashed": str(dest), "level": lv}


def move(level: int, name: str, dest: str = "", dest_level=None, new_name: str = "") -> dict:
    lv = WP.check_level(level)
    name = (name or "").strip()
    if not name:
        raise ValueError("name required")
    root = WP.warehouse_dir(lv)
    src = WP.safe_rel(root, name)
    if not src.exists():
        raise LookupError("no such item")
    dst_lv = WP.check_level(lv if dest_level in (None, "") else dest_level)
    WP.ensure_dirs()
    dst_root = WP.warehouse_dir(dst_lv)
    dst_dir = WP.safe_rel(dst_root, str(dest or "").strip())
    if not dst_dir.is_dir():
        raise ValueError("목적지가 폴더가 아니에요")
    if src.is_dir() and (dst_dir == src or str(dst_dir.resolve()).startswith(str(src.resolve()) + os.sep)):
        raise ValueError("폴더를 자기 안으로는 옮길 수 없어요")
    new_name = (new_name or "").strip()
    if new_name and ("/" in new_name or new_name.startswith(".")):
        raise ValueError("쓸 수 없는 이름이에요")
    base_name = new_name or src.name
    if src.parent == dst_dir and base_name == src.name:
        return {"ok": True, "moved": name, "noop": True, "level": dst_lv}

    def _is_src(p: Path) -> bool:
        try:
            return os.path.samefile(p, src)
        except OSError:
            return False
    target = dst_dir / base_name
    if new_name and target.exists() and not _is_src(target):
        raise FileExistsError("같은 이름이 이미 있어요")
    n = 2
    while target.exists() and not _is_src(target):
        stem, dot, ext = base_name.rpartition(".")
        target = dst_dir / (f"{stem} ({n}).{ext}" if (dot and src.is_file()) else f"{base_name} ({n})"); n += 1
    src.rename(target)
    return {"ok": True, "moved": str(target.relative_to(dst_root)), "level": dst_lv}


def mkdir(level: int, name: str = "", dest: str = "") -> dict:
    lv = WP.check_level(level)
    WP.ensure_dirs()
    root = WP.warehouse_dir(lv)
    parent = WP.safe_rel(root, str(dest or "").strip())
    if not parent.is_dir():
        raise ValueError("목적지가 폴더가 아니에요")
    name = (name or "").strip() or "새 폴더"
    if "/" in name or name.startswith("."):
        raise ValueError("쓸 수 없는 이름이에요")
    target = parent / name
    n = 2
    while target.exists():
        target = parent / f"{name} ({n})"; n += 1
    target.mkdir()
    return {"ok": True, "created": str(target.relative_to(root)), "level": lv}


def trash_list() -> dict:
    items = []
    for lv in WP.LEVELS:
        d = WP.trash_dir(lv)
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.name.startswith("."):
                continue
            st = p.stat()
            if p.is_dir():
                inner = [f for f in p.rglob("*") if f.is_file() and not f.name.startswith(".")]
                items.append({"name": p.name, "level": lv, "is_dir": True, "count": len(inner),
                              "bytes": sum(f.stat().st_size for f in inner),
                              "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
            else:
                items.append({"name": p.name, "level": lv, "is_dir": False, "count": 1, "bytes": st.st_size,
                              "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return {"items": items, "count": len(items)}


def restore(level: int, name: str) -> dict:
    lv = WP.check_level(level)
    name = (name or "").strip()
    if not name:
        raise ValueError("name required")
    trash = WP.trash_dir(lv)
    src = WP.safe_rel(trash, name)
    if src.parent != trash or not src.exists():
        raise LookupError("no such item")
    WP.ensure_dirs()
    root = WP.warehouse_dir(lv)
    target = root / src.name
    n = 2
    while target.exists():
        target = root / (f"{src.stem} ({n}){src.suffix}" if src.is_file() else f"{src.name} ({n})"); n += 1
    src.rename(target)
    return {"ok": True, "restored": str(target.relative_to(root)), "level": lv}


def purge(level=None, name: str = "", all: bool = False) -> dict:
    """휴지통 영구 삭제 — 단건(level, name) 또는 전부. 여기만 파괴적."""
    if all:
        removed = 0
        for lv in WP.LEVELS:
            d = WP.trash_dir(lv)
            if not d.is_dir():
                continue
            for p in d.iterdir():
                if p.name.startswith("."):
                    continue
                shutil.rmtree(p) if p.is_dir() else p.unlink(); removed += 1
        return {"ok": True, "removed": removed}
    lv = WP.check_level(level)
    name = (name or "").strip()
    if not name:
        raise ValueError("name required")
    trash = WP.trash_dir(lv)
    src = WP.safe_rel(trash, name)
    if src.parent != trash or not src.exists():
        raise LookupError("no such item")
    shutil.rmtree(src) if src.is_dir() else src.unlink()
    return {"ok": True, "removed": 1, "level": lv}


def my_warehouse_op(params: dict) -> Any:
    """[self:warehouse] — 내 창고 관리."""
    op = (params.get("op") or "list").strip()
    lv = params.get("level", 0)
    try:
        if op == "list":
            res = list_level(lv)
            return {"success": True, "items": res["files"], "count": len(res["files"]), **{k: v for k, v in res.items() if k != "files"}}
        if op == "add":
            paths = params.get("paths") or ([params["path"]] if params.get("path") else [])
            return {"success": True, **add(lv, paths, params.get("dest") or "")}
        if op == "remove":
            return {"success": True, **remove(lv, params.get("name") or "")}
        if op == "move":
            return {"success": True, **move(lv, params.get("name") or "", params.get("dest") or "", params.get("dest_level"), params.get("new_name") or "")}
        if op == "mkdir":
            return {"success": True, **mkdir(lv, params.get("name") or "", params.get("dest") or "")}
        if op == "trash":
            res = trash_list()
            return {"success": True, **res}
        if op == "restore":
            return {"success": True, **restore(lv, params.get("name") or "")}
        if op == "purge":
            return {"success": True, **purge(lv, params.get("name") or "", bool(params.get("all")))}
    except (ValueError, FileExistsError) as exc:
        return {"success": False, "error": str(exc)}
    except LookupError as exc:
        return {"success": False, "error": f"없는 항목: {exc}"}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|add|remove|move|mkdir|trash|restore|purge)"}
