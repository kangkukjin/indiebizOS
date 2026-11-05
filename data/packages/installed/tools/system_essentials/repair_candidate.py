"""수리 사본의 기준·검사·적용 바이트. 원장은 신뢰된 호스트만 쓴다."""
import base64
import hashlib
import json
import os
import stat
import subprocess
import shutil
from contextlib import contextmanager
from pathlib import Path

VERSION = 1
from program_boundary import WORKSPACE_PRIVATE

PRIVATE = tuple(WORKSPACE_PRIVATE)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def target(root, relative, *, read_only=False):
    root = Path(root).resolve()
    rel = Path(relative)
    from program_boundary import readable_runtime_state
    private = any(relative == p or relative.startswith(p + '/') for p in PRIVATE)
    if (rel.is_absolute() or ".." in rel.parts
            or private and not (read_only and readable_runtime_state(relative))):
        raise ValueError("수리 경로가 보호 영역 또는 사본 밖입니다: " + relative)
    path = root / rel
    if not path.resolve().is_relative_to(root):
        raise ValueError("수리 경로의 심볼릭 링크가 사본 밖을 가리킵니다: " + relative)
    # 파일뿐 아니라 부모 링크도 거절한다. 적용 시 부모를 바꿔 다른 곳에 쓰지 않는다.
    if any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
        raise ValueError("수리 변경에 심볼릭 링크를 사용할 수 없습니다: " + relative)
    return path


def fingerprint(path):
    path = Path(path)
    if not path.exists():
        return None
    if path.is_symlink():
        return {"link": os.readlink(path)}
    if not path.is_file():
        raise ValueError("일반 파일이 아닌 수리 대상: " + str(path))
    return {"sha": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": stat.S_IMODE(path.stat().st_mode)}


def inventory(root, artifacts=()):
    p = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                       cwd=root, capture_output=True, timeout=120)
    if p.returncode:
        raise ValueError("수리 사본의 파일 목록을 읽지 못했습니다")
    names = {os.fsdecode(x) for x in p.stdout.split(b"\0") if x}
    names.update(name for name in artifacts if target(root, name).exists())
    return {name: fingerprint(Path(root) / name) for name in sorted(names)
            if not any(name == p or name.startswith(p + "/") for p in PRIVATE)
            and not set(Path(name).parts) & {"__pycache__", ".pytest_cache", "node_modules", ".venv"}}


def register_artifacts(repo, session, paths):
    """명시한 outputs 파일만 적용 대상에 포함한다. 키·기존 폴더 전체는 복제하지 않는다."""
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        raise ValueError("artifact_paths는 outputs/ 아래 상대 파일 경로 목록이어야 합니다")
    if session.get("status") != "staging":
        raise ValueError("예약·적용 이후에는 산출물 목록을 바꿀 수 없습니다")
    registered = set(session.get("artifact_paths", []))
    wt = Path(repo) / session["worktree"]
    additions = {}
    for rel in paths:
        from program_boundary import artifact_path
        if not artifact_path(rel):
            raise ValueError("산출물은 outputs/ 아래 정규 상대 경로만 지원합니다: " + rel)
        live, staged = target(repo, rel), target(wt, rel)
        if not staged.is_file() or staged.stat().st_nlink != 1:
            raise ValueError("사본에 완성된 일반 산출물 파일이 필요합니다: " + rel)
        if rel in session["baseline"] and rel not in registered:
            raise ValueError("Git 추적 파일은 일반 수리 델타로 적용합니다: " + rel)
        if rel not in registered:
            additions[rel] = fingerprint(live)
    for rel, before in additions.items():
        if before is not None:
            session["baseline"][rel] = before
    removed = registered - set(paths)
    for rel in removed:
        session["baseline"].pop(rel, None)
    if additions or removed:
        session["artifact_paths"] = sorted(set(paths))
        invalidate(session)


def artifact_manifest(session):
    """평가자는 사본의 내용·배치 계획을, 완료자는 적용된 바이트를 확인한다."""
    return [{"path": r["rel"], "candidate": r["candidate"], "before": r["base"],
             "phase": "apply", "git_commit": False}
            for r in session.get("files", {}).values()
            if r["rel"] in session.get("artifact_paths", [])]


def artifact_review_context(session):
    return {"workspace_artifacts": artifact_manifest(session), "artifact_policy":
            "workspace_artifacts는 같은 고정 묶음으로 실제 대상에 배치될 파일이다. "
            "이 단계에서는 사본의 내용·권한과 명시된 배치 경로를 검사한다. "
            "적용 전 실제 대상 변경을 요구하지 않는다. 전체 완료는 적용 뒤 같은 바이트인지 별도로 대조한다. "
            "명시되지 않은 파일·설정·키의 변경이나 복사는 이 계획에 포함되지 않는다."}


def initialize(repo, session):
    wt = Path(repo) / session["worktree"]
    session["baseline"] = inventory(wt)
    session["candidate_version"] = VERSION
    session["root_task_id"] = session.get("root_task_id") or session["key"]
    session["execution_checks"] = []
    session["repository_baseline"] = repository_baseline(repo)
    from execution_turn import current
    if current() is not None:
        session['program_policy'] = 1


def repository_baseline(repo):
    """Git 메타데이터는 사본 자식 대신 준비 서비스가 조회·갱신한다. 작업 파일은 바꾸지 않는다."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                              timeout=15, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    local = git("rev-parse", "HEAD").stdout.strip()
    result = {"live_head": local, "source": "canonical_working_tree", "includes_local_changes": True,
              "fetch_owner": "preparation_service", "fetch_status": "no_origin"}
    if git("remote", "get-url", "origin").returncode == 0:
        try:
            result["fetch_status"] = "ok" if git("fetch", "origin").returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            result["fetch_status"] = "timeout"
        remote = git("rev-parse", "--verify", "origin/main")
        if remote.returncode == 0:
            result["origin_main"] = remote.stdout.strip()
            count = git("rev-list", "--count", local + "..origin/main")
            result["behind_origin_main"] = int(count.stdout.strip()) if count.returncode == 0 else None
    result["hint"] = ("사본은 정본의 코드와 미커밋 변경에서 준비했습니다. git fetch는 준비 서비스가 소유합니다. "
                      "fetch_status=ok일 때만 원격 최신성을 확인한 것이며 사본 셸에서 fetch를 반복하지 마세요.")
    return result


def collect(repo, session):
    """실제 사본 델타를 수집한다. 시작 시 가져온 타인의 미커밋 변경은 델타가 아니다."""
    baseline = session.get("baseline")
    if baseline is None:
        raise ValueError("기준 지문 없는 옛 수리 사본입니다. 새 기준으로 다시 준비해야 합니다")
    root = Path(repo).resolve()
    wt = root / session["worktree"]
    if any(not target(wt, p).is_file() for p in session.get("artifact_paths", [])):
        raise ValueError("등록된 배치 산출물이 사본에서 사라졌습니다")
    current = inventory(wt, session.get("artifact_paths", []))
    for rel, receipt in session.get('managed_files', {}).items():
        if current.get(rel) != receipt['fingerprint']:
            raise PermissionError('공식 관리 연산 이후 원장이 직접 변경됐습니다: ' + rel)
    for rel, expected in session.get('derived_files', {}).items():
        if current.get(rel) != expected:
            raise PermissionError('호스트 빌드 후 파생 파일이 변경됐습니다: ' + rel)
    files = {}
    for rel in sorted(set(baseline) | set(current)):
        before, after = baseline.get(rel), current.get(rel)
        if before == after:
            continue
        live, staged = target(root, rel), target(wt, rel)
        if (before or {}).get("link") or (after or {}).get("link"):
            raise ValueError("심볼릭 링크 변경은 지원하지 않습니다: " + rel)
        if staged.exists() and staged.stat().st_nlink != 1:
            raise ValueError("하드 링크 변경은 지원하지 않습니다: " + rel)
        files[str(live)] = {"rel": rel, "staged": str(staged),
                            "op": "write" if after else "delete", "existed": bool(before),
                            "base_sha": (before or {}).get("sha"), "base": before,
                            "candidate": after}
    if session.get('program_policy'):
        import importlib.util
        spec = importlib.util.spec_from_file_location('repair_program_derived', Path(__file__).with_name('program_derived.py'))
        derived = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(derived)
        derived.accept(__import__('types').SimpleNamespace(**globals()), repo, session,
                       current, [r['rel'] for r in files.values()])
    from task_repair import check_delta
    check_delta(session, [r['rel'] for r in files.values()], current=current)
    session["files"] = files
    if session.get('program_policy'):
        from program_dependencies import analyse, with_derived_inputs
        token = digest(current)
        if session.get('program_analysis_hash') != token:
            from program_boundary import candidate_plan
            ownership = candidate_plan(session, current)
            scope = analyse(wt, [r['rel'] for r in files.values()], ownership=ownership)
            scope = with_derived_inputs(wt, scope, session.get('derived_files', {}))
            if scope['protected'] or scope['unmanaged']:
                raise PermissionError('일반 프로그램 수리 범위 밖 변경: ' +
                                      ', '.join([*scope['protected'], *scope['unmanaged']]))
            session.update(program_scope=scope, program_analysis_hash=token)
    # Builders discover source with git ls-files. Only the host may publish
    # validated new candidate paths to this worktree's index; the sandbox must
    # never gain access to the shared repository metadata for git add.
    added = [r['rel'] for r in files.values() if r['base'] is None and r['op'] == 'write']
    if added and (wt / '.git').exists():
        listed = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '-z', '--', *added],
                                cwd=wt, capture_output=True, check=True, timeout=30)
        untracked = [os.fsdecode(p) for p in listed.stdout.split(b'\0') if p]
        if untracked:
            subprocess.run(['git', 'add', '--intent-to-add', '--', *untracked], cwd=wt,
                           capture_output=True, check=True, timeout=30)
    from execution_situation import emit, current as current_situation
    if current_situation():
        emit({'kind': 'code_candidate', 'workspace': str(wt.resolve()), 'session': session.get('id')},
             'version', {}, source='repair_check', subject_revision=digest(current))
    return current


def register_derived(repo, session, gate):
    """Only a successful host-owned build can add exact derived bytes to a scope."""
    if gate and gate.get('passed') and gate.get('gate') == 'body_bundle':
        paths = gate.get('derived_paths', [])
        if any(p != 'data/bodies/android.engine.json' for p in paths):
            raise ValueError('알 수 없는 몸 번들 산출물')
        session.setdefault('derived_files', {}).update({
            p: fingerprint(target(Path(repo) / session['worktree'], p)) for p in paths})


def conflicts(repo, session, current=None):
    """덮어쓸 파일의 동시 변경만 충돌이다. 다른 작업의 변경은 적용을 막지 않는다."""
    paths = {r['rel'] for r in session.get('files', {}).values()}
    baseline = session['baseline']
    return sorted(p for p in paths if fingerprint(target(repo, p)) != baseline.get(p))


def invalidate(session):
    session.pop("readiness", None)
    session.pop("sealed", None)


def refresh(repo, session):
    """준비 이전에만 미수정 의존 파일을 동기화한다. 수리 델타와 충돌하면 보존한다."""
    current = collect(repo, session)
    live = inventory(repo, session.get("artifact_paths", []))
    baseline = session["baseline"]
    changed = [p for p in set(live) | set(baseline) if live.get(p) != baseline.get(p)]
    collisions = [p for p in changed if current.get(p) not in (baseline.get(p), live.get(p))]
    if collisions:
        raise ValueError("정본과 사본 모두 수정한 파일의 충돌: " + ", ".join(sorted(collisions)))
    wt = Path(repo) / session["worktree"]
    for rel in changed:
        dst, src = target(wt, rel), target(repo, rel)
        if live.get(rel) is None:
            dst.unlink(missing_ok=True)
            baseline.pop(rel, None)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            baseline[rel] = live[rel]
    if changed:
        invalidate(session)
    return collect(repo, session)


def ignored_source_files(worktree):
    """검사에는 쓰였지만 Git 무시 규칙 때문에 적용 묶음에서 빠질 코드는 거절한다."""
    scopes = ["backend", "scripts", "frontend/src", "data/packages/installed/tools",
              "data/ibl_nodes_src", "data/scripts"]
    result = subprocess.run(["git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", *scopes],
                            cwd=worktree, capture_output=True, check=True, timeout=60)
    caches = {"__pycache__", ".pytest_cache", ".hypothesis", "node_modules", ".venv"}
    return [os.fsdecode(name) for name in result.stdout.split(b"\0") if name
            and Path(os.fsdecode(name)).suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".yaml", ".yml"}
            and not set(Path(os.fsdecode(name)).parts) & caches]


def seal(repo, session, checks, decision, criteria):
    hidden = ignored_source_files(Path(repo) / session["worktree"])
    if hidden:
        raise ValueError("적용 묶음에서 누락된 무시 대상 소스: " + ", ".join(hidden[:12]))
    current = collect(repo, session)
    if conflicts(repo, session, current):
        raise ValueError("정본 기준이 변경됐습니다. 사본에 동기화하고 다시 검증하세요")
    if not session["files"]:
        raise ValueError("반영할 수리 델타가 없습니다")
    payload = {}
    for rec in session["files"].values():
        data = Path(rec["staged"]).read_bytes() if rec["op"] != "delete" else None
        if data is not None and hashlib.sha256(data).hexdigest() != rec["candidate"]["sha"]:
            raise ValueError("고정 중 사본이 변경됐습니다")
        payload[rec["rel"]] = {"before": rec["base"], "after": rec["candidate"],
                               "before_data": base64.b64encode(Path(repo, rec["rel"]).read_bytes()).decode()
                               if rec["base"] else None,
                               "data": base64.b64encode(data).decode() if data is not None else None}
        if rec["rel"] in session.get("artifact_paths", []):
            payload[rec["rel"]]["artifact"] = True
    for rel, item in payload.items():
        if item["before_data"] is not None and hashlib.sha256(base64.b64decode(item["before_data"])).hexdigest() != item["before"]["sha"]:
            raise ValueError("고정 중 정본이 변경됐습니다: " + rel)
    session["sealed"] = payload
    session["readiness"] = {"version": 2 if session.get("repair_policy") == 2 else VERSION,
                            "candidate_hash": digest({p: item['after'] for p, item in payload.items()}),
                            "bundle_hash": digest(payload), "criteria": criteria,
                            "criteria_hash": digest(criteria), "checks": checks,
                            "decision": decision, "owner": session.get("owner"),
                            "root_task_id": session["root_task_id"],
                            "activation_commands": session.get("activation_commands", {})}


def validate(repo, session):
    from task_repair import check_delta, parent_of
    parent_of(session, repo)
    ready, payload = session.get("readiness") or {}, session.get("sealed") or {}
    expected_version = 2 if session.get("repair_policy") == 2 else VERSION
    if (ready.get("version") != expected_version or not payload
            or ready.get("decision", {}).get("status") != "APPROVED"
            or ready.get("bundle_hash") != digest(payload)
            or ready.get("criteria_hash") != digest(ready.get("criteria"))
            or ready.get("owner") != session.get("owner")
            or ready.get("root_task_id") != session.get("root_task_id")):
        raise ValueError("유효한 사본 준비 판정이 없습니다")
    cancelled = Path(repo) / "data/system_ai_state/repair_continuations" / (session["root_task_id"] + ".cancel")
    if cancelled.exists():
        raise ValueError("취소된 수리입니다")
    if ignored_source_files(Path(repo) / session["worktree"]):
        raise ValueError("검증 이후 적용 묶음에 없는 소스가 생겼습니다")
    current = inventory(Path(repo) / session["worktree"], session.get("artifact_paths", []))
    check_delta(session, payload.keys(), current=current)
    if session.get('program_policy'):
        from program_boundary import candidate_plan
        ownership = candidate_plan(session, current)
        if ownership['protected'] or ownership['unmanaged']:
            raise PermissionError('적용 후보의 변경 권한이 유효하지 않습니다')
    # 봉인한 게시 바이트와 실제 수정분을 대조한다. 설치 환경·무관한 파일의
    # 지문을 시험 유효성의 대리 기준으로 쓰지 않는다.
    delta = {p: current.get(p) for p in set(current) | set(session['baseline'])
             if current.get(p) != session['baseline'].get(p)}
    if delta != {p: item['after'] for p, item in payload.items()}:
        raise ValueError("봉인 이후 사본의 수정분이 변경됐습니다. 다시 apply 하세요")
    drift = conflicts(repo, session, current)
    if drift:
        raise ValueError("정본 충돌: " + ", ".join(sorted(drift)[:12]))
    plan = []
    for rel, item in payload.items():
        path = target(repo, rel)
        data = base64.b64decode(item["data"], validate=True) if item["data"] is not None else None
        if data is not None and hashlib.sha256(data).hexdigest() != item["after"]["sha"]:
            raise ValueError("고정된 수리 바이트가 손상됐습니다")
        if fingerprint(path) != item["before"]:
            raise ValueError("적용 직전 정본 충돌: " + rel)
        plan.append((path, data, item))
    return plan


def commit(repo, session, body):
    """기존 각인 실행기에 수리 델타만 전달한다. 공유 인덱스/시작 미커밋 변경은 보존한다."""
    import tempfile
    if (session.get("commit") or {}).get("success"):
        return session["commit"]
    if session.get("status") != "applied" or not session.get("verified"):
        return {"success": False, "error": "적용 확인 전에는 커밋하지 않습니다"}
    payload = session.get("sealed") or {}
    if not payload or digest(payload) != (session.get("readiness") or {}).get("bundle_hash"):
        return {"success": False, "error": "커밋할 검증 묶음이 없습니다"}
    for rel, item in payload.items():
        if fingerprint(target(repo, rel)) != item["after"]:
            return {"success": False, "error": "적용 후 정본 변경: " + rel}
    payload = {rel: item for rel, item in payload.items() if not item.get("artifact")}
    if not payload:
        return {"success": True, "artifacts_only": True,
                "bundle_hash": session["readiness"]["bundle_hash"]}
    marker = "Repair-Attempt: " + session["root_task_id"] + ":" + session["readiness"]["bundle_hash"]
    found = subprocess.run(["git", "log", "-1", "--format=%H", "--fixed-strings", "--grep=" + marker],
                           cwd=repo, capture_output=True, text=True, timeout=30)
    if found.returncode == 0 and found.stdout.strip():
        return {"success": True, "commit": found.stdout.strip(), "recovered": True}
    with tempfile.TemporaryDirectory(prefix="repair-commit-") as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        def git(*args, data=None):
            return subprocess.run(["git", *args], cwd=repo, env=env, input=data,
                                  capture_output=True, check=True, timeout=30).stdout
        # Git 자체가 경로·인용·바이너리 패치를 만든다. no-index 임시 폴더 접두를
        # 손으로 바꾸면 추가/삭제의 diff 헤더가 서로 다른 경로로 남는다.
        trees = []
        for field, state in (("before_data", "before"), ("data", "after")):
            git("read-tree", "--empty")
            for rel, item in payload.items():
                if item[field] is None:
                    continue
                data = base64.b64decode(item[field], validate=True)
                blob = git("hash-object", "-w", "--stdin", data=data).decode().strip()
                mode = "100755" if item[state]["mode"] & 0o111 else "100644"
                git("update-index", "--add", "--cacheinfo", mode, blob, rel)
            trees.append(git("write-tree").decode().strip())
        patch = git("diff", "--binary", "--no-renames", *trees).decode()
        result = body.op_commit({"paths": list(payload), "message": "수리 사본 검증 후 반영\n\n" + marker},
                                index_patch=patch, trusted_root=str(repo))
        if result.get("success"):
            result["commit"] = result["items"][0]["커밋"]
        return result


def active_generation_bytes(base, session):
    """활성 세대(제어자 state 의 generation_dir)가 봉인 묶음과 같은 바이트인지(G4 '활성 바이트 대조').
    반환 (verdict, detail): verdict ∈ matched | mismatch | unknown."""
    if session.get('program_activation'):
        from program_versions import activation_matches
        from runtime_utils import get_code_root
        matched = activation_matches(base, get_code_root(), session)
        return ('matched', '프로그램 활성 판본 일치') if matched else ('mismatch', '프로그램 활성 판본 미확인')
    from restart_protocol import control_dir, read_json
    state = read_json(control_dir(base) / "state.json", {}) or {}
    gen_dir = state.get("generation_dir")
    if not gen_dir or not Path(gen_dir).is_dir():
        return "unknown", "활성 세대 기록이 없습니다(제어자 없음 또는 옛 체계)"
    manifest = read_json(Path(gen_dir) / "manifest.json", {}) or {}
    files = manifest.get("files") or {}
    mismatch, outside = [], []
    for rel, item in (session.get("sealed") or {}).items():
        if item.get("artifact"):
            continue
        if rel not in files:
            if item.get("after") is None:
                continue  # 삭제는 세대 사본에도 없어야 맞다
            outside.append(rel)
            continue
        if item.get("after") is None or files[rel] != item["after"]["sha"]:
            mismatch.append(rel)
    if mismatch:
        return "mismatch", "활성 세대의 바이트가 수리 델타와 다릅니다: " + ", ".join(mismatch[:8])
    if outside:
        return "unknown", "세대 실행 입력 밖의 경로라 활성 대조 대상이 아닙니다: " + ", ".join(outside[:8])
    return "matched", "활성 세대 " + str(manifest.get("generation")) + " 이 수리 델타와 같은 바이트입니다"


def freshness(repo, session):
    """key 조회에서 사본의 현재 재고 해시를 다시 센다 — 검증 뒤 사본이 바뀌었으면 verified 는
    현재 후보의 것이 아니다(긴문장 98회차 L98-1: 제안 뒤 사본을 바꿔도 status 가 verified:true·
    files 1건을 그대로 보였다). files 도 현재 델타로 갱신한다(범위 밖 변경이 드러나게)."""
    stored = session.get("candidate_hash")
    try:
        now = digest(collect(repo, session))
    except (ValueError, OSError) as exc:
        return {"candidate_hash": stored, "candidate_hash_now": None, "verified_current": None,
                "verified_note": "현재 사본 해시를 세지 못했습니다: " + str(exc)[:200]}
    out = {"candidate_hash": stored, "candidate_hash_now": now, "verified_current": now == stored,
           "files": [r.get("rel") for r in (session.get("files") or {}).values()]}
    if now != stored:
        out["verified"] = False
        out["verified_note"] = ("검증 뒤 사본이 바뀌었습니다 — 기계 검증 영수증은 candidate_hash 판본의 것입니다. "
                                "현재 후보는 미검증이며 apply 가 다시 검증하거나 새로 propose 하세요.")
    return out


def candidate_hash(repo, session):
    """검증 직후 사본 재고 해시 — 제안 영수증을 판본에 묶는다(readiness.candidate_hash 와 같은 계산)."""
    try:
        return digest(collect(repo, session))
    except (ValueError, OSError):
        return None


def text_diff(repo, rel, staged_abs):
    """미추적 대상은 사본의 `git diff` 가 비어 있다(98회차 L98-3: 독립 AI 가 "diff 빈 문자열" 을 스스로 보고).
    라이브 원문(없으면 신규)과 사본 본문을 텍스트로 대조한다."""
    import difflib
    live = Path(repo) / rel
    try:
        before = live.read_text(encoding="utf-8").splitlines(True) if live.is_file() else []
        after = Path(staged_abs).read_text(encoding="utf-8").splitlines(True)
    except (OSError, UnicodeDecodeError):
        return ""
    return "".join(difflib.unified_diff(before, after, ("a/" + rel) if before else "/dev/null", "b/" + rel))


@contextmanager
def locked(repo, key, *, nonblocking=False):
    """동시 적용/편집 진입을 직렬화한다. OS 미지원이면 쓰기 경로를 열지 않는다."""
    import fcntl
    path = Path(repo) / "data/system_ai_state/repair_sessions" / (key + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def activation_plan(session, request):
    """명시적 apply는 실패한 읽기 확인을 재시도하며, 확인 명령도 고칠 수 있다."""
    applied = session.get('status') == 'applied'
    commands = dict(((session.get('readiness') or {}).get('activation_commands') if applied else
                     session.get('activation_commands')) or {})
    records = session.setdefault('activation_checks', {})
    for field in ('verify_cmd', 'active_verify_cmd'):
        command = str(request[field] or '').strip() if field in request else commands.get(field, '')
        record = records.get(field)
        if record and (record.get('state') == 'failed' or command != commands.get(field, '')):
            if record.get('state') == 'running':
                raise ValueError('진행 중인 활성 확인의 결과를 먼저 회수하세요: ' + field)
            session.setdefault('activation_history', {}).setdefault(field, []).append(records.pop(field))
        commands[field] = command
    session['activation_commands'] = commands
    if applied:
        session.setdefault('readiness', {})['activation_commands'] = dict(commands)
    return commands


def activation(repo, session, field, command, save):
    from repair_live_probe import activation_check
    from red_apply import _run_post_verify
    records = session.setdefault('activation_checks', {})
    def persist(record):
        records[field] = record
        save(repo, session)
    return activation_check(repo, records.get(field), command, persist, _run_post_verify)
