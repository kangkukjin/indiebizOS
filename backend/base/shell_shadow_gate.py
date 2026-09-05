"""shell_shadow_gate.py — 셸 그림자 관문 (2026-09-05, ep2862·2866 실측 뒤 근본 처방 1번).

뿌리: "IBL 등가물이 있는 일을 Bash 로 하지 마라"는 규칙이 **산문**으로만 있었다(claude_code.TOOL_POLICY).
두 주행에서 Bash 27건 중 18건이 grep·sed -n·cat 이었고, 대량 편집은 /tmp 파이썬 스크립트로
갔다 — 전부 `[self:grep]`·`[self:read]`·`[self:edit]` 의 **그림자**라 해마·타입검사·쓰기 원장 밖이었다.
Read·Grep 네이티브를 이름 골라 하드 차단했더니 물이 Bash 로 옮겨간 것뿐이다(손으로 고른 스윕은 샌다).

처방: 관문표를 **어휘 단일 소스에서 파생**한다. 각 낱말 yaml 의 `shell_shadow:` 블록(heads·argmap…)을
빌드가 `data/shell_shadow.json` 으로 파생하고, 이 모듈이 그 표 하나로
  ① Claude Code 실행기의 PreToolUse 훅(__main__ — Bash·Write·Edit 호출 전에 판정)과
  ② in-process 프로바이더의 run_command(handler.py)
두 자리에서 같은 판정을 내린다. 거절문은 **그 명령을 옮긴 IBL 문장**을 돌려준다 — 다음 걸음이 IBL 안에 있게.
새 낱말이 `shell_shadow:` 를 선언하면 관문이 저절로 넓어진다(코드에 낱말 이름 없음 — 헌법 '표준/사전 경계').

통과(셸의 몫): git·pytest·빌드·등록 스크립트·프로세스 조회·파이프 안의 필터(stdin 을 받는 grep/head 등)·
임시 폴더(/tmp·$TMPDIR) 안의 읽기/쓰기(셸 코드 루프의 짝).

★잎 모듈(표준 라이브러리만) — 훅은 Bash 호출마다 새 프로세스로 뜨므로 기동 비용이 곧 왕복 비용이다.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE_REL = os.path.join("data", "shell_shadow.json")

#: 파이프라인을 가르는 토큰(shlex punctuation_chars 가 낸다)
_SEG_OPS = {"&&", "||", ";", "|", "|&", "&", "\n"}
_REDIRECT_OPS = {">", ">>"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"sudo", "env", "command", "time", "nohup", "exec", "builtin"}
_RANGE_SCRIPT_RE = re.compile(r"^(\d+),(\d+)\s*p$")
_SINGLE_LINE_SCRIPT_RE = re.compile(r"^(\d+)\s*p$")
#: 인라인 파이썬(히어독·-c) — 본문이 파일을 쓰면 [self:edit]/[self:write] 의 그림자
_PY_INLINE_RE = re.compile(r"\bpython[0-9.]*(?:\.exe)?\s+(?:-\s*<<|-c\s|<<|-\s*$)", re.M)
_PY_WRITE_RE = re.compile(
    r"open\([^)]*['\"][wax]\+?b?['\"]|\.write_text\(|\.write_bytes\(|\.writelines\(|"
    r"(?<!stdout)(?<!stderr)(?<!sys\.stdout)\.write\(|os\.remove\(|os\.unlink\(|\.unlink\(|"
    r"shutil\.(?:rmtree|move|copy\w*)\(|os\.rename\(|os\.replace\(|os\.makedirs\(|\.rename\(|\.replace_text\(")
_PY_HEADS = re.compile(r"^python[0-9.]*(?:\.exe)?$")
_MAX_SCRIPT_SCAN = 200_000


# ---------------------------------------------------------------- 표
def load_table(root: Optional[str] = None) -> Dict[str, Any]:
    """`data/shell_shadow.json` 을 읽는다 — 없으면 빈 표(관문 없음 = 파생물이 아직 없는 몸)."""
    base = root or _ROOT
    path = os.path.join(base, TABLE_REL)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"shadows": {}}
    return data if isinstance(data, dict) else {"shadows": {}}


def _index(table: Dict[str, Any]) -> Tuple[Dict[str, List[Tuple[str, Optional[str]]]], Dict[str, str], Dict[str, str]]:
    """head → [(word, 필수 flag|None)], native 도구 → word, kind(redirect/python_write) → word."""
    heads: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    natives: Dict[str, str] = {}
    kinds: Dict[str, str] = {}
    for word, spec in (table.get("shadows") or {}).items():
        if not isinstance(spec, dict):
            continue
        for h in spec.get("heads") or []:
            parts = str(h).split()
            if not parts:
                continue
            heads.setdefault(parts[0], []).append((word, parts[1] if len(parts) > 1 else None))
        for n in spec.get("native") or []:
            natives[str(n)] = word
        if spec.get("redirect"):
            kinds["redirect"] = word
        if spec.get("python_write"):
            kinds["python_write"] = word
    # flag 있는 머리(sed -i)가 flag 없는 머리보다 먼저 판정되게
    for h in heads:
        heads[h].sort(key=lambda t: t[1] is None)
    return heads, natives, kinds


# ---------------------------------------------------------------- 경로 판정
def _temp_roots() -> List[str]:
    roots = ["/tmp", "/private/tmp", "/var/folders", "/dev", "/proc"]
    for cand in (tempfile.gettempdir(), os.environ.get("TMPDIR"), os.environ.get("TEMP"), os.environ.get("TMP")):
        if cand:
            roots.append(cand)
    out = []
    for r in roots:
        try:
            out.append(os.path.realpath(r))
        except OSError:
            out.append(r)
    return out


def is_exempt_path(p: str, cwd: Optional[str] = None) -> bool:
    """임시 폴더·장치 파일이면 셸의 몫(셸 코드 루프의 짝). 그 밖의 모든 실경로는 낱말의 몫."""
    if not p or p in ("-", "&", "|"):
        return True
    if p.startswith("~"):
        p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.join(cwd or os.getcwd(), p)
    try:
        real = os.path.realpath(p)
    except OSError:
        real = os.path.abspath(p)
    for r in _temp_roots():
        if real == r or real.startswith(r.rstrip(os.sep) + os.sep):
            return True
    return False


# ---------------------------------------------------------------- 토큰화
_HEREDOC_RE = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")


def _tokenize(command: str) -> List[str]:
    """줄 단위로 토큰화한다 — 줄바꿈은 조각 경계, 히어독 본문(<<TAG … TAG)은 인자가 아니라 버린다.
    (ep2862 꼴 `cat > /tmp/x.py <<'EOF' … EOF` 다음 줄의 `python3 /tmp/x.py` 가 머리로 보여야 한다.)"""
    out: List[str] = []
    lines = command.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HEREDOC_RE.search(line)
        tag = m.group(1) if m else None
        lex = shlex.shlex(line, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        try:
            toks = list(lex)
        except ValueError:
            toks = line.split()   # 따옴표 불균형 — 관대한 공백 분할
        for t in toks:
            # punctuation_chars 는 '2>&1' 을 '2', '>&', '1' 로 낼 수 있다 — 연산자 정규화
            if t in ("&&", "||", ";", "|", "|&", "&", ">", ">>", "<", "<<", "<<<", ">&", "&>"):
                out.append(">" if t in (">&", "&>") else t)
            elif t.startswith(("&&", "||", ";;")):
                out.append(t[:2])
            else:
                out.append(t)
        out.append("\n")
        i += 1
        if tag:
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
            i += 1  # 종결 TAG 줄
    return out


def _segments(tokens: List[str]) -> List[Tuple[List[str], bool]]:
    """파이프라인 조각 [(tokens, stdin_from_pipe)]."""
    segs: List[Tuple[List[str], bool]] = []
    cur: List[str] = []
    piped = False
    for t in tokens:
        if t in _SEG_OPS:
            if cur:
                segs.append((cur, piped))
            cur = []
            piped = t in ("|", "|&")
        else:
            cur.append(t)
    if cur:
        segs.append((cur, piped))
    return segs


def _strip_wrappers(seg: List[str]) -> List[str]:
    i = 0
    while i < len(seg) and (_ENV_ASSIGN_RE.match(seg[i]) or seg[i] in _WRAPPERS):
        i += 1
        if i < len(seg) and seg[i - 1] == "env" and seg[i].startswith("-"):
            i += 1  # env -u NAME
            if i < len(seg) and not seg[i].startswith("-") and "=" not in seg[i] and seg[i - 1] in ("-u", "--unset"):
                i += 1
    return seg[i:]


def _split_redirects(seg: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """(명령 토큰, 쓰기 리다이렉트 대상들, 히어독 표식 뒤 토큰들)."""
    cmd: List[str] = []
    writes: List[str] = []
    i = 0
    while i < len(seg):
        t = seg[i]
        if t in _REDIRECT_OPS:
            if i + 1 < len(seg):
                writes.append(seg[i + 1])
                i += 2
                continue
            i += 1
            continue
        if t in ("<", "<<", "<<<"):
            # 히어독 본문은 명령 인자가 아니다 — 표식 뒤는 버린다
            if t == "<<":
                break
            i += 2
            continue
        m = re.match(r"^(\d)?(>>?)(.+)$", t)
        if m and m.group(2) and m.group(3) and not t.startswith("-"):
            writes.append(m.group(3))
            i += 1
            continue
        cmd.append(t)
        i += 1
    return cmd, writes, seg[i:]


# ---------------------------------------------------------------- 인자 → IBL 문장
def _q(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_q(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def _render(word: str, params: Dict[str, Any], spec: Dict[str, Any]) -> str:
    body = ", ".join(f"{k}: {_q(v)}" for k, v in params.items() if v not in (None, ""))
    return f"[{word}]{{{body}}}"


def _apply_argmap(args: List[str], spec: Dict[str, Any], head: str) -> Tuple[Dict[str, Any], List[str]]:
    """셸 인자를 낱말 param 으로 — argmap(데이터)이 정한다. 반환 (params, 경로로 읽힌 인자들).

    argmap 어휘: positional(순서 param, `_`=버림) · positional_by_head/flags_by_head(머리별 덮어쓰기) ·
    flags{"-x": param | param=값 | _} · range_script[start,end](sed 'A,Bp') · path_params · skeleton(빠진 필수 자리표)."""
    argmap = spec.get("argmap") or {}
    positional: List[str] = list((argmap.get("positional_by_head") or {}).get(head) or argmap.get("positional") or [])
    flags: Dict[str, str] = dict(argmap.get("flags") or {})
    flags.update((argmap.get("flags_by_head") or {}).get(head) or {})
    value_flags = {f for f, p in flags.items() if "=" not in str(p)}
    range_params = argmap.get("range_script") or []
    path_params = set(argmap.get("path_params") or [p for p in positional if p in ("path", "src", "dest")])
    params: Dict[str, Any] = {}
    pos_vals: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos_vals.extend(args[i + 1:])
            break
        if a.startswith("-") and len(a) > 1:
            key, val = a, None
            if "=" in a and a.startswith("--"):
                key, val = a.split("=", 1)
            if key in flags:
                target = str(flags[key])
                if "=" in target:
                    k, v = target.split("=", 1)
                    params[k] = {"true": True, "false": False}.get(v, v)
                else:
                    if val is None and i + 1 < len(args):
                        val = args[i + 1]
                        i += 1
                    if val is not None and target != "_":
                        params[target] = int(val) if val.isdigit() else val
            elif key in value_flags:
                i += 1
            elif len(a) > 1 and not a.startswith("--") and a[1:].isdigit() and "-n" in flags and "=" not in str(flags["-n"]):
                params[str(flags["-n"])] = int(a[1:])   # -40 (head/tail 옛 표기) = -n 40
            elif len(a) > 2 and not a.startswith("--") and a[:2] in value_flags and a[2:].isdigit():
                params[str(flags[a[:2]])] = int(a[2:])  # -A3 (flag 에 값이 붙은 꼴)
            i += 1
            continue
        if a != "":
            pos_vals.append(a)
        i += 1
    # 줄 범위 스크립트(sed -n '12,40p')
    if range_params and pos_vals:
        m = _RANGE_SCRIPT_RE.match(pos_vals[0])
        m1 = _SINGLE_LINE_SCRIPT_RE.match(pos_vals[0])
        if m:
            params[range_params[0]] = int(m.group(1))
            params[range_params[1]] = int(m.group(2))
            pos_vals = pos_vals[1:]
        elif m1:
            params[range_params[0]] = int(m1.group(1))
            params[range_params[1]] = int(m1.group(1))
            pos_vals = pos_vals[1:]
    paths: List[str] = []
    for idx, name in enumerate(positional):
        if idx >= len(pos_vals):
            break
        if name == "_":
            continue
        if idx == len(positional) - 1 and name in path_params and len(pos_vals) > len(positional):
            # 마지막 positional 이 경로면 남는 인자 전부 경로(grep pat a b c)
            vals = pos_vals[idx:]
            params[name] = vals[0] if len(vals) == 1 else vals
            paths.extend(vals)
        else:
            params[name] = pos_vals[idx]
            if name in path_params:
                paths.append(pos_vals[idx])
    for k, v in (argmap.get("skeleton") or {}).items():
        params.setdefault(k, v)
    return params, paths


# ---------------------------------------------------------------- 판정
def _hint_tail(word: str, spec: Dict[str, Any]) -> str:
    extra = [p for p in (spec.get("params") or [])]
    tail = f" — execute_ibl 로 실행한다. 다른 param: {', '.join(extra)}." if extra else " — execute_ibl 로 실행한다."
    return tail + " 셸은 IBL 낱말이 없는 일(git·pytest·빌드·등록 스크립트 실행·프로세스 조회)에만. 결과가 잘리면 셸로 갈아타지 말고 같은 낱말의 limit·범위 param 으로 좁혀라."


def _deny(shown: str, word: str, sentence: str, spec: Dict[str, Any]) -> str:
    return (f"셸 그림자 거절 — `{shown}` 은(는) [{word}] 로 표현되는 일입니다. IBL 로:\n  {sentence}"
            + _hint_tail(word, spec))


def _judge_python(command: str, cmd: List[str], cwd: Optional[str], kinds: Dict[str, str],
                  table: Dict[str, Any]) -> Optional[str]:
    """인라인 파이썬(히어독·-c)·임시 폴더 스크립트가 파일을 쓰면 편집 낱말의 그림자."""
    word = kinds.get("python_write")
    if not word:
        return None
    spec = (table.get("shadows") or {}).get(word) or {}
    head = os.path.basename(cmd[0]) if cmd else ""
    if not _PY_HEADS.match(head):
        return None
    inline = bool(_PY_INLINE_RE.search(command)) or (len(cmd) >= 2 and cmd[1] in ("-", "-c"))
    body = ""
    if inline:
        body = command
    elif len(cmd) >= 2 and not cmd[1].startswith("-") and is_exempt_path(cmd[1], cwd):
        # /tmp 에 써 둔 스크립트를 돌린다 — 본문을 본다(ep2862: cat > /tmp/x.py && python3 /tmp/x.py --apply)
        p = cmd[1] if os.path.isabs(cmd[1]) else os.path.join(cwd or os.getcwd(), cmd[1])
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                body = f.read(_MAX_SCRIPT_SCAN)
        except OSError:
            # 같은 명령 안에서 히어독으로 막 쓰고 바로 돌리는 꼴 — 파일이 아직 없으니 명령 본문이 곧 스크립트
            body = command if "<<" in command else ""
    if body and _PY_WRITE_RE.search(body):
        # 되돌림 문장은 낱말이 데이터로 준다(python_write_hint) — 관문 코드에 낱말 이름을 두지 않는다
        sentence = str(spec.get("python_write_hint") or _render(word, dict((spec.get("argmap") or {}).get("skeleton") or {}), spec))
        shown = "python … (파일을 쓰는 인라인·임시 스크립트)"
        return (f"셸 그림자 거절 — `{shown}` 은 [{word}] 의 그림자입니다(쓰기 원장·RED 격리·해마 밖). IBL 로:\n  {sentence}"
                + _hint_tail(word, spec))
    return None


def judge_shell(command: str, cwd: Optional[str] = None, root: Optional[str] = None,
                table: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """셸 명령이 IBL 낱말의 그림자면 거절문(그 명령을 옮긴 IBL 문장 포함), 아니면 None."""
    if not command or not command.strip():
        return None
    table = table if table is not None else load_table(root)
    shadows = table.get("shadows") or {}
    if not shadows:
        return None
    heads, _natives, kinds = _index(table)
    tokens = _tokenize(command)
    for seg, piped in _segments(tokens):
        seg = _strip_wrappers(seg)
        if not seg:
            continue
        cmd, writes, _rest = _split_redirects(seg)
        if not cmd:
            continue
        head = os.path.basename(cmd[0])
        if head == "cd":
            continue
        # ① 리다이렉션으로 파일을 쓴다 → 쓰기 낱말의 그림자
        w_word = kinds.get("redirect")
        if w_word:
            for target in writes:
                if target in ("/dev/null", "&1", "&2", "1", "2") or target.startswith("&"):
                    continue
                if not is_exempt_path(target, cwd):
                    spec = shadows.get(w_word) or {}
                    sentence = f"[{w_word}]{{path: {_q(target)}, content: \"<내용>\"}}"
                    return _deny(f"… > {target}", w_word, sentence, spec)
        # ② 파일을 쓰는 인라인 파이썬·임시 스크립트
        py = _judge_python(command, cmd, cwd, kinds, table)
        if py:
            return py
        # ③ 머리 낱말
        cands = heads.get(head)
        if not cands:
            continue
        args = cmd[1:]
        flagset = {a for a in args if a.startswith("-")}
        for word, need_flag in cands:
            if need_flag and not any(a == need_flag or (a.startswith(need_flag) and not a.startswith("--")) for a in flagset):
                continue
            spec = shadows.get(word) or {}
            params, paths = _apply_argmap(args, spec, head)
            argmap = spec.get("argmap") or {}
            cwd_default = bool(argmap.get("cwd_default")) or head in (argmap.get("cwd_default_heads") or [])
            if not paths:
                if piped and not cwd_default:
                    break  # 파이프 안의 필터(git diff | grep …) — 셸의 몫
                if cwd_default or any(a in ("-r", "-R", "--recursive") for a in flagset):
                    paths = ["."]
                    for p in (argmap.get("positional_by_head") or {}).get(head) or argmap.get("positional") or []:
                        if p in ("path", "src") and p not in params:
                            params[p] = "."
                            break
                else:
                    break  # stdin 을 읽는 cat/head/tail — 셸 파이프의 몫
            if all(is_exempt_path(p, cwd) for p in paths):
                break
            sentence = _render(word, params, spec)
            shown = " ".join(cmd[:6]) + (" …" if len(cmd) > 6 else "")
            return _deny(shown, word, sentence, spec)
    return None


def judge_native(tool_name: str, tool_input: Dict[str, Any], cwd: Optional[str] = None,
                 root: Optional[str] = None, table: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """네이티브 Write/Edit 류 — 대상 경로가 임시 폴더 밖이면 쓰기·편집 낱말의 그림자."""
    table = table if table is not None else load_table(root)
    _heads, natives, _kinds = _index(table)
    word = natives.get(str(tool_name))
    if not word:
        return None
    path = (tool_input or {}).get("file_path") or (tool_input or {}).get("notebook_path") or (tool_input or {}).get("path")
    if not path or is_exempt_path(str(path), cwd):
        return None
    spec = (table.get("shadows") or {}).get(word) or {}
    params: Dict[str, Any] = {"path": str(path)}
    for k, v in ((spec.get("argmap") or {}).get("skeleton") or {}).items():
        params.setdefault(k, v)
    return _deny(f"{tool_name}({path})", word, _render(word, params, spec), spec)


def judge_hook_event(event: Dict[str, Any], root: Optional[str] = None) -> Optional[str]:
    """Claude Code PreToolUse 이벤트 한 건 → 거절문 또는 None."""
    name = str(event.get("tool_name") or "")
    inp = event.get("tool_input") or {}
    cwd = event.get("cwd")
    table = load_table(root)
    if name == "Bash":
        return judge_shell(str(inp.get("command") or ""), cwd=cwd, root=root, table=table)
    return judge_native(name, inp, cwd=cwd, root=root, table=table)


def main(argv: Optional[List[str]] = None) -> int:
    """훅 진입: stdin 의 PreToolUse JSON 을 판정한다. 거절이면 JSON deny(+exit 2 폴백) — 사유가 모델에게 간다."""
    argv = list(sys.argv[1:] if argv is None else argv)
    root = argv[0] if argv else None
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    try:
        verdict = judge_hook_event(event, root=root)
    except Exception as e:  # noqa: BLE001 — 관문 자체의 고장은 셸을 막지 않되 흔적은 남긴다
        sys.stderr.write(f"[shell_shadow_gate] 판정 오류(통과): {e}\n")
        return 0
    if not verdict:
        return 0
    sys.stderr.write(verdict + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
