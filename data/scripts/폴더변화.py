"""폴더변화 — 폴더의 파일 골격을 지난번 본 모습과 대조해 바뀐 것만 items 로 낸다.

"변화가 있는가"는 측정이다. 그 측정을 AI 턴에 맡기면 깨운 뒤에야 할 일이 없음을 안다
(2026-10-01 감사: 주간 재조사 한 회 입력 72만 토큰, 기록의 61%가 "변화 없음").
여기서는 재고(경로·크기·수정 시각)만 대조한다 — 무엇이 기억할 만한가는 받는 쪽이 판단한다.

args:
  path    (필수) 폴더. 상대 경로는 작업공간 기준.
  exclude 대조에서 뺄 glob 목록(상대 경로와 파일 이름 양쪽에 적용). 기본 제외(DB·캐시)에 더해진다.
  name    같은 폴더를 다른 목적으로 따로 지켜볼 때의 이름(기준 저장 열쇠에 섞인다).
  since   기준이 아직 없을 때만 쓰는 첫 대조 시각 — ISO 시각 또는 파일 경로(그 파일의 수정 시각).
          없으면 첫 대조는 기준만 세우고 변화 0건으로 답한다.
  commit  기본 true — 대조한 뒤 지금 모습을 새 기준으로 저장한다.
          false 면 기준을 그대로 두고, 방금 본 모습을 '확인 대기'로만 적어 둔다 — 받는 쪽이 일을 마친 뒤
          op:"ack" 로 확인해야 기준이 된다. 확인 전에 다시 대조하면 같은 변화가 (그 사이 변화와 함께) 다시 나온다.
          받는 쪽이 중간에 죽어도 변화를 잃지 않는 길(2026-10-01 실측: 위임 턴 45회 중 5회가 흔적 없이 끊김).
  op      check(기본) | ack — ack 는 path·name 으로 '확인 대기'를 기준으로 올린다(대기가 없으면 acked:false).
  limit   items 상한(기본 60). 넘치면 omitted 와 by_dir(1단 폴더별 건수)로 접는다.
"""
import fnmatch
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
STATE_DIR = BASE / "data" / "folder_watch"
# 내용이 아니라 실행의 부산물로 바뀌는 것들 — 보는 것만으로도 수정 시각이 움직인다.
ALWAYS_EXCLUDE = ["*.db", "*.db-shm", "*.db-wal", "*.db-journal", "*.sqlite", "*.sqlite-*",
                  ".DS_Store", "__pycache__/*", "*.pyc", ".git/*"]


def _resolve(path: str) -> Path:
    p = Path(os.path.expanduser(path))
    return (p if p.is_absolute() else BASE / p).resolve()


def _excluded(rel: str, patterns) -> bool:
    name = rel.rsplit("/", 1)[-1]
    parts = rel.split("/")
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
            return True
        # "dir/*" 꼴은 어느 깊이의 그 폴더든 통째로 뺀다.
        if pat.endswith("/*") and any(fnmatch.fnmatch(part, pat[:-2]) for part in parts[:-1]):
            return True
    return False


def _snapshot(root: Path, patterns) -> dict:
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if _excluded(rel, patterns):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            files[rel] = [st.st_size, int(st.st_mtime)]
    return files


def _since_ts(value):
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        p = _resolve(text)
        if not p.exists():
            raise ValueError(f"since 를 시각으로도 파일로도 읽을 수 없다: {text}")
        return p.stat().st_mtime


def _save(state_path: Path, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".watch-", dir=STATE_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, state_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _iso(ts) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def main(args: dict) -> dict:
    if not args.get("path"):
        raise ValueError("path 가 필요하다")
    root = _resolve(args["path"])
    if not root.is_dir():
        raise ValueError(f"폴더가 없다: {root}")
    patterns = ALWAYS_EXCLUDE + [str(x) for x in (args.get("exclude") or [])]
    limit = int(args.get("limit") or 60)
    commit = args.get("commit", True) is not False

    key = hashlib.sha1((str(root) + "\n" + str(args.get("name") or "")).encode()).hexdigest()[:16]
    state_path = STATE_DIR / f"{key}.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else None

    if (args.get("op") or "check") == "ack":
        pending = (state or {}).get("pending")
        if not pending:
            return {"items": [], "acked": False, "path": str(root), "reason": "확인 대기 중인 대조가 없다"}
        _save(state_path, {"path": str(root), "name": args.get("name") or "",
                           "checked_at": pending["checked_at"], "files": pending["files"]})
        return {"items": [], "acked": True, "path": str(root), "baseline_at": pending["checked_at"]}
    if args.get("op") not in (None, "", "check"):
        raise ValueError("op 는 check 또는 ack")

    now = datetime.now().timestamp()
    files = _snapshot(root, patterns)

    rows = []
    first = state is None
    if first:
        cut = _since_ts(args.get("since"))
        if cut is not None:
            rows = [{"path": rel, "change": "modified", "size": v[0], "modified_at": _iso(v[1])}
                    for rel, v in files.items() if v[1] > cut]
        baseline_at = _iso(cut) if cut is not None else None
    else:
        old = state.get("files") or {}
        # 제외 목록이 달라졌으면 지난 기준에도 같은 눈을 씌운다 — 규칙 변경이 변화로 읽히지 않게.
        old = {rel: v for rel, v in old.items() if not _excluded(rel, patterns)}
        for rel, v in files.items():
            if rel not in old:
                rows.append({"path": rel, "change": "added", "size": v[0], "modified_at": _iso(v[1])})
            elif list(old[rel]) != v:
                rows.append({"path": rel, "change": "modified", "size": v[0], "modified_at": _iso(v[1])})
        for rel, v in old.items():
            if rel not in files:
                rows.append({"path": rel, "change": "removed", "size": v[0], "modified_at": None})
        baseline_at = state.get("checked_at")

    rows.sort(key=lambda r: (r["modified_at"] or "", r["path"]), reverse=True)
    by_dir = {}
    for r in rows:
        top = r["path"].split("/", 1)[0] if "/" in r["path"] else "."
        by_dir[top] = by_dir.get(top, 0) + 1

    snapshot = {"path": str(root), "name": args.get("name") or "", "checked_at": _iso(now), "files": files}
    if commit or (first and not rows):
        # 기준이 아직 없고 알릴 변화도 없으면 commit 과 무관하게 기준을 세운다 — 첫 대조의 뜻이 그것이다.
        _save(state_path, snapshot)
    elif rows and not first:
        _save(state_path, {**state, "pending": {"checked_at": snapshot["checked_at"], "files": files}})
    elif not rows and (state or {}).get("pending"):
        # 변화가 되돌려져 기준과 같아졌다 — 낡은 대기를 걷는다.
        _save(state_path, {k: v for k, v in state.items() if k != "pending"})
    elif rows:
        # 기준 없이 since 로 잰 변화: 빈 기준에 대기를 걸 수 없으니, since 이전 것만 기준으로 세우고 대기를 건다.
        seen = {r["path"] for r in rows}
        _save(state_path, {**snapshot, "checked_at": baseline_at, "files": {k: v for k, v in files.items() if k not in seen},
                           "pending": {"checked_at": snapshot["checked_at"], "files": files}})

    return {"items": rows[:limit], "count": len(rows), "omitted": max(0, len(rows) - limit),
            "by_dir": by_dir, "path": str(root), "watched_files": len(files),
            "baseline_at": baseline_at, "checked_at": _iso(now), "first_check": first, "committed": commit,
            "awaiting_ack": bool(rows) and not commit}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(1)
