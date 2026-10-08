"""코딩 프로젝트 — 폴더 하나가 프로젝트다 (2026-10-07, docs/CODING_APP_ON_IBL_PLAN_2026_10_07.md §2).

사용자는 코딩하는 사람이 아니라 맡기는 사람이다. 그래서 단위는 과제·worktree·검토 묶음이 아니라
**프로젝트 폴더**(`outputs/coding/<이름>/` — 목표 문서 `목표.md` + 코드 + 조용한 git)이고, AI 코딩의
결과는 diff 승인이 아니라 **기록(커밋) + 되돌리기**로 지킨다. 옛 과제별 worktree 몸(coding_workspace·
coding_runs)은 이 모듈이 대체했다. 실행자(AI)는 여기 없다 — `[others:delegate]{scope:"system", role:"coding"}`
로 실행 에이전트에게 맡기며, 이 모듈은 폴더·git·목표 문서·실행(프로젝트 명령의 샌드박스 프로세스)만 안다.
"""
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from coding_git import CodingConflict, git, safe_path, text_git
from coding_store import CodingStore, fingerprint, identifier
from runtime_utils import get_base_path

GOAL_NAME = "목표.md"
DEFAULT_FOLDER = "outputs/coding"
GOAL_SECTIONS = ("무엇을 만드나", "꼭 되어야 하는 것", "안 해도 되는 것", "실행 방법", "진행 기록")
OUTPUT_READ_MAX = 1_000_000   # 출력 한 번 읽기 상한(바이트) — 넘는 요청은 깎고 clamped 로 알린다
ACTIVE = {}
ACTIVE_LOCK = threading.RLock()
_COMMIT_ENV = {"GIT_AUTHOR_NAME": "indiebizOS", "GIT_AUTHOR_EMAIL": "indiebizos@local",
               "GIT_COMMITTER_NAME": "indiebizOS", "GIT_COMMITTER_EMAIL": "indiebizos@local"}
_GOAL_PLACEHOLDER = {"무엇을 만드나": "(만들고 싶은 것을 한두 문장으로)", "꼭 되어야 하는 것": "- ", "안 해도 되는 것": "- ",
                     "실행 방법": "(정해지지 않음)", "진행 기록": ""}


def goal_template(name: str, body: dict | None = None) -> str:
    """목표 문서의 틀 — 절 이름이 고정이라 앱(요약·실행 방법·진행 기록)이 읽는다."""
    body = body or {}
    out = [f"# {name} — 코딩 목표", ""]
    for section in GOAL_SECTIONS:
        out += [f"## {section}", "", str(body.get(section, _GOAL_PLACEHOLDER[section])).rstrip(), ""]
    return "\n".join(out).rstrip() + "\n"


def parse_goal(text: str) -> dict:
    """목표 문서에서 앱이 쓰는 칸을 읽는다 — 제목(아이콘)·요약·실행 명령·실행 URL·진행 기록. 없는 칸은 빈 값."""
    sections, current = {}, None
    title = ""
    for line in (text or "").splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    body = {k: "\n".join(v).strip() for k, v in sections.items()}
    icon = ""
    if title and not title[0].isalnum() and ord(title[0]) > 0x2000:
        icon = title[0]
    what = body.get("무엇을 만드나", "")
    summary = next((ln.strip() for ln in what.splitlines() if ln.strip() and not ln.strip().startswith("(")), "")
    run = body.get("실행 방법", "")
    command = next((m.group(1).strip() for m in re.finditer(r"`([^`\n]+)`", run)), "")
    url = next((m.group(0) for m in re.finditer(r"https?://[^\s)>\]]+", run)), "")
    return {"title": title, "icon": icon, "summary": summary[:160], "run_command": command, "run_url": url,
            "log": body.get("진행 기록", "")}


# 개발 서버 프레임워크 → (실행 파일 이름, 기본 포트). 주소는 고른 스크립트가 그 실행 파일을 부를 때만 쓴다 —
# run_url 이 있으면 실행 샌드박스가 로컬 포트를 열기 때문에 추측 포트는 적지 않는다.
_JS_SERVERS = (("next", "next", 3000), ("vite", "vite", 5173), ("react-scripts", "react-scripts", 3000),
               ("nuxt", "nuxt", 3000), ("astro", "astro", 4321), ("@angular/cli", "ng", 4200), ("gatsby", "gatsby", 8000))
_LOCKS = (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun"))


def _readme_summary(folder: Path) -> str:
    """README 의 첫 산문 문단 한 줄 — 제목·배지·코드·HTML 은 건너뛰고 링크는 글자만 남긴다."""
    for name in ("README.md", "README.markdown", "README.txt", "README", "readme.md"):
        try:
            text = (folder / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        para, fence = [], False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("```"):
                fence = not fence
                continue
            if fence or s.startswith(("#", "<", "![", "[![", "|", "---", "===")):
                if para:
                    break
                continue
            if not s:
                if para:
                    break
                continue
            para.append(s)
        if para:
            return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(para)).replace("`", "")[:300]
    return ""


def infer_goal(folder) -> dict:
    """가져온 폴더의 매니페스트에서 목표 문서의 '무엇을 만드나'·'실행 방법' 을 결정적으로 추론한다(모델 호출 없음).
    package.json(scripts dev>start + 프레임워크 기본 포트) · Django manage.py · Streamlit · Python 진입 파일 ·
    정적 index.html 만 안다. 추론 못 한 칸은 넣지 않는다 — goal_template 이 자리표시로 채운다."""
    folder = Path(folder)
    body, what, run = {}, "", ""
    pkg = None
    try:
        pkg = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        pkg = None
    if isinstance(pkg, dict):
        if isinstance(pkg.get("description"), str):
            what = pkg["description"].strip()
        scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
        script = next((s for s in ("dev", "start") if isinstance(scripts.get(s), str) and scripts[s].strip()), "")
        if script:
            pm = next((tool for lock, tool in _LOCKS if (folder / lock).exists()), "npm")
            command = f"{pm} start" if script == "start" and pm == "npm" else f"{pm} run {script}"
            line = scripts[script]
            deps = {k for key in ("dependencies", "devDependencies") if isinstance(pkg.get(key), dict) for k in pkg[key]}
            port = next((p for dep, binary, p in _JS_SERVERS if dep in deps and re.search(rf"(^|[\s/]){re.escape(binary)}(\s|$)", line)), None)
            explicit = re.search(r"(?:--port[ =]|-p\s+)(\d{2,5})\b", line)
            if explicit and port:
                port = int(explicit.group(1))
            run = f"`{command}`" + (f" → http://localhost:{port}" if port else "")
    elif (folder / "manage.py").is_file():
        run = "`python manage.py runserver` → http://localhost:8000"
    else:
        manifests = {}
        for name in ("requirements.txt", "pyproject.toml"):
            try:
                manifests[name] = (folder / name).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                manifests[name] = ""
        reqs = "\n".join(manifests.values()).lower()
        entry = next((n for n in ("app.py", "main.py", "streamlit_app.py") if (folder / n).is_file()), "")
        if entry and "streamlit" in reqs:
            run = f"`streamlit run {entry}` → http://localhost:8501"
        elif entry:
            run = f"`python3 {entry}`"
        elif (folder / "index.html").is_file():
            run = "`python3 -m http.server 8000` → http://localhost:8000"
        m = re.search(r'(?m)^description\s*=\s*"([^"\n]+)"', manifests["pyproject.toml"])
        what = m.group(1).strip() if m else ""
    what = what or _readme_summary(folder)
    if what:
        body["무엇을 만드나"] = what
    if run:
        body["실행 방법"] = run
    return body


class CodingProjects:
    def __init__(self, store=None):
        self.store = store or CodingStore()

    # ── 등록·목록 ────────────────────────────────────────────────────────────
    def project(self, resource: str) -> dict:
        return self.store.get("project", resource)

    @staticmethod
    def resource_id(path: Path) -> str:
        return "coding_" + fingerprint(str(path))[:24]

    def _refuse_self(self, target: Path):
        """자기 몸(indiebizOS 저장소 루트·RED 구역·사전)은 프로젝트가 아니다 — 자기수리는 REPAIR 경로. outputs·projects/*/outputs 는 프로젝트 자리."""
        base = Path(get_base_path()).resolve()
        if target == base:
            raise ValueError("indiebizOS 자기 저장소는 코딩 프로젝트로 열 수 없습니다 — 자기수리는 시스템 AI 의 REPAIR 경로로")
        if base in target.parents:
            head = target.relative_to(base).parts[0]
            if head in {"backend", "frontend", "scripts", "data", "docs", ".git", ".venv", "node_modules"}:
                raise ValueError(f"indiebizOS 의 {head}/ 는 몸의 코드·사전이라 코딩 프로젝트로 열 수 없습니다 — 자기수리는 REPAIR 경로로")

    @staticmethod
    def _ensure_git(target: Path):
        if not (target / ".git").exists():
            git(target, "init", "-q")

    def open(self, path, goal=None) -> dict:
        target = Path(path).expanduser().resolve(strict=True)
        if not target.is_dir():
            raise ValueError("코딩 프로젝트는 폴더입니다 — 파일이 아니라 프로젝트 폴더를 고르세요")
        self._refuse_self(target)
        self._ensure_git(target)
        pid = self.resource_id(target)
        try:
            row = self.store.get("project", pid)
        except ValueError:
            row = {"id": pid, "path": str(target), "name": target.name, "created_at": time.time()}
        row["opened_at"] = time.time()
        row["registered"] = True
        if not (target / GOAL_NAME).exists():
            # 가져온 폴더에 목표 문서가 없으면 매니페스트로 추론해 쓴다 — 사용자가 준 goal 이 '무엇을 만드나' 에 우선.
            # 'x' 로 열어 그 사이 생긴 문서도 덮지 않는다.
            body = infer_goal(target)
            if goal:
                body["무엇을 만드나"] = str(goal)
            try:
                with (target / GOAL_NAME).open("x", encoding="utf-8") as stream:
                    stream.write(goal_template(target.name, body))
            except FileExistsError:
                pass
        return self.store.save("project", row)

    def unregister(self, row: dict) -> dict:
        """목록 등록만 해제한다. 폴더·git·실행 기록은 보존하며 다시 open하면 재등록된다."""
        with self.store.lock("registration:" + row["id"]):
            current = self.project(row["id"])
            current["registered"] = False
            self.store.save("project", current)
        return {"closed": True, "unregistered": True, "path": row["path"]}

    def goal_path(self, row: dict) -> Path:
        return Path(row["path"]) / GOAL_NAME

    def _goal(self, row: dict) -> dict:
        p = self.goal_path(row)
        try:
            return {"exists": True, **parse_goal(p.read_text(encoding="utf-8"))}
        except (OSError, UnicodeDecodeError):
            return {"exists": False, "title": "", "icon": "", "summary": "", "run_command": "", "run_url": "", "log": ""}

    def _active_delegation(self, row: dict):
        """이 프로젝트를 context 로 받은 살아 있는 시스템 AI 위임 — 카드의 'AI 작업 중' 과 상단 칩의 근거."""
        try:
            from system_ai_memory import get_pending_tasks
            needle = json.dumps(row["path"], ensure_ascii=False)
            for t in get_pending_tasks():
                req = t.get("original_request") or ""
                if '"project": ' + needle in req or '"project":' + needle in req:
                    return {"kind": "delegation", "owner": "system", "task_id": t["task_id"]}
        except Exception:  # noqa: BLE001 — 위임 원장을 못 읽어도 프로젝트 목록은 선다
            return None
        return None

    def latest_run(self, row: dict):
        for r in self.store.list("run"):
            if r.get("project") == row["id"]:
                return r
        return None

    def _item(self, row: dict, registered: bool = True) -> dict:
        path = Path(row["path"])
        g = self._goal(row)
        run = self.latest_run(row) if registered else None
        active = self._active_delegation(row)
        status = "ai" if active else ("run" if run and run.get("state") == "running" else "")
        try:
            mtime = max([path.stat().st_mtime] + [c.stat().st_mtime for c in path.iterdir() if c.name != ".git"])
        except OSError:
            mtime = 0
        return {"resource": row["id"] if registered else None, "path": str(path), "name": path.name,
                "icon": g["icon"] or "💻", "summary": g["summary"] or ("목표 문서가 없습니다" if not g["exists"] else ""),
                "status": status, "status_label": {"ai": "AI 작업 중", "run": "실행 중"}.get(status, ""),
                "mtime": mtime, "goal": g["exists"], "active_task": active}

    def projects(self, root=None) -> list:
        """등록된 프로젝트 + 기본 폴더(outputs/coding)의 하위 폴더. 최근 활동순."""
        # 해제된 행도 유지해 기본 폴더 스캔이 다시 목록에 올리지 않게 한다.
        rows = {r["path"]: r for r in self.store.list("project")}
        items = [self._item(r) for r in rows.values()
                 if r.get("registered", True) and Path(r["path"]).is_dir()]
        base = Path(root).expanduser() if root else None
        folder = (base / DEFAULT_FOLDER) if base else None
        if folder and folder.is_dir():
            for child in sorted(folder.iterdir()):
                if child.is_dir() and not child.name.startswith(".") and str(child.resolve()) not in rows:
                    items.append(self._item({"id": self.resource_id(child.resolve()), "path": str(child.resolve())}, registered=False))
        items.sort(key=lambda it: it["mtime"], reverse=True)
        return items

    # ── 읽기 ────────────────────────────────────────────────────────────────
    def _has_head(self, row: dict) -> bool:
        return git(row["path"], "rev-parse", "--verify", "-q", "HEAD", check=False).strip() != b""

    def _status(self, row: dict) -> dict:
        """경로 → 상태 글자(M/A/D/?). git status 가 보는 그대로."""
        out = git(row["path"], "status", "--porcelain=v1", "-z", "--untracked-files=all").decode(errors="replace")
        changed = {}
        for entry in out.split("\0"):
            if len(entry) > 3:
                code, path = entry[:2], entry[3:]
                changed[path] = "?" if code == "??" else (code.strip() or "M")[0]
        return changed

    def detail(self, row: dict) -> dict:
        g = self._goal(row)
        head = text_git(row["path"], "rev-parse", "--short", "HEAD") if self._has_head(row) else ""
        changed = self._status(row)
        return {"selector": {"project": True}, "name": row["name"], "path": row["path"], "goal_path": str(self.goal_path(row)),
                "goal_exists": g["exists"], "icon": g["icon"] or "💻", "summary": g["summary"], "run_command": g["run_command"],
                "run_url": g["run_url"], "log": g["log"], "head": head, "dirty": bool(changed), "changed": sorted(changed),
                "active_task": self._active_delegation(row), "run": self.latest_run(row)}

    def files(self, row: dict) -> list:
        root = Path(row["path"])
        paths = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
        changed = self._status(row)
        items = []
        for p in sorted(set(x for x in paths if x)):
            f = root / p
            try:
                size = f.stat().st_size
            except OSError:
                continue
            items.append({"path": p, "size": size, "changed": changed.get(p, "")})
        return items

    def read_file(self, row: dict, path: str) -> dict:
        target = safe_path(row["path"], path)
        if not target.is_file():
            raise ValueError("파일이 없습니다: " + path)
        data = target.read_bytes()
        binary = b"\0" in data[:8192]
        try:
            text = "" if binary else data.decode("utf-8")
        except UnicodeDecodeError:
            binary, text = True, ""
        return {"path": path, "fingerprint": fingerprint(data), "binary": binary, "size": len(data), "text": text}

    def diff(self, row: dict) -> dict:
        changed = self._status(row)
        patch = git(row["path"], "diff", "HEAD", "--", ".").decode(errors="replace") if self._has_head(row) else ""
        return {"selector": {"diff": True}, "paths": sorted(changed), "status": changed, "patch": patch}

    def read(self, row: dict, selector: dict) -> dict:
        if selector.get("project"):
            return self.detail(row)
        if selector.get("diff"):
            return self.diff(row)
        if selector.get("files") or not selector.get("path"):
            return {"selector": {"files": True}, "items": self.files(row)}
        opened = self.read_file(row, selector["path"])
        lines = opened["text"].splitlines()
        start = int(selector.get("start_line", 1)); end = int(selector.get("end_line", len(lines)))
        if not 1 <= start <= max(end, 1):
            raise ValueError("줄 범위를 확인하세요")
        piece = "\n".join(lines[start - 1:end])
        return {"selector": {"path": selector["path"], "start_line": start, "end_line": min(end, len(lines))},
                "fingerprint": opened["fingerprint"], "binary": opened["binary"], "text": piece, "lines": len(lines)}

    # ── 제안·적용(직접 편집) ─────────────────────────────────────────────────
    def propose(self, row: dict, selector: dict, replacement) -> dict:
        path = selector.get("path")
        if not path or not (isinstance(replacement, str) or replacement is None):
            raise ValueError("코딩 제안에는 selector.path 와 replacement(본문 또는 줄 범위 교체문, null=삭제)가 필요합니다")
        target = safe_path(row["path"], path)
        opened = self.read_file(row, path) if target.is_file() else {"fingerprint": None, "text": ""}
        if replacement is None:
            content = None
        elif selector.get("start_line") is not None:
            lines = opened["text"].splitlines()
            start = int(selector["start_line"]); end = int(selector.get("end_line", start))
            if not 1 <= start <= end <= max(len(lines), 1):
                raise ValueError("줄 범위를 확인하세요")
            content = "\n".join(lines[:start - 1] + replacement.splitlines() + lines[end:]) + ("\n" if opened["text"].endswith("\n") else "")
        else:
            content = replacement
        p = {"id": identifier("proposal"), "project": row["id"], "path": path, "expected": opened["fingerprint"],
             "content": content, "selector": selector, "created_at": time.time()}
        self.store.save("workspace_proposal", p)
        return {"proposal": p["id"], "selector": {"path": path}, "expected": opened["fingerprint"], "delete": content is None}

    def apply(self, row: dict, proposal: str) -> dict:
        p = self.store.get("workspace_proposal", proposal)
        if p.get("project") != row["id"]:
            raise PermissionError("다른 프로젝트의 제안입니다")
        target = safe_path(row["path"], p["path"])
        actual = fingerprint(target.read_bytes()) if target.is_file() else None
        if actual != p["expected"]:
            raise CodingConflict("파일이 그 사이 바뀌었습니다. 다시 읽고 제안하세요")
        if p["content"] is None:
            if target.is_file():
                target.unlink()
            return {"proposal": proposal, "applied": True, "path": p["path"], "deleted": True}
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".coding-save")
        tmp.write_text(p["content"], encoding="utf-8")
        if target.exists():
            tmp.chmod(target.stat().st_mode & 0o777)
        os.replace(tmp, target)
        return {"proposal": proposal, "applied": True, "path": p["path"], "fingerprint": fingerprint(target.read_bytes())}

    # ── 기록(커밋)·버전·되돌리기 ─────────────────────────────────────────────
    def save(self, row: dict, message: str) -> dict:
        """기록 = 지금 폴더의 모든 변경을 한 묶음으로 커밋. 바뀐 것이 없으면 clean."""
        if not message or not str(message).strip():
            raise ValueError("기록에는 message(무엇을 했는지 한 줄)가 필요합니다")
        root = row["path"]
        git(root, "add", "-A", "--", ".")
        if not git(root, "status", "--porcelain", "-z").strip():
            return {"state": "clean", "commit": text_git(root, "rev-parse", "HEAD") if self._has_head(row) else None, "paths": []}
        paths = sorted(self._status(row))
        git(root, "commit", "-q", "-m", str(message)[:500], env=_COMMIT_ENV)
        return {"state": "committed", "commit": text_git(root, "rev-parse", "HEAD"), "paths": paths}

    def versions(self, row: dict) -> list:
        if not self._has_head(row):
            return []
        log = text_git(row["path"], "log", "--format=%H%x1f%ct%x1f%s", "-30")
        items = []
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 3:
                items.append({"id": parts[0], "short": parts[0][:8], "created_at": int(parts[1]), "label": parts[2]})
        return items

    def restore(self, row: dict, revision: str, path: str = None) -> dict:
        """되돌리기 — 지금 상태를 먼저 기록해 두고(잃지 않는다) 그 기록으로 폴더(또는 파일 하나)를 되돌린 뒤 다시 기록."""
        root = row["path"]
        if not revision or not re.fullmatch(r"[0-9a-fA-F]{4,40}", str(revision)):
            raise ValueError("revision 은 기록(커밋) 해시입니다 — versions 에서 고르세요")
        full = text_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
        kept = self.save(row, "되돌리기 전 상태 보관")
        if path:
            safe_path(root, path)
            git(root, "checkout", full, "--", path)
        else:
            git(root, "read-tree", "-u", "--reset", full)
        label = text_git(root, "log", "-1", "--format=%s", full)
        done = self.save(row, f"되돌림: {label} ({full[:8]})")
        return {"restored": full, "path": path, "kept": kept.get("commit"), "state": done["state"], "commit": done.get("commit")}

    # ── 실행(프로젝트 명령) — 엔진 I/O. 샌드박스 프로세스 하나, 프로젝트당 동시에 하나. ──
    def run(self, row: dict, command: str, serve: bool = False) -> dict:
        from coding_process import CodingProcesses, available
        if not isinstance(command, str) or not command.strip():
            raise ValueError("실행 명령이 비었습니다 — 목표 문서의 '실행 방법' 절에 `명령` 을 적거나 여기 입력하세요")
        if not available():
            raise ValueError("이 몸에서는 프로젝트 실행 샌드박스를 쓸 수 없습니다(macOS 필요)")
        live = self.latest_run(row)
        if live and live.get("state") == "running":
            self.stop(live["id"])
        run_id = identifier("run")
        runtime = self.store.root / "runtime" / run_id
        runtime.mkdir(parents=True, exist_ok=True)
        controller = CodingProcesses(row["path"], runtime, local_network=serve)
        log = runtime / "output.log"
        out = log.open("ab")
        out.write(("$ " + command.strip() + "\n").encode())
        out.flush()
        proc = controller.spawn(["/bin/sh", "-c", command], stdout=out, stderr=subprocess.STDOUT)
        rec = {"id": run_id, "project": row["id"], "command": command.strip(), "serve": bool(serve), "state": "running",
               "pid": proc.pid, "started_at": time.time(), "finished_at": None, "exit_code": None, "output": str(log)}
        self.store.save("run", rec)
        with ACTIVE_LOCK:
            ACTIVE[run_id] = controller

        def wait():
            code = proc.wait()
            out.close()
            fresh = self.store.get("run", run_id)
            if fresh["state"] == "running":
                fresh["state"] = "cancelled" if controller.cancelled.is_set() else ("passed" if code == 0 else "failed")
            fresh["exit_code"] = code
            fresh["finished_at"] = time.time()
            self.store.save("run", fresh)
            controller.close()
            with ACTIVE_LOCK:
                ACTIVE.pop(run_id, None)

        threading.Thread(target=wait, daemon=True, name="coding-run-" + run_id).start()
        return rec

    def run_status(self, run_id: str) -> dict:
        return self.store.get("run", run_id)

    def output(self, run_id: str, offset: int = 0, limit: int = 200000) -> dict:
        rec = self.store.get("run", run_id)
        requested = int(limit or OUTPUT_READ_MAX)
        limit = max(1, min(OUTPUT_READ_MAX, requested))
        try:
            with open(rec["output"], "rb") as f:
                f.seek(max(0, int(offset)))
                chunk = f.read(limit)
                end = f.tell()
        except OSError:
            chunk, end = b"", int(offset)
        out = {"run": rec, "text": chunk.decode(errors="replace"), "offset": end}
        if requested != limit:
            out["clamped"] = True
            out["requested"] = requested
        return out

    def stop(self, run_id: str) -> dict:
        rec = self.store.get("run", run_id)
        with ACTIVE_LOCK:
            controller = ACTIVE.get(run_id)
        if controller:
            controller.cancel()
        elif rec.get("state") == "running" and rec.get("pid"):
            # 백엔드 재기동 뒤 — 프로세스 그룹만 남았다.
            try:
                os.killpg(int(rec["pid"]), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if rec.get("state") == "running":
            rec["state"] = "cancelled"
            rec["finished_at"] = time.time()
            self.store.save("run", rec)
        return rec
