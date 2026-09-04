"""
hippo_tree.py — 실행기억(해마 용례)의 **주제 가지 트리 문서** + 지도(목차)

2026-09-03 사용자 판정: "같은 방식으로 실행기억도 — 주제별 폴더로 만들어 서치할 수 있지 않을까" → 추천대로 착수.

원리(심층 기억 memory_tree 와 같은 배치, 다른 점 하나)
- 용례(의도 → IBL 문장) 평면 표 위에 **주제 가지**(`topic` 컬럼, `보고서/부동산` 꼴)를 얹는다.
  가지는 가이드와 맞물린다(`guide:` 줄) — 가이드는 주제의 산문, 가지 문서는 그 주제에서 실제로
  성공한 문장들. 결정화 사다리(용례 → 워크플로 → 가이드)가 한 자리에 놓인다.
- 가지마다 문서 하나: `data/hippocampus_tree/<가지>/memory.md`(표식 + `> 한 줄 요약` + `guide:` +
  `## 용례` 기계 절 + 갱신 기록). 문서가 정본, DB 는 색인 — 사람이 줄을 고치면 색인이 따라온다.
- **지도(목차)는 항상 올린다**(`<execution_map>`), 가지의 내용은 AI 가 `[self:memory]{op:"recall",
  node, store:"실행"}` 로 연다.
- ★다른 점: 매 턴의 유사도 자동 주입(해마 Top-5·반사 0.85)은 **그대로 둔다** — "이 말을 IBL 로 어떻게
  쓰나"는 사용자 문장 자체가 단서라 벡터가 맞는 도구. 트리는 대체가 아니라 축 하나를 얹는 것.
- 어디에 넣을지는 AI 가 정한다: 증류기가 지도를 보고 topic 을 적는다(코드 분류기 없음). 미배치는
  `file_unfiled` 가 모델에게 배치시킨다.
- **관용구 절(2026-09-04, docs/IBL_IDIOM_TIER_HANDOFF.md)**: 낱말(용례 한 문장)과 얼린 워크플로 사이의
  층. 독립 문장 2~8개를 `;` 로 이은 골격에 구체값은 `${슬롯}` 으로 비운 것 — DB 에는 `category='phrase'`
  로 살고, 가지 문서의 `## 관용구` 절이 정본(용례 절과 같은 규약: 사람이 고친 블록은 구문 관문을 거쳐
  색인 반영, 지우면 색인에서도 지워짐). `## 주행`(녹취록)은 관용구의 증거로 남고, 관용구는 그 위의 추상.
"""
import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

DOC_NAME = "memory.md"
SECTION = "## 용례"
LEDGER = "## 갱신 기록"
RUNS = "## 주행"
RUNS_MAX = 20                 # 가지당 보존 주행 수
RUNS_MAX_SENTENCES = 30       # 주행당 문장 수 상한(넘으면 앞부분만, 절단 신고)
RUNS_MAX_LEN = 400            # 문장 한 줄 상한(넘으면 꼬리 절단 신고)
RUNS_NOTE = ("<!-- 이 가지에서 실제로 성공한 주행의 문장 묶음(실행 순서 그대로). 얼린 프로그램이 아니라 용례 — "
             f"다음 주행이 읽고 고쳐 쓴다. 최근 {RUNS_MAX}건·주행당 {RUNS_MAX_SENTENCES}문장, 오래된 것부터 빠진다. "
             "한 주행 = `### 날짜 · 의도 · 문장 n · ✓` 머리 + 번호 목록. -->")
RUN_HEAD_RE = re.compile(r"(?m)^### (\d{4}-\d{2}-\d{2})")
PHRASES = "## 관용구"
PHRASE_CATEGORY = "phrase"
PHRASE_MIN_SENTENCES = 2      # 한 문장은 낱말이다
PHRASE_MAX_SENTENCES = 10     # 프롬프트는 3~8 을 권하고, 관문은 10 에서 자른다(넘으면 거절)
PHRASES_NOTE = ("<!-- 기계가 읽는 절: 관용구 = 독립 문장 2~8개의 골격(실행 순서), 구체값은 `${슬롯}` 으로 비어 있다. "
                "얼린 프로그램이 아니라 다음 주행이 슬롯을 채우고 문장을 빼거나 더해 쓰는 모양이다. "
                "관용구는 이름 붙은 함수다(2026-09-05) — 머리의 이름으로 `[fn:이름]{슬롯…}` 을 부르면 그대로 돌고, 고치려면 "
                "`[def: 이름]{문장들}` 로 프로그램에 붙여 넣는다. 한 관용구 = `### 이름 — 의도 · 문장 n · 슬롯 a, b ‹#id · ✓성공/✗실패 · 날짜›` "
                "머리 + `호출: ` 줄 + 번호 목록(문장마다 `코드`). "
                "블록을 고치면 색인이 따라오고, 지우면 색인에서도 지워지며, ‹#id› 없이 새 블록을 적으면 새 관용구가 된다(구문 관문 통과 시). -->")
PHRASE_HEAD_RE = re.compile(r"^### (?:(\S+) — )?(.*?) · 문장 (\d+)(?: · 슬롯 (.*?))?(?:\s*‹#(\d+)[^›]*›)?\s*$")
PHRASE_CALL_RE = re.compile(r"^호출: `(.+)`\s*$")
PHRASE_LINE_RE = re.compile(r"^\d+\. `(.+)`\s*$")
SLOT_RE = re.compile(r"\$\{([^}]+)\}")
MARKER_RE = re.compile(r'<!--\s*hippo-topic\s+topic="([^"]*)"\s*-->')
GUIDE_RE = re.compile(r"(?m)^guide:\s*(.+?)\s*$")
LINE_RE = re.compile(r'^- (.*?)\s+→\s+`(.+?)`\s*‹#(\d+)[^›]*›\s*$')      # 색인된 줄
NEW_LINE_RE = re.compile(r'^- (.*?)\s+→\s+`(.+?)`\s*(?:‹[^›]*›)?\s*$')   # 사람이 새로 적은 줄(#id 없음)
SECTION_NOTE = ("<!-- 기계가 읽는 절: 한 줄 = 용례 하나 `- 의도 → `IBL 문장` ‹#id · ✓성공/✗실패 · 날짜›`. "
                "줄을 고치면 색인이 따라오고, 지우면 색인에서도 지워지며, #id 없이 `- 의도 → `문장`` 을 적으면 "
                "새 용례가 된다(구문 관문 통과 시). 요약·guide·산문은 자유롭게 쓴다. -->")
GIST_PLACEHOLDER = "(한 줄 요약 — 이 주제에서 IBL 로 무엇을 하나. AI 가 채운다; 지도에 실린다)"
MAX_DEPTH = 3


def _default_db_path() -> str:
    try:
        import ibl_usage_db as U
        for name in ("DB_PATH", "_DB_PATH"):
            if hasattr(U, name):
                return str(getattr(U, name))
        for name in ("_db_path", "_resolve_db_path", "resolve_db_path", "db_path"):
            fn = getattr(U, name, None)
            if callable(fn):
                return str(fn())
    except Exception:
        pass
    from runtime_utils import get_base_path
    return str(get_base_path() / "data" / "ibl_usage.db")


def _base_dir() -> str:
    from runtime_utils import get_base_path
    return str(get_base_path())


DOC_DIR: Optional[str] = None   # 시험이 바꾼다; None 이면 <base>/data/hippocampus_tree
GUIDE_DB_PATH: Optional[str] = None   # 시험이 바꾼다; None 이면 <base>/data/guide_db.json
_seed_cache: Tuple[float, Dict[str, str]] = (-1.0, {})


def guide_db_path() -> str:
    return GUIDE_DB_PATH or os.path.join(_base_dir(), "data", "guide_db.json")


def seed_guides(topic: str) -> str:
    """가이드 씨앗 — guide_db.json 의 `topic` 필드(추적되는 데이터)로 가지↔가이드를 나른다 (2026-09-03).

    가지 문서(data/hippocampus_tree/)는 몸-사적(gitignore)이라 `guide:` 줄만으로는 빈 몸(새 설치)의
    지도에 가이드가 하나도 안 실린다. 문서의 `guide:` 줄이 정본(사람·AI 가 고친 것이 이긴다)이고,
    문서가 없거나 줄이 비었을 때만 이 씨앗이 채운다. 반환은 문서와 같은 꼴 — 쉼표 목록.
    """
    global _seed_cache
    p = guide_db_path()
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return ""
    if _seed_cache[0] != mt:
        idx: Dict[str, List[str]] = {}
        try:
            with open(p, encoding="utf-8") as f:
                for g in (json.load(f).get("guides") or []):
                    t = norm_topic(g.get("topic"))
                    if t and g.get("file"):
                        idx.setdefault(t, []).append(str(g["file"]))
        except (OSError, ValueError):
            idx = {}
        _seed_cache = (mt, {t: ", ".join(v) for t, v in idx.items()})
    return _seed_cache[1].get(norm_topic(topic), "")


def doc_dir() -> str:
    return DOC_DIR or os.path.join(_base_dir(), "data", "hippocampus_tree")


# ─────────────────────────── 위치 ───────────────────────────

def norm_topic(topic: Optional[str]) -> str:
    parts = []
    for seg in str(topic or "").replace("\\", "/").split("/"):
        seg = re.sub(r"\s+", " ", seg).strip().strip(".")
        if seg:
            parts.append(seg)
    return "/".join(parts[:MAX_DEPTH])


def topic_dir(topic: str) -> str:
    t = norm_topic(topic)
    return os.path.join(doc_dir(), *t.split("/")) if t else doc_dir()


def doc_path(topic: str) -> str:
    return os.path.join(topic_dir(topic), DOC_NAME)


def parent_of(topic: str) -> Optional[str]:
    t = norm_topic(topic)
    if not t:
        return None
    return t.rsplit("/", 1)[0] if "/" in t else ""


# ─────────────────────────── 색인(DB) ───────────────────────────

def _conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or _default_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(db_path: Optional[str] = None) -> None:
    conn = sqlite3.connect(db_path or _default_db_path(), timeout=10)
    try:
        for col in ("topic", "alias"):
            try:
                conn.execute(f"SELECT {col} FROM ibl_examples LIMIT 1")
            except sqlite3.OperationalError:
                try:
                    conn.execute(f"ALTER TABLE ibl_examples ADD COLUMN {col} TEXT DEFAULT ''")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
    finally:
        conn.close()


def rows_of(topic: str, db_path: Optional[str] = None, kind: str = "all") -> List[Dict[str, Any]]:
    """가지의 용례 행. kind: "all" | "word"(관용구 제외) | "phrase"(관용구만)."""
    ensure_column(db_path)
    conn = _conn(db_path)
    try:
        where = {"word": " AND COALESCE(category,'') != ?", "phrase": " AND COALESCE(category,'') = ?"}.get(kind, "")
        args = (norm_topic(topic),) + ((PHRASE_CATEGORY,) if where else ())
        rows = conn.execute(
            "SELECT id, intent, ibl_code, nodes, category, source, success_count, fail_count, created_at, "
            "COALESCE(topic,'') AS topic, COALESCE(alias,'') AS alias FROM ibl_examples WHERE COALESCE(topic,'') = ?" + where +
            " ORDER BY created_at, id", args).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _counts(db_path: Optional[str], phrase: bool) -> Dict[str, int]:
    ensure_column(db_path)
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT COALESCE(topic,'') AS t, COUNT(*) AS c FROM ibl_examples WHERE COALESCE(category,'') "
            + ("=" if phrase else "!=") + " ? GROUP BY t", (PHRASE_CATEGORY,)).fetchall()
        return {norm_topic(r["t"]): r["c"] for r in rows}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def topic_counts(db_path: Optional[str] = None) -> Dict[str, int]:
    """가지별 낱말(용례) 수 — 관용구는 뺀다(phrase_counts 가 센다)."""
    return _counts(db_path, phrase=False)


def phrase_counts(db_path: Optional[str] = None) -> Dict[str, int]:
    """가지별 관용구 수."""
    return _counts(db_path, phrase=True)


def all_topics(db_path: Optional[str] = None) -> List[str]:
    topics = set(topic_counts(db_path).keys()) | set(phrase_counts(db_path).keys())
    root = doc_dir()
    if os.path.isdir(root):
        for cur, _d, files in os.walk(root):
            if DOC_NAME in files:
                rel = os.path.relpath(cur, root)
                topics.add("" if rel == "." else norm_topic(rel.replace(os.sep, "/")))
    for t in list(topics):
        p = parent_of(t)
        while p is not None:
            topics.add(p)
            p = parent_of(p)
    topics.add("")
    return sorted(topics, key=lambda s: (s.count("/"), s))


def children_of(topic: str, db_path: Optional[str] = None) -> List[str]:
    t = norm_topic(topic)
    return [m for m in all_topics(db_path) if m and parent_of(m) == t]


def unfiled(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    return rows_of("", db_path)


# ─────────────────────────── 문서 렌더 ───────────────────────────

def _one_line(text: str) -> str:
    return re.sub(r"\s*\n+\s*", " ", (text or "").strip())


def render_line(r: Dict[str, Any]) -> str:
    s, f = int(r.get("success_count") or 0), int(r.get("fail_count") or 0)
    meta = [f"#{r['id']}"]
    if s or f:
        meta.append(f"✓{s}/✗{f}")
    meta.append((r.get("created_at") or "")[:10])
    code = _one_line(r.get("ibl_code")).replace("`", "'")
    return f"- {_one_line(r.get('intent'))} → `{code}` ‹{' · '.join(m for m in meta if m)}›"


def render_section(rows: List[Dict[str, Any]]) -> str:
    body = [SECTION, SECTION_NOTE]
    body.extend(render_line(r) for r in rows)
    return "\n".join(body) + "\n"


# ─────────────────────────── 관용구 (phrase) ───────────────────────────

def split_sentences(code: str) -> List[str]:
    """`;` 로 이은 독립 문장들로 자른다 — 따옴표·중괄호 안의 `;` 는 경계가 아니다."""
    out, buf, q, depth = [], [], None, 0
    i, n = 0, len(code or "")
    while i < n:
        ch = code[i]
        if q:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:
                buf.append(code[i + 1]); i += 2; continue
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch; buf.append(ch)
        elif ch in "{[(":
            depth += 1; buf.append(ch)
        elif ch in "}])":
            depth = max(0, depth - 1); buf.append(ch)
        elif ch == ";" and depth == 0:
            out.append("".join(buf).strip()); buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def _sentence_one_line(s: str) -> str:
    """문장 하나를 한 줄로 — 괄호 안(깊이>0)·따옴표 밖의 줄바꿈은 독립 문장 경계 `;` 로(함수 정의 몸 `[def: x]{줄들}` 보존,
    2026-09-05), 그 밖의 공백 줄바꿈은 한 칸으로."""
    out, q, depth, i, n = [], None, 0, 0, len(s or "")
    while i < n:
        ch = s[i]
        if q:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1]); i += 2; continue
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch; out.append(ch)
        elif ch in "{[(":
            depth += 1; out.append(ch)
        elif ch in "}])":
            depth = max(0, depth - 1); out.append(ch)
        elif ch == "\n":
            j = len(out) - 1
            while j >= 0 and out[j] in " \t":
                j -= 1
            prev = out[j] if j >= 0 else ""
            k = i + 1
            while k < n and s[k] in " \t\r\n":
                k += 1
            nxt = s[k] if k < n else ""
            if depth > 0 and prev not in "{;([,&|>" and nxt not in "}])" and not s[k:k + 2] == ">>":
                out.append("; ")
            else:
                out.append(" ")
            i = k; continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


def join_sentences(sentences: List[str]) -> str:
    return "; ".join(_sentence_one_line(s) for s in sentences if s and s.strip())


def slot_names(code: str) -> List[str]:
    seen, out = set(), []
    for m in SLOT_RE.findall(code or ""):
        k = m.strip()
        if k and k not in seen:
            seen.add(k); out.append(k)
    return out


def phrase_call_line(alias: str, code: str) -> str:
    """관용구를 그대로 쓰는 호출 한 줄 — `[fn:이름]{슬롯: "…", …}` (슬롯은 몸의 `${슬롯}`)."""
    if not alias:
        return ""
    slots = slot_names(code or "")
    args = ", ".join(f'{s}: "…"' for s in slots)
    return f"[fn:{alias}]{{{args}}}"


def phrase_def_block(alias: str, code: str) -> str:
    """관용구를 고쳐 쓰는 정의 블록 — 프로그램에 붙여 넣는 `[def: 이름]{ 문장들 }` (여러 줄)."""
    sents = split_sentences(code or "")
    body = "\n".join("  " + s for s in sents)
    return f"[def: {alias or '이름'}]{{\n{body}\n}}"


def render_phrase(r: Dict[str, Any]) -> str:
    s, f = int(r.get("success_count") or 0), int(r.get("fail_count") or 0)
    meta = [f"#{r['id']}"]
    if s or f:
        meta.append(f"✓{s}/✗{f}")
    meta.append((r.get("created_at") or "")[:10])
    code = r.get("ibl_code") or ""
    sents = split_sentences(code)
    slots = slot_names(code)
    alias = (r.get("alias") or "").strip()
    head = "### " + (f"{alias} — " if alias else "") + f"{_one_line(r.get('intent'))} · 문장 {len(sents)}"
    if slots:
        head += " · 슬롯 " + ", ".join(slots)
    head += f" ‹{' · '.join(m for m in meta if m)}›"
    lines = [head]
    if alias:
        lines.append(f"호출: `{phrase_call_line(alias, code)}`")
    for i, sent in enumerate(sents, 1):
        lines.append(f"{i}. `{_one_line(sent).replace('`', chr(39))}`")
    return "\n".join(lines)


def render_phrases(rows: List[Dict[str, Any]]) -> str:
    body = [PHRASES, PHRASES_NOTE]
    body.extend(render_phrase(r) for r in rows)
    return "\n".join(body) + "\n"


def _split_phrases(text: str) -> Tuple[str, str, str]:
    """`## 관용구` 절을 (앞, 절, 뒤) 로. 없으면 `## 주행` 앞(없으면 갱신 기록 앞)을 자리로 잡는다."""
    m = re.search(r"(?m)^## 관용구\s*$", text)
    if m:
        nxt = re.search(r"(?m)^## ", text[m.end():])
        end = m.end() + nxt.start() if nxt else len(text)
        return text[:m.start()], text[m.start():end], text[end:]
    for anchor in (r"(?m)^## 주행\s*$", r"(?m)^## 갱신 기록\s*$"):
        am = re.search(anchor, text)
        if am:
            return text[:am.start()], "", text[am.start():]
    return text, "", ""


def _replace_phrases(text: str, section: str) -> str:
    head, _old, tail = _split_phrases(text)
    if head and not head.endswith("\n\n"):
        head = head.rstrip("\n") + "\n\n"
    if tail and not tail.startswith("\n"):
        section = section + "\n"
    return head + section + tail


def parse_phrases(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """`## 관용구` 절 → (색인된 블록, 사람이 새로 적은 블록). 블록 = 머리 + 번호 목록, 코드 = 문장을 `; ` 로 이은 것."""
    _h, sec, _t = _split_phrases(text)
    known, fresh = [], []
    cur = None
    def _flush():
        if cur and cur["sentences"]:
            item = {"intent": cur["intent"], "ibl_code": join_sentences(cur["sentences"]), "alias": cur.get("alias") or ""}
            if cur["id"] is not None:
                item["id"] = cur["id"]; known.append(item)
            else:
                fresh.append(item)
    for line in sec.splitlines():
        hm = PHRASE_HEAD_RE.match(line)
        if hm:
            _flush()
            cur = {"alias": (hm.group(1) or "").strip(), "intent": hm.group(2).strip(),
                   "id": int(hm.group(5)) if hm.group(5) else None, "sentences": []}
            continue
        if PHRASE_CALL_RE.match(line):
            continue                                   # 호출 예시 줄은 파생(이름+슬롯) — 색인 대상이 아니다
        lm = PHRASE_LINE_RE.match(line)
        if lm and cur is not None:
            cur["sentences"].append(lm.group(1).strip())
    _flush()
    return known, fresh


def _split_section(text: str) -> Tuple[str, str, str]:
    m = re.search(r"(?m)^## 용례\s*$", text)
    if m:
        nxt = re.search(r"(?m)^## ", text[m.end():])
        end = m.end() + nxt.start() if nxt else len(text)
        return text[:m.start()], text[m.start():end], text[end:]
    lm = re.search(r"(?m)^## 갱신 기록\s*$", text)
    if lm:
        return text[:lm.start()], "", text[lm.start():]
    return text, "", ""


def _split_runs(text: str) -> Tuple[str, str, str]:
    """`## 주행` 절을 (앞, 절, 뒤) 로. 없으면 갱신 기록 앞을 자리로 잡는다."""
    m = re.search(r"(?m)^## 주행\s*$", text)
    if m:
        nxt = re.search(r"(?m)^## ", text[m.end():])
        end = m.end() + nxt.start() if nxt else len(text)
        return text[:m.start()], text[m.start():end], text[end:]
    lm = re.search(r"(?m)^## 갱신 기록\s*$", text)
    if lm:
        return text[:lm.start()], "", text[lm.start():]
    return text, "", ""


def runs_of(path: str) -> int:
    """문서의 주행 수(`### 날짜` 머리 계수)."""
    try:
        with open(path, encoding="utf-8") as f:
            _h, sec, _t = _split_runs(f.read())
    except OSError:
        return 0
    return len(RUN_HEAD_RE.findall(sec))


def note_run(topic: str, intent: str, sentences: List[str], ok: bool = True,
             when: Optional[str] = None, db_path: Optional[str] = None) -> Dict[str, Any]:
    """주행 하나(성공한 문장 묶음)를 가지 문서의 `## 주행` 절에 적는다 (2026-09-04, 사용자 판정).

    왜: 증류는 에피소드당 대표 문장 하나를 코퍼스에 넣는데, 가장 값진 주행(보고서 40문장·앱 개발
    31문장)은 한 문장으로 대표되지 않아 '재사용 패턴 없음'으로 끝났다 — 학습 0건. 그리고 그
    코퍼스는 top-1 로 거의 쓰이지 않고(08-28~ 귀속 5회, 증류 출신 0), 에이전트가 실제로 읽는 것은
    지도→가지 문서(recall{store:"실행"})다. 그러니 주행의 문장들을 그 자리에 실행 순서대로 남긴다.
    얼린 워크플로가 아니라 용례다 — 다음 주행이 읽고 고쳐 쓴다.
    상한은 정직하게: 주행 RUNS_MAX 건(오래된 것부터 삭제)·주행당 RUNS_MAX_SENTENCES 문장·문장
    RUNS_MAX_LEN 자, 넘치면 절단을 표기한다.
    """
    topic = norm_topic(topic)
    sentences = [s for s in (sentences or []) if isinstance(s, str) and s.strip()]
    if not topic or not sentences:
        return {"success": False, "error": "topic 과 문장이 필요합니다"}
    path = doc_path(topic)
    if not os.path.exists(path):
        refresh_topic(topic, db_path)
    text = open(path, encoding="utf-8").read()
    head, sec, tail = _split_runs(text)
    day = (when or datetime.now().strftime("%Y-%m-%d"))[:10]
    shown = sentences[:RUNS_MAX_SENTENCES]
    lines = [f"### {day} · {_one_line(intent)[:120]} · 문장 {len(sentences)} · {'✓' if ok else '✗'}"]
    for i, s in enumerate(shown, 1):
        one = _one_line(s).replace("`", "'")
        if len(one) > RUNS_MAX_LEN:
            one = one[:RUNS_MAX_LEN] + f" …[+{len(one) - RUNS_MAX_LEN}자 절단]"
        lines.append(f"{i}. `{one}`")
    if len(sentences) > len(shown):
        lines.append(f"- …[{len(sentences) - len(shown)}문장 더 — 상한 {RUNS_MAX_SENTENCES}]")
    entry = "\n".join(lines) + "\n"
    # 기존 절의 주행 블록들(### 머리 기준) — 최신이 위, 오래된 것부터 잘라낸다
    body = sec.split("\n", 1)[1] if sec else ""
    body = "\n".join(l for l in body.splitlines() if not l.startswith("<!--")).strip("\n")
    blocks = [b for b in re.split(r"(?m)^(?=### )", body) if b.strip()]
    blocks = [entry] + blocks
    dropped = max(0, len(blocks) - RUNS_MAX)
    blocks = blocks[:RUNS_MAX]
    new_sec = RUNS + "\n" + RUNS_NOTE + "\n" + "\n".join(b.rstrip("\n") for b in blocks) + "\n"
    if head and not head.endswith("\n\n"):
        head = head.rstrip("\n") + "\n\n"
    if tail and not tail.startswith("\n"):
        new_sec += "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + new_sec + tail)
    _stamp(topic, path)
    return {"success": True, "topic": topic, "doc": path, "sentences": len(shown),
            "truncated": len(sentences) > len(shown), "dropped_runs": dropped}


def _replace_section(text: str, section: str) -> str:
    head, _old, tail = _split_section(text)
    if head and not head.endswith("\n\n"):
        head = head.rstrip("\n") + "\n\n"
    if tail and not tail.startswith("\n"):
        section = section + "\n"
    return head + section + tail


def _marker(topic: str) -> str:
    return f'<!-- hippo-topic topic="{norm_topic(topic)}" -->'


def gist_of(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(3000)
    except OSError:
        return ""
    m = re.search(r"(?m)^>\s*(.+?)\s*$", text)
    g = m.group(1).strip() if m else ""
    return "" if g.startswith("(한 줄 요약") else g


def guide_of(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            m = GUIDE_RE.search(f.read(3000))
        return (m.group(1).strip() if m else "").strip("`")
    except OSError:
        return ""


def _stamp_path(topic: str) -> str:
    return os.path.join(topic_dir(topic), ".rendered")


def _stamp(topic: str, path: str) -> None:
    try:
        with open(_stamp_path(topic), "w") as f:
            f.write(str(os.path.getmtime(path)))
    except OSError:
        pass


def refresh_topic(topic: str, db_path: Optional[str] = None, guide: str = "") -> str:
    """DB → 문서(`## 용례` 절만 다시 그린다; 요약·guide·산문·갱신 기록 보존). 없으면 껍데기 생성."""
    topic = norm_topic(topic)
    path = doc_path(topic)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        if not MARKER_RE.search(text[:1500]):
            text = _marker(topic) + "\n" + text
    else:
        title = topic or "(뿌리 — 아직 가지가 없는 용례)"
        guide = guide or seed_guides(topic)      # 껍데기의 guide: 줄은 씨앗(guide_db topic)으로
        text = (f"{_marker(topic)}\n# 실행기억 — {title}\n> {GIST_PLACEHOLDER}\n"
                + (f"guide: {guide}\n" if guide else "")
                + f"\n{LEDGER}\n- {datetime.now().strftime('%Y-%m-%d')} 가지 생성\n")
    text = _replace_section(text, render_section(rows_of(topic, db_path, kind="word")))
    phrases = rows_of(topic, db_path, kind="phrase")
    if phrases or re.search(r"(?m)^## 관용구\s*$", text):
        text = _replace_phrases(text, render_phrases(phrases))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    _stamp(topic, path)
    return path


def refresh_all(db_path: Optional[str] = None) -> List[str]:
    return [refresh_topic(t, db_path) for t in all_topics(db_path)]


# ─────────────────────────── 문서 → 색인 (사람이 고친 줄) ───────────────────────────

def parse_section(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    _h, sec, _t = _split_section(text)
    known, fresh = [], []
    for line in sec.splitlines():
        if not line.startswith("- "):
            continue
        m = LINE_RE.match(line)
        if m:
            known.append({"intent": m.group(1).strip(), "ibl_code": m.group(2).strip(), "id": int(m.group(3))})
            continue
        m = NEW_LINE_RE.match(line)
        if m and m.group(1).strip() and m.group(2).strip():
            fresh.append({"intent": m.group(1).strip(), "ibl_code": m.group(2).strip()})
    return known, fresh


def _index(db_path: Optional[str], example_id: int, intent: str, code: str) -> None:
    """실 DB 일 때만 임베딩 색인(시험 DB 는 벡터 없음)."""
    if db_path and os.path.abspath(db_path) != os.path.abspath(_default_db_path()):
        return
    try:
        from ibl_usage_db import IBLUsageDB
        IBLUsageDB()._index_single(example_id, intent, code)
    except Exception as e:
        print(f"[hippo_tree] 색인 실패(무시): {e}")


def sync_topic(topic: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """문서가 마지막 렌더보다 새로우면 절을 읽어 색인에 반영: 고침=UPDATE · 지움=DELETE · 새 줄=INSERT(구문 관문)."""
    topic = norm_topic(topic)
    path = doc_path(topic)
    if not os.path.exists(path):
        return {"synced": False, "reason": "no_doc"}
    try:
        mtime = os.path.getmtime(path)
        stamp = float(open(_stamp_path(topic)).read() or 0)
    except Exception:
        mtime, stamp = 1.0, 0.0
    if mtime <= stamp + 1e-6:
        return {"synced": False, "reason": "fresh"}
    text = open(path, encoding="utf-8").read()
    known, fresh = parse_section(text)
    pk, pf = parse_phrases(text)
    known += pk
    fresh += [dict(f, category=PHRASE_CATEGORY) for f in pf]
    existing = {r["id"]: r for r in rows_of(topic, db_path)}
    updated = deleted = inserted = 0
    rejected: List[str] = []
    try:
        from ibl_usage_db import _syntax_reason
    except Exception:
        _syntax_reason = lambda code: None   # noqa: E731
    conn = sqlite3.connect(db_path or _default_db_path(), timeout=10)
    try:
        now = datetime.now().isoformat()
        seen = set()
        for k in known:
            r = existing.get(k["id"])
            if r is None:
                fresh.append({"intent": k["intent"], "ibl_code": k["ibl_code"]})
                continue
            seen.add(k["id"])
            _alias_changed = ("alias" in k) and (k.get("alias") or "") != (r.get("alias") or "")
            if k["intent"] != r["intent"] or k["ibl_code"] != r["ibl_code"] or _alias_changed:
                why = _syntax_reason(k["ibl_code"])
                if why:
                    rejected.append(f"#{k['id']}: {why}")
                    continue
                conn.execute("UPDATE ibl_examples SET intent=?, ibl_code=?, alias=?, updated_at=? WHERE id=?",
                             (k["intent"], k["ibl_code"], (k.get("alias") if "alias" in k else r.get("alias")) or "", now, k["id"]))
                updated += 1
                _index(db_path, k["id"], k["intent"], k["ibl_code"])
        gone = [mid for mid in existing if mid not in seen]
        if gone:
            ph = ",".join("?" * len(gone))
            conn.execute(f"DELETE FROM ibl_examples WHERE id IN ({ph})", gone)
            deleted += len(gone)
            try:
                vconn = sqlite3.connect(db_path or _default_db_path(), timeout=10)
                import sqlite_vec
                vconn.enable_load_extension(True); sqlite_vec.load(vconn); vconn.enable_load_extension(False)
                vconn.execute(f"DELETE FROM ibl_examples_vec WHERE rowid IN ({ph})", gone); vconn.commit(); vconn.close()
            except Exception:
                pass
        for f in fresh:
            why = _syntax_reason(f["ibl_code"])
            if why:
                rejected.append(f"{f['ibl_code'][:40]}: {why}")
                continue
            nodes = ",".join(sorted(set(re.findall(r"\[([a-z_-]+):", f["ibl_code"]))))
            if f.get("category") == PHRASE_CATEGORY:
                n_s = len(split_sentences(f["ibl_code"]))
                if not (PHRASE_MIN_SENTENCES <= n_s <= PHRASE_MAX_SENTENCES):
                    rejected.append(f"{f['ibl_code'][:40]}: 관용구 문장 수 {n_s} (허용 {PHRASE_MIN_SENTENCES}~{PHRASE_MAX_SENTENCES})")
                    continue
                cat = PHRASE_CATEGORY
            else:
                cat = "pipeline" if (">>" in f["ibl_code"] or "&" in f["ibl_code"]) else "single"
            cur = conn.execute(
                "INSERT INTO ibl_examples (intent, ibl_code, nodes, category, difficulty, source, tags, created_at, updated_at, topic, alias) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f["intent"], f["ibl_code"], nodes, cat, 1, "manual", "doc", now, now, topic, f.get("alias") or ""))
            inserted += 1
            _index(db_path, cur.lastrowid, f["intent"], f["ibl_code"])
        conn.commit()
    finally:
        conn.close()
    refresh_topic(topic, db_path)
    out = {"synced": True, "updated": updated, "deleted": deleted, "inserted": inserted}
    if rejected:
        out["rejected"] = rejected
    return out


def sync_all(db_path: Optional[str] = None) -> Dict[str, int]:
    n = 0
    for t in all_topics(db_path):
        if sync_topic(t, db_path).get("synced"):
            n += 1
    return {"synced_docs": n}


# ─────────────────────────── 지도 · 회상 · 이동 ───────────────────────────

def map_lines(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    counts = topic_counts(db_path)
    pcounts = phrase_counts(db_path)
    out = []
    for t in all_topics(db_path):
        p = doc_path(t)
        ex = os.path.exists(p)
        out.append({"topic": t, "count": counts.get(t, 0), "phrases": pcounts.get(t, 0), "runs": runs_of(p) if ex else 0,
                    "gist": gist_of(p) if ex else "",
                    "guide": (guide_of(p) if ex else "") or seed_guides(t), "doc": p if ex else None})
    return out


def map_text(db_path: Optional[str] = None) -> str:
    """항상 올리는 목차 — `- 주제 (n · 관용구 k · 주행 m) — 요약 · guide: x.md`. 뿌리(미배치)는 건수만."""
    lines = []
    for row in map_lines(db_path):
        if row["topic"] == "":
            if row["count"]:
                lines.append(f"- (뿌리 — 아직 가지가 없는 용례) ({row['count']})")
            continue
        s = (f"- {row['topic']} ({row['count']}" + (f" · 관용구 {row['phrases']}" if row.get("phrases") else "")
             + (f" · 주행 {row['runs']}" if row.get("runs") else "") + ")")
        if row["gist"]:
            s += f" — {row['gist']}"
        if row["guide"]:
            s += f" · guide: {row['guide']}"
        lines.append(s)
    return "\n".join(lines)


def recall(topic: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    topic = norm_topic(topic)
    sync_topic(topic, db_path)
    path = doc_path(topic)
    if not os.path.exists(path) and topic not in all_topics(db_path):
        return {"success": False, "topic": topic,
                "error": f"없는 가지: '{topic}' — 지도(execution_map)의 이름을 쓰거나 증류·move 로 가지를 만든다.",
                "topics": [m["topic"] for m in map_lines(db_path) if m["topic"]]}
    if not os.path.exists(path):
        refresh_topic(topic, db_path)
    rows = rows_of(topic, db_path, kind="word")
    phrases = rows_of(topic, db_path, kind="phrase")
    counts = topic_counts(db_path)
    return {"success": True, "topic": topic, "doc": path, "guide": guide_of(path) or seed_guides(topic),
            "text": open(path, encoding="utf-8").read(),
            "items": rows, "count": len(rows), "phrases": phrases, "phrase_count": len(phrases),
            "children": [{"topic": c, "count": counts.get(c, 0), "gist": gist_of(doc_path(c))} for c in children_of(topic, db_path)],
            "parent": parent_of(topic)}


def move(example_id: int, topic: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    ensure_column(db_path)
    topic = norm_topic(topic)
    conn = _conn(db_path)
    try:
        row = conn.execute("SELECT COALESCE(topic,'') AS topic FROM ibl_examples WHERE id=?", (example_id,)).fetchone()
        if not row:
            return {"success": False, "error": f"용례 {example_id} 없음"}
        old = norm_topic(row["topic"])
        conn.execute("UPDATE ibl_examples SET topic=? WHERE id=?", (topic, example_id))
        conn.commit()
    finally:
        conn.close()
    refresh_topic(old, db_path)
    refresh_topic(topic, db_path)
    return {"success": True, "id": example_id, "from": old, "to": topic}


# ─────────────────────────── 미배치 배치(AI 몫) ───────────────────────────

FILE_PROMPT = """아래는 실행기억(IBL 용례)의 주제 지도와, 아직 주제가 없는 용례들이다.
각 용례를 **가장 알맞은 주제 가지**에 넣어라. 규칙:
- 기존 가지를 우선한다. 정말 새 주제면 새 경로를 만들어도 된다(`상위/하위` 꼴, 최대 2단, 한국어 명사).
- 가지는 **무슨 일을 하는 문장인가**(작업 주제 — 부동산·보고서·일정… / 또는 어휘 부류 — 표 다루기·파일·웹 검색…)로 나눈다.
- 한두 건짜리 가지를 만들지 마라 — 여럿이 모일 주제만 새 가지, 아니면 가장 가까운 기존 가지.
- 판단 불가면 빈 문자열.

[주제 지도]
{map}

[배치할 용례]
{rows}

JSON 객체로만 응답: {{"<id>": "<가지 경로>", ...}}"""


def file_unfiled(ai_call: Callable[[str, str], Optional[str]], batch: int = 30,
                 db_path: Optional[str] = None, extra_map: str = "") -> Dict[str, Any]:
    import json
    rows = unfiled(db_path)
    filed, skipped, new_topics = 0, 0, set()
    known = set(all_topics(db_path))
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        m = map_text(db_path)
        if extra_map:
            m = (m + "\n" + extra_map).strip()
        listing = "\n".join(f"{r['id']}: {_one_line(r['intent'])[:120]} → {_one_line(r['ibl_code'])[:160]}" for r in chunk)
        resp = ai_call(FILE_PROMPT.format(map=m or "(아직 가지 없음)", rows=listing), "용례 배치기. JSON 객체로만 응답.")
        try:
            from runtime_utils import parse_first_json
            verdict = parse_first_json(resp or "") or {}
        except Exception:
            try:
                verdict = json.loads(resp or "{}")
            except Exception:
                verdict = {}
        if not isinstance(verdict, dict):
            verdict = {}
        conn = sqlite3.connect(db_path or _default_db_path(), timeout=10)
        try:
            for r in chunk:
                t = norm_topic(verdict.get(str(r["id"])) or verdict.get(r["id"]) or "")
                if not t:
                    skipped += 1
                    continue
                conn.execute("UPDATE ibl_examples SET topic=? WHERE id=?", (t, r["id"]))
                filed += 1
                if t not in known:
                    new_topics.add(t); known.add(t)
            conn.commit()
        finally:
            conn.close()
    refresh_all(db_path)
    return {"total": len(rows), "filed": filed, "skipped": skipped, "new_topics": sorted(new_topics)}
