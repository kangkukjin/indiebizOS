"""param 선언 완전성 검사 — iblbuild_validators 의 형제 모듈.

2026-08-24 분리: validate_declared_params(B35-3 2조각)가 iblbuild_validators 를
1500줄 규칙 너머로 밀어서, 변경분을 규칙대로 형제 모듈로 옮겼다. 로직 이동만이며
호출자는 build_ibl_nodes.py 하나다.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from iblbuild_common import (
    CORPUS_PARAM_ALLOW,
    RUNTIME_META_KEYS,
    UNIVERSAL_PARAM_KEYS,
    _extract_action_param_aliases,
)
from iblbuild_derive import build_tool_index
from iblbuild_validators import _load_corpus_param_keys

# --- 구현-읽기 감사 (2026-08-29 #repair) 의 예외 대장 2종 ---------------------
# 왜 필요한가 — 형제 검사 둘(corpus 정합·선언 완전성)은 전부 **코퍼스 앵커**라,
# 코퍼스가 안 쓰는 param 자리는 원리적으로 안 본다. 그 틈으로 web-builder 의
# checks(구현 O·가이드 O·선언 X)가 런타임 컨테이너 관문(ibl_routing B35-3 3조각:
# 미선언 자리의 목록/사전 = 거절)에 막혀 산 기능이 죽어 있었다. 이 감사는 앵커를
# 코퍼스가 아니라 **구현 자신**(tool_input/ti 읽기)에 둔다.

# 어휘가 아닌 프로그램 배관 — IBL 라우팅을 거치지 않는 함수층 호출 전용 키.
# 새 항목은 반드시 "왜 어휘가 아닌지"를 적을 것.
IMPL_READ_ALLOW: dict[str, set[str]] = {
    # 은퇴 레거시 _TOOL_FNS 직행 경로(blog_search·blog_save_summary) 전용 —
    # 2026-07-03 죽은 tool.json 항목 제거 때 은퇴, 어느 액션도 미라우팅(삭제 후보).
    "blog": {"search_in", "summary", "keywords"},
    # html_video 갈래는 2026-08-05 어휘 은퇴 — create_html_video/render_html_video 는
    # lecture_workspace 가 함수층에서 차용하는 엔진으로만 잔류(handler.py 상단 주석).
    # slide 갈래(shadcn_slides·slide_native·slide_image)도 같은 은퇴 부류 —
    # lecture_workspace·REST 표면이 함수층에서 쓰는 렌더러 엔진(2026-08-29 2차 확장 때 편입).
    # 3차(대장 전량 상환): 은퇴 갈래의 나머지 키 + on_progress(콜백 — IBL 문장에
    # 실을 수 없는 함수 객체) + seed(generate_ai_image — 디스패치에 없는 도달 불가).
    "media_producer": {"scenes", "narration_texts", "narration_audio_paths",
                       "scene_files", "narration_files",
                       "slides", "style_reference_images", "aesthetic", "composition",
                       "content", "critique", "critique_rounds", "design_system",
                       "format", "instruction", "output_dir", "theme",
                       "verify", "verify_rounds",
                       "bgm_path", "capture_mode", "duration_per_scene", "fps",
                       "narration_padding", "on_progress", "scene_dir", "seed",
                       "topic", "transition", "transition_duration"},
    # 워크플로우 봉투를 벗기는 내부 배관: tool_input.get("params",{}).get("_prev_result")
    "system_essentials": {"params"},
}

# 스칼라 미선언 읽기의 동결 대장 — 런타임 관문은 스칼라를 통과시키므로(모르면 통과)
# 죽은 기능은 아니나, tool.json 에 없어 발견 불가·타입 보호 밖이다. **여기 적힌
# 것만 유예**하고 새 미선언 읽기는 빌드 실패다. 갚는 법: 해당 패키지
# ibl_actions.yaml 의 params/tool_json 에 타입을 선언하고 이 대장에서 지운다.
# 어휘가 아닌 배관이면 IMPL_READ_ALLOW 로 옮긴다(사유 필수). 목표 = 빈 사전.
IMPL_READ_BASELINE: dict[str, set[str]] = {
    # 2026-08-29 3차: 대장 전량 상환(빈 사전 달성) — 159키를 선언·별칭·ALLOW 로 분해.
    # 새 미선언 읽기는 이제 예외 없이 빌드 실패다. 정본 기록 = git log(3차 커밋).
}

_IMPL_VAR_NAMES = {"tool_input", "ti"}


def validate_declared_params(data: dict, root: Path) -> list[str] | None:
    """B35-3 2조각 (2026-08-24 #repair): 코퍼스가 **실제로 쓰는** param 자리 중
    tool.json input_schema.properties 에 선언이 없는 것을 오류로 보고한다.

    왜 새 검사가 필요한가 — 형제인 validate_corpus_params 는 "**핸들러가 이 키를 읽나**"
    만 묻고 "**타입이 선언돼 있나**"는 묻지 않는다. 그 틈으로 타입 관문(ibl_routing)이
    눈감는 자리가 생겼고, 거기서 파이썬 예외가 그대로 새었다
    (실측: [self:read]{path: [...]} → "expected str, bytes or os.PathLike object, not list").

    ★이 검사는 카운터가 아니라 **빌드 실패**다. 수를 세어 지켜보는 장치는 수리를 미루는
    장치일 뿐이고, 판정 기준이 코드 안에 전부 있을 때는 세지 말고 닫아야 한다.
    남은 자리는 각 패키지 ibl_actions.yaml 의 tool_json.tools[].input_schema.properties 에
    타입을 적어 0 으로 만든다(정당한 컨테이너 용법은 object/array 로 선언).

    파서/코퍼스 미가용 시 None (검사 건너뜀).
    """
    corpus = _load_corpus_param_keys(root)
    if corpus is None:
        return None
    aliases = _extract_action_param_aliases(data)
    tool_index = build_tool_index(root)
    tj_cache: dict[Path, dict] = {}

    def _props_of(pkg_dir: Path, tool_name: str) -> set[str] | None:
        """그 패키지 tool.json 에서 tool_name 의 properties 키 집합. 문서가 없으면 None."""
        if pkg_dir not in tj_cache:
            path = pkg_dir / "tool.json"
            try:
                tj_cache[pkg_dir] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # 파일 부재·깨진 JSON 만 "문서 없음"으로 취급. 넓은 except 는 이 검사
                # 자체의 결함(실측: import json 누락 NameError)까지 삼켜 관문을 2026-08-24
                # 모듈 분리 이후 통째로 침묵 no-op 으로 만들었다.
                tj_cache[pkg_dir] = {}
        doc = tj_cache[pkg_dir] or {}
        for t in (doc.get("tools") or []):
            if isinstance(t, dict) and t.get("name") == tool_name:
                isch = t.get("input_schema")
                if not isinstance(isch, dict):
                    return set()
                return set((isch.get("properties") or {}).keys())
        return None

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
            if action.get("router") != "handler":
                continue          # tool.json 이 없는 라우터(system/engine/…)는 대상 밖
            tool_name = action.get("tool")
            if not tool_name or tool_name not in tool_index:
                continue
            declared = _props_of(tool_index[tool_name][0], tool_name)
            if declared is None:
                continue          # 액션 미소유 도구·문서 미이관 — 다른 가드의 일
            known = set(declared) | set(UNIVERSAL_PARAM_KEYS) | set(RUNTIME_META_KEYS)
            known |= aliases.get(qualified, set())
            known |= CORPUS_PARAM_ALLOW.get(qualified, set())
            missing = sorted(used - known)
            if missing:
                issues.append(
                    f"{qualified} ({tool_name}): 코퍼스가 쓰는 param 에 타입 선언이 없음 — {missing} "
                    f"(해당 패키지 ibl_actions.yaml 의 tool_json.tools[name={tool_name}]"
                    f".input_schema.properties 에 타입을 적을 것; 컨테이너 자리면 object/array)"
                )
    return issues


def _scan_impl_reads(py: Path) -> dict[str, bool]:
    """한 파일에서 tool_input/ti 로부터 읽는 리터럴 키 → 컨테이너 기대 여부.

    컨테이너 기대 = .get("k", [] | {}) 또는 .get("k") or [] | {} — 이 모양의 키에
    에이전트가 목록/사전을 실으면 런타임 컨테이너 관문이 미선언 자리라며 거절하므로,
    선언이 없는 한 그 기능은 문서·구현이 살아 있어도 죽어 있다(실측: engines:web checks).
    """
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}

    def _get_key(call: ast.expr) -> str | None:
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr in ("get", "pop")
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id in _IMPL_VAR_NAMES
                and call.args and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)):
            return call.args[0].value
        return None

    out: dict[str, bool] = {}
    for node in ast.walk(tree):
        key, container = None, False
        k = _get_key(node)
        if k is not None:
            key = k
            if (len(node.args) > 1 and isinstance(node.args[1], (ast.List, ast.Dict))):
                container = True
        elif (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id in _IMPL_VAR_NAMES
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
                # Load 만 읽기 — ti["k"]=v 같은 쓰기(엔진에 넘길 dict 조립)는 param
                # 읽기가 아니다(2026-08-29 3차: lecture_workspace 오탐 3키로 발견).
                and isinstance(node.ctx, ast.Load)):
            key = node.slice.value
        elif (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)
                and len(node.values) == 2
                and isinstance(node.values[1], (ast.List, ast.Dict))):
            k = _get_key(node.values[0])
            if k is not None:
                key, container = k, True
        if key and not key.startswith("_"):
            out[key] = out.get(key) or container
    return out


def validate_impl_reads(data: dict, root: Path) -> list[str]:
    """구현-읽기 감사 (2026-08-29 #repair): 각 패키지 구현(패키지 루트 *.py 전체
    + tools/*.py)이 실제로 읽는 tool_input 키 중 그 패키지 tool.json 어디에도 선언이
    없는 것을 보고한다. 형제 검사들의 코퍼스 앵커가 못 보는 축이다.

    수집 규칙이 handler.py·tool_*.py 만 보던 첫 판은 system_essentials 의 서브모듈
    규약(패키지 루트 *_ops.py — body_ops·office_ops·script_ops …)을 통째로 놓쳤다
    (2026-08-29 2차 확장). `_` 접두 파일은 스크래치/배관 봉인 규약이라 제외.

    두 급으로 닫는다:
    - 컨테이너 기대 + 미선언 = **즉시 빌드 실패** (런타임 관문이 거절하는 죽은 기능,
      IMPL_READ_ALLOW 의 함수층 배관만 예외).
    - 스칼라 미선언 = IMPL_READ_BASELINE 동결 대장 밖의 **새 항목만 빌드 실패**
      (기존 부채는 대장이 유예하되 갚으면 지운다 — 목표는 빈 사전).
    """
    tool_index = build_tool_index(root)
    aliases_by_action = _extract_action_param_aliases(data)

    pkg_declared: dict[Path, set[str]] = {}
    tool_pkg: dict[str, Path] = {}
    for tname, (pkg_dir, tdef) in tool_index.items():
        tool_pkg[tname] = pkg_dir
        props = set((((tdef.get("input_schema") or {}).get("properties")) or {}).keys())
        pkg_declared.setdefault(pkg_dir, set()).update(props)

    pkg_alias: dict[Path, set[str]] = {}
    for node_name, node in (data.get("nodes", {}) or {}).items():
        if not isinstance(node, dict):
            continue
        for aname, action in (node.get("actions", {}) or {}).items():
            if not isinstance(action, dict):
                continue
            pkg = tool_pkg.get(action.get("tool") or "")
            if pkg is not None:
                pkg_alias.setdefault(pkg, set()).update(
                    aliases_by_action.get(f"{node_name}:{aname}", set()))

    issues: list[str] = []
    stale_ledger: list[str] = []
    for pkg_dir in sorted(pkg_declared):
        name = pkg_dir.name
        known = (pkg_declared[pkg_dir] | set(UNIVERSAL_PARAM_KEYS)
                 | set(RUNTIME_META_KEYS) | pkg_alias.get(pkg_dir, set()))
        reads: dict[str, bool] = {}
        files = sorted(p for p in pkg_dir.glob("*.py") if not p.name.startswith("_"))
        if (pkg_dir / "tools").is_dir():
            files += sorted((pkg_dir / "tools").glob("*.py"))
        for f in files:
            if f.is_file():
                for k, c in _scan_impl_reads(f).items():
                    reads[k] = reads.get(k) or c
        undeclared = {k: c for k, c in reads.items()
                      if k not in known and k not in IMPL_READ_ALLOW.get(name, set())}
        dead = sorted(k for k, c in undeclared.items() if c)
        if dead:
            issues.append(
                f"{name}: 구현이 컨테이너를 기대하는 param 에 선언이 없음 — {dead} "
                f"(런타임 관문이 목록/사전을 거절해 기능이 죽는다; ibl_actions.yaml "
                f"params 에 array/object 로 선언하거나, 함수층 배관이면 "
                f"IMPL_READ_ALLOW 에 사유와 함께 등재)")
        fresh = sorted(k for k, c in undeclared.items()
                       if not c and k not in IMPL_READ_BASELINE.get(name, set()))
        if fresh:
            issues.append(
                f"{name}: 구현이 읽는 param 에 선언이 없음(신규) — {fresh} "
                f"(ibl_actions.yaml params 에 타입 선언; 배관이면 IMPL_READ_ALLOW)")
        # 대장 위생: 갚았거나 사라진 항목이 대장에 남으면 신고 — 대장은 줄기만 해야 한다.
        paid = sorted(IMPL_READ_BASELINE.get(name, set())
                      - {k for k, c in undeclared.items() if not c})
        if paid:
            stale_ledger.append(f"{name}: {paid}")
    if stale_ledger:
        issues.append(
            "IMPL_READ_BASELINE 대장에 이미 갚은(선언됐거나 읽지 않는) 항목이 남음 — "
            + "; ".join(stale_ledger) + " (대장에서 지울 것)")
    return issues


