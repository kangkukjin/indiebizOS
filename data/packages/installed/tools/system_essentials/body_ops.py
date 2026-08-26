"""system_essentials 몸 변화 회상 층 ([self:body] — 2026-08-21 신설)

몸(이 코드가 사는 저장소의 파일들)의 변화 이력을 git 원장에서 읽어 items 통화로 낸다.
전 op 읽기 전용 — 원장은 git 이 이미 쓰고 있고, 이 어휘는 **회상 통로**다.
(설계 배경: 08-05 층 분리 같은 몸 개조가 회상 불가능해 grep 방언 사건이 6주 잠복했다.
 몸이 바뀌면 몸에 대한 가정이 깨진다 — 변화 자체가 연상 가능한 기억이어야 한다.)

- changes(기본): 최근 파일 단위 변화 (미커밋 작업분 포함)
- log: 커밋 단위 이력 ("내가 뭘 했나")
- file: 한 파일의 일생 — git --follow 로 생성·수정·이동(이름변경)을 관통 추적
- trajectory: 한 run 의 요청·IBL·검증·부작용 핵심 사건 — 원문이 아닌 hash/ref 순번 원장
- diff: 실제 바뀐 줄 — 미커밋 작업분(기본)·한 커밋·구간(ref..HEAD). 파일별 items + 본문
  (2026-08-21 추가: 7일간 Bash git 서브커맨드 1위가 `git diff` 95회 — 회상 통로가 "무엇이"
   까지만 답하고 "어떻게"는 못 답해 셸로 떨어지던 자리)
"""
import os
import shutil
import subprocess

_TIMEOUT_S = 20
_DEFAULT_DAYS = 7
_MAX_DAYS = 365
_DEFAULT_LIMIT = 200
_MAX_LIMIT = 1000
_SEP = "\x01"  # 커밋 요지에 | 가 흔해 제어문자 구분자 (%x01)

_STATUS_KO = {"A": "추가", "M": "수정", "D": "삭제", "R": "이동", "C": "복사", "T": "속성변경"}


def _find_git():
    p = shutil.which("git")
    if p:
        return p
    for cand in ("/usr/bin/git", "/opt/homebrew/bin/git", "/usr/local/bin/git"):
        if os.path.exists(cand):
            return cand
    return None


def _repo_root():
    """이 코드가 사는 저장소의 루트 = 몸. 파일 위치에서 .git 조상 탐색."""
    d = os.path.dirname(os.path.abspath(__file__))
    while d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return None


def _git(root, args):
    """git 실행 — (stdout, None) 또는 (None, 오류문). 침묵 실패 금지."""
    git = _find_git()
    if not git:
        return None, "git 실행파일을 찾을 수 없습니다 (이 몸에는 git 이 없음)."
    try:
        proc = subprocess.run([git, "-C", root] + args, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"git 실행 실패: {e}"
    if proc.returncode != 0:
        return None, f"git 오류 (exit {proc.returncode}): {(proc.stderr or '').strip()[:300]}"
    return proc.stdout, None


def _area_of(path):
    """파일의 영역(층) — table:groupby 용 열. backend 는 층 디렉토리까지."""
    parts = path.split("/")
    if not parts:
        return ""
    if parts[0] == "backend" and len(parts) > 2:
        return "backend/" + parts[1]
    if parts[0] == "data" and len(parts) > 2:
        return "data/" + parts[1]
    return parts[0]


def _clamp(tool_input, key, default, maximum, notes):
    """정수 파라미터 상한 — 조용히 깎지 않는다(silent-clamp 금지): 깎으면 신고."""
    try:
        v = int(tool_input.get(key, default))
    except (TypeError, ValueError):
        v = default
    if v > maximum:
        notes.append(f"{key} {v}→{maximum} (상한)")
        v = maximum
    return max(1, v)


def _guard_root():
    root = _repo_root()
    if root is None:
        return None, {"success": False,
                      "message": "이 몸은 git 저장소가 아닙니다 — 변화 원장이 없어 회상할 수 없습니다."}
    return root, None


def _parse_name_status(stdout):
    """`--pretty=C%x01h%x01ad%x01s --name-status` 출력 → 파일 단위 행 목록."""
    rows = []
    commit = date = subject = None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        if line.startswith("C" + _SEP):
            _, commit, date, subject = line.split(_SEP, 3)
            continue
        parts = line.split("\t")
        code = parts[0][:1]
        status = _STATUS_KO.get(code, parts[0])
        if code in ("R", "C") and len(parts) >= 3:
            old, new = parts[1], parts[2]
            rows.append({"파일": new, "상태": status, "이전경로": old, "영역": _area_of(new),
                         "시각": date, "요지": subject, "커밋": commit})
        elif len(parts) >= 2:
            fp = parts[1]
            rows.append({"파일": fp, "상태": status, "영역": _area_of(fp),
                         "시각": date, "요지": subject, "커밋": commit})
    return rows


_LOG_FMT = ["--date=format:%Y-%m-%dT%H:%M", f"--pretty=format:C{_SEP}%h{_SEP}%ad{_SEP}%s"]


def _scope_of(tool_input, root):
    """path 스코프 정규화 — 저장소 밖이면 오류문 반환."""
    raw = (tool_input.get("path") or "").strip()
    if not raw:
        return None, None
    p = os.path.expanduser(raw)
    if os.path.isabs(p):
        rel = os.path.relpath(p, root)
        if rel.startswith(".."):
            return None, f"저장소 밖 경로입니다: {raw} (몸={root})"
        return rel, None
    return raw.rstrip("/"), None


def op_changes(tool_input):
    """최근 파일 단위 변화 — 커밋된 것 + 미커밋 작업분."""
    root, err = _guard_root()
    if err:
        return err
    notes = []
    days = _clamp(tool_input, "days", _DEFAULT_DAYS, _MAX_DAYS, notes)
    limit = _clamp(tool_input, "limit", _DEFAULT_LIMIT, _MAX_LIMIT, notes)
    scope, serr = _scope_of(tool_input, root)
    if serr:
        return {"success": False, "message": serr}

    # ① 미커밋 작업분 — "지금 뭐 만지고 있나"도 몸 변화다
    rows = []
    porcelain, gerr = _git(root, ["status", "--porcelain"] + (["--", scope] if scope else []))
    if gerr:
        return {"success": False, "message": gerr}
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        fp = line[3:].strip().strip('"')
        if " -> " in fp:  # 미커밋 rename
            fp = fp.split(" -> ", 1)[1]
        rows.append({"파일": fp, "상태": "미커밋", "영역": _area_of(fp),
                     "시각": "", "요지": "작업 중 (커밋 전)", "커밋": ""})
    uncommitted = len(rows)

    # ② 커밋된 변화 (파일 단위, rename 감지 -M)
    args = ["log", f"--since={days} days ago", "--name-status", "-M"] + _LOG_FMT
    if scope:
        args += ["--", scope]
    stdout, gerr = _git(root, args)
    if gerr:
        return {"success": False, "message": gerr}
    rows += _parse_name_status(stdout)

    total = len(rows)
    truncated = total > limit
    rows = rows[:limit]
    scope_txt = f" (스코프 {scope})" if scope else ""
    text = f"최근 {days}일 몸 변화{scope_txt}: 파일 변경 {total}건 (미커밋 {uncommitted}건)"
    if truncated:
        text += f" — {limit}건만 표시 (limit 로 조절)"
    if notes:
        text += " · " + ", ".join(notes)
    return {"success": True, "items": rows, "total": total, "truncated": truncated, "text": text}


def op_log(tool_input):
    """커밋 단위 이력 — '무슨 일을 했나'."""
    root, err = _guard_root()
    if err:
        return err
    notes = []
    days = _clamp(tool_input, "days", _DEFAULT_DAYS, _MAX_DAYS, notes)
    limit = _clamp(tool_input, "limit", _DEFAULT_LIMIT, _MAX_LIMIT, notes)
    scope, serr = _scope_of(tool_input, root)
    if serr:
        return {"success": False, "message": serr}
    args = ["log", f"--since={days} days ago", "--shortstat"] + _LOG_FMT
    if scope:
        args += ["--", scope]
    stdout, gerr = _git(root, args)
    if gerr:
        return {"success": False, "message": gerr}
    rows = []
    for line in stdout.splitlines():
        if line.startswith("C" + _SEP):
            _, commit, date, subject = line.split(_SEP, 3)
            rows.append({"커밋": commit, "시각": date, "요지": subject, "파일수": 0})
        elif "changed" in line and rows:
            # " 3 files changed, 162 insertions(+), 3 deletions(-)"
            try:
                rows[-1]["파일수"] = int(line.strip().split(" ", 1)[0])
            except ValueError:
                pass
    total = len(rows)
    truncated = total > limit
    rows = rows[:limit]
    text = f"최근 {days}일 커밋 {total}건" + (f" — {limit}건만 표시" if truncated else "")
    if notes:
        text += " · " + ", ".join(notes)
    return {"success": True, "items": rows, "total": total, "truncated": truncated, "text": text}


def _join_episode_requests(root, rows):
    """원장 task ↔ episode_log.task_id 조인 — "이 파일 왜 바뀌었나"의 답(요청 원문).

    2026-08-21 개통: 그 전엔 시각창 추정 조인뿐이라 동시 실행에서 정확히 깨졌다.
    표시분(limit 이후) task 만 한 번에 조회 — 옛 DB(컬럼 부재)·조인 실패는 조용히
    생략(회상은 관측 — 원장 표시를 절대 깨지 않는다)."""
    tasks = sorted({r["작업"] for r in rows if r.get("작업")})
    if not tasks:
        return
    try:
        import sqlite3
        conn = sqlite3.connect(os.path.join(root, "data", "world_pulse.db"))
        try:
            q = ",".join("?" * len(tasks))
            found = dict(conn.execute(
                f"SELECT task_id, user_message FROM episode_log "
                f"WHERE task_id IN ({q}) AND task_id != ''", tasks))
        finally:
            conn.close()
        for r in rows:
            msg = found.get(r.get("작업") or "")
            if msg:
                r["요청"] = (msg or "")[:80]
    except Exception:
        pass


def op_writes(tool_input):
    """런타임 쓰기 원장 회상 — git 이 못 보는 층(data/·outputs/)의 관문 통과 쓰기.

    ★부분성 정직: 원장은 선언된 관문(safe_store·[self:write]·개별 저장 관문 — gate 열이 목록)을 지난 쓰기만 기록한다 —
    관문 밖 직접 쓰기는 원리적으로 없다. 전수가 필요한 코드 층은 changes(git)가 정답.
    또 심장박동 가족(write_ledger._HEARTBEAT_PATHS)의 행위자 없는 폴링 쓰기는
    6시간당 1건으로 압축된다(출처="심장박동(압축)") — 그 파일의 마지막 실쓰기 시각은 mtime.
    """
    root, err = _guard_root()
    if err:
        return err
    notes = []
    days = _clamp(tool_input, "days", _DEFAULT_DAYS, _MAX_DAYS, notes)
    limit = _clamp(tool_input, "limit", _DEFAULT_LIMIT, _MAX_LIMIT, notes)
    scope, serr = _scope_of(tool_input, root)
    if serr:
        return {"success": False, "message": serr}

    ledger = os.path.join(root, "data", "write_ledger.jsonl")
    raw = []
    for p in (ledger + ".1", ledger):
        try:
            with open(p, encoding="utf-8") as f:
                raw += [ln for ln in f.read().splitlines() if ln.strip()]
        except OSError:
            continue
    if not raw:
        return {"success": True, "items": [], "total": 0, "truncated": False,
                "text": "쓰기 원장이 비어 있습니다 — 관문(safe_store·[self:write]·개별 저장 관문) 쓰기가 아직 기록되지 않았습니다."}

    import json as _json
    from datetime import datetime as _dt, timedelta as _td
    cutoff = (_dt.now() - _td(days=days)).isoformat(timespec="seconds")
    rows = []
    for ln in raw:
        try:
            r = _json.loads(ln)
        except ValueError:
            continue
        if (r.get("ts") or "") < cutoff:
            continue
        fp = r.get("path") or ""
        if scope and not (fp == scope or fp.startswith(scope + "/")):
            continue
        rows.append({"시각": r.get("ts", ""), "파일": fp, "사건": r.get("event", ""),
                     "관문": r.get("gate", ""), "영역": _area_of(fp),
                     "행위자": r.get("agent") or "",
                     "작업": r.get("task") or "",
                     "출처": ("심장박동(압축)" if r.get("hb")
                              else "자가점검" if r.get("hc")
                              else (r.get("origin") or ""))})
    rows.sort(key=lambda r: r["시각"], reverse=True)
    total = len(rows)
    truncated = total > limit
    rows = rows[:limit]
    _join_episode_requests(root, rows)
    scope_txt = f" (스코프 {scope})" if scope else ""
    text = (f"최근 {days}일 런타임 쓰기{scope_txt}: {total}건 — "
            f"선언 관문 통과분만(전수 아님 — gate 열이 관문 이름, 코드 층 전수는 changes) · "
            f"심장박동 폴링은 6시간당 1건 압축")
    if truncated:
        text += f" · {limit}건만 표시"
    if notes:
        text += " · " + ", ".join(notes)
    return {"success": True, "items": rows, "total": total, "truncated": truncated, "text": text}


def op_trajectory(tool_input):
    """한 실행의 기계용 핵심 사건을 회상한다.

    식별자는 run_id / episode_id / task_id 중 하나. 없으면 최근 실사용 episode 한 건을
    고른다. episode memory 를 대체하지 않으며 request·IBL·검증 원문도 복제하지 않는다 —
    data 에는 hash/ref/길이와 부작용 경로만 있다.
    """
    notes = []
    limit = _clamp(tool_input, "limit", _DEFAULT_LIMIT, _MAX_LIMIT, notes)
    run_id = str(tool_input.get("run_id") or "").strip()
    task_id = str(tool_input.get("task_id") or "").strip()
    episode_raw = tool_input.get("episode_id")
    episode_id = None
    if episode_raw not in (None, ""):
        try:
            episode_id = int(episode_raw)
        except (TypeError, ValueError):
            return {"success": False,
                    "message": "episode_id 는 정수여야 합니다 — 예: [self:body]{op: \"trajectory\", episode_id: 123}"}
        if episode_id <= 0:
            return {"success": False, "message": "episode_id 는 1 이상의 정수여야 합니다."}

    given = sum(bool(x) for x in (run_id, task_id, episode_id))
    if given > 1:
        return {"success": False,
                "message": "run_id·episode_id·task_id 중 하나만 지정하세요 — 서로 다른 실행을 섞지 않습니다."}

    try:
        from episode_logger import (get_episode_detail, get_episode_journal,
                                    get_trajectory, trajectory_run_id)
    except Exception as e:
        return {"success": False, "message": f"trajectory 회상기를 불러올 수 없습니다: {e}"}

    selected = ""
    if episode_id is not None:
        ep = get_episode_detail(episode_id)
        if not ep:
            return {"success": False,
                    "message": f"episode {episode_id}를 찾을 수 없습니다 — 상세 로그 보존창 밖일 수 있습니다."}
        run_id = ep.get("run_id") or trajectory_run_id(ep.get("task_id") or "")
        task_id = ep.get("task_id") or ""
        events = get_trajectory(episode_id=episode_id)
        selected = f"episode {episode_id}"
    elif task_id:
        run_id = trajectory_run_id(task_id)
        events = get_trajectory(run_id=run_id)
        selected = f"task {task_id}"
    elif run_id:
        events = get_trajectory(run_id=run_id)
        selected = run_id
    else:
        latest = get_episode_journal(1)
        if not latest:
            return {"success": True, "items": [], "total": 0, "truncated": False,
                    "text": "회상할 최근 실사용 episode가 없습니다."}
        ep = latest[0]
        episode_id = ep.get("id")
        run_id = ep.get("run_id") or ""
        if not run_id:
            detail = get_episode_detail(episode_id) or {}
            task_id = detail.get("task_id") or ""
            run_id = trajectory_run_id(task_id) if task_id else ""
        events = get_trajectory(episode_id=episode_id)
        selected = f"최근 episode {episode_id}"

    total = len(events)
    truncated = total > limit
    if truncated:
        # 시작 원인과 최종 결과를 함께 보존한다. 중간 생략은 event_seq 틈으로도 드러난다.
        head = max(1, limit // 2)
        tail = max(0, limit - head)
        events = events[:head] + (events[-tail:] if tail else [])
    text = (f"{selected}의 trajectory: 핵심 사건 {total}건"
            + (f" — 앞뒤 {limit}건만 표시(중간 {total - limit}건 생략)" if truncated else "")
            + " · 원문 기억이 아니라 순번 있는 hash/ref 원장")
    if not events:
        text += " — 이 실행은 trajectory 계측 이전 기록이거나 핵심 사건이 없습니다"
    if notes:
        text += " · " + ", ".join(notes)
    return {"success": True, "items": events, "total": total,
            "truncated": truncated, "run_id": run_id, "episode_id": episode_id,
            "task_id": task_id, "text": text}


def op_file(tool_input):
    """한 파일의 일생 — --follow 가 이름변경·이동을 관통해 생성까지 거슬러 오른다."""
    root, err = _guard_root()
    if err:
        return err
    notes = []
    limit = _clamp(tool_input, "limit", _DEFAULT_LIMIT, _MAX_LIMIT, notes)
    scope, serr = _scope_of(tool_input, root)
    if serr:
        return {"success": False, "message": serr}
    if not scope:
        return {"success": False,
                "message": "file op 은 path 가 필요합니다 — 예: [self:body]{op: \"file\", path: \"backend/api.py\"}"}
    # --follow 는 단일 파일 전용
    args = ["log", "--follow", "--name-status", "-M"] + _LOG_FMT + ["--", scope]
    stdout, gerr = _git(root, args)
    if gerr:
        return {"success": False, "message": gerr}
    rows = _parse_name_status(stdout)
    if not rows:
        exists = os.path.exists(os.path.join(root, scope))
        why = "미추적 파일(아직 커밋된 적 없음)" if exists else "그 경로의 이력이 없습니다(경로 확인)"
        return {"success": True, "items": [], "total": 0, "truncated": False,
                "text": f"{scope}: git 이력 없음 — {why}"}
    total = len(rows)
    truncated = total > limit
    rows = rows[:limit]
    born = rows[-1] if not truncated else None
    text = f"{scope}: 이력 {total}건"
    moves = [r for r in rows if r.get("이전경로")]
    if moves:
        text += f", 이동 {len(moves)}회"
    if born is not None:
        text += f" — 생성 {born['시각']} ({born['커밋']})"
    if truncated:
        text += f" — {limit}건만 표시"
    if notes:
        text += " · " + ", ".join(notes)
    return {"success": True, "items": rows, "total": total, "truncated": truncated, "text": text}


_DEFAULT_DIFF_LINES = 200   # 파일당 본문 줄 상한(기본) — 넘치면 자르고 신고
_MAX_DIFF_LINES = 2000
_DEFAULT_DIFF_FILES = 50
_MAX_DIFF_FILES = 300


def op_diff(tool_input):
    """실제 바뀐 줄 — 파일별 items(추가·삭제·본문).

    범위: commit 지정=그 커밋 하나(부모 대비) / ref 지정=ref..HEAD / 둘 다 없음=미커밋 작업분
    (스테이지+미스테이지, HEAD 대비). path 로 스코프. 본문은 파일당 lines 줄까지 싣고 넘치면 신고.
    """
    root, err = _guard_root()
    if err:
        return err
    notes = []
    lines = _clamp(tool_input, "lines", _DEFAULT_DIFF_LINES, _MAX_DIFF_LINES, notes)
    limit = _clamp(tool_input, "limit", _DEFAULT_DIFF_FILES, _MAX_DIFF_FILES, notes)
    scope, serr = _scope_of(tool_input, root)
    if serr:
        return {"success": False, "message": serr}
    commit = (tool_input.get("commit") or "").strip()
    ref = (tool_input.get("ref") or "").strip()
    if commit and ref:
        return {"success": False, "message": "commit 과 ref 는 동시에 줄 수 없습니다 — 한 커밋이면 commit, 구간이면 ref(예 HEAD~3)."}
    if commit:
        rng, label = [f"{commit}^!"], f"커밋 {commit}"
    elif ref:
        rng, label = [f"{ref}..HEAD"], f"{ref}..HEAD"
    else:
        rng, label = ["HEAD"], "미커밋 작업분"
    tail = ["--", scope] if scope else []
    stdout, gerr = _git(root, ["diff", "--numstat", "-M"] + rng + tail)
    if gerr:
        return {"success": False, "message": gerr}
    files = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add, dele, fp = parts[0], parts[1], parts[2]
        if " => " in fp:  # 이름변경 표기 "a/{old => new}.py" 는 새 경로만
            fp = fp.replace("{", "").replace("}", "")
            fp = fp.split(" => ")[-1] if "/" not in fp.split(" => ")[0] else fp
        files.append((fp, add, dele))
    total = len(files)
    truncated = total > limit
    files = files[:limit]
    rows = []
    for fp, add, dele in files:
        body, derr = _git(root, ["diff", "-M"] + rng + ["--", fp])
        body_lines = (body or "").splitlines() if not derr else [f"(diff 실패: {derr})"]
        cut = len(body_lines) > lines
        row = {"파일": fp, "영역": _area_of(fp),
               "추가": int(add) if add.isdigit() else None,
               "삭제": int(dele) if dele.isdigit() else None,
               "diff": "\n".join(body_lines[:lines])}
        if cut:
            row["diff_잘림"] = f"{len(body_lines)}줄 중 {lines}줄 — lines 를 올리거나 path 로 좁히세요"
        rows.append(row)
    text = f"{label}: 변경 파일 {total}개" + (f" — {limit}개만 표시" if truncated else "")
    if total == 0:
        text += " (바뀐 줄 없음)"
    if notes:
        text += " · " + ", ".join(notes)
    return {"success": True, "items": rows, "total": total, "truncated": truncated, "range": label, "text": text}
