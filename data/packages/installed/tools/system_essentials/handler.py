import os
import glob
import re
import time
import fnmatch
import unicodedata
import subprocess
import shlex
import shutil
import json
from datetime import datetime
from pathlib import Path
import importlib.util

_CURRENT_DIR = Path(__file__).parent


def _load_sibling(module_name):
    """패키지 형제 모듈 spec-load (real-estate load_module 선례)."""
    spec = importlib.util.spec_from_file_location(module_name, _CURRENT_DIR / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# file_find 무경계 재귀 glob 방지 — 매 호출 홈 전체(node_modules·캐시)를 색인 없이
# stat 하던 게 타임아웃 원인. 절대-dead 가지치기 + 시간 예산으로 바운드.
# ★ 절대-dead 목록은 file_index(포식 substrate)와 *공유* — fs_query 와 같은 단일 출처라
#   드리프트 없음. path-substring 판정이라 ~/Library 통째가 아니라 캐시류만 쳐냄(iCloud 보존).
try:
    from file_index import ABSOLUTE_DEAD_SUBSTR as _DEAD_SUBSTR
except Exception:  # import 경로 미확보 시 폴백(동일 내용)
    _DEAD_SUBSTR = (
        "/System/", "/Applications/", "/Library/Caches/",
        "/Library/Application Support/", "/Library/Containers/",
        "/Library/Group Containers/", "/node_modules/", "/.Trash", ".app/",
        "/__pycache__/", "/site-packages/", "/.venv/", "/venv/",
        "/.git/", "/DerivedData/", "/.gradle/", "/.cargo/", "/.npm/",
    )
_FIND_DEADLINE_S = 25.0  # 엔진 타임아웃 전에 부분결과라도 반환


def _is_dead_dir(path):
    """절대-dead(설치트리·캐시) 디렉토리면 True — walk 가 안 들어감(의도 불문 제외)."""
    p = path.rstrip("/") + "/"
    return any(n in p for n in _DEAD_SUBSTR)


def _bounded_find(root, basename_pat, max_results):
    """root 하위를 바운드 재귀 순회 — 정크 가지치기 + dot-dir 스킵(glob ** 와 동일) + 시간 예산.

    무한정 walk 로 시스템을 멈추지 않는다. 시간 초과/상한 도달 시 partial=True 로 알린다.
    """
    deadline = time.time() + _FIND_DEADLINE_S
    # macOS 한글 파일명=NFD(자모분해), 패턴은 보통 NFC → fnmatch 바이트비교가 침묵 누락.
    # 양쪽을 NFC 로 정규화해 비교(mdfind 는 정규화하지만 fnmatch 는 안 함. forage_map #33).
    pat = unicodedata.normalize("NFC", basename_pat)
    pat_lower = pat.lower()
    matches, partial = [], False
    for dirpath, dirs, files in os.walk(root, topdown=True):
        if time.time() > deadline:
            partial = True
            break
        # 가지치기: 절대-dead(공유 목록, path-substring) + dot-dir. 제자리 수정으로 walk 가 안 들어감.
        #   ~/Library 통째가 아니라 캐시류만 → ~/Library/Mobile Documents(iCloud) 는 보존.
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and not _is_dead_dir(os.path.join(dirpath, d))]
        # 매칭: 파일 + 디렉토리 둘 다 (glob.glob 은 둘 다 매칭했음 — 예: .epub 번들·iCloud 책은 디렉토리).
        # macOS 파일시스템은 대소문자 무시 → 소문자 비교로 맞춤.
        for name in files + dirs:
            nfc = unicodedata.normalize("NFC", name)
            if fnmatch.fnmatch(nfc.lower(), pat_lower):
                matches.append(os.path.join(dirpath, name))
                if len(matches) >= max_results:
                    return matches, True
    return matches, partial

# 시스템 AI 전용 상태 폴더 (data/system_ai_state/)
DATA_PATH = Path(__file__).parent.parent.parent.parent
SYSTEM_AI_STATE_PATH = DATA_PATH / "system_ai_state"


def get_state_paths(project_path: str, agent_id: str = None) -> dict:
    """에이전트별 상태 파일 경로 반환

    - 시스템 AI: data/system_ai_state/
    - 프로젝트 에이전트: projects/{project_id}/agent_{agent_id}_*.json
    """
    project_path = Path(project_path).resolve()

    # 시스템 AI인지 확인 (project_path가 data 폴더 또는 "."인 경우)
    if str(project_path).endswith("data") or project_path == Path(".").resolve():
        state_dir = SYSTEM_AI_STATE_PATH
        prefix = ""
    else:
        # 프로젝트 에이전트는 프로젝트 폴더에 상태 저장
        state_dir = project_path
        # 에이전트별 파일명 접두사 (agent_id가 있으면 사용)
        prefix = f"agent_{agent_id}_" if agent_id else ""

    # 폴더 생성
    state_dir.mkdir(parents=True, exist_ok=True)

    return {
        "todo": state_dir / f"{prefix}todo_state.json",
        "question": state_dir / f"{prefix}question_state.json",
        "plan_mode": state_dir / f"{prefix}plan_mode_state.json",
        "plan_file": state_dir / f"{prefix}current_plan.md"
    }


# 위험한 명령어 패턴 (정규식, 사용자 승인 필요)
# 단어 경계(\b)를 사용하여 'add'에서 'dd'가 매칭되는 등의 오탐 방지
import re

DANGEROUS_PATTERNS_RE = [
    # 파일 삭제/수정
    r'\brm\s', r'\brmdir\b', r'\bunlink\b',
    # 권한 관련
    r'\bsudo\b', r'\bchmod\b', r'\bchown\b', r'\bchgrp\b',
    # 디스크 관련 위험 명령어
    r'\bdd\s', r'\bmkfs\b', r'\bformat\b', r'\bdiskutil\s+erase\b', r'\bdiskutil\s+partitionDisk\b',
    # 시스템 종료/재시작
    r'\bshutdown\b', r'\breboot\b', r'\bhalt\b',
    # 프로세스 종료
    r'\bkill\s', r'\bkillall\b', r'\bpkill\b',
]

_DANGEROUS_RE = re.compile('|'.join(DANGEROUS_PATTERNS_RE), re.IGNORECASE)


# ── 자기개조 안전장치 Floor #1: RED 구역(살아있는 기질) 직접 쓰기 차단 ──
# docs/SELF_MODIFICATION_SAFETY_DESIGN.md. 이 핸들러가 돌고 있는 코어 코드(backend/·
# frontend/·scripts/)를 IBL 매개 쓰기가 직접 덮어쓰면 자해(uvicorn reload 가 개조 중인
# 호출 자체를 절단)·관찰자 오염(자기채점 ACHIEVED)이 난다(에피소드 551 실측). 규칙:
# 개조는 data/ 차원(어휘·yaml·상태)에서 끝내거나, 코어가 정말 필요하면 사람에게 제안.
# repo 루트는 backend+frontend 동시 존재로 독립 탐지 — 설치 위치·경로 깊이에 안 흔들림.
def _find_repo_root():
    p = Path(__file__).resolve()
    for anc in p.parents:
        if (anc / "backend").is_dir() and (anc / "frontend").is_dir():
            return anc
    return None  # 미탐지 시 RED 가드 fail-open(정상 쓰기를 막지 않음 > 안전 과잉)

_REPO_ROOT = _find_repo_root()
_RED_ZONE_DIRS = ("backend", "frontend", "scripts")
# 사람 전용 승인 상태 파일 — 에이전트가 IBL 파일 쓰기로 자가승인하면 게이트가 무의미해진다.
# ([self:install_lib] 공급망 방어 게이트. 승인 채널은 HTTP /install-approvals/* 뿐.)
_PROTECTED_STATE_FILES = ("data/system_ai_state/install_approvals.json",)


def _red_zone_violation(abs_path: str) -> str | None:
    """쓰기 대상 실경로가 RED 구역이면 거부 메시지, 아니면 None.
    realpath 로 정규화 → 심볼릭·../ 우회(data/../backend/…)까지 잡는다."""
    if _REPO_ROOT is None:
        return None
    real = os.path.realpath(abs_path)
    for pf in _PROTECTED_STATE_FILES:
        if real == str(_REPO_ROOT / pf):
            return (
                f"Error: 사람 전용 승인 상태 파일은 IBL 쓰기가 금지됩니다: {pf}\n"
                f"이 파일은 [self:install_lib] 공급망 방어 게이트의 승인 원장입니다. "
                f"승인·거부는 사용자가 HTTP 채널(/install-approvals/*)로만 합니다."
            )
    for d in _RED_ZONE_DIRS:
        red_root = str(_REPO_ROOT / d)
        if real == red_root or real.startswith(red_root + os.sep):
            rel = os.path.relpath(real, str(_REPO_ROOT))
            return (
                f"Error: RED 구역(살아있는 기질) 직접 쓰기는 금지됩니다: {rel}\n"
                f"이 코드는 지금 시스템이 돌고 있는 기질이라, IBL 이 직접 덮어쓰면 "
                f"reload 절단(자해)·자기채점 오염이 납니다.\n"
                f"→ data/ 차원(어휘·yaml·상태)에서 끝낼 수 있는지 먼저 보고, "
                f"코어 코드 변경이 정말 필요하면 사람에게 제안하세요."
            )
    return None


def _validate_path_in_scope(path: str, project_path: str) -> str | None:
    """쓰기 대상 경로가 허용 범위인지 검증. 벗어나면 에러 메시지 반환, 정상이면 None

    두 게이트(순서대로):
    1. RED 구역(backend/·frontend/·scripts/) 직접 쓰기 금지 — 절대/상대 무관(Floor #1).
    2. 상대 경로가 ../로 프로젝트 밖으로 나가는 경우 차단(기존 동작).
    절대 경로는 RED 밖이면 허용(시스템 파일·다른 프로젝트 접근).
    """
    # 게이트 1: RED 구역 — 입력이 절대든 상대든, 최종 실경로로 판정(기존 해석과 동일하게 계산)
    abs_for_red = path if os.path.isabs(path) else os.path.join(project_path, path)
    red = _red_zone_violation(abs_for_red)
    if red:
        return red

    # 게이트 2: RED 통과 후 절대 경로면 허용 (시스템 파일 수정, 다른 프로젝트 파일 접근 등)
    if os.path.isabs(path):
        return None

    # 상대 경로: 프로젝트 범위 안에 있는지 확인
    abs_path = os.path.abspath(os.path.join(project_path, path))
    abs_project = os.path.abspath(project_path)
    if not abs_path.startswith(abs_project + os.sep) and abs_path != abs_project:
        return f"Error: 프로젝트 범위를 벗어나는 상대 경로입니다: {path} → {abs_path}"
    return None


# ── 자기개조 안전장치 Floor #2: RED 개조를 격리 사본(worktree)에만 제안 ──
# docs/SELF_MODIFICATION_SAFETY_DESIGN.md. Floor #1 이 RED 직접 쓰기를 막았으니,
# RED(backend/·frontend/·scripts/)를 건드리는 유일한 정규 통로는 이 제안 채널이다.
# 라이브 트리는 절대 손대지 않는다 — git worktree(HEAD 격리 사본)에만 기록하고,
# 그 사본에서 py_compile + build --check 로 기계 검증한 뒤, diff·검증결과를
# data/system_ai_state/patch_proposals/ 에 남긴다. 채택(머지)·폐기는 사람 몫(Floor #4).
def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=120)


def _propose_red_patch(raw_path: str, content, old_string, new_string, reason: str) -> dict:
    """RED 파일 변경을 worktree 격리 사본에 제안 + 검증. 라이브 무변경. dict 반환."""
    repo = _REPO_ROOT
    if repo is None:
        return {"success": False, "error": "repo 루트를 찾지 못해 propose_patch 를 실행할 수 없습니다."}
    repo = str(repo)

    if not raw_path:
        return {"success": False, "error": "대상 파일 경로(path)가 필요합니다."}
    if not (reason or "").strip():
        return {"success": False, "error": "reason(변경 근거)이 필요합니다 — 사람 검토용."}
    has_content = content is not None
    has_edit = old_string is not None and new_string is not None
    if not has_content and not has_edit:
        return {"success": False, "error": "변경 내용이 필요합니다: content(전체 내용) 또는 old_string+new_string(부분 교체)."}

    # 대상 실경로 — RED 전용 게이트(밖이면 그냥 write/edit 쓰라고 안내)
    abs_target = os.path.realpath(raw_path if os.path.isabs(raw_path) else os.path.join(repo, raw_path))
    if _red_zone_violation(abs_target) is None:
        return {"success": False, "error": "propose_patch 는 RED 구역(backend/·frontend/·scripts/) 전용입니다. 그 밖의 파일은 [self:write]/[self:edit]로 직접 쓰세요."}
    rel_target = os.path.relpath(abs_target, repo)
    if rel_target.startswith(".."):
        return {"success": False, "error": f"repo 밖 경로는 propose_patch 대상이 아닙니다: {abs_target}"}

    if _git(["rev-parse", "--git-dir"], repo).returncode != 0:
        return {"success": False, "error": "git 저장소가 아니라 격리(worktree)를 만들 수 없습니다."}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    wt_rel = os.path.join(".worktrees", f"selfpatch-{ts}")
    wt_abs = os.path.join(repo, wt_rel)
    add = _git(["worktree", "add", "--detach", wt_abs, "HEAD"], repo)
    if add.returncode != 0:
        return {"success": False, "error": f"worktree 생성 실패: {add.stderr.strip()}"}

    try:
        wt_file = os.path.join(wt_abs, rel_target)
        # 변경은 격리 사본에만 적용 (HEAD 기준 — 라이브 미커밋 변경과 무관하게 깨끗한 베이스)
        if has_content:
            os.makedirs(os.path.dirname(wt_file), exist_ok=True)
            with open(wt_file, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            if not os.path.exists(wt_file):
                raise FileNotFoundError(f"대상 파일이 HEAD에 없어 old_string 교체 불가: {rel_target} (신규 파일은 content 로 제안)")
            with open(wt_file, "r", encoding="utf-8") as f:
                orig = f.read()
            n = orig.count(old_string)
            if n == 0:
                raise ValueError("old_string 이 대상 파일에 없습니다.")
            if n > 1:
                raise ValueError(f"old_string 이 {n}번 나와 모호합니다 — 주변 맥락을 더 포함하세요.")
            with open(wt_file, "w", encoding="utf-8") as f:
                f.write(orig.replace(old_string, new_string, 1))

        diff = _git(["diff", "--", rel_target], wt_abs).stdout

        # 기계 검증 — 격리 사본에서만 (라이브 무오염). 자기채점 아님, pass/fail 기계값.
        # gate: py_compile(구문) + plain build(삼각 검증 handler↔src↔tool.json, 실패 시 exit 1).
        # --check 의 코퍼스/fixture/gitignore-매니페스트 검사는 런타임 DB·미추적 파생물에
        # 의존해 바레 worktree 에서 못 돈다 → 사람이 머지할 때(라이브·pre-commit) 완전 검증.
        checks = []
        if wt_file.endswith(".py"):
            pc = subprocess.run(["python3", "-m", "py_compile", wt_file],
                                capture_output=True, text=True, timeout=60)
            checks.append({"gate": "py_compile", "passed": pc.returncode == 0,
                           "detail": (pc.stderr or "").strip()[-500:]})
        bc = subprocess.run(["python3", "scripts/build_ibl_nodes.py"],
                            cwd=wt_abs, capture_output=True, text=True, timeout=240)
        checks.append({"gate": "ibl_triangle", "passed": bc.returncode == 0,
                       "detail": ((bc.stdout or "") + (bc.stderr or "")).strip()[-800:]})
        verified = all(c["passed"] for c in checks)

        prop_dir = os.path.join(repo, "data", "system_ai_state", "patch_proposals")
        os.makedirs(prop_dir, exist_ok=True)
        proposal = {
            "id": ts, "target": rel_target, "reason": reason,
            "diff": diff, "checks": checks, "verified": verified,
            "worktree": wt_rel, "status": "proposed",
            "created_at": datetime.now().isoformat(),
        }
        with open(os.path.join(prop_dir, f"{ts}.json"), "w", encoding="utf-8") as f:
            json.dump(proposal, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "proposal_id": ts,
            "target": rel_target,
            "verified": verified,
            "verdict": ("기계 검증 통과 ✓" if verified else "기계 검증 실패 ✗ — checks 확인"),
            "checks": checks,
            "worktree": wt_rel,
            "diff": diff[:4000] + ("\n…(diff 잘림)" if len(diff) > 4000 else ""),
            "note": ("이 변경은 격리 사본(worktree)에만 있고 라이브는 무변경입니다. "
                     "적용은 사람이 검토 후 수행합니다(자기가 자기 몸에 자가 적용하지 않음). "
                     f"채택: cd {wt_rel} 확인 후 사람이 머지·리로드. "
                     f"폐기: git worktree remove {wt_rel}."),
        }
    except Exception as e:
        _git(["worktree", "remove", "--force", wt_abs], repo)
        return {"success": False, "error": f"propose_patch 실패: {e}"}


def is_dangerous_command(command: str) -> bool:
    """명령어가 위험한지 검사 (정규식 단어 경계 사용)"""
    return bool(_DANGEROUS_RE.search(command))

# _get_path/_truthy/_fill_pdf/_fill_docx 는 office_ops.py 로 이동 (2026-07-18 모듈화).
# _get_path 는 다른 분기(read/write/edit/make_directory/propose_patch)도 쓰므로 별칭 유지.
_office = _load_sibling("office_ops")
_get_path = _office._get_path


def execute(tool_input: dict, context) -> str:
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    project_path = context.project_path
    agent_id = context.agent_id

    # 단일 액션 패턴: read {format} 통합 액션. format 명시 또는 확장자 자동 인식.
    if tool_name == "read_op":
        # end(끝 줄/블록) → limit 흡수: start 는 액션 aliases(레지스트리)가 offset 으로
        # 변환하지만, end 는 이름변경이 아니라 계산(limit = end − offset)이라 여기서 흡수.
        # (모델이 start/end 를 써 조용히 무시되고 통파일이 오던 silent-ignore 해소.)
        if tool_input.get("end") is not None and tool_input.get("limit") is None:
            try:
                _end_off = int(tool_input.get("offset") or tool_input.get("start") or 0)
                tool_input = {**tool_input, "limit": max(1, int(tool_input["end"]) - _end_off)}
            except (TypeError, ValueError):
                pass  # 숫자 아님 — 기존 흐름(무시)에 맡김, 런타임 param 경고층이 알림
        # 파이프라인 자동 바인딩: path 가 없으면 직전 step 결과에서 파일 경로 추출.
        # "방금 찾은 파일을 읽기"([self:file_find]{...} | take: 1 >> [self:read]) 조합 개통.
        if not (tool_input.get("path") or tool_input.get("file_path") or tool_input.get("target")):
            prev = tool_input.get("_prev_result") or tool_input.get("params", {}).get("_prev_result", "")
            if prev:
                try:
                    from ibl_executors import _extract_path_from_prev
                    extracted = _extract_path_from_prev(prev if isinstance(prev, str) else json.dumps(prev, ensure_ascii=False))
                    if extracted:
                        tool_input = {**tool_input, "path": extracted}
                except Exception:  # noqa: BLE001 — 추출 실패 시 기존 경로 없음 흐름
                    pass
        fmt = (tool_input.get("format") or "").strip().lower()
        if not fmt:
            raw = tool_input.get("path") or ""
            ext = os.path.splitext(raw)[1].lower().lstrip(".")
            if ext == "pdf":
                fmt = "pdf"
            elif ext in ("docx", "doc"):
                fmt = "docx"
            elif ext in ("xlsx", "xlsm"):
                fmt = "xlsx"
            else:
                fmt = "text"
        # 분기 후 tool_name 재할당해 기존 코드로 위임
        if fmt == "pdf":
            tool_name = "read_pdf"
        elif fmt == "docx":
            tool_name = "read_docx"
        elif fmt == "xlsx":
            tool_name = "read_xlsx"
        else:
            tool_name = "read_file"

    try:
        if tool_name == "read_file":
            raw_path = _get_path(tool_input)
            # system_docs/ 경로는 어떤 프로젝트에서든 data/system_docs/로 매핑
            if raw_path.startswith("system_docs/") and not os.path.isabs(raw_path):
                from runtime_utils import get_base_path
                path = str(get_base_path() / "data" / raw_path)
            else:
                path = os.path.join(project_path, raw_path)
            # client:true — 파일을 바이너리로 읽어 호출한 몸(폰)이 네이티브 저장하도록 b64 봉투로 반환.
            # 폰 /ibl/execute 프록시(phone_api)가 download_in_client+b64 를 가로채 MediaStore(Music)에
            # 네이티브 저장 → 음악앱이 인식(오프라인·백그라운드·잠금화면 재생). 텍스트 read 와 달리
            # 바이너리(mp3·pdf·이미지)를 나른다. 일반 능력: 어떤 맥 파일이든 부른 몸으로. (오디오 브리핑
            # "폰에 저장" 이 소비자 — [self:read]{path, client:true, mime:"audio/mpeg"}@hub)
            if tool_input.get("client"):
                import base64 as _b64
                import mimetypes as _mt
                if not os.path.isfile(path):
                    return json.dumps({"success": False, "error": f"파일을 찾을 수 없습니다: {path}"}, ensure_ascii=False)
                with open(path, 'rb') as _bf:
                    _bytes = _bf.read()
                _fn = os.path.basename(path)
                _mime = (tool_input.get("mime") or "").strip() or _mt.guess_type(_fn)[0] or "application/octet-stream"
                return json.dumps({
                    "success": True, "download_in_client": True,
                    "filename": _fn, "mime": _mime, "bytes": len(_bytes),
                    "b64": _b64.b64encode(_bytes).decode("ascii"),
                    "message": f"{_fn} 을(를) 폰에 저장 준비",
                }, ensure_ascii=False)
            # blocks: 문서를 *타입 있는 문서 IR* items 로 반환(2026-07-03 승격 — 옛 {text}
            # 문단 조각은 표면에서 마크다운이 생으로 보였음). markdown_to_blocks(backend/doc_ir)
            # 가 heading/list/quote/table/code/divider 를 살려 blocks 뷰·render_document 가
            # 그대로 소비. docx·pdf 읽기의 자체 IR 방출과 같은 통화로 3경로 정렬.
            # 원문은 message 로도 보존. 어느 파일이든 쓰는 일반 표시 옵션.
            if tool_input.get("blocks"):
                from doc_ir import markdown_to_blocks
                with open(path, 'r', encoding='utf-8') as f:
                    _txt = f.read()
                _parts = markdown_to_blocks(_txt)
                return json.dumps({"success": True, "items": _parts, "message": _txt,
                                   "path": path, "count": len(_parts)}, ensure_ascii=False)
            offset = tool_input.get("offset", 0) or 0
            limit = tool_input.get("limit")
            file_size = os.path.getsize(path)

            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            total_lines = len(lines)

            # offset/limit 적용
            if offset > 0 or limit is not None:
                end = min(offset + limit, total_lines) if limit else total_lines
                selected = lines[offset:end]
                content = ''.join(selected)
                header = f"[줄 {offset}-{min(end, total_lines)-1} / 전체 {total_lines}줄, {file_size:,}바이트]\n"
                return header + content
            else:
                # 전체 읽기 — 대용량 파일 방어 (1MB 제한)
                MAX_READ_SIZE = 1_000_000
                content = ''.join(lines)
                if len(content) > MAX_READ_SIZE:
                    content = content[:MAX_READ_SIZE]
                    content += f"\n\n... (파일이 {file_size // 1000}KB로 큽니다. 처음 1MB만 표시. offset/limit으로 부분 읽기를 사용하세요. 전체 {total_lines}줄)"
                return content

        elif tool_name == "write_file":
            raw_path = _get_path(tool_input)
            if not raw_path:
                return json.dumps({"success": False, "error": "파일 경로(path)가 지정되지 않았습니다."}, ensure_ascii=False)
            path = os.path.join(project_path, raw_path)

            # 새 파일 + bare 파일명(디렉토리 없음) → outputs/ 폴더로 자동 리다이렉트
            redirected = False
            if (not os.path.isabs(raw_path)
                    and os.sep not in raw_path and '/' not in raw_path
                    and not os.path.exists(path)):
                raw_path = os.path.join("outputs", raw_path)
                path = os.path.join(project_path, raw_path)
                redirected = True

            scope_err = _validate_path_in_scope(path, project_path)
            if scope_err:
                return scope_err
            os.makedirs(os.path.dirname(path), exist_ok=True)
            content = tool_input["content"]
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            abs_path = os.path.abspath(path)
            result = {"success": True, "path": abs_path, "size": len(content)}
            if redirected:
                result["redirected_to"] = "outputs/"
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "fill_op":
            # 양식 채우기(PDF 폼/DOCX 자리표시자) — office_ops 로 이동 (2026-07-18 모듈화).
            return _office.fill_op(tool_input, project_path)

        elif tool_name == "list_directory":
            dir_path = os.path.join(project_path, os.path.expanduser(tool_input.get("dir_path") or tool_input.get("path") or tool_input.get("target") or "."))
            items = os.listdir(dir_path)
            text = "\n".join(items)
            # === 공유 통화 table {columns, rows} (비파괴 ADD) ===
            # 파일 목록 → [이름, 크기, 수정일, 경로]. 디렉터리는 크기 "".
            rows = []
            records = []  # records 통화(보편) — 파일=명사. 선언 returns:records와 일치.
            for name in items:
                full = os.path.join(dir_path, name)
                try:
                    st = os.stat(full)
                    is_dir = os.path.isdir(full)
                    size = "" if is_dir else st.st_size
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                except OSError:
                    is_dir, size, mtime = False, "", ""
                abs_full = os.path.abspath(full)
                rows.append([name, size, mtime, abs_full])
                records.append({
                    "title": name + ("/" if is_dir else ""),
                    "meta": " · ".join(x for x in [
                        ("디렉터리" if is_dir else (f"{size:,}B" if isinstance(size, int) else None)),
                        (mtime or None),
                    ] if x),
                    "summary": "",
                    "url": abs_full,
                })
            table = {"columns": ["이름", "크기", "수정일", "경로"], "rows": rows}
            return json.dumps({"text": text, "table": table, "items": records}, ensure_ascii=False)

        elif tool_name == "grep_files":
            pattern = tool_input["pattern"]
            file_pattern = tool_input.get("file_pattern", "**/*")
            # 검색 루트: path > root_path > project_path (glob_files 와 동일 규칙).
            # ★과거엔 root_path 만 읽어 src 가 광고하는 path 가 조용히 무시됐다(param 불일치 버그).
            raw_root = tool_input.get("path") or tool_input.get("root_path") or "."
            expanded = os.path.expanduser(raw_root)
            root = expanded if os.path.isabs(expanded) else os.path.join(project_path, expanded)
            # 정규식이 기본이다(grep/ripgrep·Claude Grep 습관과 동일, src desc도 "정규식"으로 광고).
            # 과거엔 기본이 fixed-string('a|b' 를 리터럴로 취급)이라 alternation·메타문자가
            # 조용히 No matches 가 되는 silent-failure 함정이었다. regex=false 로 리터럴 강제 가능.
            use_regex = tool_input.get("regex", True)
            # output_mode (Claude Grep 습관): content(매칭 라인, 기본) / files_with_matches(파일 목록) /
            # count(파일별 매칭 수). 알 수 없는 값은 content 로 폴백.
            output_mode = (tool_input.get("output_mode") or "content").lower()
            if output_mode not in ("content", "files_with_matches", "count"):
                output_mode = "content"
            max_results = 100
            # 줄 수만으로는 토큰 폭발을 못 막는다 — 미니파이드/JSON 한 줄이 수만 자면
            # 100줄로도 수십만 자가 된다. 줄 길이·총량 상한을 함께 둔다.
            MAX_LINE_CHARS = 500       # 한 줄 매칭 내용 상한 (초과 시 잘라 표시)
            MAX_TOTAL_CHARS = 40_000   # content 누적 총량 상한 (초과 시 검색 중단 + 좁히기 안내)
            total_chars = 0
            hit_size_cap = False

            # 검색 제외 디렉토리/확장자 (바이너리, 캐시, VCS)
            SKIP_DIRS = {'.git', '.svn', '__pycache__', 'node_modules', '.venv', 'venv', '.tox', '.mypy_cache'}
            SKIP_EXTS = {'.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe', '.bin',
                         '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
                         '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv',
                         '.zip', '.gz', '.tar', '.rar', '.7z', '.bz2',
                         '.woff', '.woff2', '.ttf', '.eot', '.otf',
                         '.pdf', '.doc', '.docx', '.xls', '.xlsx',
                         '.db', '.sqlite', '.sqlite3'}

            # 검색할 파일 목록 가져오기 (불필요 파일 필터링)
            # root 가 단일 파일이면 그 파일만 검색한다. file_pattern 기본값 '**/*' 를 파일 경로에
            # join 하면 'file.py/**/*' 가 되어 빈 목록 → 조용한 "No matches" 버그가 된다.
            # 모델(Claude Grep 습관)은 흔히 단일 파일을 겨누므로 이 케이스를 명시 처리한다.
            # 사용자가 직접 지정한 파일이므로 SKIP 확장자/디렉토리 필터도 적용하지 않는다.
            if os.path.isfile(root):
                files = [root]
            else:
                files = glob.glob(os.path.join(root, file_pattern), recursive=True)
                files = [
                    f for f in files
                    if os.path.isfile(f)
                    and os.path.splitext(f)[1].lower() not in SKIP_EXTS
                    and not any(skip in f.split(os.sep) for skip in SKIP_DIRS)
                ]

            results = []
            match_rows = []  # 공유 통화 table용 [파일, 줄번호, 내용]
            file_counts = {}  # output_mode=files_with_matches/count용 {파일: 매칭 수}
            file_order = []   # 파일 첫 등장 순서 보존
            # 잘못된 정규식(짝 안 맞는 괄호 등)은 크래시 대신 리터럴 검색으로 폴백한다 —
            # 절대 크래시도 침묵 실패도 만들지 않는다. 폴백 시 결과에 안내를 덧붙인다.
            regex_pattern = None
            regex_error = None
            if use_regex:
                try:
                    regex_pattern = re.compile(pattern)
                except re.error as e:
                    regex_error = str(e)
                    use_regex = False  # 리터럴로 폴백
            search_done = False

            for file_path in files:
                if search_done:
                    break
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if use_regex:
                                matched = regex_pattern.search(line)
                            else:
                                matched = pattern in line

                            if matched:
                                rel_path = os.path.relpath(file_path, project_path)
                                snippet = line.rstrip()
                                if len(snippet) > MAX_LINE_CHARS:
                                    snippet = snippet[:MAX_LINE_CHARS] + " …(줄 잘림)"
                                results.append(f"{rel_path}:{line_num}: {snippet}")
                                match_rows.append([rel_path, line_num, snippet])
                                if rel_path not in file_counts:
                                    file_order.append(rel_path)
                                file_counts[rel_path] = file_counts.get(rel_path, 0) + 1
                                total_chars += len(snippet)
                                if len(results) >= max_results or total_chars >= MAX_TOTAL_CHARS:
                                    search_done = True
                                    hit_size_cap = total_chars >= MAX_TOTAL_CHARS
                                    break
                except (UnicodeDecodeError, PermissionError, OSError):
                    continue

            regex_note = ""
            if regex_error:
                regex_note = (f"\n(주의: 정규식 '{pattern}' 컴파일 실패 [{regex_error}] → "
                              f"리터럴 문자열로 검색했습니다. 의도가 정규식이면 패턴을 고치세요.)")

            if not results:
                return f"No matches found for: {pattern}{regex_note}"

            if search_done and hit_size_cap:
                truncated = ("\n... (결과가 너무 큽니다 — root_path/file_pattern 으로 범위를 좁히거나, "
                             "output_mode='files_with_matches'/'count' 로 먼저 분포를 보세요.)")
            elif search_done:
                truncated = "\n... (결과가 {0}개에 도달하여 검색 중단)".format(max_results)
            else:
                truncated = ""
            truncated += regex_note

            if output_mode == "files_with_matches":
                # 매칭된 파일 목록만 (라인 무관). 단일 통화 items(행 dict).
                text = "\n".join(file_order) + truncated
                items = [{"파일": fp} for fp in file_order]
                return json.dumps({"text": text, "items": items}, ensure_ascii=False)

            if output_mode == "count":
                # 파일별 매칭 수. 단일 통화 items(행 dict).
                rows = [[fp, file_counts[fp]] for fp in file_order]
                text = "\n".join(f"{fp}: {cnt}" for fp, cnt in rows) + truncated
                items = [{"파일": fp, "매칭 수": cnt} for fp, cnt in rows]
                return json.dumps({"text": text, "items": items}, ensure_ascii=False)

            # output_mode == "content" (기본): 매칭 라인 전체.
            text = "\n".join(results) + truncated
            # === 단일 통화 items(행 dict — 파일/줄번호/내용) ===
            items = [{"파일": r[0], "줄번호": r[1], "내용": r[2]} for r in match_rows]
            return json.dumps({"text": text, "items": items}, ensure_ascii=False)

        elif tool_name == "get_current_time":
            fmt = tool_input.get("format", "%Y-%m-%d %H:%M:%S")
            return datetime.now().strftime(fmt)

        elif tool_name == "ai_ask":
            # 시스템 AI 원샷 호출 — 도구·다단계 없이 경량 LLM 으로 즉답. [self:ask]
            # 능력=어휘: 앱(선언형/커스텀)이 raw fetch 없이 IBL 로 AI 를 부른다.
            prompt = (tool_input.get("prompt") or "").strip()
            if not prompt:
                return json.dumps({"success": False, "error": "prompt(지시/질문)가 필요합니다."}, ensure_ascii=False)
            # context 명시가 없으면 파이프 입력(_prev_result)을 맥락으로 받는다 → 조합 가능
            # (예: [sense:search_gnews]{...} >> [self:ask]{prompt: "요약해줘"}).
            ctx = tool_input.get("context")
            if ctx is None:
                prev = tool_input.get("_prev_result")
                if prev not in (None, ""):
                    ctx = prev if isinstance(prev, str) else json.dumps(prev, ensure_ascii=False)
            if ctx is not None and not isinstance(ctx, str):
                ctx = json.dumps(ctx, ensure_ascii=False)
            message = f"{ctx}\n\n---\n\n{prompt}" if ctx else prompt
            sys_prompt = (tool_input.get("system") or
                          "당신은 앱에 내장된 유능한 조수입니다. 사용자의 지시에 간결하고 정확하게 답하세요. "
                          "불필요한 서론·맺음말 없이 요청한 결과만 반환하세요.")
            try:
                from consciousness_agent import lightweight_ai_call
                answer = lightweight_ai_call(message, system_prompt=sys_prompt, role="background")
            except Exception as e:
                return json.dumps({"success": False, "error": f"AI 호출 실패: {e}"}, ensure_ascii=False)
            if not answer:
                return json.dumps({"success": False, "error": "AI 응답을 받지 못했습니다(모델 미설정 가능)."}, ensure_ascii=False)
            return json.dumps({"result": answer, "text": answer}, ensure_ascii=False)

        elif tool_name == "glob_files":
            pattern = tool_input["pattern"]

            # 검색 루트 결정 (우선순위: path > root_path > project_path)
            # - 절대경로(/...): 그대로 사용 → 컴퓨터 어디든 검색 가능
            # - ~ 시작: 홈 디렉토리로 확장
            # - 상대경로: project_path 기준
            # - 미지정: project_path
            raw_root = tool_input.get("path") or tool_input.get("root_path") or "."
            expanded = os.path.expanduser(raw_root)
            if os.path.isabs(expanded):
                root = expanded
            else:
                root = os.path.join(project_path, expanded)

            try:
                max_results = int(tool_input.get("max_results", 200))
            except (TypeError, ValueError):
                max_results = 200

            partial = False
            if "/" not in pattern and "**" not in pattern:
                # 재귀 basename 검색(지배적 케이스) — 바운드 walk: 정크 가지치기 + 시간예산.
                # glob.glob('~/**/*X*') 의 색인없는 홈 전체 stat(=타임아웃)을 회피.
                matches, partial = _bounded_find(root, pattern, max_results)
            else:
                # 명시 경로/패턴(`/`·`**` 포함) — 보통 앵커돼 빠름. glob 유지.
                search_pattern = pattern if "**" in pattern else f"**/{pattern}"
                try:
                    matches = glob.glob(os.path.join(root, search_pattern), recursive=True)
                except Exception as e:
                    return f"검색 오류: {e}"

            absolute_paths = sorted(os.path.abspath(m) for m in matches)
            total = len(absolute_paths)
            truncated = (total > max_results > 0) or partial
            if total > max_results > 0:
                absolute_paths = absolute_paths[:max_results]

            if absolute_paths:
                header_parts = [f"{total}개 매칭"]
                if partial:
                    header_parts.append(f"(시간예산 {int(_FIND_DEADLINE_S)}초/상한 도달 — 부분 결과. 더 좁은 path 로 재검색하거나 fs_query(OS색인) 사용 권장)")
                elif truncated:
                    header_parts.append(f"(상위 {max_results}개만 반환 — 더 많으면 max_results 또는 더 좁은 path 사용)")
                header_parts.append(f"root: {root}")
                header = " | ".join(header_parts)
                text = header + "\n" + "\n".join(absolute_paths)
                # === 공유 통화 table {columns, rows} (비파괴 ADD) ===
                # 매칭 파일 → [이름, 크기, 수정일, 경로]. 디렉터리는 크기 "".
                rows = []
                records = []  # records 통화(보편) — 파일=명사. 선언 returns:records와 일치.
                for p in absolute_paths:
                    try:
                        is_dir = os.path.isdir(p)
                        st = os.stat(p)
                        size = "" if is_dir else st.st_size
                        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    except OSError:
                        is_dir, size, mtime = False, "", ""
                    rows.append([os.path.basename(p), size, mtime, p])
                    records.append({
                        "title": os.path.basename(p) + ("/" if is_dir else ""),
                        "meta": " · ".join(x for x in [
                            ("디렉터리" if is_dir else (f"{size:,}B" if isinstance(size, int) else None)),
                            (mtime or None),
                        ] if x),
                        "summary": "",
                        "url": p,
                    })
                table = {"columns": ["이름", "크기", "수정일", "경로"], "rows": rows}
                return json.dumps({"text": text, "table": table, "items": records}, ensure_ascii=False)

            # 결과 없을 때 — 안내 메시지에 path 옵션 힌트 포함
            hint = (
                f"매칭 없음: pattern={pattern!r} root={root}\n"
                "힌트: 프로젝트 밖을 검색하려면 path 파라미터를 사용하세요. "
                '예: {pattern: "*.docx", path: "~/Desktop"} 또는 {pattern: "*.docx", path: "/Users"}'
            )
            return hint

        elif tool_name == "edit_file":
            file_path = os.path.join(project_path, _get_path(tool_input))
            scope_err = _validate_path_in_scope(file_path, project_path)
            if scope_err:
                return scope_err
            old_string = tool_input["old_string"]
            new_string = tool_input["new_string"]

            # 파일 읽기
            if not os.path.exists(file_path):
                return f"Error: 파일이 존재하지 않습니다: {_get_path(tool_input)}"

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # old_string이 파일에 있는지 확인
            count = content.count(old_string)
            if count == 0:
                return f"Error: 교체할 문자열을 찾을 수 없습니다. 파일 내용을 다시 확인하세요."
            elif count > 1:
                return f"Error: 교체할 문자열이 {count}번 발견되었습니다. 더 구체적인 문자열을 지정하세요."

            # 교체 수행
            new_content = content.replace(old_string, new_string, 1)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 절대 경로로 반환 (에이전트 간 경로 혼동 방지)
            return f"Successfully edited {os.path.abspath(file_path)}"

        elif tool_name == "run_command":
            command = tool_input.get("command", "").strip()
            timeout = min(tool_input.get("timeout", 60), 300)  # 최대 300초
            approved = tool_input.get("approved", False)

            if not command:
                return "Error: 명령어가 비어있습니다."

            # 위험한 명령어 감지 - 승인되지 않았으면 승인 요청
            if not approved and is_dangerous_command(command):
                return f"__REQUIRES_APPROVAL__:{command}"

            # 명령어 실행
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=project_path
                )

                output = ""
                if result.stdout:
                    output += result.stdout
                if result.stderr:
                    output += f"\n[stderr]\n{result.stderr}" if output else result.stderr

                if result.returncode != 0:
                    output += f"\n[exit code: {result.returncode}]"

                return output.strip() if output else "(명령어가 출력 없이 완료됨)"

            except subprocess.TimeoutExpired:
                return f"Error: 명령어 실행 시간 초과 ({timeout}초)"
            except Exception as e:
                return f"Error: 명령어 실행 실패: {e}"

        elif tool_name == "copy_path":
            _src = tool_input.get("src") or tool_input.get("source")  # src 우선(코퍼스/자연어), source 별칭
            _dst = tool_input.get("dest") or tool_input.get("destination")
            if not _src or not _dst:
                return "Error: src(원본)와 dest(대상) 경로가 필요합니다."
            src = os.path.join(project_path, os.path.expanduser(_src))
            dst = os.path.join(project_path, os.path.expanduser(_dst))
            scope_err = _validate_path_in_scope(dst, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(src):
                return f"Error: 원본이 존재하지 않습니다: {src}"

            # 대상 상위 디렉토리 생성
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

            if os.path.isdir(src):
                # 폴더 복사 (대상이 이미 있으면 삭제 후 복사)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                count = sum(len(files) for _, _, files in os.walk(dst))
                return f"폴더를 복사했습니다: {os.path.abspath(dst)} ({count}개 파일)"
            else:
                # 파일 복사
                shutil.copy2(src, dst)
                return f"파일을 복사했습니다: {os.path.abspath(dst)}"

        elif tool_name == "move_path":
            _src = tool_input.get("src") or tool_input.get("source")  # src 우선(코퍼스/자연어), source 별칭
            _dst = tool_input.get("dest") or tool_input.get("destination")
            if not _src or not _dst:
                return "Error: src(원본)와 dest(대상) 경로가 필요합니다."
            src = os.path.join(project_path, os.path.expanduser(_src))
            dst = os.path.join(project_path, os.path.expanduser(_dst))
            scope_err = _validate_path_in_scope(dst, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(src):
                return f"Error: 원본이 존재하지 않습니다: {src}"

            # 대상 상위 디렉토리 생성
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

            # 대상이 이미 있으면 삭제
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)

            shutil.move(src, dst)
            return f"이동 완료: {os.path.abspath(dst)}"

        elif tool_name == "delete_path":
            target = os.path.join(project_path, os.path.expanduser(tool_input["path"]))
            scope_err = _validate_path_in_scope(target, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(target):
                return f"Error: 경로가 존재하지 않습니다: {target}"

            abs_target = os.path.abspath(target)

            if os.path.isdir(target):
                count = sum(len(files) for _, _, files in os.walk(target))
                shutil.rmtree(target)
                return f"폴더를 삭제했습니다: {abs_target} ({count}개 파일 포함)"
            else:
                os.remove(target)
                return f"파일을 삭제했습니다: {abs_target}"

        elif tool_name == "make_directory":
            raw_path = _get_path(tool_input)
            if not raw_path:
                return json.dumps({"success": False, "error": "폴더 경로(path)가 지정되지 않았습니다."}, ensure_ascii=False)
            target = os.path.join(project_path, os.path.expanduser(raw_path))
            scope_err = _validate_path_in_scope(target, project_path)
            if scope_err:
                return scope_err
            abs_target = os.path.abspath(target)
            if os.path.isfile(abs_target):
                return json.dumps({"success": False, "error": f"같은 이름의 파일이 이미 있습니다: {abs_target}"}, ensure_ascii=False)
            existed = os.path.isdir(abs_target)
            os.makedirs(abs_target, exist_ok=True)
            return json.dumps({"success": True, "path": abs_target, "existed": existed}, ensure_ascii=False)

        elif tool_name == "propose_patch":
            # 자기개조 Floor #2: RED 개조를 worktree 격리 사본에만 제안 + 기계검증. 라이브 무변경.
            result = _propose_red_patch(
                raw_path=_get_path(tool_input),
                content=tool_input.get("content"),
                old_string=tool_input.get("old_string") or tool_input.get("old"),
                new_string=tool_input.get("new_string") or tool_input.get("new"),
                reason=tool_input.get("reason") or tool_input.get("rationale") or "",
            )
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "read_pdf":
            return _office.read_pdf(tool_input, project_path)

        elif tool_name == "read_docx":
            return _office.read_docx(tool_input, project_path)

        elif tool_name == "read_xlsx":
            return _office.read_xlsx(tool_input, project_path)

        elif tool_name == "spreadsheet":
            # [table:spreadsheet] — office_ops 로 이동. 경로 가드는 handler 소유라 주입.
            return _office.spreadsheet(tool_input, project_path, _validate_path_in_scope)

        elif tool_name == "todo_write":
            todos = tool_input.get("todos", [])
            paths = get_state_paths(project_path, agent_id)

            # 상태 저장
            state = {
                "todos": todos,
                "updated_at": datetime.now().isoformat()
            }

            with open(paths["todo"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 결과 포맷팅 (텍스트 기반, Anthropic 스타일)
            result_lines = ["Todo list updated:"]
            for i, todo in enumerate(todos, 1):
                status = todo["status"]
                if status == "in_progress":
                    result_lines.append(f"  {i}. [in_progress] {todo['activeForm']}")
                elif status == "completed":
                    result_lines.append(f"  {i}. [completed] {todo['content']}")
                else:
                    result_lines.append(f"  {i}. [pending] {todo['content']}")

            return "\n".join(result_lines)

        elif tool_name == "ask_user_question":
            # GoalEval 재실행 중에는 사용자에게 질문할 수 없음
            try:
                from thread_context import get_current_task_id
                current_task = get_current_task_id() or ""
                if current_task.startswith("goal_retry_"):
                    return (
                        "현재 평가 재실행 중이므로 사용자에게 질문할 수 없습니다. "
                        "보유한 정보만으로 최선의 답변을 작성하세요. "
                        "확실하지 않은 부분은 가정을 명시하고 진행하세요."
                    )
            except Exception:
                pass

            questions = tool_input.get("questions", [])
            paths = get_state_paths(project_path, agent_id)

            # 질문 상태 저장 (프론트엔드에서 폴링)
            state = {
                "questions": questions,
                "status": "pending",  # pending, answered
                "answers": None,
                "created_at": datetime.now().isoformat()
            }

            with open(paths["question"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 특수 마커와 함께 반환 - 프론트엔드가 질문 UI를 표시
            return "[[QUESTION_PENDING]]사용자에게 질문을 전달했습니다. 응답을 기다리는 중..."

        elif tool_name == "enter_plan_mode":
            paths = get_state_paths(project_path, agent_id)

            # 계획 모드 상태 저장
            state = {
                "active": True,
                "phase": "exploring",  # exploring, designing, reviewing, finalizing
                "entered_at": datetime.now().isoformat(),
                "plan_file": str(paths["plan_file"])
            }

            with open(paths["plan_mode"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 계획 파일 초기화
            with open(paths["plan_file"], 'w', encoding='utf-8') as f:
                f.write(f"# 구현 계획\n\n생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n## 목표\n\n(작성 중...)\n\n## 구현 단계\n\n1. \n\n## 수정할 파일\n\n- \n\n## 테스트 방법\n\n- \n")

            return "[[PLAN_MODE_ENTERED]]계획 모드로 진입했습니다. 코드를 탐색하고 구현 계획을 수립한 후 exit_plan_mode를 호출하세요."

        elif tool_name == "exit_plan_mode":
            paths = get_state_paths(project_path, agent_id)

            # 계획 모드 상태 확인
            if not paths["plan_mode"].exists():
                return "Error: 계획 모드가 활성화되어 있지 않습니다."

            with open(paths["plan_mode"], 'r', encoding='utf-8') as f:
                state = json.load(f)

            if not state.get("active"):
                return "Error: 계획 모드가 활성화되어 있지 않습니다."

            # 계획 파일 읽기
            plan_content = ""
            if paths["plan_file"].exists():
                with open(paths["plan_file"], 'r', encoding='utf-8') as f:
                    plan_content = f.read()

            # 상태 업데이트 - 승인 대기
            state["phase"] = "awaiting_approval"
            state["plan_content"] = plan_content

            with open(paths["plan_mode"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            return f"[[PLAN_APPROVAL_REQUESTED]]계획 수립이 완료되었습니다. 사용자 승인을 기다리는 중...\n\n---\n{plan_content}"

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {str(e)}"
