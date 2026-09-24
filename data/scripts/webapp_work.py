#!/usr/bin/env python3
"""웹앱 관용구의 파일·프로세스 어댑터. 계획과 결과는 JSON, 명령은 argv다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from datetime import datetime

from logging_utils import mask_secrets

LOG_ROOT = ROOT / "data" / "outputs" / "webapp_checks"
CONFIG = "webapp-checks.json"
MANAGERS = {"npm", "pnpm", "yarn", "bun"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def project_path(value):
    require(isinstance(value, str) and bool(value.strip()), "project 경로가 필요합니다")
    p = Path(value)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    require(p.is_dir(), f"프로젝트 폴더 없음: {p}")
    return p


def read_json(path):
    require(path.stat().st_size <= 1024 * 1024, f"설정 파일은 1MiB 이하여야 합니다: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name}은 JSON 객체여야 합니다")
    return value


def environment(project):
    env = os.environ.copy()
    # npm run과 동일하게 프로젝트에 설치된 Node·도구를 우선한다.
    env["PATH"] = str(project / "node_modules" / ".bin") + os.pathsep + env.get("PATH", "")
    env["CI"] = "true"
    return env


def resolve_command(argv, project, env):
    executable = argv[0]
    if "/" in executable or "\\" in executable:
        path = Path(executable)
        if not path.is_absolute():
            path = project / path
        found = str(path.resolve()) if path.is_file() else None
    else:
        found = shutil.which(executable, path=env["PATH"])
    require(found is not None, f"실행 파일 없음: {executable} — 프로젝트 의존성·런타임을 확인하세요")
    return [found, *argv[1:]]


def configuration(project):
    package_path = project / "package.json"
    package = read_json(package_path) if package_path.is_file() else {}
    cfg_path = project / CONFIG
    scripts = package.get("scripts", {})
    require(isinstance(scripts, dict), "package.json scripts는 객체여야 합니다")
    if cfg_path.is_file():
        config = read_json(cfg_path)
        checks = config.get("checks")
        require(isinstance(checks, list) and bool(checks), "webapp-checks.json checks는 비어 있지 않은 목록이어야 합니다")
        source = CONFIG
    else:
        declared = package.get("packageManager", "")
        require(isinstance(declared, str), "packageManager는 문자열이어야 합니다")
        manager = declared.split("@", 1)[0] if declared else ""
        if not manager:
            locks = {m for f, m in [("package-lock.json", "npm"), ("pnpm-lock.yaml", "pnpm"),
                                   ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("bun.lockb", "bun")]
                     if (project / f).exists()}
            require(len(locks) <= 1, "패키지 관리자 lockfile이 충돌합니다. packageManager를 명시하세요")
            manager = next(iter(locks), "npm")
        require(manager in MANAGERS, f"지원하지 않는 패키지 관리자: {manager}. {CONFIG}에 argv를 선언하세요")
        checks = [{"name": name, "argv": [manager, "run", name]} for name in ("test", "build")
                  if isinstance(scripts.get(name), str) and scripts[name].strip()]
        source = "package.json scripts"
    seen = set()
    for check in checks:
        require(isinstance(check, dict), "검사 항목은 객체여야 합니다")
        name, argv = check.get("name"), check.get("argv")
        require(isinstance(name, str) and name.strip() and name not in seen, "검사 이름은 비어 있지 않고 중복되지 않아야 합니다")
        require(isinstance(argv, list) and bool(argv) and all(isinstance(v, str) and v and '\0' not in v for v in argv),
                f"{name}: argv는 비어 있지 않은 문자열 목록이어야 합니다(셸 문자열 불가)")
        seen.add(name)
    selected_package = {k: package[k] for k in ("name", "type", "packageManager", "engines", "scripts") if k in package}
    # 계획 후 설정·의존성 잠금이 바뀌면 옛 명령으로 계속 진행하지 않는다.
    digest = hashlib.sha256()
    for name in ("package.json", CONFIG, "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"):
        p = project / name
        if p.is_file():
            digest.update(name.encode())
            with p.open("rb") as source_file:
                for block in iter(lambda: source_file.read(65536), b""):
                    digest.update(block)
    return {"source": source, "package": selected_package, "checks": checks, "fingerprint": digest.hexdigest()}


def git_state(project):
    def git(*args):
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True,
                              text=True, timeout=15, check=False)
    try:
        root = git("rev-parse", "--show-toplevel")
        if root.returncode:
            return {"status": "not_repository", "root": None, "changes": ""}
        top = Path(root.stdout.strip()).resolve()
        branch = git("branch", "--show-current")
        changes = git("status", "--short", "--untracked-files=normal", "--", ".")
        require(branch.returncode == changes.returncode == 0, "Git 상태 조회 실패")
        return {"status": "ok", "root": str(top), "branch": branch.stdout.strip(),
                "changes": changes.stdout, "scope": str(project)}
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"status": "unavailable", "root": None, "error": str(exc)}


def inspect_project(project):
    config = configuration(project)
    git = git_state(project)
    stop = Path(git["root"]) if git.get("root") else project
    ancestors = []
    current = project
    while True:
        ancestors.append(current)
        if current == stop or current == current.parent:
            break
        current = current.parent
    candidates = [p / "AGENTS.md" for p in reversed(ancestors)]
    candidates += [project / n for n in ("README.md", "README", ".nvmrc", ".node-version")]
    documents = [{"path": str(p), "name": p.name} for p in candidates if p.is_file()]
    env = environment(project)
    runtimes = {name: shutil.which(name, path=env["PATH"]) for name in ("node", "npm", "pnpm", "yarn", "bun")}
    files = [n for n in ("wrangler.toml", "wrangler.jsonc", "vite.config.js", "vite.config.ts",
                        "next.config.js", "next.config.mjs", "next.config.ts", "tsconfig.json", CONFIG)
             if (project / n).is_file()]
    return {"project": str(project), "config": config, "git": git, "documents": documents,
            "runtimes": runtimes, "config_files": files,
            "checks_available": bool(config["checks"])}


def history(project, since):
    """명시한 시각부터 고정 HEAD까지 전건 조회. 페이지 상한으로 이력을 자르지 않는다."""
    require(isinstance(since, str) and 'T' in since, "since는 시간대가 있는 ISO 날짜·시각이어야 합니다")
    try:
        start = datetime.fromisoformat(since.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError("since는 시간대가 있는 ISO 날짜·시각이어야 합니다") from exc
    require(start.tzinfo is not None, "since에 시간대를 명시하세요(예: +09:00)")

    def git(*args):
        result = subprocess.run(['git', '-C', str(project), *args], capture_output=True,
                                text=True, timeout=30, check=False)
        require(result.returncode == 0, f"Git 이력 조회 실패: {result.stderr.strip()[:500]}")
        return result.stdout

    head = git('rev-parse', '--verify', 'HEAD').strip()
    # --since와 달리 날짜가 역전된 커밋도 탐색한다. -z와 필드 NUL로 제목의 줄/탭을 보존한다.
    raw = git('log', head, f'--since-as-filter={start.isoformat()}',
              '--format=%H%x00%cI%x00%s', '-z', '--', '.')
    fields = raw.removesuffix('\0').split('\0') if raw else []
    require(len(fields) % 3 == 0, "Git 이력 응답의 필드 수가 잘못되었습니다")
    items = [{'commit': fields[i], 'committed_at': fields[i + 1], 'subject': fields[i + 2]}
             for i in range(0, len(fields), 3)]
    return {'project': str(project), 'since': start.isoformat(), 'head': head,
            'items': items, 'count': len(items), 'source_complete': True,
            'scope': '지정 폴더의 커밋된 변경; 날짜는 committer 기준',
            'git': git_state(project)}


def plan(project, names):
    require(isinstance(names, list) and bool(names) and all(isinstance(n, str) and n for n in names),
            "checks는 비어 있지 않은 검사 이름 목록이어야 합니다")
    require(len(set(names)) == len(names), "검사 이름 중복")
    config = configuration(project)
    available = {c["name"]: c for c in config["checks"]}
    missing = [n for n in names if n not in available]
    require(not missing, f"검사 설정 없음: {', '.join(missing)}. package.json 또는 {CONFIG}에 선언하세요")
    env = environment(project)
    items = [{"name": n, "argv": resolve_command(available[n]["argv"], project, env)} for n in names]
    return {"project": str(project), "items": items, "fingerprint": config["fingerprint"]}


def stop_process(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def run_check(project, name, timeout, fingerprint):
    require(type(timeout) in (int, float) and 0 < timeout <= 600, "timeout은 0초 초과·600초 이하입니다")
    selected = plan(project, [name])
    require(isinstance(fingerprint, str) and fingerprint == selected["fingerprint"],
            "검사 계획 이후 설정이 바뀌었습니다. 다시 계획하세요")
    row = selected["items"][0]
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log = LOG_ROOT / (uuid.uuid4().hex + ".log")
    t0 = time.monotonic()
    status, exit_code = "failed", None
    with log.open("wb") as output:
        try:
            process = subprocess.Popen(row["argv"], cwd=project, env=environment(project),
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != "nt")
            try:
                exit_code = process.wait(timeout=timeout)
                status = "passed" if exit_code == 0 else "failed"
            except subprocess.TimeoutExpired:
                stop_process(process)
                status = "timeout"
        except OSError as exc:
            output.write(str(exc).encode())
            status = "unavailable"
    size = log.stat().st_size
    with log.open("rb") as source:
        source.seek(max(0, size - 8000))
        tail = source.read().decode("utf-8", errors="replace")
    return {**row, "ok": status == "passed", "status": status, "exit_code": exit_code,
            "seconds": round(time.monotonic() - t0, 3), "log_path": str(log),
            "output_tail": mask_secrets(tail), "output_truncated": size > 8000, "output_bytes": size}


def execute(args):
    require(isinstance(args, dict), "입력은 JSON 객체여야 합니다")
    project = project_path(args.get("project"))
    op = args.get("op")
    if op == "inspect":
        return inspect_project(project)
    if op == "history":
        return history(project, args.get('since'))
    if op == "plan":
        return plan(project, args.get("checks", ["test", "build"]))
    if op == "run":
        return run_check(project, args.get("name"), args.get("timeout", 120), args.get("fingerprint"))
    raise ValueError("op는 inspect/history/plan/run 중 하나여야 합니다")


if __name__ == "__main__":
    try:
        result = execute(json.load(sys.stdin))
        print(mask_secrets(json.dumps(result, ensure_ascii=False)))
    except (ValueError, OSError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"success": False, "error": mask_secrets(str(exc))}, ensure_ascii=False))
        sys.exit(1)
