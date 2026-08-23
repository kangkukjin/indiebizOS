#!/usr/bin/env python3
"""수리적용상태 — "무엇을 고쳤고 지금 라이브에 있나"를 기계가 만든다.

why: 자기수리 보고의 '변경 파일·적용 상태' 절이 두 턴 연속 사실과 어긋났다
     (① "테스트 파일도 고쳤다" — 세션 원장에 그 파일이 없었다 ② "아직 라이브에
     없다" — 그 사이 적용이 끝나 있었다). 두 번이면 우연이 아니라 구조다:
     그 절이 **서술**에서 나오기 때문이다. 카운터를 달아 지켜보는 것은 수리가
     아니라 수리 유예 장치이므로, 그 절을 거짓말할 수 없는 자리로 옮긴다 —
     세션 원장 + 격리/라이브 바이트 대조 + git 원장.

args (stdin JSON):
  key       특정 스테이징 세션 키만 (기본: 종결되지 않은 세션 전부)
  commits   최근 N 커밋의 파일도 함께 (기본 1, 0이면 생략)
  all       true 면 applied/discarded 세션도 (기본 false)

산출: {"items": [...], "message": "..."}

각 행의 뜻:
  격리    = 이 세션의 격리 사본에 이 파일의 변경이 쌓여 있다
  라이브  = 격리 사본과 라이브의 **바이트가 같다**(=적용됨). 다르면 미적용.
            파일이 라이브에 없으면 '라이브없음'.
  git     = 라이브 저장소에서 그 파일의 현재 git 상태(미커밋/커밋됨)
★이 스크립트는 판단하지 않는다 — 읽은 것만 적는다. 세션 원장이 비면 '세션없음'이라
  적지, '변경 없음'이라 적지 않는다(부재의 주장과 관측의 부재는 다르다).
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESS_DIR = os.path.join(ROOT, "data", "system_ai_state", "repair_sessions")
CLOSED = ("applied", "discarded")


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def _git(args):
    try:
        # ★core.quotepath=false — 끄지 않으면 git 이 한글 경로를 "\354\210\230…" 로 이스케이프해
        #   돌려주고, 그 문자열로 os.path.exists 하면 **없는 파일**이 된다. 이 스크립트가
        #   처음 돈 자리에서 자기 자신을 '삭제됨'으로 신고했다(기계도 인코딩으로 거짓말한다).
        r = subprocess.run(["git", "-c", "core.quotepath=false"] + args,
                           cwd=ROOT, capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def main():
    try:
        args = json.loads(sys.stdin.read() or "{}")
    except Exception:
        args = {}
    want_key = args.get("key")
    commits = int(args.get("commits", 1) or 0)
    show_all = bool(args.get("all"))

    # git 원장 — 라이브 저장소의 현재 상태
    dirty = {}
    for line in _git(["status", "--porcelain"]).splitlines():
        if len(line) > 3:
            dirty[line[3:].strip().strip('"')] = line[:2].strip() or "?"

    items, notes = [], []
    sessions = []
    if os.path.isdir(SESS_DIR):
        for fn in sorted(os.listdir(SESS_DIR)):
            if not fn.endswith(".json") or fn.endswith(".apply.json"):
                continue
            key = fn[:-5]
            if want_key and key != want_key:
                continue
            try:
                with open(os.path.join(SESS_DIR, fn), encoding="utf-8") as f:
                    sess = json.load(f)
            except Exception as e:
                notes.append(f"{key}: 원장 읽기 실패 {e}")
                continue
            if not show_all and (sess.get("status") or "") in CLOSED:
                continue
            sessions.append((key, sess))
    else:
        notes.append(f"세션 디렉토리 없음: {SESS_DIR}")

    if not sessions:
        notes.append("종결되지 않은 스테이징 세션 없음" if not want_key
                     else f"세션 없음: {want_key}")

    for key, sess in sessions:
        wt = os.path.join(ROOT, sess.get("worktree") or "")
        status = sess.get("status") or "?"
        files = sess.get("files") or {}
        if not files:
            notes.append(f"{key}({status}): 원장에 파일 0건")
        for live_abs, rec in sorted(files.items()):
            rel = os.path.relpath(live_abs, ROOT)
            staged = (rec or {}).get("staged") or os.path.join(wt, rel)
            h_stage, h_live = _sha(staged), _sha(live_abs)
            if h_live is None:
                live_state = "라이브없음"
            elif h_stage is None:
                live_state = "격리사본없음"
            elif h_stage == h_live:
                live_state = "반영됨"
            else:
                live_state = "미반영(격리에만)"
            items.append({
                "파일": rel,
                "영역": os.path.dirname(rel) or ".",
                "세션": key,
                "세션상태": status,
                "라이브": live_state,
                # ★라이브에 파일이 없으면 git 상태는 '커밋됨'이 아니라 **미상**이다.
                #   없는 파일은 git status 에 안 뜨므로 기본값을 그대로 쓰면
                #   격리에만 있는 새 파일이 '커밋됨'으로 보인다(기계의 조용한 오답).
                "git": dirty.get(rel) or ("—" if live_state == "라이브없음" else "커밋됨"),
                "격리해시": (h_stage or "")[:8],
                "라이브해시": (h_live or "")[:8],
            })

    for i in range(commits):
        line = _git(["log", "-1", f"--skip={i}", "--format=%h|%s"]).strip()
        if not line:
            break
        sha, _, subj = line.partition("|")
        for rel in _git(["show", "--name-only", "--format=", sha]).split("\n"):
            rel = rel.strip().strip('"')
            if not rel:
                continue
            items.append({
                "파일": rel,
                "영역": os.path.dirname(rel) or ".",
                "세션": f"커밋 {sha}",
                "세션상태": subj[:60],
                "라이브": "반영됨" if os.path.exists(os.path.join(ROOT, rel)) else "삭제됨",
                "git": dirty.get(rel, "커밋됨"),
                "격리해시": "",
                "라이브해시": (_sha(os.path.join(ROOT, rel)) or "")[:8],
            })

    msg = f"{len(items)}행 — 세션 {len(sessions)}개"
    if notes:
        msg += " · " + " / ".join(notes)
    print(json.dumps({"items": items, "message": msg}, ensure_ascii=False))


if __name__ == "__main__":
    main()
