"""
repair_gates.py - 격리 검증 관문·라이브 파생물 신선도 (repair_staging 의 형제 모듈)

★왜 분리 (2026-09-01): repair_staging.py 가 1500줄 규칙을 넘겼다. 응집도 높은
관문류 — import 스모크 헬퍼(_module_name·_smoke_env·_orphan_importers), frontend
타입검사(_tsc_*), 라이브 파생물 신선도(sync_live_derived 일가) — 와 그들이 쓰는
공용 git 유틸(_git·_is_git_repo·_file_sha·타임아웃 상수)을 여기로 옮겼다.
규칙은 한 벌: 이 유틸들의 정본은 이제 여기고, repair_staging 은 로드 후 별칭으로
기존 표면(테스트의 st._tsc_check 등·vocab_write_gate 의 staging.sync_live_derived)
을 보존한다. 로드는 handler._load_sibling 과 같은 spec-load 이며 자기 옆
(__file__ 기준)을 읽으므로 워크트리 사본에서도 짝이 갈라지지 않는다.

세션·스테이징·적용·판정의 본체는 repair_staging.py — 설계 배경 전체는 그쪽 머리말.
"""
import hashlib
import os
import re
import subprocess
import sys

GIT_TIMEOUT = 120
SMOKE_TIMEOUT = 180
BUILD_TIMEOUT = 300


# ── 공용 유틸 (repair_staging 이 별칭으로 빌려 쓴다) ──────────────────────

def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, timeout=GIT_TIMEOUT)


def _is_git_repo(repo: str) -> bool:
    try:
        return _git(["rev-parse", "--git-dir"], repo).returncode == 0
    except Exception:
        return False


def _file_sha(path: str):
    """파일 내용 sha256 (없으면 None) — 스테이징 시점의 라이브 지문."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


# ── 스모크·타입검사 관문 ──────────────────────────────────────────────────

def _module_name(rel: str, base_abs: str = None):
    """backend 하위 .py → import 스모크가 실제로 쓸 수 있는 모듈명.

    ★backend 안에 두 규약이 공존한다(2026-08-18 실측):
      · 층 디렉토리(base·datastore·ibl·cognition·services·surface) = `__init__.py` **없음**
        → boot_paths 가 각 디렉토리를 sys.path 에 올려 **평면 이름**(`import ibl_engine`)
      · 진짜 패키지(drivers·providers·channels·common) = `__init__.py` **있음**
        → backend/ 가 sys.path 라 **점 표기**(`import providers.claude_code`)
    옛 구현은 전부 평면으로 뭉개서 후자를 `ModuleNotFoundError` 로 무조건 탈락시켰다.
    제안 내용과 무관하게 import_smoke 가 ✗ 라 **apply 가 영원히 막혔다**
    (실측: backend/drivers/sqlite_driver.py · backend/providers/claude_code.py 제안 2건).
    디렉토리 목록을 박지 않고 `__init__.py` 존재로 판정한다 — 새 패키지가 생겨도 따라온다.
    """
    if not (rel.startswith("backend" + os.sep) and rel.endswith(".py")):
        return None
    base = os.path.basename(rel)
    if base == "__init__.py":
        return None
    mod = base[:-3]
    if not base_abs:
        return mod
    parts = rel.split(os.sep)                     # backend, <디렉토리...>, 파일.py
    pkg = []
    for i in range(1, len(parts) - 1):
        d = os.path.join(base_abs, *parts[:i + 1])
        if not os.path.exists(os.path.join(d, "__init__.py")):
            pkg = []                              # 층 디렉토리 — 평면 이름
            break
        pkg.append(parts[i])
    return ".".join(pkg + [mod]) if pkg else mod


def _smoke_env(wt_abs: str):
    """격리 사본을 향하는 환경 — ★라이브 INDIEBIZ_BASE_PATH 를 물려받으면 스모크가
    라이브 data/ 를 건드린다(격리가 깨진다)."""
    env = dict(os.environ)
    env["INDIEBIZ_BASE_PATH"] = wt_abs
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _orphan_importers(wt_abs: str, mod: str, dropped_rels: set):
    """격리 사본에서 `mod` 를 아직 import 하는 파일들 — 삭제가 남길 고아 참조.

    ★왜 별도 검사인가: 쓰기의 위험은 *그 파일이 깨지는* 것이라 그 모듈만 import 해보면
    잡힌다. 삭제의 위험은 반대다 — **남의 import 가 깨진다**. 지워진 모듈은 import 해볼
    수도 없으니(없는 게 정상) 스모크로는 원리적으로 안 잡힌다."""
    esc = re.escape(mod)
    pats = [r"^\s*(?:from\s+%s\s+import|import\s+%s\b)" % (esc, esc)]
    if "." in mod:
        # 패키지 내부 상대 import — providers/__init__.py 의 `from .claude_code import ...`
        # 는 점 표기 패턴에 안 걸린다. 삭제 고아 검출에서 가장 가까운 참조를 놓치는 자리.
        pats.append(r"^\s*from\s+\.%s\s+import" % re.escape(mod.rsplit(".", 1)[-1]))
    pat = re.compile("|".join(pats), re.MULTILINE)
    hits = []
    try:
        listed = subprocess.run(["git", "ls-files", "*.py"], cwd=wt_abs,
                                capture_output=True, text=True, timeout=GIT_TIMEOUT).stdout
    except Exception:
        return hits
    for rel in listed.splitlines():
        if not rel or rel in dropped_rels:
            continue
        try:
            with open(os.path.join(wt_abs, rel), encoding="utf-8", errors="replace") as f:
                if pat.search(f.read()):
                    hits.append(rel)
        except OSError:
            continue
        if len(hits) >= 12:
            break
    return hits


_TSC_ERR = re.compile(r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s+(?P<rest>error TS\d+:.*)$")


def _tsc_errors(text: str):
    """tsc 출력 → **자리(줄·칸)를 뺀** 오류 집합. 델타 판정용 — 델타가 줄 번호를 밀면
    같은 선행 오류가 새 오류로 보인다(파일+메시지로만 동일성 판정)."""
    out = set()
    for ln in (text or "").splitlines():
        m = _TSC_ERR.match(ln.strip())
        if m:
            out.add((m.group("file").strip(), m.group("rest").strip()))
    return out


def _run_tsc(fe_dir: str, tsc_bin: str, wt_abs: str):
    p = subprocess.run([tsc_bin, "-p", "tsconfig.app.json", "--noEmit"], cwd=fe_dir,
                       capture_output=True, text=True, timeout=SMOKE_TIMEOUT,
                       env=_smoke_env(wt_abs))
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def _tsc_check(repo: str, wt_abs: str, ts_rels: list):
    """frontend 타입검사 관문 (2026-08-22 신설).

    ★왜: RED 구역은 `("backend", "frontend", "scripts")` 인데 관문은 전부 파이썬용이라
    **타입은 아무도 안 봤다** — 실측으로 이 경로를 이미 `.tsx`/`.ts` 10건이 무검사로
    통과했다(NarrationStudio.tsx 등). 브릭은 아니지만(프런트가 깨져도 백엔드는 산다)
    빌드 때까지 조용한 부류다.

    두 가지를 **빌린다**:
    - `node_modules` — 의존성은 델타가 아니다. 워크트리는 HEAD 로 뜨고 node_modules 는
      gitignore 라 없으므로 라이브 것을 심링크로 읽고 **검증 후 즉시 회수**한다(격리
      사본에 남기면 워크트리 청소가 라이브를 향하게 된다).
    - **선행 상태** — 실패했을 때만 라이브에서 한 번 더 돌려(읽기 전용·noEmit) 델타가
      *새로* 만든 오류만 빨강으로 친다. 선행 파손이 무관한 수리를 볼모로 잡지 않게
      (`build --check` 를 격리에 못 들인 것과 같은 이유가 여기선 이렇게 풀린다).

    ★검사할 수 없으면 초록도 빨강도 아닌 **건너뜀**을 적는다 — node_modules 없는 몸에서
    apply 가 영원히 막히는 것은 import 스모크가 패키지 모듈을 탈락시켜 apply 를 막던
    2026-08-18 부류의 재생산이다. 대신 침묵하지 않는다(사유를 detail 에 적는다).
    """
    gate = {"gate": "frontend_tsc", "files": ts_rels[:12]}
    fe_wt = os.path.join(wt_abs, "frontend")
    if not os.path.exists(os.path.join(fe_wt, "tsconfig.app.json")):
        return dict(gate, passed=True, skipped=True,
                    detail="frontend/tsconfig.app.json 없음 — 타입검사 건너뜀")

    nm_wt = os.path.join(fe_wt, "node_modules")
    nm_live = os.path.join(repo, "frontend", "node_modules")
    borrowed = False
    if not os.path.exists(nm_wt):
        if not os.path.isdir(nm_live):
            return dict(gate, passed=True, skipped=True,
                        detail="frontend/node_modules 미설치 — 타입검사 불가"
                               "(npm install 후 재검증하면 이 관문이 켜집니다)")
        try:
            os.symlink(nm_live, nm_wt)
            borrowed = True
        except OSError as e:
            return dict(gate, passed=True, skipped=True,
                        detail=f"node_modules 를 빌리지 못함 — 타입검사 건너뜀 ({e})")

    tsc_bin = os.path.join(nm_wt, ".bin", "tsc")
    try:
        if not os.path.exists(tsc_bin):
            return dict(gate, passed=True, skipped=True,
                        detail="node_modules/.bin/tsc 없음 — 타입검사 건너뜀")
        try:
            rc, out = _run_tsc(fe_wt, tsc_bin, wt_abs)
        except (OSError, subprocess.SubprocessError) as e:
            return dict(gate, passed=True, skipped=True,
                        detail=f"tsc 실행 실패 — 타입검사 건너뜀 ({e})")
        if rc == 0:
            return dict(gate, passed=True, detail="타입 오류 없음")

        # 실패 — 선행 상태와 대조해 '이 델타가 만든 오류'만 빨강으로
        after = _tsc_errors(out)
        base_bin = os.path.join(nm_live, ".bin", "tsc")
        before = None
        if after and os.path.exists(base_bin):
            try:
                # ★선행 상태 실측 — 라이브 소스를 읽기만 한다(noEmit·incremental 없음).
                #   _smoke_env 에 라이브 루트를 넘기지 않는다(격리 규약: 라이브
                #   INDIEBIZ_BASE_PATH 를 물려주지 않는다 — tsc 는 안 읽지만 규약을 지킨다).
                _, base_out = _run_tsc(os.path.join(repo, "frontend"), base_bin,
                                       os.path.join(repo, "frontend"))
                before = _tsc_errors(base_out)
            except (OSError, subprocess.SubprocessError):
                before = None
        if before is not None:
            new = after - before
            if not new:
                return dict(gate, passed=True, preexisting=len(after),
                            detail=(f"타입 오류 {len(after)}건은 전부 **선행 파손**"
                                    f"(이 델타가 만든 것 아님) — 통과시킵니다.\n"
                                    + out[-800:]))
            return dict(gate, passed=False, preexisting=len(after) - len(new),
                        detail=(f"이 델타가 만든 타입 오류 {len(new)}건"
                                f"(선행 {len(after) - len(new)}건 제외):\n"
                                + "\n".join(f"{f}: {m}" for f, m in sorted(new))[:1500]))
        return dict(gate, passed=False, detail=out[-1500:])
    finally:
        if borrowed:
            try:
                os.unlink(nm_wt)           # ★심링크만 끊는다(라이브는 못 건드린다)
            except OSError:
                pass


# ── 라이브 파생물 신선도 (2026-09-01 ep2519 봉합) ──────────────────────────

def _live_build_inputs_touched(repo: str) -> bool:
    """라이브 작업 트리에 빌드 트리거 파일이 하나라도 걸려 있나 — 7초짜리 --check 의 문지기.

    트리거 목록은 여기 없다: 빌더가 선언하고(iblbuild_common.GUARD_INPUT_PATTERNS)
    `--inputs-regex` 로 물어본다. pre-commit 훅과 같은 출처를 쓴다 — 목록을 두 벌
    두면 한쪽만 늙는다(2026-07-25 훅 하드코딩 사건).
    """
    build = os.path.join(repo, "scripts", "build_ibl_nodes.py")
    if not os.path.exists(build):
        return False
    py = sys.executable or "python3"
    try:
        r = subprocess.run([py, "scripts/build_ibl_nodes.py", "--inputs-regex"],
                           cwd=repo, capture_output=True, text=True, timeout=GIT_TIMEOUT)
        if r.returncode != 0 or not (r.stdout or "").strip():
            return True                    # 트리거를 못 물었으면 건너뛰지 않는다
        pattern = re.compile((r.stdout or "").strip().splitlines()[-1])
        st = _git(["status", "--porcelain", "-z", "--no-renames",
                   "--untracked-files=all"], repo)
        if st.returncode != 0:
            return True
        return any(pattern.match(e[3:].replace(os.sep, "/"))
                   for e in st.stdout.split("\0") if len(e) > 3)
    except (OSError, re.error, subprocess.SubprocessError):
        return True


def sync_live_derived(repo: str):
    """라이브 파생물을 **라이브에서** 재생성한다. 관문 레코드(dict) 또는 None.

    ★왜 (2026-09-01 ep2519 봉합): ibl_triangle 관문은 격리 사본 **안에서** plain build 를
    돌린다 — 그 빌드가 ibl_nodes.yaml·tool.json 을 워크트리에 **쓴다**. 그래서 수리
    에이전트가 이어서 `build_ibl_nodes.py --check` 를 돌리면(셸 cwd 도 워크트리다) 초록이
    나오고, git status 에도 파생물이 갱신된 것처럼 찍힌다. 그 상태로 discard 하면
    워크트리와 함께 **빌드 산출물이 같이 죽는다**. 실측 결과: 자막 옵션이 ibl_actions.yaml·
    핸들러엔 살아 있는데 data/ibl_nodes.yaml 에는 없어, 시스템이 제 낱말을 못 보는
    상태로 턴이 끝났다. 관문은 "빌드하면 통과한다"만 증명했지 "라이브가 빌드돼 있다"를
    증명한 적이 없다.

    처방을 문장으로 돌려주지 않고 여기서 집행하는 이유: 파생물은 기계 소유다
    (data_ownership: derived · CLAUDE.md "파생물 직접 편집 금지 — 다음 빌드가 되돌린다").
    keeper 표식과 같은 부류다 — 기계가 세우고 기계가 회수한다. 사람/AI 의 다음 단계로
    미루면 그 단계는 턴이 죽는 자리에서 영영 안 온다.

    실패는 두 종류로 갈라 보고한다: **드리프트**(재생성으로 닫힘, passed)와
    **소스 결함**(빌드 자체가 검증에 걸림, passed=False — 처방은 빌더의 말 그대로).
    """
    build = os.path.join(repo, "scripts", "build_ibl_nodes.py")
    if not os.path.exists(build) or not _is_git_repo(repo):
        return None
    if not _live_build_inputs_touched(repo):
        return None                        # 빌드와 무관한 변경만 — 7초를 쓸 이유가 없다
    py = sys.executable or "python3"
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"   # ★라이브다 — INDIEBIZ_BASE_PATH 는 건드리지 않는다
    try:
        chk = subprocess.run([py, "scripts/build_ibl_nodes.py", "--check"], cwd=repo,
                             capture_output=True, text=True, timeout=BUILD_TIMEOUT, env=env)
        if chk.returncode == 0:
            return {"gate": "live_derived", "passed": True, "regenerated": [],
                    "detail": "라이브 파생물 신선 ✓"}
        before = _derived_fingerprint(repo)
        bld = subprocess.run([py, "scripts/build_ibl_nodes.py"], cwd=repo,
                             capture_output=True, text=True, timeout=BUILD_TIMEOUT, env=env)
        if bld.returncode != 0:
            return {"gate": "live_derived", "passed": False, "regenerated": [],
                    "detail": ("라이브 파생물이 낡았는데 재생성도 실패했습니다 — 소스가 "
                               "검증에 걸립니다. 빌더의 말 그대로:\n"
                               + ((bld.stdout or "") + (bld.stderr or "")).strip()[-1200:])}
        # 지문(경로@sha)에서 경로만 남긴다 — 보고는 "무엇이 바뀌었나"지 해시가 아니다.
        regenerated = sorted({f.rsplit("@", 1)[0]
                              for f in set(_derived_fingerprint(repo)) - set(before)})
        return {"gate": "live_derived", "passed": True, "regenerated": regenerated,
                "detail": ("라이브 파생물이 낡아 재생성했습니다(기계 소유물) — "
                           + (", ".join(regenerated) if regenerated else "내용 동일")
                           + ". 격리에서 난 초록은 라이브 판정이 아닙니다.")[:1200]}
    except (OSError, subprocess.SubprocessError) as e:
        return {"gate": "live_derived", "passed": False, "regenerated": [],
                "detail": f"라이브 파생물 점검 실패: {e}"}


def _derived_fingerprint(repo: str):
    """지금 라이브에서 변경된 파일 (경로@sha) 집합 — 재생성이 무엇을 건드렸는지 대조용."""
    st = _git(["status", "--porcelain", "-z", "--no-renames",
               "--untracked-files=all"], repo)
    if st.returncode != 0:
        return []
    out = []
    for entry in st.stdout.split("\0"):
        if len(entry) <= 3:
            continue
        rel = entry[3:]
        out.append(f"{rel.replace(os.sep, '/')}@{_file_sha(os.path.join(repo, rel))}")
    return out
