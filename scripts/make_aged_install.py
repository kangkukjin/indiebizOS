#!/usr/bin/env python3
"""make_aged_install.py — 노후·개인화 설치본 픽스처 (2026-09-02, ② B)

"빈 설치본이 뜬다"(ci_boot_smoke)는 증명돼 있었지만 "옛 설치본이 업그레이드 뒤에도 뜬다·
사용자 것이 남는다"는 아무도 증명하지 않았다. 이 스크립트는 그 옛 몸을 만든다:

  1. 직전 태그를 git worktree 로 꺼낸다(= 그 시점에 설치한 사람의 소스 트리)
  2. 한 번 부팅해 그 시점의 DB·파생물이 생기게 한다
  3. 개인화를 주입한다 — 코어 패키지 하나 끔, 사용자 패키지 추가, 사용자 파일·설정, DB 행,
     옛 액션명 행(스키마 마이그레이션 검증용), 은퇴 예정 어휘 조각(격리 검증용)
  4. 사용자 소유물의 해시·행수를 스냅샷으로 남긴다 — 업그레이드 뒤 대조의 기준

사용: python3 scripts/make_aged_install.py [--tag vX.Y.Z] [--out DIR] [--python PY]
      (ci_upgrade_smoke.py 가 import 해서 쓴다 — 단독 실행은 픽스처 확인용)
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEADLINE_S = int(os.environ.get("BOOT_SMOKE_DEADLINE", "240"))

# 개인화 — 여기 이름들이 곧 "보존돼야 하는 것"의 목록이다.
# 끌 코어 패키지는 고정하지 않고 "태그 이후 상류가 바꾼 것"을 우선 고른다(pick_core_package) —
# 사용자가 옮긴 패키지를 상류가 고친 경우가 맨손 pull 이 깨지던 자리이고, scripts/update.py 의
# 배치 되돌림→pull→재적용이 그걸 살린다는 것을 이 관문이 증명한다.
USER_PKG = "user_own_pkg"                 # 사용자가 직접 만든(미추적) 패키지
USER_NOTE = "data/user_note.txt"
USER_CONFIG = "data/system_ai_config.json"
RETIRED_FRAGMENT = "retired_probe.yaml"   # 은퇴 검증용 어휘 조각 (매니페스트 retired 에 올려 격리돼야 함)


def sh(cmd, cwd=ROOT, check=True) -> str:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} 실패({r.returncode}): {r.stderr.strip()[:800]}")
    return r.stdout


def default_python() -> str:
    cand = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python3")
    return str(cand) if cand.exists() else sys.executable


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def previous_tag() -> str:
    return sh(["git", "describe", "--tags", "--abbrev=0"]).strip()


def add_worktree(tag: str, dest: Path) -> None:
    sh(["git", "worktree", "add", "--detach", str(dest), tag])


def remove_worktree(dest: Path) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", str(dest)], cwd=str(ROOT),
                   capture_output=True, text=True)
    subprocess.run(["git", "worktree", "prune"], cwd=str(ROOT), capture_output=True, text=True)


def boot(tree: Path, base_path: Path, python: str, label: str, deadline_s: int = DEADLINE_S) -> dict:
    """tree/backend/api.py 를 base_path 위에서 띄워 /health 200 을 받는다. 실패는 예외(로그 꼬리 포함)."""
    port = free_port()
    env = dict(os.environ)
    env.update({"INDIEBIZ_PRODUCTION": "1", "INDIEBIZ_API_PORT": str(port),
                "INDIEBIZ_BASE_PATH": str(base_path), "PYTHONUTF8": "1"})
    log_fd, log_path = tempfile.mkstemp(prefix=f"upgrade_smoke_{label}_", suffix=".log")
    health = f"http://127.0.0.1:{port}/health"
    t0 = time.monotonic()
    with os.fdopen(log_fd, "wb") as log_f:
        proc = subprocess.Popen([python, str(tree / "backend" / "api.py")], cwd=str(tree / "backend"),
                                env=env, stdout=log_f, stderr=subprocess.STDOUT)
        try:
            payload = None
            while time.monotonic() - t0 < deadline_s:
                if proc.poll() is not None:
                    raise RuntimeError(f"[{label}] 부팅 중 죽음 exit={proc.returncode}\n{_tail(log_path)}")
                try:
                    with urllib.request.urlopen(health, timeout=3) as r:
                        payload = json.loads(r.read().decode("utf-8"))
                        break
                except Exception:
                    time.sleep(2)
            if payload is None:
                raise RuntimeError(f"[{label}] {deadline_s}s 안에 /health 없음\n{_tail(log_path)}")
            if payload.get("status") != "healthy":
                raise RuntimeError(f"[{label}] /health 비정상: {payload}\n{_tail(log_path)}")
            took = time.monotonic() - t0
            print(f"[{label}] /health 200 in {took:.1f}s", flush=True)
            # 부팅 뒤 지연 초기화(DB 생성 등)가 끝날 여유 — 다음 부팅이 그 파일을 봐야 한다
            time.sleep(3)
            return {"payload": payload, "log": log_path, "took_s": took}
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()


def _tail(path, n=80) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError as e:
        return f"(로그 읽기 실패: {e})"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[str(p.relative_to(root))] = sha(p)
    return out


def pick_core_package(tree: Path, tag: str) -> tuple:
    """옛 트리 installed/tools 중 끌 패키지. **상류가 바꾼 것을 우선** 고른다 — 사용자가 옮긴 패키지를
    상류가 고친 경우가 맨손 pull 이 깨지던 어려운 경우이고, update.py 의 배치 되돌림이 이걸 살린다.
    없으면 안 바뀐 것 중 가장 작은 것. 반환 (이름, 상류변경여부)."""
    base = tree / "data" / "packages" / "installed" / "tools"
    changed_c, stable_c = [], []
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        rel = f"data/packages/installed/tools/{d.name}"
        changed = subprocess.run(["git", "diff", "--quiet", tag, "--", rel], cwd=str(ROOT)).returncode != 0
        untracked = sh(["git", "ls-files", "--others", "--exclude-standard", "--", rel]).strip()
        # 상류에서 통째로 사라진(은퇴) 패키지는 제외 — 그건 별도 단언 대상
        if not (ROOT / rel).is_dir():
            continue
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        (changed_c if (changed or untracked) else stable_c).append((size, d.name))
    if changed_c:
        return sorted(changed_c)[0][1], True
    if stable_c:
        return sorted(stable_c)[0][1], False
    raise RuntimeError("픽스처: installed/tools 에 코어 패키지가 없다")


def personalize(tree: Path, tag: str) -> dict:
    """개인화 주입 → 기대 스냅샷 반환."""
    data = tree / "data"
    pk = data / "packages"
    # 1) 코어 패키지 하나를 사용자가 껐다 (installed → not_installed)
    disabled, upstream_changed = pick_core_package(tree, tag)
    src = pk / "installed" / "tools" / disabled
    dst = pk / "not_installed" / "tools" / disabled
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    print(f"[fixture] 사용자가 끈 코어 패키지 = {disabled} (상류 변경 {'있음 — 어려운 경우' if upstream_changed else '없음'})", flush=True)
    # 2) 사용자 패키지 (코어 패키지를 복제해 이름만 바꾼 미추적 패키지 — 비활성 자리에 둔다)
    upk = pk / "not_installed" / "tools" / USER_PKG
    shutil.copytree(dst, upk, ignore=shutil.ignore_patterns("__pycache__"))
    tj = json.loads((upk / "tool.json").read_text(encoding="utf-8"))
    tj["id"] = USER_PKG
    tj["name"] = "사용자 자작 패키지 (픽스처)"
    (upk / "tool.json").write_text(json.dumps(tj, ensure_ascii=False, indent=2), encoding="utf-8")
    (upk / ".origin").write_text("user\n", encoding="utf-8")
    # 3) 사용자 파일·설정
    (tree / USER_NOTE).write_text("이 파일은 사용자 것 — 업그레이드가 건드리면 안 된다\n", encoding="utf-8")
    (tree / USER_CONFIG).write_text(json.dumps(
        {"enabled": True, "provider": "ollama", "model": "probe-model", "apiKey": ""}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    # 4) DB 행 — 사용자 표(보존) + 옛 액션명 행(마이그레이션 검증)
    biz = data / "business.db"
    con = sqlite3.connect(str(biz))
    con.execute("CREATE TABLE IF NOT EXISTS user_probe (k TEXT)")
    con.executemany("INSERT INTO user_probe VALUES (?)", [("a",), ("b",), ("c",)])
    con.commit(); con.close()
    wp = data / "world_pulse.db"
    have_wp = wp.exists()
    if have_wp:
        con = sqlite3.connect(str(wp))
        con.execute("CREATE TABLE IF NOT EXISTS action_health (id INTEGER PRIMARY KEY AUTOINCREMENT, node TEXT NOT NULL, "
                    "action TEXT NOT NULL, success INTEGER NOT NULL, response_ms INTEGER, "
                    "source TEXT NOT NULL DEFAULT 'usage', timestamp TEXT NOT NULL, channel TEXT, error TEXT)")
        con.executemany("INSERT INTO action_health (node, action, success, timestamp) VALUES (?,?,?,?)",
                        [("sense", "cctv_search", 1, "2026-01-01T00:00:00"), ("self", "storage", 1, "2026-01-01T00:00:00")])
        con.commit(); con.close()
    usage = data / "ibl_usage.db"
    have_usage = False
    if usage.exists():
        con = sqlite3.connect(str(usage))
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ibl_examples'").fetchone():
            con.execute("INSERT INTO ibl_examples (intent, ibl_code, created_at, updated_at) VALUES (?,?,?,?)",
                        ("픽스처 옛 이름", '[self:storage_scan]{path: "/tmp"}', "2026-01-01", "2026-01-01"))
            con.commit(); have_usage = True
        con.close()
    # 5) 은퇴 예정 어휘 조각 (부팅은 ibl_nodes.yaml 만 읽으므로 src 조각 하나는 부팅에 무해)
    frag = data / "ibl_nodes_src" / RETIRED_FRAGMENT
    frag.parent.mkdir(parents=True, exist_ok=True)
    frag.write_text("# 은퇴 검증용 — 매니페스트 retired 에 오르면 격리돼야 한다\n", encoding="utf-8")

    return {
        "disabled_pkg": disabled,
        "disabled_pkg_upstream_changed": upstream_changed,
        "user_pkg_hashes": tree_hashes(upk),
        "user_note_sha": sha(tree / USER_NOTE),
        "user_config_sha": sha(tree / USER_CONFIG),
        "business_user_rows": 3,
        "have_world_pulse": have_wp,
        "have_usage": have_usage,
    }


def build(out: Path, tag: str = None, python: str = None) -> dict:
    tag = tag or previous_tag()
    python = python or default_python()
    tree = out / "aged"
    if tree.exists():
        remove_worktree(tree)
        shutil.rmtree(tree, ignore_errors=True)
    print(f"[fixture] 직전 태그 {tag} → worktree {tree}", flush=True)
    add_worktree(tag, tree)
    boot(tree, tree, python, label=f"aged-boot({tag})")
    expect = personalize(tree, tag)
    print(f"[fixture] 개인화 주입 완료 (world_pulse={expect['have_world_pulse']}, usage={expect['have_usage']})", flush=True)
    return {"tree": tree, "tag": tag, "python": python, "expect": expect}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag")
    ap.add_argument("--out", default=None)
    ap.add_argument("--python", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="indiebiz_aged_"))
    fx = build(out, a.tag, a.python)
    print(json.dumps({"tree": str(fx["tree"]), "tag": fx["tag"], "expect": fx["expect"]}, ensure_ascii=False, indent=2)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
