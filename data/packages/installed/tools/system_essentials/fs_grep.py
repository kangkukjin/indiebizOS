"""system_essentials 내용 검색(grep) 층 (2026-08-08 분리 — 1500줄 규칙)

handler.py 에서 verbatim 이동: [self:grep] 2층 검색(rg --json 고속 경로 + 파이썬
인코딩-인지 폴백) + 전수 계수(_rg_count) + grep_files 분기 본체(run).
handler 가 fs_meta 선례(_load_sibling)로 위임한다.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import time
from runtime_utils import expand_body_path  # 경로 펼침 단일 해소점 (~workspace/·~)

# fs_find.FIND_DEADLINE_S 와 동일 값 (엔진 타임아웃 전에 부분결과라도 반환)
_DEADLINE_S = 25.0

# === grep_files 내용 검색 2층 =====================================================
# ripgrep(rg) 있으면 --json 고속 경로, 없으면 파이썬 줄 스캔 폴백(윈도우 등 rg 미보장).
# ★한글(비ASCII) 패턴은 cp949 파일과 바이트 표현이 달라 rg 로는 원리적으로 못 찾으므로
#   항상 파이썬 경로(인코딩 폴백)를 탄다. ASCII 패턴은 cp949 파일에서도 바이트가 같아 rg 안전.
_GREP_SKIP_DIRS = {'.git', '.svn', '__pycache__', 'node_modules', '.venv', 'venv', '.tox', '.mypy_cache'}
_GREP_SKIP_EXTS = {'.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe', '.bin',
                   '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
                   '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv',
                   '.zip', '.gz', '.tar', '.rar', '.7z', '.bz2',
                   '.woff', '.woff2', '.ttf', '.eot', '.otf',
                   '.pdf', '.doc', '.docx', '.xls', '.xlsx',
                   '.db', '.sqlite', '.sqlite3'}
# utf-8 실패 시 cp949 재시도, 그래도 실패 시 utf-8(replace) — 옛 한글(cp949) 문서가
# UnicodeDecodeError 로 파일째 조용히 탈락하던 침묵 실패 부류 봉합(음악 태그 모지바케와 같은 계열).
_GREP_ENCODINGS = (("utf-8", "strict"), ("cp949", "strict"), ("utf-8", "replace"))


def _find_rg():
    """rg 바이너리 탐색 — 백엔드 프로세스 PATH 에 brew 경로가 없을 수 있어 관용 후보도 본다."""
    p = shutil.which("rg")
    if p:
        return p
    for cand in ("/opt/homebrew/bin/rg", "/usr/local/bin/rg", "/usr/bin/rg"):
        if os.path.exists(cand):
            return cand
    return None


_RG_BIN = _find_rg()


def _rg_grep(pattern, root, file_pattern, use_regex, max_results, max_line_chars, max_total_chars):
    """ripgrep --json 위임(고속 경로). 성공 시 (rows, search_done, hit_size_cap) —
    rows=[(절대경로, 줄번호, 내용)]. 매칭 0 은 정상 결과([], False, False).
    rg 실행 실패·패턴 문법 오류(exit 2)면 None 반환 → 호출부가 파이썬 경로로 폴백.
    바이너리는 rg 가 자동 스킵, .gitignore·숨김 파일 기본 스킵(파이썬 glob 도 dot 미매칭이라 동등).
    """
    # --sort path: 병렬 walk 의 도착 순서 복권을 제거(2026-08-08 실측 — 같은 질의 2연속이
    # 다른 100건을 반환·같은 파일 개수마저 상이). 단일 스레드가 되지만 스코프 검색엔 충분히
    # 빠르고, 상한 절단이 "임의 표본"이 아니라 "경로순 앞 N건"이라는 결정적 의미를 얻는다.
    cmd = [_RG_BIN, "--json", "--no-messages", "--sort", "path", "--max-count", str(max_results)]
    if not use_regex:
        cmd.append("-F")
    if not os.path.isfile(root) and file_pattern and file_pattern != "**/*":
        cmd += ["--glob", file_pattern]
    for d in _GREP_SKIP_DIRS:
        cmd += ["--glob", f"!**/{d}/**"]
    # svg 는 텍스트라 rg 가 검색해버림 — 파이썬 경로의 SKIP_EXTS 와 의미 정렬(나머지는 바이너리 자동 스킵)
    cmd += ["--glob", "!*.svg", "--regexp", pattern, root]
    rows, total_chars = [], 0
    search_done = hit_size_cap = False
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace")
    except OSError:
        return None
    deadline = time.time() + _DEADLINE_S
    try:
        for raw in proc.stdout:
            if time.time() > deadline:
                search_done = True
                break
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get("type") != "match":
                continue
            d = ev.get("data") or {}
            fp = (d.get("path") or {}).get("text")
            if not fp:
                continue  # 비-utf8 파일명(base64 통보)은 드묾 — 생략
            snippet = ((d.get("lines") or {}).get("text") or "").rstrip()
            rows.append((os.path.abspath(fp), d.get("line_number") or 0, snippet))
            total_chars += min(len(snippet), max_line_chars)
            if len(rows) >= max_results or total_chars >= max_total_chars:
                search_done = True
                hit_size_cap = total_chars >= max_total_chars
                break
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    if not rows and proc.returncode == 2:
        return None  # 패턴 문법 등 rg 오류 — 파이썬 경로가 컴파일 폴백까지 처리
    return rows, search_done, hit_size_cap


def _rg_count(pattern, root, file_pattern, use_regex):
    """rg --count-matches 전수 계수(2026-08-08, ⑥′ 수리의 핵).

    내용을 반환하지 않으므로 토큰 상한이 필요 없다 — 표본이 아니라 **전수**.
    count/files_with_matches 모드의 정답 소스이자, content 모드의 진짜 total 공급원.
    반환: {절대경로: 매칭수} (경로 정렬 = 결정적) 또는 None(실행 실패 → 호출부 폴백).
    """
    # --with-filename: 단일 파일 대상이면 rg 가 "path:N" 대신 "N" 만 내 아래 파싱이 빈 dict 를
    # 만들고, {} 는 None(미가용) 이 아니라 "전수 0건" 으로 읽혀 "매칭 0건 중 2건만 표시"
    # 같은 거짓 신고가 났다(2026-08-21 라이브 실측). 항상 파일명 접두를 강제.
    cmd = [_RG_BIN, "--count-matches", "--with-filename", "--no-messages"]
    if not use_regex:
        cmd.append("-F")
    if not os.path.isfile(root) and file_pattern and file_pattern != "**/*":
        cmd += ["--glob", file_pattern]
    for d in _GREP_SKIP_DIRS:
        cmd += ["--glob", f"!**/{d}/**"]
    cmd += ["--glob", "!*.svg", "--regexp", pattern, root]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=_DEADLINE_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 2:  # 패턴 오류 등 — 폴백 (1=매칭 없음, 정상)
        return None
    counts = {}
    for line in (proc.stdout or "").splitlines():
        p, _, c = line.rpartition(":")
        if p and c.isdigit():
            counts[os.path.abspath(p)] = int(c)
    return dict(sorted(counts.items()))


def _py_grep(pattern, root, file_pattern, use_regex, max_results, max_line_chars, max_total_chars):
    """파이썬 스캔 경로 — rg 없거나 한글(비ASCII) 패턴일 때.
    파일별로 _GREP_ENCODINGS 순서로 처음부터 재시도(부분 커밋 없음=중복 방지).
    반환 (rows, search_done, hit_size_cap, regex_error) — rows=[(절대경로, 줄번호, 내용)].
    """
    regex_pattern, regex_error = None, None
    if use_regex:
        # 잘못된 정규식(짝 안 맞는 괄호 등)은 크래시 대신 리터럴 검색으로 폴백한다 —
        # 절대 크래시도 침묵 실패도 만들지 않는다. 폴백 시 결과에 안내를 덧붙인다.
        try:
            regex_pattern = re.compile(pattern)
        except re.error as e:
            regex_error = str(e)
            use_regex = False
    # 검색할 파일 목록 (불필요 파일 필터링). root 가 단일 파일이면 그 파일만 검색한다 —
    # file_pattern 기본값 '**/*' 를 파일 경로에 join 하면 빈 목록 → 조용한 No matches 버그.
    # 사용자가 직접 지정한 파일이므로 SKIP 필터도 적용하지 않는다.
    if os.path.isfile(root):
        files = [root]
    else:
        # ★글롭 방언 정렬(2026-08-21): rg --glob 은 gitignore 방언이라 '*.py'(구분자 없는
        # basename 글롭)가 전 깊이에서 매칭되는데, 파이썬 glob 은 recursive=True 여도
        # '**' 가 없으면 최상위만 봤다 — 같은 질의가 어느 층을 타느냐(한글 패턴·rg 부재·
        # rg 오류)에 따라 모집단이 조용히 갈리던 침묵 부분결과. 구분자·'**' 없는 패턴은
        # '**/' 접두로 재귀 정렬. 구분자 있는 패턴('sub/*.py')은 앵커 의미 보존.
        fp = file_pattern
        if "/" not in fp and os.sep not in fp and "**" not in fp:
            fp = os.path.join("**", fp)
        files = glob.glob(os.path.join(root, fp), recursive=True)
        files = [
            f for f in files
            if os.path.isfile(f)
            and os.path.splitext(f)[1].lower() not in _GREP_SKIP_EXTS
            and not any(skip in f.split(os.sep) for skip in _GREP_SKIP_DIRS)
        ]

    def _scan_one(fp):
        """한 파일 → [(줄번호, 내용)] (파일당 max_results 상한)."""
        for enc, err in _GREP_ENCODINGS:
            found = []
            try:
                with open(fp, 'r', encoding=enc, errors=err) as f:
                    for ln, line in enumerate(f, 1):
                        matched = regex_pattern.search(line) if use_regex else (pattern in line)
                        if matched:
                            found.append((ln, line.rstrip()))
                            if len(found) >= max_results:
                                break
                return found
            except UnicodeDecodeError:
                continue
            except (PermissionError, OSError):
                return []
        return []

    rows, total_chars = [], 0
    search_done = hit_size_cap = False
    for fp in files:
        for ln, snippet in _scan_one(fp):
            rows.append((os.path.abspath(fp), ln, snippet))
            total_chars += min(len(snippet), max_line_chars)
            if len(rows) >= max_results or total_chars >= max_total_chars:
                search_done = True
                hit_size_cap = total_chars >= max_total_chars
                break
        if search_done:
            break
    return rows, search_done, hit_size_cap, regex_error


def run(tool_input: dict, project_path: str) -> str:
    """[self:grep] 분기 본체 — handler.execute 의 grep_files 에서 위임."""
    pattern = tool_input["pattern"]
    file_pattern = tool_input.get("file_pattern", "**/*")
    # 검색 루트: path > root_path > project_path (glob_files 와 동일 규칙).
    # ★과거엔 root_path 만 읽어 src 가 광고하는 path 가 조용히 무시됐다(param 불일치 버그).
    raw_root = tool_input.get("path") or tool_input.get("root_path") or "."
    expanded = expand_body_path(raw_root)
    root = expanded if os.path.isabs(expanded) else os.path.join(project_path, expanded)
    # ★존재하지 않는 경로 = 판정 불능(2026-08-21, ep1357): rg 도 파이썬 glob 도 없는 루트에서
    # 조용히 0건을 내 "패턴이 안 잡힘"과 "경로 자체가 없음"이 구분되지 않았다 — 시스템 AI 가
    # 경로를 잘못 추측하고도 침묵 0건을 받아 거짓 단정(B8 부류)으로 흘렀다. 두 검색 층보다
    # 앞에서 한 번 가드하므로 rg/파이썬 어느 층을 타든 같은 신고. 형제 op(read/move/delete)의
    # "경로가 존재하지 않습니다" 규약·P1~P20 시끄러운 실패 계약과 정렬(success:false + error).
    if not os.path.exists(root):
        msg = f"경로가 존재하지 않습니다: {raw_root}"
        if root != raw_root:
            msg += f" (해석된 절대경로: {root})"
        msg += " — path 를 확인하세요(파일 위치가 불확실하면 [self:file_find] 로 먼저 찾기)."
        return json.dumps({"success": False, "error": msg, "items": [], "total": 0,
                           "total_files": 0, "truncated": False, "text": msg},
                          ensure_ascii=False)
    # 정규식이 기본이다(grep/ripgrep·Claude Grep 습관과 동일, src desc도 "정규식"으로 광고).
    # 과거엔 기본이 fixed-string('a|b' 를 리터럴로 취급)이라 alternation·메타문자가
    # 조용히 No matches 가 되는 silent-failure 함정이었다. regex=false 로 리터럴 강제 가능.
    use_regex = tool_input.get("regex", True)
    # output_mode (Claude Grep 습관): content(매칭 라인, 기본) / files_with_matches(파일 목록) /
    # count(파일별 매칭 수). 알 수 없는 값은 content 로 폴백.
    output_mode = (tool_input.get("output_mode") or "content").lower()
    if output_mode not in ("content", "files_with_matches", "count"):
        output_mode = "content"
    # max_results: 파라미터화(2026-08-08 ⑥′ — 옛 100 하드코딩은 올릴 길이 없었다)
    try:
        # ★정본 limit(별칭 max_results — ibl_actions.yaml aliases). 관문이 정규화하지만
        #   직접 호출도 있으니 둘 다 읽는다.
        max_results = int(tool_input.get("limit", tool_input.get("max_results", 100)))
    except (TypeError, ValueError):
        max_results = 100
    max_results = max(1, min(max_results, 2000))  # clamp-ok: 표본 상한 2000 — 초과분은 total/truncated 로 이미 신고한다
    # 줄 수만으로는 토큰 폭발을 못 막는다 — 미니파이드/JSON 한 줄이 수만 자면
    # 100줄로도 수십만 자가 된다. 줄 길이·총량 상한을 함께 둔다.
    MAX_LINE_CHARS = 500       # 한 줄 매칭 내용 상한 (초과 시 잘라 표시)
    MAX_TOTAL_CHARS = 40_000   # content 누적 총량 상한 (초과 시 검색 중단 + 좁히기 안내)

    # === 전수 계수 패스(⑥′ 수리의 핵) — 내용 없이 매칭 수만: 상한 불요·전수·결정적 ===
    # count/files_with_matches 는 이걸로 **정답**이 되고(옛날엔 잘린 100건 위에서 세어
    # 실행마다 다른 답), content 는 표본이되 진짜 total 을 봉투에 실을 수 있게 된다.
    full_counts = None  # {절대경로: 매칭수} 전수, 경로순 — None 이면 미가용(폴백)
    if _RG_BIN and pattern.isascii():
        full_counts = _rg_count(pattern, root, file_pattern, use_regex)

    # === 2층 검색: rg 고속 경로 → 파이썬 인코딩-인지 경로 (_rg_grep/_py_grep 참조) ===
    # 한글(비ASCII) 패턴은 cp949 파일을 rg 가 원리적으로 못 찾으므로 파이썬 경로로.
    raw_rows = None
    regex_error = None
    if _RG_BIN and pattern.isascii():
        rg_out = _rg_grep(pattern, root, file_pattern, use_regex,
                          max_results, MAX_LINE_CHARS, MAX_TOTAL_CHARS)
        if rg_out is not None:
            raw_rows, search_done, hit_size_cap = rg_out
    if raw_rows is None:
        raw_rows, search_done, hit_size_cap, regex_error = _py_grep(
            pattern, root, file_pattern, use_regex,
            max_results, MAX_LINE_CHARS, MAX_TOTAL_CHARS)

    results = []
    match_rows = []  # 공유 통화 table용 [파일, 줄번호, 내용]
    file_counts = {}  # output_mode=files_with_matches/count용 {파일: 매칭 수}
    file_order = []   # 파일 첫 등장 순서 보존
    for abs_fp, line_num, snippet in raw_rows:
        rel_path = os.path.relpath(abs_fp, project_path)
        if len(snippet) > MAX_LINE_CHARS:
            snippet = snippet[:MAX_LINE_CHARS] + " …(줄 잘림)"
        results.append(f"{rel_path}:{line_num}: {snippet}")
        match_rows.append([rel_path, line_num, snippet])
        if rel_path not in file_counts:
            file_order.append(rel_path)
        file_counts[rel_path] = file_counts.get(rel_path, 0) + 1

    regex_note = ""
    if regex_error:
        regex_note = (f"\n(주의: 정규식 '{pattern}' 컴파일 실패 [{regex_error}] → "
                      f"리터럴 문자열로 검색했습니다. 의도가 정규식이면 패턴을 고치세요.)")

    if not results and not full_counts:
        # 0건도 통화 봉투로(2026-08-08 ⑯) — 맨 문자열은 ??(폴백)의 빈손 술어와
        # 변환자가 구조로 인식할 수 없다. 사람용 안내는 text 에 그대로.
        return json.dumps({"success": True, "items": [], "total": 0, "total_files": 0,
                           "truncated": False,
                           "text": f"No matches found for: {pattern}{regex_note}"},
                          ensure_ascii=False)

    # 진짜 총량 — 전수 계수가 있으면 그것, 없으면 관측치(+truncated 신호)
    grand_total = sum(full_counts.values()) if full_counts is not None else len(match_rows)
    n_files = len(full_counts) if full_counts is not None else len(file_order)
    truncated_flag = bool(search_done) or (full_counts is not None and grand_total > len(match_rows))

    if search_done and hit_size_cap:
        truncated = ("\n... (결과가 너무 큽니다 — root_path/file_pattern 으로 범위를 좁히거나, "
                     "output_mode='files_with_matches'/'count' 로 먼저 분포를 보세요.)")
    elif truncated_flag and output_mode == "content":
        truncated = f"\n... (매칭 {grand_total}건 중 {len(match_rows)}건만 표시 — limit 로 조절(별칭 max_results, 최대 2000), 집계는 output_mode='count' 가 전수)"
    else:
        truncated = ""
    truncated += regex_note

    if output_mode == "files_with_matches":
        # 매칭된 파일 목록. 전수 계수 가용 시 = 전 파일(표본 아님).
        if full_counts is not None:
            file_order = [os.path.relpath(p, project_path) for p in full_counts]
        text = "\n".join(file_order) + (regex_note if full_counts is not None else truncated)
        items = [{"파일": fp} for fp in file_order]
        return json.dumps({"text": text, "items": items, "total": grand_total,
                           "total_files": n_files,
                           "truncated": False if full_counts is not None else truncated_flag},
                          ensure_ascii=False)

    if output_mode == "count":
        # 파일별 매칭 수 — 전수 계수 가용 시 **전수·결정적**(2026-08-08 이전엔 잘린
        # 100건 위에서 세어, 같은 질의가 실행마다 다른 답을 냈다).
        if full_counts is not None:
            pairs = [(os.path.relpath(p, project_path), c) for p, c in full_counts.items()]
        else:
            pairs = [(fp, file_counts[fp]) for fp in file_order]
        text = "\n".join(f"{fp}: {cnt}" for fp, cnt in pairs) + (regex_note if full_counts is not None else truncated)
        items = [{"파일": fp, "매칭 수": cnt} for fp, cnt in pairs]
        return json.dumps({"text": text, "items": items, "total": grand_total,
                           "total_files": n_files,
                           "truncated": False if full_counts is not None else truncated_flag},
                          ensure_ascii=False)

    # output_mode == "content" (기본): 매칭 라인 (상한 내 표본, 경로순 결정적).
    text = "\n".join(results) + truncated
    # === 단일 통화 items(행 dict — 파일/줄번호/내용) + 정직한 절단 신고(⑥′) ===
    items = [{"파일": r[0], "줄번호": r[1], "내용": r[2]} for r in match_rows]
    return json.dumps({"text": text, "items": items, "total": grand_total,
                       "total_files": n_files, "truncated": truncated_flag},
                      ensure_ascii=False)
