"""build_ibl_nodes 검증 계층 (2026-07-18 모듈화 — 1500줄 규칙).

build_ibl_nodes.py 에서 verbatim 이동: 액션 삼각검증(_check_action — src↔tool.json↔
handler _OP_DISPATCHERS AST)·코퍼스 param 정합·runs_on/변환자/폰도달성/fixture/가이드/
표준-코어/always_on 검증 + 총괄 validate().
"""
from __future__ import annotations
import ast
import json
import re
import sys
from pathlib import Path

from iblbuild_common import (
    CORPUS_FILES,
    DEFAULT_RUNS_ON,
    PHONE_VERIFIED_PACKAGES,
    VALID_RUNS_ON,
    UNIVERSAL_PARAM_KEYS,
    RUNTIME_META_KEYS,
    CORPUS_PARAM_ALLOW,
    _dir_read_keys,
    _extract_action_param_aliases,
)
from iblbuild_derive import build_tool_index
from iblbuild_appview import validate_app_blocks, validate_standalone_instruments


def _extract_op_dispatchers(handler_text: str) -> dict[str, tuple[set[str], object]] | None:
    """handler.py 본문에서 _OP_DISPATCHERS dict 를 AST 로 파싱.

    Returns:
        {tool_name: (op_key_set, raw_dict_node)} 또는 None (dict 없음).
        타입이 dict 가 아니거나 키가 문자열 상수가 아니면 None.
    """
    try:
        tree = ast.parse(handler_text)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_OP_DISPATCHERS" not in names:
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        result: dict[str, tuple[set[str], object]] = {}
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
                continue
            tool_name = k_node.value
            if not isinstance(v_node, ast.Dict):
                continue
            op_keys: set[str] = set()
            for op_k in v_node.keys:
                if isinstance(op_k, ast.Constant) and isinstance(op_k.value, str):
                    op_keys.add(op_k.value)
            result[tool_name] = (op_keys, v_node)
        return result
    return None


def _stub_ops(table_node) -> list[str]:
    """_OP_DISPATCHERS 테이블(ast.Dict)에서 값이 None 상수인 op 키 목록.

    장식 스텁 탐지용 (감사 ① 재발 봉쇄) — 함수 참조(ast.Name/Attribute)나
    문자열 디스패치 키(browser-action/computer-use 변형)는 통과."""
    if not isinstance(table_node, ast.Dict):
        return []
    return sorted(
        k.value
        for k, v in zip(table_node.keys, table_node.values)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
        and isinstance(v, ast.Constant) and v.value is None
    )


def _extract_op_defaults(handler_text: str) -> dict[str, str] | None:
    """handler.py 본문에서 _OP_DEFAULTS dict 를 AST 로 파싱.

    Returns:
        {tool_name: default_op_str} 또는 None.
    """
    try:
        tree = ast.parse(handler_text)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_OP_DEFAULTS" not in names:
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        result: dict[str, str] = {}
        for k_node, v_node in zip(node.value.keys, node.value.values):
            if (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)
                    and isinstance(v_node, ast.Constant) and isinstance(v_node.value, str)):
                result[k_node.value] = v_node.value
        return result
    return None


def _check_op_axis(qualified: str, action: dict, ops: dict, values: dict) -> list[str]:
    """op 축 형제 맵(`ops.returns` / `ops.side_effect`) 스키마 검증 — 감사 부채 ③.

    해소 의미론은 `backend/ibl_ops.py` 가 단일 소스. 여기선 **드리프트만** 막는다:
    유령 op 키(values 에 없는 이름)는 조용히 무시돼 "선언했는데 안 먹는" 부류가 되고,
    그건 이 감사가 잡아낸 침묵 실패 가족과 같은 병이다.
    """
    issues: list[str] = []
    from ibl_ops import OP_RETURNS_ENUM

    for field, checker, expect in (
        ("returns", lambda v: isinstance(v, str) and v in OP_RETURNS_ENUM,
         "|".join(sorted(OP_RETURNS_ENUM))),
        ("side_effect", lambda v: isinstance(v, bool), "true|false"),
        # F14-4 (2026-08-20): op 레벨 AI 낱말 고지 — 한 op 만 모델을 부르는 액션용(notebook#ask)
        ("ai_call", lambda v: isinstance(v, bool), "true|false"),
    ):
        block = ops.get(field)
        if block is None:
            continue
        if not isinstance(block, dict) or not block:
            issues.append(f"{qualified}: ops.{field} 는 비어있지 않은 매핑이어야 함 ({{op: {expect}}})")
            continue
        for op_name, val in block.items():
            if op_name not in values:
                issues.append(
                    f"{qualified}: ops.{field}.{op_name} — ops.values 에 없는 유령 op "
                    f"(선언해도 아무 효과 없음)"
                )
            if not checker(val):
                issues.append(f"{qualified}: ops.{field}.{op_name}={val!r} — {expect} 여야 함")

    # --- 행위 검증 형제 맵(`ops.fixture` / `ops.exempt`) — 감사 부채 ⑤ ---
    from ibl_ops import op_returns, op_side_effect

    for field in ("fixture", "exempt"):
        block = ops.get(field)
        if block is None:
            continue
        if not isinstance(block, dict) or not block:
            issues.append(f"{qualified}: ops.{field} 는 비어있지 않은 매핑이어야 함")
            continue
        for op_name, val in block.items():
            if op_name not in values:
                issues.append(
                    f"{qualified}: ops.{field}.{op_name} — ops.values 에 없는 유령 op "
                    f"(선언해도 아무 효과 없음)"
                )
                continue
            if not isinstance(val, str) or not val.strip():
                issues.append(f"{qualified}: ops.{field}.{op_name} 는 비어있지 않은 문자열이어야 함")
                continue
            if field != "fixture":
                continue
            # ★쓰기 op 에 fixture 를 달면 무인 건강검진이 **매일 그 부작용을 실행**한다
            # (2026-07-19 실측 부류: mkdir fixture 가 검진마다 폴더를 만들고 있었다).
            if op_side_effect(action, op_name):
                issues.append(
                    f"{qualified}: ops.fixture.{op_name} — 부작용 op 에는 fixture 를 달 수 없다 "
                    f"(건강검진이 매 실행마다 부작용을 낸다). 읽기 op 만."
                )
            if op_returns(action, op_name) == "effect":
                issues.append(
                    f"{qualified}: ops.fixture.{op_name} — returns:effect op 은 실행 대상 밖"
                )
            # fixture 코드가 정말 그 op 을 부르는가 (드리프트 차단 — 다른 op 을 부르면
            # 그 op 은 영영 미검증인 채 '커버됨'으로 계산된다)
            m = re.search(r'op\s*:\s*["\']([^"\']+)["\']', val)
            called = m.group(1) if m else ops.get("default")
            if called != op_name:
                issues.append(
                    f"{qualified}: ops.fixture.{op_name} 코드가 부르는 op 은 "
                    f"'{called}' — 키와 불일치"
                )

    both = set((ops.get("fixture") or {})) & set((ops.get("exempt") or {}))
    if both:
        issues.append(
            f"{qualified}: op {sorted(both)} 가 ops.fixture 와 ops.exempt 에 동시 선언 "
            f"(둘 중 하나만)"
        )

    # 모순 차단: 세계를 바꾸는 통화(effect)를 선언해놓고 '안전하다'고 말할 수는 없다.
    # 이걸 허용하면 무인 자가점검 루프가 부작용 op 를 매일 실행한다.
    #
    # ★**해소된** 값으로 잰다(2026-08-05 감사 ⑤). op 가 명시적으로 `side_effect: false`
    # 라고 말했는데 통화는 액션의 `returns: effect` 를 상속하는 경우가 같은 모순인데
    # 옛 검사(선언된 op_ret 만 조회)는 못 봤다 — `limbs:browser` content/find/logs 처럼
    # **읽기라고 선언해 놓고 통화는 미선언**인 op 들이 그렇게 24개 있었다. 그 상태는
    # 행위 검증에서 조용히 빠진다(effect 는 실행 대상 밖이므로 fixture 를 요구받지 않는다).
    from ibl_ops import op_returns as _op_returns

    op_se = ops.get("side_effect") if isinstance(ops.get("side_effect"), dict) else {}
    for op_name, se in op_se.items():
        if se is False and _op_returns(action, op_name) == "effect":
            issues.append(
                f"{qualified}: op '{op_name}' 가 side_effect:false 인데 통화는 effect — 모순. "
                f"읽기 op 이면 자기 통화를 선언할 것 (`ops.returns: {{{op_name}: items|scalar}}`)"
            )
    return issues


def _check_action(
    qualified: str,
    action: dict,
    tool_index: dict[str, tuple[Path, dict]],
) -> list[str]:
    """단일 액션의 정합성을 검사하고 문제 리스트를 반환."""
    issues: list[str] = []
    router = action.get("router")
    tool_name = action.get("tool")
    target_key = action.get("target_key")
    ops = action.get("ops")

    # --- ops 스키마 자체 검증 ---
    if ops is not None:
        if target_key != "op":
            issues.append(
                f"{qualified}: ops 블록은 target_key:op 인 액션에서만 허용 "
                f"(현재 target_key={target_key!r})"
            )
        if not isinstance(ops, dict):
            issues.append(f"{qualified}: ops 는 매핑이어야 함")
            return issues
        values = ops.get("values")
        if not isinstance(values, dict) or not values:
            issues.append(f"{qualified}: ops.values 가 비어있거나 매핑이 아님")
            return issues
        for op_name, op_desc in values.items():
            if not isinstance(op_desc, str):
                # values 는 {op: 설명 문자열} 로 고정 — 프롬프트 카탈로그·조종실 UI·
                # capability card 등 8곳이 이 모양을 읽는다. op 별 메타는 형제 맵
                # (ops.returns / ops.side_effect)으로 붙일 것 (backend/ibl_ops.py 참조).
                issues.append(
                    f"{qualified}: ops.values.{op_name} 는 설명 문자열이어야 함 "
                    f"(op 별 통화·부작용은 ops.returns / ops.side_effect 형제 맵으로)"
                )
        issues += _check_op_axis(qualified, action, ops, values)

    # --- aliases(파라미터 별칭) 스키마 검증 — 어휘 데이터화(2026-07-03) ---
    # 형식: aliases: {<정규 키>: [<별칭>, ...]} — 런타임 _normalize_param_aliases 가 읽는다.
    aliases = action.get("aliases")
    if aliases is not None:
        if not isinstance(aliases, dict) or not aliases:
            issues.append(f"{qualified}: aliases 는 비어있지 않은 매핑이어야 함 ({{정규키: [별칭...]}})")
        else:
            for canonical, alts in aliases.items():
                if not isinstance(alts, list) or not alts or not all(
                    isinstance(a, str) and a for a in alts
                ):
                    issues.append(f"{qualified}: aliases.{canonical} 는 비어있지 않은 문자열 리스트여야 함")
                elif canonical in alts:
                    issues.append(f"{qualified}: aliases.{canonical} 에 정규 키 자신이 별칭으로 들어감")

    # target_key:op 인데 ops 없음 — 모든 라우터에서 강제 (IBL 어휘 일관성).
    # handler 가 아닌 라우터(system/workflow_engine/trigger_engine 등)는 tool.json 삼각 검증은 못 하지만
    # ops 블록 자체는 어휘 완성을 위해 필수.
    if target_key == "op" and ops is None:
        issues.append(f"{qualified}: target_key:op 인데 ops 블록 없음 ({router or 'unknown'} 라우터)")

    # --- returns(통화 역할) 검증 — 단일 통화(items) 이행 완료(2026-06-27) ---
    # 모든 액션은 자기 통화 역할을 명시한다: 생성(items) · 변환(transform) · 종착(scalar/effect).
    # ★단일 통화: 컬렉션은 전부 items {[{…열린 필드…}]}. 옛 records/table/document/currency 는
    #   전부 items로 흡수 완료 — table(연도×지표 등)·문서IR(type+text)도 items 행dict로, 소비자가 재구성.
    #   (이행 이력: docs/SINGLE_CURRENCY_MIGRATION_HANDOFF.md / architecture_single_currency_items 메모)
    #   ※geo/지도는 통화 아님 — map_data 는 *렌더링 봉투*(파이프 변환자 없음).
    _RETURNS_ENUM = {"items", "transform", "scalar", "effect"}
    returns = action.get("returns")
    group = action.get("group")
    if returns is None:
        issues.append(f"{qualified}: returns 필드 없음 — 통화 역할 명시 필수 (items|transform|scalar|effect)")
    elif returns not in _RETURNS_ENUM:
        issues.append(f"{qualified}: returns={returns!r} 허용 안 됨 (items|transform|scalar|effect)")
    else:
        if group == "transform" and returns != "transform":
            issues.append(f"{qualified}: group:transform 인데 returns={returns!r} — transform 이어야 함")
        if returns == "transform" and group != "transform":
            issues.append(f"{qualified}: returns:transform 은 group:transform 액션에만 (현재 group={group!r})")

    # --- handler 라우터 등록 검증 ---
    if router == "handler":
        if not tool_name:
            issues.append(f"{qualified}: router:handler 인데 tool 필드 없음")
            return issues

        if tool_name not in tool_index:
            issues.append(
                f"{qualified}: tool '{tool_name}' 가 어느 패키지 tool.json 에도 미등록"
            )
            return issues

        pkg_dir, tool_def = tool_index[tool_name]
        pkg_name = pkg_dir.name

        # --- op 삼각 검증 ---
        if ops:
            tj_op_prop = (
                tool_def.get("input_schema", {})
                .get("properties", {})
                .get("op", {})
            ) or {}
            tj_enum = tj_op_prop.get("enum")
            tj_default = tj_op_prop.get("default")

            if not tj_enum:
                issues.append(
                    f"{qualified}: src.ops 선언했으나 tool.json {pkg_name}/{tool_name} "
                    f"에 input_schema.properties.op.enum 없음"
                )
            else:
                src_keys = set(ops.get("values", {}).keys())
                tj_keys = set(tj_enum)
                if src_keys != tj_keys:
                    only_src = sorted(src_keys - tj_keys)
                    only_tj = sorted(tj_keys - src_keys)
                    detail = []
                    if only_src:
                        detail.append(f"src만 있음: {only_src}")
                    if only_tj:
                        detail.append(f"tool.json만 있음: {only_tj}")
                    issues.append(
                        f"{qualified}: op 키 불일치 ({pkg_name}/{tool_name}) — "
                        f"{'; '.join(detail)}"
                    )

            src_default = ops.get("default")
            if src_default != tj_default:
                issues.append(
                    f"{qualified}: op default 불일치 ({pkg_name}/{tool_name}) — "
                    f"src={src_default!r} / tool.json={tj_default!r}"
                )

            # --- handler.py 검사 (AST 우선, substring 폴백) ---
            handler_py = pkg_dir / "handler.py"
            if handler_py.is_file():
                src_text = handler_py.read_text(encoding="utf-8")
                src_op_keys = set(ops.get("values", {}).keys())
                dispatchers = _extract_op_dispatchers(src_text)

                if dispatchers is not None and tool_name in dispatchers:
                    # AST 정확 비교 — _OP_DISPATCHERS[tool_name] 키 ↔ src.ops.values 키
                    handler_keys, table_node = dispatchers[tool_name]

                    # 장식 스텁 금지 (2026-08-05 감사 ① — 15개 스텁 전환 후 재발 봉쇄):
                    # 값이 None 인 테이블은 "준수처럼 보이는 부재" — 키만 맞고 분기는
                    # if/elif 체인에 살아 있으면, 체인에서 분기 하나가 사라져도 이 가드가
                    # 못 본다. 값은 함수 참조(또는 browser-action/computer-use 식 문자열
                    # 디스패치 키)여야 한다.
                    stub_ops = _stub_ops(table_node)
                    if stub_ops:
                        issues.append(
                            f"{qualified}: _OP_DISPATCHERS[{tool_name!r}] 값이 None "
                            f"({pkg_name}) — 장식 스텁 금지, 진짜 함수 참조로: {stub_ops}"
                        )
                    if handler_keys != src_op_keys:
                        only_src = sorted(src_op_keys - handler_keys)
                        only_handler = sorted(handler_keys - src_op_keys)
                        detail = []
                        if only_src:
                            detail.append(f"src만: {only_src}")
                        if only_handler:
                            detail.append(f"handler만: {only_handler}")
                        issues.append(
                            f"{qualified}: handler.py _OP_DISPATCHERS[{tool_name!r}] 키 불일치 "
                            f"({pkg_name}) — {'; '.join(detail)}"
                        )

                    # _OP_DEFAULTS 도 검사 (있을 때만)
                    defaults = _extract_op_defaults(src_text)
                    if defaults is not None:
                        handler_default = defaults.get(tool_name)
                        src_default = ops.get("default")
                        if handler_default != src_default:
                            issues.append(
                                f"{qualified}: _OP_DEFAULTS[{tool_name!r}] 불일치 "
                                f"({pkg_name}) — src={src_default!r} / handler={handler_default!r}"
                            )
                else:
                    # 폴백: substring 휴리스틱
                    missing = [
                        k
                        for k in src_op_keys
                        if f'"{k}"' not in src_text and f"'{k}'" not in src_text
                    ]
                    if missing:
                        issues.append(
                            f"{qualified}: handler.py {pkg_name} 에 op 문자열 미발견 — {missing} "
                            f"(_OP_DISPATCHERS 도입 권장)"
                        )

    return issues


# _file_read_keys / _dir_read_keys 는 backend/ibl_param_vocab.py 에서 import (iblbuild_common 경유).


def _load_corpus_param_keys(root: Path) -> dict[str, set[str]] | None:
    """학습 코퍼스를 실제 IBL 파서로 파싱 → {qualified: set(top-level param 키)}.
    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    backend = root / "backend"
    try:
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
            import boot_paths  # noqa: F401 — 층 디렉토리 등재

        import ibl_parser  # type: ignore
    except Exception:
        return None

    def walk(obj):
        res = []
        if isinstance(obj, dict):
            if "_node" in obj and "action" in obj:
                res.append(obj)
            for v in obj.values():
                res += walk(v)
        elif isinstance(obj, list):
            for v in obj:
                res += walk(v)
        return res

    out: dict[str, set[str]] = {}
    found_any = False
    for rel in CORPUS_FILES:
        f = root / rel
        if not f.is_file():
            continue
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        found_any = True
        for e in entries:
            try:
                parsed = ibl_parser.parse(e.get("ibl_code", ""))
            except Exception:
                continue
            for st in walk(parsed):
                q = f"{st.get('_node')}:{st.get('action')}"
                out.setdefault(q, set()).update((st.get("params") or {}).keys())
    return out if found_any else None


def _corpus_entries(root: Path, include_db: bool = False):
    """트레이너가 **실제로 읽는** 학습 입력을 그대로 훑는다.

    ★CORPUS_FILES 는 두 파일을 이름으로 못박고 있는데, 트레이너는
    `data/training/*.json` 글롭이다(ibl_embedding_trainer.py). 그 차이만큼 검사가
    학습 입력보다 좁았다 — 여기서는 트레이너와 같은 규칙을 쓴다.

    ★2026-08-22 (20회차 B20-1): 그런데 트레이너는 **DB(ibl_usage.db)와 파일을 둘 다**
    읽는다 — 바로 아래 validate_corpus_vocab 의 docstring 자신이 그렇게 적고 있으면서도
    검사는 파일만 봤다. 즉 **검사가 학습 입력의 절반만 보고 있었다**(20회차에 발견된
    유령 op 오염이 하필 DB 쪽에 있었다). include_db=True 면 DB 도 같은 모양으로 낸다.
    기본이 False 인 이유: param 정합 검사는 관대한 상위집합 대조라 범위를 넓히면
    오탐이 폭증한다 — 어휘/op 생존처럼 오탐이 없는 검사만 켠다.
    반환: (출처이름, 항목) 이터레이터. 없으면 아무것도 내지 않는다."""
    tdir = root / "data" / "training"
    if tdir.is_dir():
        for f in sorted(tdir.glob("*.json")):
            try:
                entries = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(entries, list):
                continue
            for e in entries:
                if isinstance(e, dict):
                    yield f.name, e
    if not include_db:
        return
    db = root / "data" / "ibl_usage.db"
    if not db.is_file():
        return
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute("SELECT intent, ibl_code FROM ibl_examples").fetchall()
        con.close()
    except Exception:
        return
    for intent, code in rows:
        yield "ibl_usage.db", {"intent": intent, "ibl_code": code}


def validate_corpus_vocab(data: dict, root: Path) -> list[str] | None:
    """학습 코퍼스가 **아직 존재하는 어휘**만 가르치는지 + 전부 파싱되는지.

    2026-08-22 실측 배경: 라이브 코퍼스(ibl_usage.db)는 어휘 은퇴 때마다 이관돼 왔지만
    `data/training/ibl_training_balanced_20260516.json` 은 부분적으로만 따라와, 은퇴 어휘
    20여 종 208항목을 3개월간 안고 있었다. 트레이너는 DB 와 이 파일을 **둘 다** 읽으므로
    다음 풀 재학습이 죽은 어휘를 그대로 되살린다. 아무도 안 보고 있었다 — param 정합
    검사는 같은 파일을 읽으면서도 "이 액션이 아직 있나" 는 묻지 않았고, 파싱 실패는
    `except: continue` 로 조용히 넘겼다(그 침묵이 파싱 불가 용례 1건을 살려 뒀다).

    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    backend = root / "backend"
    try:
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
            import boot_paths  # noqa: F401
        import ibl_parser  # type: ignore
    except Exception:
        return None

    def walk(obj):
        res = []
        if isinstance(obj, dict):
            if "_node" in obj and "action" in obj:
                res.append(obj)
            for v in obj.values():
                res += walk(v)
        elif isinstance(obj, list):
            for v in obj:
                res += walk(v)
        return res

    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    issues: list[str] = []
    seen_any = False
    for fname, e in _corpus_entries(root, include_db=True):
        seen_any = True
        code = e.get("ibl_code") or ""
        intent = str(e.get("intent") or "")[:40]
        try:
            parsed = ibl_parser.parse(code)
        except Exception as ex:
            issues.append(f"{fname}: 파싱 불가 — {intent} :: {str(ex)[:60]}")
            continue
        for st in walk(parsed):
            n, a = st.get("_node"), st.get("action")
            ac = (nodes.get(n, {}).get("actions") or {}).get(a) if n in nodes else None
            if ac is None:
                issues.append(f"{fname}: 죽은 어휘 [{n}:{a}] — {intent}")
                continue
            # ★2026-08-22 (20회차 B20-1): 액션이 살아 있어도 **op 가 죽어 있으면**
            # 코퍼스는 실행 불가능한 문장을 가르친다. 액션 은퇴는 이관돼 왔지만 op
            # 은퇴(stock price→quote, output file→self:write 흡수 …)는 아무도 안 봤고,
            # 해마가 그 형태를 회상시키면 번역기가 죽은 문장을 뱉는다 — 실패는 실행
            # 시점에야 드러난다. 액션 생존과 같은 자로 op 생존도 잰다(새 검사 아님, 같은 루프).
            _ops = (ac.get("ops") or {}).get("values") if isinstance(ac, dict) else None
            if _ops:
                _op = (st.get("params") or {}).get("op")
                if isinstance(_op, str) and _op and _op not in _ops:
                    issues.append(
                        f"{fname}: 죽은 op [{n}:{a}]{{op: '{_op}'}} — {intent} "
                        f"(사용 가능: {sorted(_ops)})")
    if not seen_any:
        return None
    # 같은 어휘가 수십 건 반복되므로 앞부분만 보여준다(원인은 어휘 하나다).
    return issues


def validate_corpus_params(data: dict, root: Path) -> list[str] | None:
    """코퍼스 param 키 ↔ (핸들러 읽기키 ∪ 액션 aliases 선언 ∪ 보편키 ∪ target_key) 대조.

    코퍼스가 자연어로 쓰는 키를 핸들러가 조용히 무시하는 신규 불일치를 검출한다.
    router:handler 액션은 패키지 .py 전체를, 그 외(system/engine/driver/trigger)는
    backend/*.py 전역 어휘를 핸들러 키 출처로 본다 (후자는 보수적 = 오탐 회피 우선).
    파서/코퍼스 미가용 시 None (검사 건너뜀)."""
    corpus = _load_corpus_param_keys(root)
    if corpus is None:
        return None
    aliases = _extract_action_param_aliases(data)
    tool_index = build_tool_index(root)
    backend_keys = _dir_read_keys((root / "backend").rglob("*.py"))
    pkg_cache: dict[Path, set[str]] = {}

    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            used = corpus.get(qualified)
            if not used:
                continue
            # 런타임 메타 키(project_id·scope)는 핸들러 인자가 아니라 라우팅이 읽는다.
            # 런타임 허용집합(ibl_param_vocab._allowed_keys)은 이미 이걸 더하는데 이 가드만
            # 빼놓아, 두 층이 같은 질문에 다르게 답하고 있었다 — 단일 소스로 정렬(2026-08-22).
            known = set(UNIVERSAL_PARAM_KEYS) | set(RUNTIME_META_KEYS)
            if action.get("target_key"):
                known.add(action["target_key"])
            known |= aliases.get(qualified, set())
            known |= CORPUS_PARAM_ALLOW.get(qualified, set())
            tool_name = action.get("tool")
            if action.get("router") == "handler" and tool_name and tool_name in tool_index:
                pkg_dir = tool_index[tool_name][0]
                if pkg_dir not in pkg_cache:
                    pkg_cache[pkg_dir] = _dir_read_keys(pkg_dir.rglob("*.py"))
                known |= pkg_cache[pkg_dir]
            else:
                known |= backend_keys
            unknown = sorted(used - known)
            if unknown:
                issues.append(
                    f"{qualified}: 코퍼스 param 키가 핸들러/별칭에 없음 — {unknown} "
                    f"(액션 정의처의 aliases: 블록에 별칭 추가 · 핸들러 폴백 · 코퍼스 정정 중 택1; "
                    f"의도된 노이즈면 build_ibl_nodes.CORPUS_PARAM_ALLOW 에 등록)"
                )
    return issues


def _enum_param_branch_literals(
    handler_text: str, params: set[str]
) -> dict[str, set[str]] | None:
    """handler.py AST에서 tool_input.get("<param>") 유래 값과 비교되는 ASCII 리터럴 수집.

    잡는 모양 (realty naver 드리프트 실사례 기준):
      _source = (tool_input.get("source") or "molit").strip().lower()
      if _source in ("zigbang", "직방"): ...   ← "zigbang" 수집 ("직방"=한글 별칭이라 제외)
      if tool_input.get("deal") == "trade": ... ← 중간 변수 없는 직접 비교도 수집
    반환 {param: {literal,...}} / 파싱 실패 시 None."""
    try:
        tree = ast.parse(handler_text)
    except SyntaxError:
        return None

    _ascii_val = re.compile(r"^[a-z0-9_]+$")

    def _params_in(node) -> set[str]:
        found: set[str] = set()
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "get"
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "tool_input"
                and sub.args
                and isinstance(sub.args[0], ast.Constant)
                and isinstance(sub.args[0].value, str)
                and sub.args[0].value in params
            ):
                found.add(sub.args[0].value)
        return found

    def _str_literals(comparators) -> set[str]:
        lits: set[str] = set()
        for comp in comparators:
            if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                lits.add(comp.value)
            elif isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                for elt in comp.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        lits.add(elt.value)
        return {s for s in lits if _ascii_val.match(s)}

    out: dict[str, set[str]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        varmap: dict[str, set[str]] = {}
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                ps = _params_in(node.value)
                if ps:
                    varmap[node.targets[0].id] = ps
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            if not all(
                isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn))
                for op in node.ops
            ):
                continue
            left = node.left
            if isinstance(left, ast.Name) and left.id in varmap:
                ps = varmap[left.id]
            else:
                ps = _params_in(left)
            if not ps:
                continue
            lits = _str_literals(node.comparators)
            if not lits:
                continue
            for p in ps:
                out.setdefault(p, set()).update(lits)
    return out


# handler 가 관용으로 받아주는 입력 *별칭* — 정규화 후 enum 값으로 처리되므로
# enum(광고 계약)에 싣지 않는 게 의도인 값들. 새 별칭을 handler 에 추가하면 여기 등록.
# ★진짜 새 기능 값(예 realty source=naver)은 여기 넣지 말고 enum 을 갱신할 것 —
#   여기는 "이미 enum 에 있는 값의 다른 표기"만 허용된다.
_ENUM_VALUE_ALIASES: dict[tuple[str, str], set[str]] = {
    ("data-ops", "format"): {"md"},                # md → markdown 정규화
    ("lecture_workspace", "format"): {"pptx_image"},  # pptx_image → pptx(이미지)와 동일 경로
    ("study", "source"): {
        "pmc",                                     # → pubmed 경로
        "semantic_scholar", "s2",                  # → semantic
        "kr", "dissertation",                      # → nanet
        "wd", "wikimedia",                         # → wikidata
    },
}


def validate_enum_handler_branches(root: Path) -> list[str]:
    """파라미터 enum ↔ handler 분기 리터럴 정합 (2026-07-28 신설).

    드리프트 부류: handler 가 실제로 지원하는 discriminator 값(예 realty source="naver")이
    tool.json(파생 스키마) enum 에 빠져, 실행 에이전트가 그 값의 존재를 desc 산문으로만
    알게 되는 것. 방향은 handler 분기 리터럴 ⊆ enum 한쪽만 본다 — 역방향(enum 값이
    handler 에 미등장)은 default fallthrough(molit 등)가 정상이라 검사하지 않는다.
    op 파라미터는 기존 _OP_DISPATCHERS 삼각 검증 담당이므로 제외."""
    issues: list[str] = []
    tool_index = build_tool_index(root)

    # 패키지별 {param: enum 값 합집합} — subset 검사라 합집합은 안전한 방향(느슨해질 뿐).
    by_pkg: dict[Path, dict[str, set[str]]] = {}
    for _tool_name, (pkg_dir, tool_def) in tool_index.items():
        props = (tool_def.get("input_schema") or {}).get("properties") or {}
        for pname, pdef in props.items():
            if pname == "op" or not isinstance(pdef, dict):
                continue
            enum = pdef.get("enum")
            if not enum:
                continue
            allowed = {v for v in enum if isinstance(v, str)}
            if isinstance(pdef.get("default"), str):
                allowed.add(pdef["default"])
            by_pkg.setdefault(pkg_dir, {}).setdefault(pname, set()).update(allowed)

    for pkg_dir, enum_map in sorted(by_pkg.items()):
        handler_py = pkg_dir / "handler.py"
        if not handler_py.is_file():
            continue
        got = _enum_param_branch_literals(
            handler_py.read_text(encoding="utf-8"), set(enum_map)
        )
        if not got:
            continue
        for pname, lits in sorted(got.items()):
            allowed_aliases = _ENUM_VALUE_ALIASES.get((pkg_dir.name, pname), set())
            extra = sorted(lits - enum_map[pname] - allowed_aliases)
            if extra:
                issues.append(
                    f"{pkg_dir.name}/handler.py: 파라미터 {pname!r} 분기 리터럴 {extra} 가 "
                    f"enum {sorted(enum_map[pname])} 에 없음 — "
                    f"ibl_actions.yaml tool_json 블록의 enum 갱신 필요"
                )
    return issues


def validate_runs_on(data: dict) -> list[str]:
    """모든 액션의 runs_on 값이 유효 enum 인지 검사 (미지정=anywhere 허용)."""
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            ro = action.get("runs_on")
            if ro is not None and ro not in VALID_RUNS_ON:
                issues.append(
                    f"{node_name}:{action_name} — 잘못된 runs_on '{ro}' "
                    f"(허용: {', '.join(sorted(VALID_RUNS_ON))})"
                )
    return issues


def validate_transform_contract(data: dict) -> list[str]:
    """통화 변환자(group: transform) 계약 강제 — 닫힌-계급 문법/superstructure.

    변환자(filter/sort/groupby/join…)는 통화→통화 순수 함수다 — 몸 무관, 외부 자원 없음.
    *이름*(현재 engines:)이 아니라 **group 태그가 닫힌 계급의 단일 마커**다(설계 결정:
    비싼 노드 이전 대신 태그를 load-bearing 으로 — docs/ibl_design_philosophy.md). 계약:
      - scope: workspace  — 무프로젝트 파이프에서도 돌아야(project 기본이면 0ms 즉시 실패: 과거 버그)
      - runs_on: anywhere — 통화는 몸 무관(폰-로컬 통화도 그 몸에서 거르고 정렬)
    새 변환자가 이 계약을 빠뜨리면 침묵-실패가 재발 → 여기서 구조로 막는다.
    """
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or action.get("group") != "transform":
                continue
            q = f"{node_name}:{action_name}"
            if action.get("scope") != "workspace":
                issues.append(
                    f"{q} — 변환자(group:transform)는 scope: workspace 필수 "
                    f"(현재 '{action.get('scope') or '없음=project기본'}'). "
                    f"무프로젝트 파이프서 즉시 실패 방지."
                )
            if action.get("runs_on") != "anywhere":
                issues.append(
                    f"{q} — 변환자는 runs_on: anywhere 필수 "
                    f"(현재 '{action.get('runs_on') or '없음'}'). 통화는 몸 무관."
                )
    return issues


def validate_phone_reachability(data: dict, root: Path) -> list[str]:
    """runs_on 정직성: anywhere(기본) 액션인데 handler/driver 패키지가 PHONE_VERIFIED 가 아니면
    적발. 그런 액션은 폰서 _phone_runnable=False → 조용히 _forward_to_mac 된다(ibl_engine.py).
    즉 anywhere 와 pc_only 가 폰에서 행동이 같아 태그가 거짓 → silent-forward 라 self-check 가
    못 잡던 부류. 해소: 패키지를 PHONE_VERIFIED 에 넣거나(폰 로컬 실행) 액션에 runs_on: pc_only
    명시(허브 포워드 명시). 비-패키지(system/engine 등) 액션은 대상 아님(번들 모듈로 폰서 실행)."""
    issues: list[str] = []
    tool_index = build_tool_index(root)
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            ro = action.get("runs_on", DEFAULT_RUNS_ON)
            if ro != "anywhere":
                continue  # pc_only/phone_only = 명시적(정직)
            tool = action.get("tool")
            if not tool or tool not in tool_index:
                continue  # 비-패키지 액션(system/engine 등) — 번들 모듈로 폰 실행
            pkg = tool_index[tool][0].name
            if pkg not in PHONE_VERIFIED_PACKAGES:
                issues.append(
                    f"{node_name}:{action_name} — runs_on=anywhere 인데 패키지 '{pkg}' 폰 미검증 "
                    f"→ 폰서 조용히 허브 포워드(태그 거짓). 패키지를 PHONE_VERIFIED_PACKAGES 에 넣거나 "
                    f"액션에 'runs_on: pc_only' 명시."
                )
    return issues


def validate_fixture_coverage(data: dict, root: Path) -> list[str]:
    """행동 건강 fixture 완전성 강제 — 신규 액션이 건강검사망을 빠져나갈 수 없게.

    실행 가능한(returns: items|scalar) 액션은 자기 정의에 `fixture:`(올바른 파라미터
    예 하나) 또는 `exempt:`(실행 인자 의존 — 사유) 필드를 반드시 가져야 한다.
    effect(부작용 — 실행 불가)·transform(골든파이프로 흐름검증)은 면제.

    필드는 액션이 사는 소스(패키지 ibl_actions.yaml / 코어 ibl_nodes_src)에 두고,
    build 가 ibl_fixtures.json 으로 파생한다. 파생물이라 *고아 fixture 는 구조적으로
    없다*(과거의 별도 orphan 검사 불필요). 이로써 "어휘를 만들면 fixture 한 줄도 같이"가
    권고가 아니라 커밋 게이트가 되고(new_action_checklist.md), 제거는 재빌드만으로
    fixture 가 함께 빠진다(action_removal.md).
    """
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            # fixture 가 부르는 op 가 실재하는가 (2026-08-05 감사 ③).
            # 실측: `[self:blog]{op:"list"}` 는 선언에 없는 op 였고, 핸들러의
            # `.get(op) or _op_posts` 폴백이 조용히 삼켜 fixture 가 '통과'해 왔다 —
            # op 축을 도입한 이상 이 침묵은 구조로 막는다.
            fixture_code = action.get("fixture")
            declared_ops = ((action.get("ops") or {}).get("values")) or {}
            if isinstance(fixture_code, str) and declared_ops:
                m = re.search(r'op\s*:\s*["\']([^"\']+)["\']', fixture_code)
                if m and m.group(1) not in declared_ops:
                    issues.append(
                        f"{node_name}:{action_name}: fixture 가 선언에 없는 op "
                        f"'{m.group(1)}' 를 호출 (선언된 op: {sorted(declared_ops)}) — "
                        f"핸들러 폴백이 삼켜 '통과'처럼 보인다"
                    )

            if action.get("returns") in ("items", "scalar"):
                if not action.get("fixture") and not action.get("exempt"):
                    issues.append(
                        f"{node_name}:{action_name}: returns:items|scalar 인데 "
                        f"fixture/exempt 필드 없음 — 액션 정의(패키지 ibl_actions.yaml "
                        f"또는 ibl_nodes_src)에 `fixture: '[...]'` 한 줄 추가 "
                        f"(실행 인자 의존이면 `exempt: '<사유>'`)"
                    )
            elif action.get("fixture") or action.get("exempt"):
                # 역방향 가드: 확률대상 밖(effect·transform) 액션의 fixture/exempt 는 잉여이고,
                # fixture 는 §1B 가 실제로 실행하므로 부작용 액션이면 점검마다 부작용을 낸다
                # (2026-07-19 실측: mkdir fixture 가 검진마다 폴더를 만들고 있었다).
                field = "fixture" if action.get("fixture") else "exempt"
                issues.append(
                    f"{node_name}:{action_name}: returns:{action.get('returns')} 인데 "
                    f"`{field}:` 필드 보유 — items/scalar 전용 필드다. 제거할 것"
                    + (" (부작용 액션 fixture 는 건강검진마다 부작용 실행)" if field == "fixture" else "")
                )

            issues += _check_op_fixture_coverage(f"{node_name}:{action_name}", action)
    return issues


def _check_op_fixture_coverage(qualified: str, action: dict) -> list[str]:
    """op 축 fixture 완전성 — 감사 부채 ⑤ (2026-08-05).

    액션 레벨 `fixture:` 는 액션당 **한 op** 만 증명한다. ③이 op 단위 안전 분류를
    선언에서 파생 가능하게 만든 이상, "안전하다고 선언한 읽기 op 이 실제로 도는가"는
    물을 수 있는 질문이 됐다 — 실측으로 읽기 op 133개 중 fixture 가 닿는 건 37개였다.

    규칙: 읽기(side_effect=false) + 통화 items|scalar 인 op 은 아래 중 하나로 덮인다.
      ① `ops.fixture[op]`  ② `ops.exempt[op]`  ③ 액션 레벨 `fixture:` 가 그 op 을 호출
      ④ 액션 레벨 `exempt:` (액션 통째가 자동 실행 불가 — 기기·인자 의존)
    """
    from ibl_ops import op_names, op_needs_fixture

    ops = action.get("ops") if isinstance(action.get("ops"), dict) else {}
    names = op_names(action)
    if not names:
        return []
    if action.get("exempt"):
        return []            # ④ 액션 통째 면제
    op_fx = ops.get("fixture") or {}
    op_ex = ops.get("exempt") or {}
    # ③ 액션 레벨 fixture 가 고른 op
    act_op = None
    if isinstance(action.get("fixture"), str):
        m = re.search(r'op\s*:\s*["\']([^"\']+)["\']', action["fixture"])
        act_op = m.group(1) if m else ops.get("default")

    missing = [o for o in names
               if op_needs_fixture(action, o)
               and o not in op_fx and o not in op_ex and o != act_op]
    if not missing:
        return []
    return [
        f"{qualified}: 읽기 op {missing} 이 fixture/exempt 없음 — "
        f"`ops.fixture: {{{missing[0]}: '[…]{{op: \"{missing[0]}\"}}'}}` 한 줄 "
        f"(실행 인자 의존이면 `ops.exempt: {{{missing[0]}: '<사유>'}}`)"
    ]


def validate_node_guides(data: dict, root: Path) -> list[str]:
    """노드 레벨 guides: 목록이 data/guides/ 실존 파일을 가리키는지 검증.

    유령 등재는 의식 에이전트/read_guide 경로에서 침묵 실패(_load_guide_file 이
    빈 문자열 반환)로 이어지므로 빌드에서 막는다.
    """
    issues: list[str] = []
    guides_dir = root / "data" / "guides"
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for g in node.get("guides") or []:
            if not (guides_dir / str(g)).exists():
                issues.append(f"[{node_name}] guides 유령 등재: data/guides/{g} 실존하지 않음")
    return issues


# === 표준-코어 가드: IBL 표준(문법+기능어) 경계 통제 (2026-07-03, ibl.md '언어의 경계' 조항) ===
# IBL 표준 = 문법(연산자·[node:action]{params}·파이프 설탕) + 기능어 코어(아래 집합).
# 이 집합을 바꾸는 것은 '언어 개정'이다 — ibl.md 헌법 조항·파서 desugar·노드 yaml의
# always_on 플래그를 함께, 의식적으로 바꿔야 하며, 여기 선언을 갱신하지 않으면 빌드가 멈춘다.
# 내용어(그 외 노드의 액션)는 개인 사전: yaml+패키지 데이터만으로 추가·제거되어야 하고
# 파서·엔진 코드에 이름이 박히면 안 된다 (별칭·always_on 데이터화로 확립된 불변식).
STANDARD_CORE_NODES = {"self", "others", "table"}


def validate_standard_core(data: dict, root: Path) -> list[str]:
    """표준-코어 가드 — ①always_on 노드 집합이 STANDARD_CORE_NODES 선언과 일치하는지
    ②파서 파이프 설탕(_pipe_block)의 desugar 타깃(문법이 아는 유일한 어휘)이
    표준 코어 노드의 실존 액션인지 적발한다."""
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    on = {n for n, cfg in nodes.items()
          if isinstance(cfg, dict) and cfg.get("always_on") is True}
    if nodes and on != STANDARD_CORE_NODES:
        issues.append(
            f"표준-코어 가드: always_on 노드 집합 {sorted(on)} ≠ 선언 {sorted(STANDARD_CORE_NODES)} "
            "(STANDARD_CORE_NODES). 기능어 코어 변경은 언어 개정 — ibl.md '언어의 경계' 조항과 "
            "이 선언을 함께 갱신할 것."
        )
    from iblbuild_common import backend_module_path
    parser_path = backend_module_path(root, "ibl_parser")
    try:
        src = parser_path.read_text(encoding="utf-8")
    except OSError:
        issues.append(f"표준-코어 가드: 파서를 읽지 못함 ({parser_path})")
        return issues
    m = re.search(r"def _pipe_block\(.*?(?=\ndef |\Z)", src, re.S)
    body = m.group(0) if m else ""
    targets = set(re.findall(r"\[(\w+):(\w+)\]", body))
    if not targets:
        issues.append(
            "표준-코어 가드: 파서 _pipe_block 에서 desugar 타깃([x:y] 코드젠 리터럴)을 찾지 못함 — "
            "함수 이동/개명 시 이 가드도 함께 갱신할 것"
        )
    for node_name, action_name in sorted(targets):
        if node_name not in STANDARD_CORE_NODES:
            issues.append(
                f"표준-코어 가드: 파서 desugar 가 비표준 노드 [{node_name}:{action_name}] 를 코드젠 — "
                "문법 설탕은 기능어 코어(STANDARD_CORE_NODES)로만 펼칠 수 있음"
            )
        elif action_name not in ((nodes.get(node_name) or {}).get("actions") or {}):
            issues.append(
                f"표준-코어 가드: 파서 desugar 타깃 [{node_name}:{action_name}] 가 레지스트리에 없음 — "
                "표준 코어 액션 개명 시 ibl_parser._pipe_block 도 함께 (언어 개정)"
            )
    return issues


def validate_side_effect_declaration(data: dict) -> list[str]:
    """op-분기 액션은 안전 여부를 *말로* 선언해야 한다 (2026-07-28 신설).

    `returns:` 는 오래 두 가지 일을 겸했다 — 통화 선언이자, ibl_safety.is_side_effect 가
    부작용 여부를 파생하는 근거(`returns == "effect"`). 두 축이 어긋나면 조종실 dry-run 의
    실행 자물쇠(ManualMode canExecute)가 안 걸린다. 실제로 `[self:memory]{op:"delete"}` ·
    `[others:portal]{op:"revoke"}` 등 18개가 '부작용 없음'으로 판정돼 확인 없이 실행됐다.

    규칙: op 분기가 있고 `returns` 가 effect 가 아니면 `side_effect:` 를 명시하라.
    2026-08-05(감사 ③): op 축 도입 후, **모든 op 가 `ops.side_effect` 에서 자기 몫을
    말했으면** 액션 단위 요약은 잉여다(더 정확한 선언이 이미 있다) — 그 경우도 통과.

    ★op *이름*으로 추측하지 않는 것이 요점. 처음엔 읽기 전용 op 허용목록으로 짜봤는데
      quote·inbox·nearby·hotel·transcript 처럼 도메인마다 새 낱말이 끝없이 나와
      오탐 25건이 났다(파괴적 op 목록을 쓰면 반대로 조용히 샌다). 어느 쪽이든 손으로
      기르는 낱말 목록이 되고, 그 목록이 낡는 순간 이 가드가 거짓말을 한다.
      한 줄로 적게 하면 낱말 목록이 아예 없어지고, 아는 사람이 아는 것을 말하게 된다.
    """
    issues: list[str] = []
    for node_name, node_def in (data.get("nodes") or {}).items():
        for action_name, adef in ((node_def or {}).get("actions") or {}).items():
            if not isinstance(adef, dict):
                continue
            op_values = ((adef.get("ops") or {}).get("values")) or {}
            if not op_values:
                continue
            if adef.get("returns") == "effect" or isinstance(adef.get("side_effect"), bool):
                continue
            per_op = ((adef.get("ops") or {}).get("side_effect")) or {}
            if isinstance(per_op, dict) and set(op_values) <= set(per_op):
                continue  # 전 op 가 자기 몫을 말했다 — 액션 요약 불필요
            issues.append(
                f"안전-가드: [{node_name}:{action_name}] 는 op 분기 액션인데 "
                f"returns:{adef.get('returns')} 이고 side_effect: 선언이 없음 — "
                "부작용 op 가 하나라도 있으면 조종실 dry-run 이 '부작용 없음'으로 표시해 "
                "실행 확인을 건너뛴다. `side_effect: true/false` 를 명시하라 "
                "(op 하나라도 쓰기·전송·삭제·외부변경이면 true)"
            )
    return issues


def validate_always_on(data: dict) -> list[str]:
    """노드 레벨 always_on 플래그 검증 — 인프라/문법 노드 항상-on 의 단일 소스(2026-07-03 데이터화).

    ibl_access._always_allowed() 가 이 플래그로 항상-허용 노드 집합을 만든다.
    전부 사라지면 노드 선별(allowed_nodes) 시 self/others/table 파이프라인이
    침묵으로 깨지므로 빌드에서 막는다."""
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    on: list[str] = []
    for node_name, node in nodes.items():
        if not isinstance(node, dict) or "always_on" not in node:
            continue
        if not isinstance(node["always_on"], bool):
            issues.append(f"[{node_name}] always_on 은 불리언이어야 함 (현재 {node['always_on']!r})")
        elif node["always_on"]:
            on.append(node_name)
    if nodes and not on:
        issues.append(
            "always_on: true 노드가 하나도 없음 — 인프라/문법 노드(self/others/table)가 "
            "노드 선별에서 꺼지면 파이프라인이 깨짐 (노드 yaml 에 always_on: true 복구 필요)"
        )
    return issues


def validate_desc_discipline(data: dict) -> list[str]:
    """desc 위생 lint (2026-07-28 카탈로그 감사 후속).

    description 은 '존재 신호 + 파라미터/사용 계약 + 변별'만 싣는다 — 서사·유래·구현담은
    미주입 필드(target_description/implementation)로, op 나열은 ops 블록이 카탈로그에
    이미 찍히므로 중복 금지.
    ① 길이 상한 DESC_MAX(액션)·OP_DESC_MAX(op) — 넘으면 서사가 새어 들어온 신호.
    ② 노드 간 이름 충돌 액션(cctv 3형제 등)은 desc 에 다른 멤버([node:action])를 언급해
       변별 근거를 싣는다 — 설명 없이는 어느 쪽인지 판단 근거가 사라지는 부류."""
    DESC_MAX = 200
    OP_DESC_MAX = 80
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    by_name: dict[str, list[tuple[str, str]]] = {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for aname, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            desc = action.get("description") or ""
            if len(desc) > DESC_MAX:
                issues.append(
                    f"{node_name}:{aname}: description {len(desc)}자 > {DESC_MAX}자 — "
                    f"서사·구현담은 target_description/implementation 으로, op 나열은 ops 블록으로"
                )
            ops = action.get("ops") if isinstance(action.get("ops"), dict) else {}
            for op_name, op_desc in (ops.get("values") or {}).items():
                if isinstance(op_desc, str) and len(op_desc) > OP_DESC_MAX:
                    issues.append(
                        f"{node_name}:{aname}.{op_name}: op 설명 {len(op_desc)}자 > {OP_DESC_MAX}자 — "
                        f"파라미터 상세는 target_description 으로"
                    )
            by_name.setdefault(aname, []).append((node_name, desc))
    for aname, members in by_name.items():
        if len(members) < 2:
            continue
        for node_name, desc in members:
            others = [f"{m}:{aname}" for m, _ in members if m != node_name]
            if not any(o in desc for o in others):
                issues.append(
                    f"{node_name}:{aname}: 이름 충돌({'/'.join(sorted(m for m, _ in members))})인데 "
                    f"desc 에 변별 언급 없음 — {', '.join(others)} 중 하나를 언급할 것"
                )
    return issues


def validate(data: dict, root: Path) -> list[str]:
    """전체 yaml 데이터에 대해 삼각 검증 수행."""
    issues: list[str] = []
    tool_index = build_tool_index(root)
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        actions = node.get("actions", {}) or {}
        for action_name, action in actions.items():
            if not isinstance(action, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            issues.extend(_check_action(qualified, action, tool_index))
    issues.extend(validate_app_blocks(data))
    issues.extend(validate_standalone_instruments(data))
    issues.extend(validate_runs_on(data))
    issues.extend(validate_transform_contract(data))
    issues.extend(validate_phone_reachability(data, root))
    issues.extend(validate_node_guides(data, root))
    issues.extend(validate_always_on(data))
    issues.extend(validate_side_effect_declaration(data))
    issues.extend(validate_standard_core(data, root))
    issues.extend(validate_desc_discipline(data))
    return issues


# ───────── 압축 상설 기관 (5-A): 개념중복 *경고* — 차단 아님 ─────────
# 배경(docs/VOCAB_DEDUP_HANDOFF.md): 정합성 가드는 존재 정합만 본다 — 같은 개념이
# 두 액션이어도 각자 정합이면 통과한다. 아래 두 신호는 2026-08-05 감사의 "자백"(desc
# 면책)과 "구조"(op 집합 닮음) 신호를 상설화한 것. 판단·병합은 사람 몫이라 경고만 낸다.
# (셋째 신호 "실증"=코퍼스 최근접은 주간 감사 vocab_overlap_audit — 빌드는 코퍼스를 안 읽는다.)

# 2026-08-05 동결 — 기존 다참조 desc 4건(정당한 교차 안내 포함). 새 진입만 경고.
_COMPRESSION_DESC_BASELINE = {
    "others:contact", "self:memory",   # engines:slide·html_video 는 2026-08-05 은퇴로 제거
}
_DESC_MENTION_WARN = 3     # desc 가 타 액션 ≥3개를 지목하면 개념 경계가 흐리다는 자백
_OP_JACCARD_WARN = 0.8     # 같은 group 에서 op 집합이 이만큼 닮으면 병합 후보 (다른 group=정상 CRUD 관습이라 면제)


def compression_warnings(data: dict) -> list[str]:
    """개념중복 경고(비차단) — ①desc 다참조 면책 ②같은 group op Jaccard.

    반환은 경고 문자열 목록. 호출측(build --check)은 출력만 하고 종료코드에 안 섞는다.
    """
    import itertools
    import re as _re

    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    acts: dict[str, dict] = {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if isinstance(action, dict):
                ops = action.get("ops")
                acts[f"{node_name}:{action_name}"] = {
                    "desc": str(action.get("description") or ""),
                    "group": str(action.get("group") or ""),
                    "ops": set((ops or {}).get("values") or {}) if isinstance(ops, dict) else set(),
                }

    warnings: list[str] = []
    short = {full: full.split(":", 1)[1] for full in acts}

    # ① desc 면책 과다 — 타 액션을 3개 이상 지목하는 설명(동결분 제외)
    # ★table:* 언급은 안 센다: table=통화 변환 문법(기능어 코어)이라 desc 의 table 파이프
    #   언급은 조합 초대(통화 대수 — 어휘 조합성 프로젝트가 장려)이지 경계 면책이 아니다.
    #   2026-08-16 sense:performance 오발(초대 2 + 면책 1 = 3 판정)로 확정. 내용어 지목만
    #   자백 신호로 남긴다.
    for full, info in acts.items():
        if full in _COMPRESSION_DESC_BASELINE:
            continue
        hits = set()
        for other in acts:
            if other == full or other.startswith("table:"):
                continue
            oshort = short[other]
            if _re.search(rf"(?<![\w:]){_re.escape(other)}(?![\w])", info["desc"]) or (
                len(oshort) >= 5
                and _re.search(rf"(?<![\w:]){_re.escape(oshort)}(?![\w])", info["desc"])
            ):
                hits.add(other)
        if len(hits) >= _DESC_MENTION_WARN:
            warnings.append(
                f"desc 면책 과다: {full} 이 타 액션 {len(hits)}개를 지목"
                f"({', '.join(sorted(hits)[:4])}…) — 개념 경계 재점검 후보"
            )

    # ② 같은 group 안 op 집합 닮음 — 병합 후보 (group 다르면 정상 CRUD 관습이라 면제)
    withops = [(f, i) for f, i in acts.items() if i["ops"]]
    for (f1, i1), (f2, i2) in itertools.combinations(withops, 2):
        if i1["group"] != i2["group"]:
            continue
        union = i1["ops"] | i2["ops"]
        if not union:
            continue
        j = len(i1["ops"] & i2["ops"]) / len(union)
        if j >= _OP_JACCARD_WARN:
            warnings.append(
                f"op 닮음: {f1} ↔ {f2} (group={i1['group']}, Jaccard {j:.2f}) — 병합 후보"
            )
    return warnings


# === 가이드 위생 가드 (2026-08-17) ===
# 가이드는 '절차 기억'이고 기억처럼 낡는다. 그런데 어휘 은퇴 절차에는 **코퍼스 이관 의무는
# 있어도(--check 코퍼스 param 가드가 실제로 강제한다) 가이드 정리 의무는 없었다.**
# 2026-08-17 정리에서 79→67개·81KB 를 걷어낸 것이 그 비대칭의 누적 청구서였다.
# 여기서 그 의무를 기계에 넘긴다 — 사실 관계는 하드 실패, 판단이 필요한 것은 비차단 경고.

def validate_guide_wiring(root: Path) -> list[str]:
    """가이드 배선 하드 검증 — 사실만, 판단 없음.

    ①guide_db 가 없는 파일을 가리킴(= read_guide 침묵 실패)
    ②가이드가 가리키는 backend 경로가 실존하지 않음(= 층 이동 후 끊긴 안내)

    ②를 넣는 이유: 2026-08-05 층 물리 이동 뒤 8건이 끊겨 있었는데, 모듈 이름이
    평면이라 import 는 안 깨져 **조용히** 낡았다. 가이드는 사람·AI 가 코드를 찾는
    지도라, 지도가 틀리면 자기 코드를 못 찾는다.
    """
    import json as _json
    import re as _re

    issues: list[str] = []
    guides_dir = root / "data" / "guides"
    if not guides_dir.is_dir():
        return issues
    files = {p.name for p in guides_dir.glob("*.md")}

    db_path = root / "data" / "guide_db.json"
    if db_path.exists():
        try:
            entries = _json.loads(db_path.read_text(encoding="utf-8")).get("guides", [])
        except Exception as e:
            return [f"가이드 가드: guide_db.json 을 읽지 못함 ({e})"]
        for e in entries:
            fn = Path(str(e.get("file") or "")).name
            if fn and fn not in files:
                issues.append(
                    f"guide_db 유령 등재: '{e.get('id')}' → data/guides/{fn} 실존하지 않음 "
                    "(의식 에이전트가 고르면 빈 문자열이 주입된다 — 침묵 실패)"
                )

    path_re = _re.compile(r"`(backend/[A-Za-z0-9_/]+\.py)`")
    for name in sorted(files):
        try:
            src = (guides_dir / name).read_text(encoding="utf-8")
        except OSError:
            continue
        for rel in sorted(set(path_re.findall(src))):
            if not (root / rel).exists():
                base = Path(rel).name
                hit = ""
                for d in (root / "backend").rglob(base):
                    if "__pycache__" not in str(d):
                        hit = f" → 실제 위치 backend/{d.relative_to(root / 'backend')}"
                        break
                issues.append(f"[{name}] 끊긴 코드 경로: {rel}{hit}")
    return issues


# 2026-08-17 동결 — 이 시점에 남아 있는 '설명된 죽은 참조'(은퇴 기록·가상의 제안)와
# 코드가 경로로 직접 읽는 고아 셋. 새 진입만 경고한다.
_GUIDE_ORPHAN_BASELINE = {
    "world_pulse.md",     # 런타임 산출물 — world_pulse.py 가 쓰고 prompt_builder 가 읽음
    "forage_search.md",   # api_system_ai.py 가 경로로 직접 읽음
}


def guide_staleness_warnings(data: dict, root: Path) -> list[str]:
    """가이드 부패 경고(비차단) — 판단이 필요한 신호만.

    ①죽은 어휘 참조: 은퇴/제안임을 밝히는 문맥이면 면제(그건 기록이지 오류가 아니다).
    ②살아있는 어휘 0 + 죽은 어휘 ≥1: 은퇴·미설치 능력의 가이드 냄새.
    ③고아: guide_db·노드 yaml 어디도 안 가리킴(= 검색으로 못 찾는 파일).

    ★전부 경고인 이유: 2026-08-17 정리에서 `remotion.md` 를 묘비로 남길지 지울지는
    기계가 못 정했고 실제로 사용자 판정으로 뒤집혔다. 검출은 시스템, 결정은 사람.
    """
    import json as _json
    import re as _re

    warns: list[str] = []
    guides_dir = root / "data" / "guides"
    if not guides_dir.is_dir():
        return warns
    files = sorted(p.name for p in guides_dir.glob("*.md"))

    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    live = {f"{n}:{a}" for n, v in nodes.items()
            if isinstance(v, dict) for a in (v.get("actions") or {})}
    if not live:
        return warns

    referenced = set()
    db_path = root / "data" / "guide_db.json"
    if db_path.exists():
        try:
            for e in _json.loads(db_path.read_text(encoding="utf-8")).get("guides", []):
                referenced.add(Path(str(e.get("file") or "")).name)
        except Exception:
            pass
    for _n, v in nodes.items():
        if isinstance(v, dict):
            referenced.update(str(g) for g in (v.get("guides") or []))
            for a in (v.get("actions") or {}).values():
                if isinstance(a, dict):
                    referenced.update(str(g) for g in (a.get("guides") or []))

    act_re = _re.compile(r"\[([a-z_]+):([a-z_]+)\]")
    # 은퇴/제안임을 밝히는 말 — 이런 문맥의 죽은 이름은 기록이지 오류가 아니다
    excused = _re.compile(r"구 |은퇴|폐지|개명|흡수|승격|부활|아직 없는|가상의|제안|통합|합병|없습니다|아니다|자리표시자")

    for name in files:
        try:
            lines = (guides_dir / name).read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        dead_unexcused, dead_all, live_hits = set(), set(), 0
        for i, line in enumerate(lines):
            ctx = " ".join(lines[max(0, i - 1): i + 4])
            for node, act in act_re.findall(line):
                if node not in nodes:
                    continue
                ref = f"{node}:{act}"
                if ref in live:
                    live_hits += 1
                    continue
                dead_all.add(ref)
                if not excused.search(ctx):
                    dead_unexcused.add(ref)
        if dead_unexcused:
            warns.append(
                f"[{name}] 설명 없는 죽은 어휘 참조: {', '.join(sorted(dead_unexcused))} "
                "(후계 어휘로 고치거나, 은퇴 기록임을 문장으로 밝힐 것)"
            )
        if dead_all and live_hits == 0:
            warns.append(
                f"[{name}] 살아있는 어휘를 하나도 안 부른다 (죽은 참조만 {len(dead_all)}종) "
                "— 은퇴·미설치 능력의 가이드일 수 있다"
            )
        if name not in referenced and name not in _GUIDE_ORPHAN_BASELINE:
            warns.append(
                f"[{name}] 고아 — guide_db·노드 yaml 어디도 안 가리킨다 "
                "(검색으로 못 찾으니 등록하거나 지울 것)"
            )
    return warns
