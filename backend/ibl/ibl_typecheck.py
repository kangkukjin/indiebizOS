"""ibl_typecheck.py — 정적 통화 검사 (실행 전 타입 검사, 2026-09-05, docs/IBL_STATIC_TYPECHECK_HANDOFF.md)

왜: 모델이 IBL 을 REPL 로 쓰는 이유는 **뒷문장을 쓰려면 앞문장의 반환 모양을 봐야** 하기 때문이다.
오늘(09-05) 보고서 주행의 실패 11건 대부분이 실행 전에 알 수 있는 것이었다 — union 의 통화 불일치, join 의
스칼라 입력, 분기 안에서만 태어난 변수 읽기, 확정된 열 밖의 필드. 여기서는 파서의 step 리스트를 걸으며
문장마다 **통화 종류와 열 집합**을 계산해, 확정된 위반만 실행 전에 말한다.

격자:  T ::= items⟨C⟩ | prose | scalar | effect | bundle[T…] | unknown
       C ::= 열 집합(closed=문장 안에서 확정) | 열 집합(open=관측·추가 허용) | None(미상)
- **unknown 은 꼭대기다 — unknown 이 들어간 판정은 절대 error 가 아니다.** 검사기는 아는 것만 말한다
  (거짓 빨강 방지 — `scripts/check_validate_parity.py --typecheck` 가 "실행 성공 문장에 error 0" 을 집행).
- error   = 확정 정보만으로 반드시 실패하는 것(종류 불일치·확정 열 밖 참조·prose 에 .items).
- warning = 아마(관측 열 밖 참조·분기 안에서만 태어난 변수 읽기·미상 입력).

규칙의 출처: 사전 데이터뿐이다. 낱말의 통화는 `returns`(op·변형 해소는 ibl_pipe_types.step_currency 한 벌),
변환자의 흐름은 액션 정의의 `flow:{accepts, emits, columns, columns_param, reads_fields}` 선언, 열은
fixture 실측 카탈로그(data/ibl_return_shapes.json). **액션 이름은 이 파일에 없다** — 문법인 것(fn·블록·
$변수·&·>>·;)만 코드가 안다(헌법 '언어의 경계').

★기존 T1/T2(ibl_pipe_types — 머리 변환자 기아·이음매 기아)는 그대로 산다. 여기는 그 위의 층이다.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

KINDS = ("items", "prose", "scalar", "effect", "bundle", "unknown")
MAX_FN_DEPTH = 3

# {{_step_N_result[.path]}} 자리표 — 파서(_resolve_variables)가 남기는 모양 그대로(workflow_binding 과 한 벌)
_STEP_REF_RE = re.compile(r"\{\{_step_(\d+)_result((?:\.[^}]*)?)\}\}")
_IDENT_RE = re.compile(r"^[A-Za-z_가-힣][\w가-힣]*$")
_WHERE_HEAD_RE = re.compile(r"^\s*([A-Za-z_가-힣][\w가-힣\.]*)\s+"
                            r"(>=|<=|==|!=|>|<|contains|in|matches|startswith|endswith|eq|ne|lt|le|gt|ge|not_in)\b")

_FN_CACHE: Dict[str, "T"] = {}

# `[fn:이름]` 의 몸을 이름으로 내주는 외부 소스(저장 워크플로·이름 붙은 관용구). 검사기는 ibl 층이라 해마(data 층의
# ibl_usage_db)를 직접 부르지 않는다 — cognition(ibl_idiom)이 부팅 때 등록한다(층 관문 '등록=의존 역전').
FN_CODE_SOURCES: List[Any] = []


def register_fn_code_source(fn) -> None:
    if fn not in FN_CODE_SOURCES:
        FN_CODE_SOURCES.append(fn)


# ───────────────────────────── 타입 값 ─────────────────────────────

class T:
    """통화 타입 하나. cols=None 이면 열 미상, closed=True 면 문장 안에서 확정된 열(밖의 참조는 error)."""
    __slots__ = ("kind", "cols", "closed", "branches", "conditional")

    def __init__(self, kind: str = "unknown", cols: Optional[List[str]] = None, closed: bool = False,
                 branches: Optional[List["T"]] = None, conditional: bool = False):
        self.kind = kind if kind in KINDS else "unknown"
        self.cols = list(dict.fromkeys(cols)) if cols else None
        self.closed = bool(closed) if cols else False
        self.branches = list(branches or [])
        self.conditional = conditional

    def copy(self, **kw) -> "T":
        t = T(self.kind, self.cols, self.closed, self.branches, self.conditional)
        for k, v in kw.items():
            setattr(t, k, v)
        return t

    def __repr__(self) -> str:
        return describe(self)


def unknown() -> T:
    return T("unknown")


def describe(t: Optional[T]) -> str:
    """사람·모델이 읽는 한 낱말: items⟨a·b⟩ · items⟨a·b·…⟩(open) · items⟨열 미상⟩ · prose · scalar · effect · bundle[…] · ?"""
    if t is None:
        return "?"
    if t.kind == "items":
        if t.cols:
            body = "·".join(t.cols[:10]) + ("·…" if len(t.cols) > 10 or not t.closed else "")
            return f"items⟨{body}⟩"
        return "items⟨열 미상⟩"
    if t.kind == "bundle":
        return "bundle[" + ", ".join(describe(b) for b in t.branches) + "]"
    if t.kind == "unknown":
        return "?"
    return t.kind


def join(ts: List[T]) -> T:
    """격자 합 — 가지들의 결과가 하나로 흐를 때(폴백·if/else·case·try). 종류가 다르면 unknown,
    같으면 그 종류. 열은 교집합(전부 확정일 때만 확정)."""
    ts = [t for t in ts if t is not None]
    if not ts:
        return unknown()
    kinds = {t.kind for t in ts}
    if len(kinds) != 1 or "unknown" in kinds or "bundle" in kinds:
        return unknown()
    kind = kinds.pop()
    if kind != "items":
        return T(kind)
    if any(t.cols is None for t in ts):
        return T("items")
    common = [c for c in ts[0].cols if all(c in t.cols for t in ts[1:])]
    return T("items", common or None, closed=all(t.closed for t in ts))


# ───────────────────────────── 사전·카탈로그 ─────────────────────────────

def _action_def(node: str, action: str) -> Optional[Dict[str, Any]]:
    try:
        from ibl_registry import load_nodes_installed
        cfg = (load_nodes_installed().get("nodes", {}).get(node, {}).get("actions", {}).get(action))
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    try:
        from ibl_access import load_nodes_raw
        cfg = (load_nodes_raw() or {}).get("nodes", {}).get(node, {}).get("actions", {}).get(action)
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None


def _catalog_cols(node: str, action: str, params: Dict[str, Any]) -> Optional[List[str]]:
    """fixture 실측 열(data/ibl_return_shapes.json) — `node:action` · `#op` · `@param=값` 순. 없으면 None(미상)."""
    try:
        from ibl_access import _return_shapes
        shapes = _return_shapes() or {}
    except Exception:
        return None
    q = f"{node}:{action}"
    if (_action_def(node, action) or {}).get("columns_from") == "data":
        return None                                  # 열은 데이터가 정한다(ledger·read·script) — fixture 열은 그 fixture 의 것
    # 변이 축(F20-1): param 리터럴이 변이 키와 맞으면 그 열이 정본
    for k, v in shapes.items():
        if not k.startswith(q + "@"):
            continue
        try:
            p, want = k[len(q) + 1:].split("=", 1)
        except ValueError:
            continue
        val = params.get(p)
        if val is not None and not _dynamic(val) and str(val) == want and (v or {}).get("keys"):
            return list(v["keys"])
    op = params.get("op")
    if isinstance(op, str) and not _dynamic(op):
        ent = shapes.get(f"{q}#{op}")
        if ent and ent.get("keys"):
            return list(ent["keys"])
    ad = _action_def(node, action) or {}
    ent = shapes.get(q)
    if ent and ent.get("keys"):
        # 액션 레벨 관측은 액션 fixture 의 op 하나가 낸 열이다 — 다른 op 로 부른 문장에 그 열을 빌려주지 않는다
        # (2026-09-05 ep2858: `[self:lecture]{op:"load"}` 가 list fixture 의 title·meta·summary·url 을 받았다). 미상이 맞다.
        fop = _fixture_op(ad)
        if not (isinstance(op, str) and not _dynamic(op) and fop and op != fop):
            return list(ent["keys"])
    try:
        from ibl_ops import default_op
        d = default_op(ad)
    except Exception:
        d = None
    if d:
        ent = shapes.get(f"{q}#{d}")
        if ent and ent.get("keys"):
            return list(ent["keys"])
    return None


_FIXTURE_OP_RE = re.compile(r'\bop\s*:\s*["\']([\w-]+)["\']')


def _fixture_op(action_def: Dict[str, Any]) -> Optional[str]:
    """액션 레벨 fixture 문장이 부른 op(없으면 None) — 액션 레벨 관측 열의 출처."""
    fx = (action_def or {}).get("fixture")
    if not isinstance(fx, str):
        return None
    m = _FIXTURE_OP_RE.search(fx)
    return m.group(1) if m else None


def _dynamic(v: Any) -> bool:
    return isinstance(v, str) and ("$" in v or "{{" in v)


# ───────────────────────────── 검사기 ─────────────────────────────

class _Checker:
    def __init__(self, variables: Optional[Dict[str, int]] = None, fn_depth: int = 0,
                 given: Optional[Dict[str, T]] = None):
        self.env: Dict[int, T] = {}                 # step 인덱스(또는 팬텀 슬롯) → T
        self.names: Dict[int, str] = {int(i): n for n, i in (variables or {}).items() if str(i).lstrip("-").isdigit()}
        self.name_to_idx: Dict[str, int] = {n: int(i) for n, i in (variables or {}).items() if str(i).lstrip("-").isdigit()}
        self.given = given or {}                    # 함수 인자 등 이름으로 주어진 타입
        self.issues: List[Dict[str, Any]] = []
        self.types: List[str] = []
        self.fn_returns: Dict[str, str] = {}
        self.fn_defs: Dict[str, Dict[str, Any]] = {}
        self.fn_depth = fn_depth
        self._warned_conditional: set = set()
        self.stmt = 0
        self._prev_def = False                       # 직전 문장이 [def:] 뿐이었나 — 정의는 문장 번호를 먹지 않는다

    # ── 신고 ──
    def _issue(self, severity: str, step_idx: int, at: str, message: str, hint: str = "",
               expected: Any = None, got: Any = None) -> None:
        d = {"severity": severity, "statement": self.stmt, "step": step_idx + 1, "at": at, "message": message}
        if hint:
            d["hint"] = hint
        if expected is not None:
            d["expected"] = expected
        if got is not None:
            d["got"] = got
        self.issues.append(d)

    # ── 진입 ──
    def run(self, steps: List[Any]) -> T:
        prev: Optional[T] = None
        last: Optional[T] = None
        stmt_last_name: Optional[str] = None
        self.stmt = 1 if steps else 0
        for i, st in enumerate(steps):
            if not isinstance(st, dict):
                continue
            if st.get("_seq_boundary") and i > 0:
                self._close_statement(last, stmt_last_name)
                if not self._prev_def:
                    self.stmt += 1
                prev = None
                stmt_last_name = None
            if st.get("_def"):
                self._type_def(st, i)
                self.env[i] = unknown()
                last = None                                  # 정의 문장은 통화도 types 줄도 문장 번호도 없다
                self._prev_def = True
                continue
            self._prev_def = False
            t = self.type_step(st, prev, i)
            self.env[i] = t
            if st.get("_assign_name"):
                stmt_last_name = st["_assign_name"]
                self.name_to_idx.setdefault(stmt_last_name, i)
            born = st.get("_born_vars")
            if isinstance(born, dict):
                for n, slot in born.items():
                    try:
                        self.env[int(slot)] = T("unknown", conditional=True)
                        self.names[int(slot)] = n
                    except (TypeError, ValueError):
                        pass
            prev = t
            last = t
        self._close_statement(last, stmt_last_name)
        return last or unknown()

    def _close_statement(self, t: Optional[T], name: Optional[str]) -> None:
        if t is None:
            return
        label = f"${name}: " if name else f"({self.stmt}) "
        self.types.append(label + describe(t))

    # ── step 분기 ──
    def type_step(self, st: Dict[str, Any], prev: Optional[T], idx: int) -> T:
        if st.get("_def"):
            return self._type_def(st, idx)
        if st.get("_assign"):
            return T("scalar")
        if st.get("_var_emit"):
            return self._type_var_emit(st, idx)
        if st.get("_parallel"):
            return T("bundle", branches=[self._type_branch(b, prev, idx) for b in (st.get("branches") or [])])
        if "_fallback_chain" in st:
            return join([self._type_branch(b, prev, idx) for b in (st.get("_fallback_chain") or [])])
        if st.get("_branch_steps"):
            return self._type_sub(st.get("_branch_steps") or [], prev)
        if st.get("_condition"):
            outs = [self._type_body((b or {}).get("action"), prev) for b in (st.get("branches") or [])]
            return join(outs)
        if st.get("_case"):
            outs = [self._type_body((b or {}).get("action") if isinstance(b, dict) else b, prev)
                    for b in (st.get("branches") or [])]
            if st.get("default") is not None:
                outs.append(self._type_body(st.get("default"), prev))
            return join(outs)
        if st.get("_try"):
            outs = [self._type_body(st.get("body"), prev)]
            if st.get("catch") is not None:
                outs.append(self._type_body(st.get("catch"), prev))
            if st.get("finally") is not None:
                self._type_body(st.get("finally"), prev)
            return join(outs)
        if st.get("_repeat"):
            self._type_body(st.get("body"), prev)
            return T("items") if st.get("collect") else unknown()
        if st.get("_goal"):
            return unknown()
        node = st.get("_node") or st.get("node") or ""
        action = st.get("action") or ""
        if node == "fn":
            return self._type_fn_call(st, prev, idx)
        if not node or not action:
            return unknown()
        return self._type_action(st, node, action, prev, idx)

    def _type_branch(self, b: Any, prev: Optional[T], idx: int) -> T:
        if isinstance(b, dict) and b.get("_branch_steps"):
            return self._type_sub(b["_branch_steps"], prev)
        if isinstance(b, dict):
            return self.type_step(b, prev, idx)
        return unknown()

    def _type_body(self, body: Any, prev: Optional[T]) -> T:
        """블록 몸(단일 step dict 또는 step 리스트) — 몸 안의 파이프도 같은 규칙, 몸은 직전 통화를 받는다."""
        if body is None:
            return unknown()
        if isinstance(body, list):
            return self._type_sub(body, prev)
        if isinstance(body, dict):
            return self._type_sub([body], prev)
        return unknown()

    def _type_sub(self, steps: List[Any], prev: Optional[T]) -> T:
        """안쪽 파이프 — 바깥 env 를 공유(변수는 보이고), 신고도 같은 목록에."""
        p = prev
        last: Optional[T] = None
        for j, s in enumerate(steps):
            if not isinstance(s, dict):
                continue
            if s.get("_seq_boundary") and j > 0:
                p = None
            t = self.type_step(s, p, j)
            p = t
            last = t
        return last or unknown()

    # ── 변수 ──
    def _lookup(self, idx: int) -> Optional[T]:
        return self.env.get(idx)

    def _apply_path(self, t: T, path: str, idx: int, at: str) -> T:
        """`$x` 의 경로 — .items → 같은 열의 items · .count → scalar · .message → prose · .items.*.열 / .items.N.열 → 열 검사."""
        path = (path or "").strip()
        if not path or t.kind == "unknown":
            return t if not path else unknown()
        from common.field_path import parse_path
        parts = [str(p) for p in parse_path(path.lstrip(".")) if str(p)]     # 점 경로 해석은 common.field_path 한 벌
        if not parts:
            return t
        head = parts[0]
        if head == "items":
            if t.kind == "prose":
                self._issue("error", idx, at, "산문(prose) 결과에는 .items 가 없습니다 — [table:brief]·산문 결과는 맨몸 $이름 또는 .message 로 씁니다.",
                            hint="items 가 필요하면 brief 대신 [table:ai]{fields: […]} 로 표를 만드세요.", expected="items", got="prose")
                return unknown()
            if t.kind == "effect":
                self._issue("warning", idx, at, "effect(부수효과) 결과에 .items 를 붙였습니다 — 통화(items)를 내는 액션인지 확인하세요.", got=t.kind)
                return unknown()
            if t.kind == "scalar":
                return T("items")                        # 스칼라는 items 로 승격될 수 있다(script stdout·JSON 파일) — 미상 열
            if len(parts) == 1:
                return T("items", t.cols, t.closed)
            if parts[1] in ("*",) or parts[1].isdigit():
                if len(parts) >= 3:
                    self._check_field(t, parts[2], idx, at)
                    return T("scalar")
                return T("items", t.cols, t.closed) if parts[1] == "*" else T("scalar")
            return unknown()
        if head == "count":
            return T("scalar")
        if head == "message":
            return T("prose")
        if t.kind == "items" and t.cols is not None and head not in t.cols and head not in ("final_result", "results", "success", "error", "note"):
            # 봉투 필드일 수도 있다 — items 열 확인은 .items.* 경로에서만 error, 여기서는 정보성 경고 없음
            return unknown()
        return unknown()

    def _type_var_emit(self, st: Dict[str, Any], idx: int) -> T:
        name = st.get("name") or ""
        at = f"${name}"
        if name in self.given:
            return self._apply_path(self.given[name], st.get("path") or "", idx, at)
        vi = (st.get("_vars") or {}).get(name)
        if vi is None:
            vi = self.name_to_idx.get(name)
        if vi is None:
            return unknown()
        t = self._lookup(int(vi))
        if t is None:
            return unknown()
        self._warn_conditional(t, name, idx, at)
        return self._apply_path(t, st.get("path") or "", idx, at)

    def _warn_conditional(self, t: T, name: str, idx: int, at: str) -> None:
        if t.conditional and name not in self._warned_conditional:
            self._warned_conditional.add(name)
            self._issue("warning", idx, at,
                        f"${name} 은(는) 분기 몸 안에서만 태어난 변수입니다 — 그 분기에 들어가지 않으면 값이 없어 "
                        f"실행에서 '아직 값을 기록하지 않았습니다' 로 죽습니다.",
                        hint=f"블록 앞에서 `${name} = …` 로 초기화하거나, 읽는 자리를 같은 분기 안으로 옮기세요.")

    def _param_ref_type(self, v: Any) -> Optional[T]:
        """param 값이 통짜 자리표(`{{_step_N_result[.path]}}`)면 그 타입 — 아니면 None(리터럴·동적 미상)."""
        if not isinstance(v, str):
            return None
        m = _STEP_REF_RE.fullmatch(v.strip())
        if not m:
            return None
        t = self._lookup(int(m.group(1)))
        if t is None:
            return None
        name = self.names.get(int(m.group(1)), f"step{int(m.group(1)) + 1}")
        return self._apply_path(t, m.group(2) or "", 0, f"${name}")

    def _check_param_refs(self, params: Dict[str, Any], idx: int, at: str) -> None:
        """param 문자열 안의 `{{_step_N_result.items.*.열}}` 류 — 열 확인(확정 열 밖=error, 관측 열 밖=warning)."""
        def walk(v: Any) -> None:
            if isinstance(v, str):
                for m in _STEP_REF_RE.finditer(v):
                    t = self._lookup(int(m.group(1)))
                    if t is None:
                        continue
                    name = self.names.get(int(m.group(1)), f"step{int(m.group(1)) + 1}")
                    self._warn_conditional(t, name, idx, at)
                    path = m.group(2) or ""
                    if path:
                        self._apply_path(t, path, idx, f"${name}{path}")
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(params)

    # ── 열 ──
    def _check_field(self, t: T, field: str, idx: int, at: str) -> None:
        if t.kind != "items" or t.cols is None or not field or not _IDENT_RE.match(field):
            return
        if field in t.cols:
            return
        if field.startswith("_"):
            return                                   # _error 같은 정직 표지 열
        if t.closed:
            self._issue("error", idx, at, f"'{field}' 열이 없습니다 — 앞 문장이 열을 {describe(t)} 로 확정했습니다.",
                        hint="앞의 select/rename/compute/ai(fields) 가 남긴 열 이름 가운데 고르거나 그 문장에 열을 더하세요.",
                        expected=t.cols, got=field)
        else:
            self._issue("warning", idx, at, f"'{field}' 은(는) 관측된 열 {describe(t)} 에 없습니다 — 실행에서 빈 결과나 열 오류가 날 수 있습니다.",
                        hint="열 이름이 확실치 않으면 check: true 로 types 를 보고, 필요하면 앞에 [table:select] 로 열을 확정하세요.",
                        expected=t.cols, got=field)

    @staticmethod
    def _fields_in(value: Any) -> List[str]:
        """reads_fields 가 가리키는 param 값에서 열 이름 후보 — 문자열 where 의 머리, dict 의 field/키, 목록의 각 항."""
        out: List[str] = []
        if isinstance(value, str):
            if _dynamic(value):
                return out
            m = _WHERE_HEAD_RE.match(value)
            if m:
                out.append(m.group(1).split(".")[0])  # path-ok: where 문자열의 머리 낱말(열 이름)만 — 경로 해석이 아니다
            elif _IDENT_RE.match(value.strip()):
                out.append(value.strip())
        elif isinstance(value, dict):
            if "field" in value and isinstance(value["field"], str):
                out.append(value["field"])
            elif "op" not in value:
                out.extend(k for k in value.keys() if isinstance(k, str))
        elif isinstance(value, list):
            for v in value:
                out.extend(_Checker._fields_in(v))
        return [f for f in out if f]

    # ── 낱말·변환자 ──
    def _type_action(self, st: Dict[str, Any], node: str, action: str, prev: Optional[T], idx: int) -> T:
        at = f"{node}:{action}"
        params = st.get("params") if isinstance(st.get("params"), dict) else {}
        self._check_param_refs(params, idx, at)
        ad = _action_def(node, action)
        if not ad:
            return unknown()
        try:
            from ibl_pipe_types import step_currency
            returns = step_currency(st)
        except Exception:
            returns = ad.get("returns")
        flow = ad.get("flow") if isinstance(ad.get("flow"), dict) else None
        if returns == "transform" or (flow and flow.get("emits") and returns != "effect"):
            if flow:
                return self._type_transform(st, node, action, params, flow, prev, idx, at)
            return unknown()                             # flow 미선언 변환자 — 빌더 관문이 막는다; 여기선 미상
        if returns == "items":
            f = params.get("fields")
            if isinstance(f, list) and f and all(isinstance(c, str) and not _dynamic(c) for c in f):
                return T("items", [str(c) for c in f], closed=True)      # fields 리터럴 = 이 호출이 확정한 열(ledger select 등)
            return T("items", _catalog_cols(node, action, params))
        if returns in ("scalar", "effect"):
            return T(returns)
        return unknown()

    def _input_for(self, params: Dict[str, Any], prev: Optional[T]) -> Tuple[Optional[T], str]:
        """변환자의 입력 — items param 이 있으면 그것(자리표면 그 타입·리터럴이면 열 추출), 아니면 직전 통화."""
        if "items" in params:
            v = params["items"]  # items-ok: 정적 검사 — 값을 소비하지 않고 자리표·리터럴의 모양(열 이름)만 본다
            t = self._param_ref_type(v)
            if t is not None:
                return t, "items param"
            if isinstance(v, list):
                first = v[0] if v else None
                cols = list(first.keys()) if isinstance(first, dict) else None
                return T("items", cols, closed=bool(cols)), "items literal"
            return unknown(), "items param"
        return prev, "pipe"

    def _type_transform(self, st: Dict[str, Any], node: str, action: str, params: Dict[str, Any],
                        flow: Dict[str, Any], prev: Optional[T], idx: int, at: str) -> T:
        accepts = str(flow.get("accepts") or "any")
        emits = str(flow.get("emits") or "same")
        columns = flow.get("columns")
        cparam = flow.get("columns_param")
        inp, _src = self._input_for(params, prev)
        # each 의 do — 안쪽 문장을 타입해 방출 열을 안다($it = 입력 행)
        do_t: Optional[T] = None
        if isinstance(params.get("do"), str) and params.get("do").strip():
            do_t = self._type_do(params["do"], inp)

        # ── accepts ──
        if inp is not None and inp.kind != "unknown":
            if accepts == "same-kind":
                self._check_same_kind(inp, idx, at)
            elif accepts == "pair":
                self._check_pair(inp, idx, at)
            elif accepts == "items":
                if inp.kind == "scalar":
                    pass                                   # 스칼라는 데이터 의존 승격(script stdout·JSON 파일)이 있다 — 확답 불가, 침묵
                elif inp.kind == "prose":
                    self._issue("error", idx, at, f"[{at}] 는 items 를 받는 변환자인데 앞 통화가 산문(prose)입니다.",
                                hint="산문은 [self:write]{path} 로 저장하거나 [others:notify]로 보내는 종착이고, 표가 필요하면 산문 대신 [table:ai]{fields: […]} 로 만드세요.",
                                expected="items", got="prose")
                elif inp.kind == "bundle":
                    self._issue("warning", idx, at, f"병렬(&) 결과는 이항 변환자(union/merge/join)가 먼저 받아야 합니다 — [{at}] 는 병렬 봉투를 소비하지 못합니다.",
                                hint="[A] & [B] >> [table:union] >> [" + at + "]{…} 순으로 두거나, 분기 하나에만 전처리를 붙이려면 괄호 분기.",
                                expected="items", got=describe(inp))
                # effect 는 T2(이음매 기아)가 이미 같은 판정을 한다 — 중복 신고 없음
            elif accepts in ("prose|items", "items|prose"):
                if inp.kind in ("effect",):
                    self._issue("error", idx, at, f"[{at}] 는 산문 또는 items 를 받는데 앞 통화가 effect(부수효과 결과)입니다.",
                                expected="prose|items", got="effect")

        # ── reads_fields (열 참조) ──
        base_for_fields = inp
        if base_for_fields is not None and base_for_fields.kind == "bundle":
            base_for_fields = self._bundle_union(base_for_fields)
        for pname in (flow.get("reads_fields") or []):
            if pname in params and base_for_fields is not None:
                for f in self._fields_in(params[pname]):
                    self._check_field(base_for_fields, f, idx, at)

        # ── emits ──
        if emits == "same":
            out_kind = inp.kind if (inp is not None and inp.kind in ("items", "prose", "scalar", "effect")) else ("items" if inp is None else "unknown")
        else:
            out_kind = emits
        if out_kind != "items":
            return T(out_kind)

        # ── columns ──
        in_cols, in_closed = (None, False)
        if inp is not None:
            if inp.kind == "bundle":
                u = self._bundle_union(inp)
                in_cols, in_closed = u.cols, u.closed
            elif inp.kind == "items":
                in_cols, in_closed = inp.cols, inp.closed
        lit = params.get(cparam) if cparam else None
        if columns in (None, "keep"):
            return T("items", in_cols, in_closed)
        if columns == "reset":
            return T("items")
        if columns == "union":
            u = self._bundle_union(inp) if (inp is not None and inp.kind == "bundle") else T("items", in_cols, in_closed)
            return T("items", u.cols, u.closed)
        if columns == "subset":
            if isinstance(lit, list) and lit and all(isinstance(c, str) and not _dynamic(c) for c in lit):
                base = T("items", in_cols, in_closed)
                for c in lit:
                    self._check_field(base, c, idx, at)
                return T("items", [str(c) for c in lit], closed=True)
            return T("items")                                # 동적 columns — 미상
        if columns == "rename":
            if isinstance(lit, dict) and in_cols is not None and not any(_dynamic(k) or _dynamic(v) for k, v in lit.items()):
                base = T("items", in_cols, in_closed)
                for k in lit.keys():
                    self._check_field(base, str(k), idx, at)
                new = [str(lit.get(c, c)) for c in in_cols]
                return T("items", new, closed=in_closed)
            return T("items", None)
        if columns == "add":
            if isinstance(lit, dict) and in_cols is not None:
                return T("items", list(in_cols) + [str(k) for k in lit.keys()], closed=in_closed)
            return T("items", in_cols, False) if in_cols else T("items")
        if columns == "open":
            # ai(fields 로 확정) · each(keep + do 의 열)
            if isinstance(lit, list) and lit and all(isinstance(c, str) and not _dynamic(c) for c in lit) and cparam == "fields":
                return T("items", [str(c) for c in lit], closed=True)
            if do_t is not None:
                keep = [str(c) for c in (params.get("keep") or []) if isinstance(c, str)] if isinstance(params.get("keep"), list) else []
                if do_t.kind == "items":
                    cols = (do_t.cols or []) + keep
                    return T("items", cols or None, closed=False)
                # do 가 통화를 안 내면 원 행이 흐른다(passthrough)
                return T("items", in_cols, False) if in_cols else T("items")
            return T("items", in_cols, False) if in_cols else T("items")
        return T("items", in_cols, in_closed)

    def _bundle_union(self, b: T) -> T:
        cols: List[str] = []
        closed = True
        for br in b.branches:
            if br.kind == "items" and br.cols:
                cols.extend(c for c in br.cols if c not in cols)
                closed = closed and br.closed
            elif br.kind == "items":
                return T("items")
            elif br.kind == "effect":
                closed = False                       # 효과 행(path·size·message …)이 섞인다
        return T("items", cols or None, closed=closed and bool(cols))

    def _check_same_kind(self, inp: T, idx: int, at: str) -> None:
        if inp.kind != "bundle":
            if inp.kind == "prose":
                self._issue("error", idx, at, f"[{at}] 는 통화(items)를 합치는 변환자인데 앞 통화가 산문(prose)입니다.",
                            expected="items", got=inp.kind)
            return
        kinds = [br.kind for br in inp.branches]
        soft = [(i + 1, k) for i, k in enumerate(kinds) if k == "scalar"]
        if soft:
            self._issue("warning", idx, at,
                        f"[{at}] 의 " + ", ".join(f"가지 {i}" for i, _ in soft) + " 은(는) 스칼라 선언 액션입니다 — items 로 승격되지 않으면 실행에서 '통화 종류가 같아야 합니다' 로 죽습니다.",
                        hint="통화(items)를 내는 op 가 있으면 그것을 쓰세요.", got=kinds)
        bad = [(i + 1, k) for i, k in enumerate(kinds) if k == "prose"]
        if bad:
            self._issue("error", idx, at,
                        f"[{at}] 은 같은 종류의 가지만 받습니다 — " + ", ".join(f"가지 {i} = {k}" for i, k in bad)
                        + " (items 가 아님). 실행하면 '모든 입력의 통화 종류가 같아야 합니다' 로 죽습니다.",
                        hint="산문 가지([table:brief])는 합치지 말고 $변수로 받아 따로 쓰고, 스칼라 가지는 통화를 내는 op 로 바꾸세요. 효과 봉투(write 등)는 1행으로 허용됩니다.",
                        expected="same-kind(items)", got=kinds)

    def _check_pair(self, inp: T, idx: int, at: str) -> None:
        if inp.kind != "bundle":
            if inp.kind in ("prose", "effect"):
                self._issue("error", idx, at, f"[{at}] 는 두 통화를 받는 이항 변환자인데 앞이 {inp.kind} 하나입니다.",
                            hint="[A] & [B] >> [" + at + "]{…} 로 두 가지를 병렬 공급하세요.", expected="items×items", got=inp.kind)
            return
        soft = [(i + 1, br.kind) for i, br in enumerate(inp.branches) if br.kind == "scalar"]
        if soft:
            self._issue("warning", idx, at, f"[{at}] 의 " + ", ".join(f"가지 {i}" for i, _ in soft) + " 은(는) 스칼라 선언 액션입니다 — items 로 승격되지 않으면 join 할 행이 없습니다.",
                        got=[br.kind for br in inp.branches])
        bad = [(i + 1, br.kind) for i, br in enumerate(inp.branches) if br.kind in ("prose", "effect")]
        if bad:
            self._issue("error", idx, at,
                        f"[{at}] 의 입력은 둘 다 통화(items)여야 합니다 — " + ", ".join(f"가지 {i} = {k}" for i, k in bad) + ".",
                        hint="그 가지를 통화를 내는 액션·op 으로 바꾸세요(스칼라·산문·효과는 join/merge 할 행이 없습니다).",
                        expected="items×items", got=[br.kind for br in inp.branches])

    def _type_do(self, do_code: str, inp: Optional[T]) -> Optional[T]:
        """each 의 do 문장 — `$it` 은 입력 행(열 = 입력 열)으로 두고 안쪽을 타입. 파싱 실패는 기권."""
        try:
            from ibl_parser import parse_with_vars
            steps, variables = parse_with_vars(do_code)
        except Exception:
            return None
        row = T("items", inp.cols, inp.closed) if (inp is not None and inp.kind == "items") else unknown()
        sub = _Checker(variables, self.fn_depth, given={"it": row, **self.given})
        sub.fn_defs = self.fn_defs
        sub.fn_returns = self.fn_returns
        out = sub.run(steps)
        # do 안의 신고는 문장 번호를 바깥 것으로 붙여 올린다(위치는 do 안이라 표시)
        for iss in sub.issues:
            iss = dict(iss)
            iss["statement"] = self.stmt
            iss["at"] = f"each.do › {iss.get('at', '')}"
            self.issues.append(iss)
        return out

    # ── 함수 ──
    def _type_def(self, st: Dict[str, Any], idx: int) -> T:
        name = st.get("name") or ""
        if not name:
            return unknown()
        if st.get("todo") or not st.get("body"):
            self.fn_defs[name] = {"body": None, "signature": list(st.get("signature") or [])}
            self.fn_returns[name] = "?"
            return unknown()
        self.fn_defs[name] = {"body": st.get("body"), "signature": list(st.get("signature") or [])}
        rt = self._type_fn_body(st.get("body"), st.get("signature") or [])
        self.fn_returns[name] = describe(rt)
        return unknown()                                  # 정의 문장은 통화를 내지 않는다

    def _type_fn_body(self, body: Any, signature: List[str]) -> T:
        if self.fn_depth >= MAX_FN_DEPTH:
            return unknown()
        steps = body if isinstance(body, list) else ([body] if isinstance(body, dict) else [])
        sub = _Checker(None, self.fn_depth + 1, given={n: unknown() for n in signature})
        sub.fn_defs = dict(self.fn_defs)
        sub.fn_returns = dict(self.fn_returns)
        out = sub.run(steps)
        # `$return = …` 규약 — 그 문장의 결과가 반환(마지막이 effect 여도 됨)
        for i, s in enumerate(steps):
            if isinstance(s, dict) and s.get("_assign_name") == "return":
                t = sub.env.get(i)
                if t is not None:
                    return t
        return out

    def _type_fn_call(self, st: Dict[str, Any], prev: Optional[T], idx: int) -> T:
        name = st.get("action") or ""
        at = f"fn:{name}"
        params = st.get("params") if isinstance(st.get("params"), dict) else {}
        self._check_param_refs(params, idx, at)
        if name in self.fn_returns and self.fn_returns[name] not in ("?", ""):
            return _parse_desc(self.fn_returns[name])
        # 정의 표(같은 프로그램) → 저장 워크플로 → 이름 붙은 관용구 (실행기 _execute_fn 과 같은 순서)
        ref = st.get("_fn_ref")
        if isinstance(ref, dict) and ref.get("name") in self.fn_defs:
            d = self.fn_defs[ref["name"]]
            if d.get("body"):
                t = self._type_fn_body(d["body"], d.get("signature") or [])
                self.fn_returns[name] = describe(t)
                return t
            return unknown()
        code = _external_fn_code(name)
        if not code:
            return unknown()
        key = hashlib.sha1(code.encode("utf-8")).hexdigest()
        if key in _FN_CACHE:
            return _FN_CACHE[key]
        try:
            from ibl_parser import parse_with_vars
            from workflow_contract import _free_vars
            steps, _vars = parse_with_vars(code)
            sig = _free_vars(steps)
        except Exception:
            return unknown()
        t = self._type_fn_body(steps, sig)
        _FN_CACHE[key] = t
        if len(_FN_CACHE) > 256:
            _FN_CACHE.pop(next(iter(_FN_CACHE)))
        self.fn_returns[name] = describe(t)
        return t


def _external_fn_code(name: str) -> Optional[str]:
    """`[fn:이름]` 의 몸 — 등록된 소스(저장 워크플로 → 이름 붙은 관용구, 실행기 _execute_fn 과 같은 순서로 cognition 이
    등록한다). 여기서 workflow_store 를 직접 부르면 workflow_engine 을 거쳐 cognition 으로 되돌아오는 층 순환이 생긴다
    (층 관문 실측 2026-09-05) — 그래서 두 길 다 등록이다. 없으면 None."""
    for src in list(FN_CODE_SOURCES):
        try:
            code = src(name)
            if isinstance(code, str) and code.strip():
                return code
        except Exception:
            continue
    return None


def _parse_desc(s: str) -> T:
    """describe() 의 역 — 저장된 반환 문자열(`items⟨a·b⟩` 등)을 타입으로."""
    s = (s or "").strip()
    if s.startswith("items⟨"):
        inner = s[len("items⟨"):-1] if s.endswith("⟩") else s[len("items⟨"):]
        if inner in ("열 미상", ""):
            return T("items")
        open_ = inner.endswith("·…")
        cols = [c for c in inner.rstrip("·…").split("·") if c]
        return T("items", cols or None, closed=not open_)
    if s in ("prose", "scalar", "effect"):
        return T(s)
    return unknown()


# ───────────────────────────── 공개 표면 ─────────────────────────────

def typecheck(steps: List[Any], variables: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """파싱된 step 리스트의 정적 통화 검사.

    반환: {"ok": error 없음, "issues": [{severity, statement, step, at, message, hint?, expected?, got?}],
           "types": ["$이름: items⟨…⟩", "(2) prose", …], "fn_returns": {이름: "items⟨…⟩"}}
    예외는 삼킨다(검사기가 실행을 죽이면 안 된다) — 그때는 ok=True·issues 빈 목록·`abstained` 표지."""
    try:
        c = _Checker(variables)
        c.run(steps or [])
        errors = [i for i in c.issues if i.get("severity") == "error"]
        return {"ok": not errors, "issues": c.issues, "types": c.types, "fn_returns": c.fn_returns}
    except Exception as e:                            # pragma: no cover — 안전망
        return {"ok": True, "issues": [], "types": [], "fn_returns": {}, "abstained": f"{type(e).__name__}: {e}"}


def typecheck_code(code: str) -> Dict[str, Any]:
    """코드 문자열 → 파싱 + 검사. 파싱 실패는 {"ok": False, "syntax_error": …}."""
    try:
        from ibl_parser import parse_with_vars
        steps, variables = parse_with_vars(code or "")
    except Exception as e:
        return {"ok": False, "syntax_error": str(e), "issues": [], "types": [], "fn_returns": {}}
    return typecheck(steps, variables)


def return_type_of(code: str, signature: Optional[List[str]] = None) -> str:
    """함수·관용구·워크플로 몸의 반환 타입 한 낱말(서명 표시용) — `items⟨title·url⟩` / `prose` / `?`.
    인자는 미상으로 두고 몸을 타입한다. 실패는 "?"(정직)."""
    try:
        from ibl_parser import parse_with_vars
        steps, _ = parse_with_vars(code or "")
        if signature is None:
            from workflow_contract import _free_vars
            signature = _free_vars(steps)
        c = _Checker(None, 0, given={n: unknown() for n in (signature or [])})
        t = c._type_fn_body(steps, list(signature or []))
        return describe(t)
    except Exception:
        return "?"


def return_type_of_steps(steps: List[Any], signature: Optional[List[str]] = None) -> str:
    try:
        c = _Checker(None, 0, given={n: unknown() for n in (signature or [])})
        return describe(c._type_fn_body(steps, list(signature or [])))
    except Exception:
        return "?"


def format_issues(issues: List[Dict[str, Any]], limit: int = 6) -> str:
    """오류 봉투의 한 줄 요약(첫 error 우선)."""
    errs = [i for i in issues if i.get("severity") == "error"] or issues
    parts = []
    for i in errs[:limit]:
        parts.append(f"문장 {i.get('statement')} step {i.get('step')} [{i.get('at')}]: {i.get('message')}")
    return " | ".join(parts)
