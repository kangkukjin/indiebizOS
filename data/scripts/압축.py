"""압축 — zip 묶기·풀기·목록 (표준 라이브러리, 외부 의존 없음).

args(JSON stdin):
  op: "pack" | "unpack" | "list"
  pack:   paths:[파일·폴더…] (또는 path / items:[{path|saved_path|src|out}]) · output: 결과 zip 경로
          (생략 = 첫 대상 옆 `<이름>.zip`) · include: ["*.pdf"] 글로브(파일명 기준, 생략=전부)
          · exclude: 기본 [".DS_Store", "__pycache__", "*.pyc", "Thumbs.db"] · base: 폴더를 묶을 때
          안쪽 경로 기준(생략 = 대상의 부모 — 폴더 이름이 zip 안 첫 칸)
  unpack: path: zip/tar(.gz/.bz2/.xz) · out_dir: 풀 폴더(생략 = 압축 파일 옆 `<이름>/`)
          · include: ["*.pdf"] 일부만 · overwrite: false(이미 있는 파일은 거절)
          경로 탈출(../, 절대경로) 항목은 거절 — zip slip 차단
  list:   path: zip/tar → 항목 items(name·size·compressed·is_dir·modified)
출력: pack → {"items":[{name,size}], "output", "count", "bytes"} / unpack → {"items":[{name,out,size}], "out_dir", "count"}
      / list → {"items":[…], "count", "total_size"}. 실패는 success:false + error.
"""
import fnmatch
import json
import os
import sys
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "base"))
try:
    from runtime_utils import expand_body_path
except Exception:  # noqa: BLE001
    expand_body_path = os.path.expanduser

_DEFAULT_EXCLUDE = [".DS_Store", "__pycache__", "*.pyc", "Thumbs.db"]


def _resolve(p: str) -> Path:
    q = Path(expand_body_path(str(p)))
    return q if q.is_absolute() else (_REPO / q)


def _collect_paths(args: dict) -> list[str]:
    if args.get("paths"):
        return [str(p) for p in args["paths"]]
    if args.get("path"):
        return [str(args["path"])]
    out = []
    for it in args.get("items") or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            v = it.get("path") or it.get("saved_path") or it.get("src") or it.get("out") or it.get("file")
            if v:
                out.append(str(v))
    return out


def _match(name: str, patterns) -> bool:
    base = os.path.basename(name.rstrip("/"))
    return any(fnmatch.fnmatch(base, p) or fnmatch.fnmatch(name, p) for p in patterns)


def _excluded(rel: str, exclude) -> bool:
    return any(_match(part, exclude) for part in rel.split("/") if part)


def _is_tar(path: Path) -> bool:
    return path.suffix.lower() in (".tar", ".tgz", ".gz", ".bz2", ".xz", ".tbz2", ".txz") and tarfile.is_tarfile(str(path))


# ---------------------------------------------------------------- pack

def op_pack(args: dict) -> dict:
    targets = [_resolve(p) for p in _collect_paths(args)]
    if not targets:
        return {"success": False, "error": "paths(또는 path/items)가 필요합니다."}
    missing = [str(t) for t in targets if not t.exists()]
    if missing:
        return {"success": False, "error": f"없는 경로: {missing}"}
    include = args.get("include") or []
    exclude = args.get("exclude") if args.get("exclude") is not None else _DEFAULT_EXCLUDE
    base = _resolve(args["base"]) if args.get("base") else None
    output = _resolve(args["output"]) if args.get("output") else targets[0].with_suffix("").with_name(targets[0].stem + ".zip")
    if output.exists() and not args.get("overwrite"):
        return {"success": False, "error": f"출력 zip 이 이미 있습니다(overwrite:true 로 허용): {output}"}
    output.parent.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[Path, str]] = []
    for t in targets:
        root = base or t.parent
        if t.is_dir():
            for dirpath, dirnames, files in os.walk(t):
                dirnames[:] = [d for d in dirnames if not _match(d, exclude)]
                for f in sorted(files):
                    fp = Path(dirpath) / f
                    try:
                        rel = fp.relative_to(root).as_posix()
                    except ValueError:
                        rel = fp.name
                    if _excluded(rel, exclude):
                        continue
                    if include and not _match(rel, include):
                        continue
                    entries.append((fp, rel))
        else:
            try:
                rel = t.relative_to(root).as_posix()
            except ValueError:
                rel = t.name
            if include and not _match(rel, include):
                continue
            entries.append((t, rel))
    if not entries:
        return {"success": False, "error": "묶을 파일이 없습니다(include/exclude 조건 확인)."}
    seen = set()
    items = []
    with zipfile.ZipFile(str(output), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp, rel in entries:
            if rel in seen:
                continue
            seen.add(rel)
            if fp.resolve() == output.resolve():
                continue
            zf.write(str(fp), rel)
            items.append({"name": rel, "size": fp.stat().st_size})
    return {"items": items, "output": str(output), "count": len(items), "bytes": output.stat().st_size}


# ---------------------------------------------------------------- unpack

def _safe_dest(out_dir: Path, name: str) -> Path | None:
    if not name or name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts or (len(name) > 1 and name[1] == ":"):
        return None
    dest = (out_dir / name).resolve()
    try:
        dest.relative_to(out_dir.resolve())
    except ValueError:
        return None
    return dest


def op_unpack(args: dict) -> dict:
    if not args.get("path"):
        return {"success": False, "error": "path(압축 파일)가 필요합니다."}
    src = _resolve(args["path"])
    if not src.is_file():
        return {"success": False, "error": f"압축 파일이 없습니다: {src}"}
    out_dir = _resolve(args["out_dir"]) if args.get("out_dir") else src.with_name(src.name.split(".")[0] or src.stem)
    include = args.get("include") or []
    overwrite = bool(args.get("overwrite"))
    out_dir.mkdir(parents=True, exist_ok=True)
    items, skipped, rejected = [], [], []

    if zipfile.is_zipfile(str(src)):
        with zipfile.ZipFile(str(src)) as zf:
            enc = [i.filename for i in zf.infolist() if i.flag_bits & 0x1]
            if enc:
                return {"success": False, "error": f"암호가 걸린 항목이 있어 풀지 못합니다: {enc[:5]}"}
            for info in zf.infolist():
                name = info.filename
                if info.is_dir():
                    continue
                if include and not _match(name, include):
                    continue
                dest = _safe_dest(out_dir, name)
                if dest is None:
                    rejected.append(name)
                    continue
                if dest.exists() and not overwrite:
                    skipped.append(name)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as fsrc, open(dest, "wb") as fdst:
                    while True:
                        chunk = fsrc.read(1 << 20)
                        if not chunk:
                            break
                        fdst.write(chunk)
                items.append({"name": name, "out": str(dest), "size": info.file_size})
    elif _is_tar(src):
        with tarfile.open(str(src)) as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                if include and not _match(m.name, include):
                    continue
                dest = _safe_dest(out_dir, m.name)
                if dest is None:
                    rejected.append(m.name)
                    continue
                if dest.exists() and not overwrite:
                    skipped.append(m.name)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                f = tf.extractfile(m)
                if f is None:
                    continue
                with open(dest, "wb") as fdst:
                    fdst.write(f.read())
                items.append({"name": m.name, "out": str(dest), "size": m.size})
    else:
        return {"success": False, "error": f"zip/tar 형식이 아닙니다: {src}"}

    res = {"items": items, "out_dir": str(out_dir), "count": len(items)}
    if skipped:
        res["skipped_existing"] = skipped
        res["hint"] = "이미 있는 파일은 건너뜀 — overwrite:true 로 덮어쓰기"
    if rejected:
        res["rejected_unsafe"] = rejected
    if not items and (skipped or rejected):
        res["success"] = False
        res["error"] = "푼 파일이 없습니다(기존 파일 건너뜀 또는 안전하지 않은 경로 거절)."
    return res


# ---------------------------------------------------------------- list

def op_list(args: dict) -> dict:
    if not args.get("path"):
        return {"success": False, "error": "path(압축 파일)가 필요합니다."}
    src = _resolve(args["path"])
    if not src.is_file():
        return {"success": False, "error": f"압축 파일이 없습니다: {src}"}
    items = []
    if zipfile.is_zipfile(str(src)):
        with zipfile.ZipFile(str(src)) as zf:
            for i in zf.infolist():
                items.append({"name": i.filename, "size": i.file_size, "compressed": i.compress_size,
                              "is_dir": i.is_dir(), "modified": datetime(*i.date_time).isoformat(),
                              "encrypted": bool(i.flag_bits & 0x1)})
    elif _is_tar(src):
        with tarfile.open(str(src)) as tf:
            for m in tf.getmembers():
                items.append({"name": m.name, "size": m.size, "compressed": None, "is_dir": m.isdir(),
                              "modified": datetime.fromtimestamp(m.mtime).isoformat(), "encrypted": False})
    else:
        return {"success": False, "error": f"zip/tar 형식이 아닙니다: {src}"}
    return {"items": items, "count": len(items), "total_size": sum(i["size"] for i in items), "path": str(src)}


def main() -> int:
    args = json.loads(sys.stdin.read() or "{}")
    op = (args.get("op") or "").lower()
    fn = {"pack": op_pack, "unpack": op_unpack, "list": op_list}.get(op)
    if not fn:
        print(json.dumps({"success": False, "error": "op 는 pack/unpack/list 중 하나여야 합니다."}, ensure_ascii=False))
        return 1
    try:
        res = fn(args)
    except Exception as e:  # noqa: BLE001
        res = {"success": False, "error": f"{op} 실패: {e}"}
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("success", True) else 1


if __name__ == "__main__":
    sys.exit(main())
