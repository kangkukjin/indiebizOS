"""
ibl_routing.py - IBL 엔진 라우팅 모듈

IBL 엔진(ibl_engine.py)에서 분리된 라우팅 함수들.
노드 액션을 적절한 백엔드(handler, driver, system 등)로 라우팅합니다.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional


# 도구 실행 타임아웃 (초) — 이 시간을 초과하면 강제로 에러 반환
TOOL_EXECUTION_TIMEOUT = 60

# 동기 handler.execute 타임아웃 (초, D6 2026-08-05) — 예전엔 async 경로에만 타임아웃이 있어
# router:handler 동기 핸들러 전체가 무제한 행 가능했다. async(60초)보다 길게 두는 이유:
# 목적이 '무한 행 방지'지 지연 정책이 아니고, 정상 동작으로 문서화된 느린 동기 핸들러가
# 있다(예: music-player compose 실측 58~104초 — CLAUDE.md/가이드에 명기). 타임아웃 시
# 스레드는 강제 종료할 수 없어 고아로 완주하지만(compose 가 타임아웃 후에도 저장되는 기존
# 관찰과 동일 의미), 호출자는 행 대신 명확한 에러를 받는다.
SYNC_TOOL_EXECUTION_TIMEOUT = 300


# === 시스템 라우터 인지 능력 테이블 (2026-08-05 감사 ⑦ 후반부) ===
# 라우터는 이름만 안다 — 구현(인지층)은 routing_system.register_all() 이 부팅 시 주입.
# (파서 register_parse·채팅 스트림 슬롯과 같은 의존 역전. 라우팅층은 인지층을 모른다.)
_SYSTEM_CAPS: Dict[str, Any] = {}


def register_system_capabilities(mapping: Dict[str, Any]) -> None:
    """인지 능력 주입 — 조립 루트(boot_common.wire_local_subsystems)가 부팅 시 1회."""
    _SYSTEM_CAPS.update(mapping)


def _cap(name: str):
    fn = _SYSTEM_CAPS.get(name)
    if fn is None:
        raise RuntimeError(
            f"시스템 능력 미등록: {name} — 조립 루트가 routing_system.register_all() 을 "
            "불러야 한다 (boot_common.wire_local_subsystems 경유)")
    return fn


class _SyncHandlerTimeout(Exception):
    """동기 핸들러 타임아웃 내부 신호 (핸들러 자신이 던진 TimeoutError 와 구분)."""


def _run_sync_with_timeout(fn, args: tuple, timeout: float, tool_name: str):
    """동기 함수를 워커 스레드에서 실행해 타임아웃을 부여한다 (D6).

    thread_context(threading.local)는 snapshot/restore 로 워커 스레드에 승계한다
    (패키지 핸들러들은 get_current_task_id 등 *읽기*만 한다 — 전수 확인 2026-08-05).
    풀 대신 호출마다 새 스레드를 쓰는 이유: 핸들러가 execute_ibl 을 재귀 호출하는
    구조라 고정 풀은 자기교착 위험이 있다. 타임아웃 시 스레드는 데몬으로 남아 완주한다.
    """
    import threading
    import thread_context as _tc
    snap = _tc.snapshot()
    box: dict = {}

    def _worker():
        _tc.restore(snap)
        try:
            box["result"] = fn(*args)
        except BaseException as e:  # 원 예외를 호출 스레드로 그대로 재전파
            box["exc"] = e

    t = threading.Thread(target=_worker, daemon=True,
                         name=f"ibl-handler-{tool_name}")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise _SyncHandlerTimeout(
            f"도구 실행 시간 초과 ({int(timeout)}초): {tool_name}")
    if "exc" in box:
        raise box["exc"]
    return box.get("result")


# === 파라미터 alias 정규화 ===
# AI(특히 실행기억/해마 RAG)가 자연스러운 이름으로 호출했을 때 핸들러의 정규 키로 자동 매핑.
# 별칭은 어휘 데이터가 소유한다: 각 액션 정의(src yaml / 패키지 ibl_actions.yaml)의
# `aliases: {<정규 키>: [<alias1>, ...]}` 블록 → 빌드가 ibl_nodes.yaml 로 병합 →
# 여기서는 레지스트리의 action_config 를 읽기만 한다 (tool.json 파생화와 같은 수).
# 정규화 규칙: 정규 키가 비어있고 alias 키 중 하나에 값이 있으면 그 값을 정규 키로 옮긴다.


def _normalize_param_aliases(node: str, action: str, params: dict,
                             action_config: Optional[dict] = None) -> dict:
    """액션의 aliases 선언(레지스트리)을 적용해 핸들러가 받는 정규 키로 변환.

    핸들러는 변경 없이 정규 키만 받고, AI 호출자는 자연스러운 이름을 써도 통과한다.
    이미 정규 키에 값이 있으면 alias는 무시 (정규 키 우선).
    action_config 미전달 시 레지스트리(ibl_nodes.yaml)에서 직접 조회한다.
    """
    if not isinstance(params, dict):
        return params
    if action_config is None:
        from ibl_registry import load_nodes_installed
        action_config = (load_nodes_installed().get("nodes", {})
                         .get(node, {}).get("actions", {}).get(action)) or {}
    aliases = action_config.get("aliases") if isinstance(action_config, dict) else None
    if not isinstance(aliases, dict):
        return params
    for canonical, alts in aliases.items():
        if params.get(canonical) is not None:
            continue
        for alt in (alts or []):
            if params.get(alt) is not None:
                params[canonical] = params[alt]
                break
    return params


# === 라우터 구현 ===

def _route_api_engine(action: str, params: dict, project_path: str,
                      mapped_tool: str = None) -> Any:
    """API 엔진으로 라우팅

    mapped_tool이 지정되면 해당 api_registry 도구를 직접 실행합니다.
    이를 통해 노드 액션(informant:search 등)이 handler.py 없이
    api_registry.yaml + api_engine.py transform으로 직접 동작합니다.
    """
    from api_engine import execute_tool as api_execute, is_registry_tool

    # 노드 액션에서 직접 매핑된 api_registry 도구 실행.
    # (범용 self:call / self:list_api 액션은 2026-06-04 은퇴 — 모든 등록 도구가
    #  정식 명명 액션으로 노출되어 mapped_tool 경로로만 디스패치됨.)
    if mapped_tool:
        if not is_registry_tool(mapped_tool):
            return {"error": f"api_registry에 등록되지 않은 도구: {mapped_tool}"}
        return api_execute(mapped_tool, dict(params), project_path)

    return {"error": f"api 노드에 '{action}' 액션이 없습니다 (mapped_tool 미지정)."}


# ─────────────────────────────────────────────────────────────────────
# 액션 스코프 (Phase 30) — 액션의 데이터 경계 선언
# ─────────────────────────────────────────────────────────────────────
#
# IBL 액션은 데이터 경계가 서로 다르다. 스코프는 ibl_actions.yaml에 명시:
#
#   - "project" (기본): 특정 프로젝트의 데이터에서 작동. project_path 필요.
#                       예: self:read, self:write — 프로젝트 폴더에서 작동.
#
#   - "workspace":      indiebizOS 인스턴스 전체에 걸친 데이터. 프로젝트 무관.
#                       예: lecture_workspace (outputs/lectures/),
#                       앞으로 추가될 비즈니스 관계, NAS, 통합 메모 등.
#                       resolved path = get_base_path() (indiebizOS 루트 / userData)
#
#   - "system":         indiebizOS 자체에 대한 작업 (설정, 패키지 관리 등).
#                       workspace와 동일한 경로를 쓰되, 향후 권한 모델에서 분리.
#
# scope는 ibl_actions.yaml의 파일 레벨(전체 적용) 또는 액션 레벨(개별 오버라이드)
# 어디든 선언 가능. 라우팅은 이 선언을 보고 project_path 강요 여부를 결정.

WORKSPACE_SCOPES = {"workspace", "system"}


def _resolve_path_by_scope(scope: str, project_path: str,
                            params: Optional[dict] = None) -> Optional[str]:
    """scope에 따라 ToolContext에 줄 base path 결정.

    - workspace/system: get_base_path() (indiebizOS 루트 / userData).
                       project_path/project_id 무시 — 의도적 격리.
    - project (기본):   기존 4단 폴백 우선순위 적용 (resolve_project_path).
    """
    if scope in WORKSPACE_SCOPES:
        try:
            from runtime_utils import get_base_path
            return str(get_base_path())
        except Exception as e:
            print(f"[ibl_routing] workspace 경로 해석 실패: {e}")
            return None
    return resolve_project_path(project_path, params)


def resolve_project_path(project_path: str,
                          params: Optional[dict] = None) -> Optional[str]:
    """project_path를 우선순위로 해석 (scope='project' 전용).

    우선순위:
      1) params["project_id"] — 작가가 IBL 코드에 손으로 명시한 대상 프로젝트.
         '이 프로젝트를 뜻함'이라는 의도적 신호이므로, 호출자가 정체성으로
         들고 있는 project_path(예: 위임된 시스템 AI의 data/)보다 우선한다.
         해석에 실패하면(존재하지 않는 id 등) 조용히 넘어가 2번으로 폴백.
      2) 호출자가 직접 인자로 넘긴 project_path (디폴트 '.' 가 아닐 때)
         — 프로젝트 에이전트 등 컨텍스트가 살아있는 정상 경로
      3) params["project_path"] — 명시 절대/상대 경로 (web-builder처럼 동일
         키를 도구 인자로 쓰는 핸들러와의 충돌을 피하려고 positional·id가
         비어있는 경우에만 본다)
      4) 안전망 — thread_context.project_id

    ★1번이 2번보다 앞서는 이유(2026-07-09): 위임(delegate) 실행 시 시스템 AI는
    자신의 정체성 경로 project_path=data/ 를 들고 온다. 이 값이 우선하면 작가가
    코드에 적은 project_id 가 조용히 무시돼 산출물이 엉뚱한 data/outputs 로 떨어진다
    (오디오 브리핑 사고 이력). 명시 project_id=의도, 호출자 경로=정체성 — 의도를
    우선한다. project_id 가 없으면 1번은 건너뛰므로 프로젝트 에이전트 흐름은 무변경.
    부수 효과로 프로젝트 에이전트의 교차 프로젝트 지정(`[self:read]{project_id:"투자"}`)도
    라우팅 단에서 제대로 존중된다(이전엔 호출자 경로가 이겨 잠재 무시됐음).
    """
    # 1) 명시 project_id — 작가가 손으로 쓴 의도적 대상. 호출자 정체성 경로보다 우선.
    #    (의미상 메타 키 — 도구 인자로 쓰는 핸들러 없음)
    if isinstance(params, dict):
        explicit_id = params.get("project_id")
        if isinstance(explicit_id, str) and explicit_id.strip():
            resolved = _resolve_project_id(explicit_id)
            if resolved:
                return resolved
            # 해석 실패 시엔 조용히 2번으로 폴백(침묵 오배치 방지)

    # 2) 호출자가 직접 인자로 넘긴 값
    if project_path and project_path.strip() and project_path != ".":
        return os.path.abspath(project_path)

    # positional·id가 비어있을 때만 params.project_path 명시 키 탐색
    if isinstance(params, dict):
        # 3) params.project_path — 명시 경로
        explicit_path = params.get("project_path")
        if isinstance(explicit_path, str) and explicit_path.strip() and explicit_path != ".":
            candidate = os.path.abspath(explicit_path)
            if os.path.isdir(candidate):
                return candidate
            # 디렉토리가 아니면 project_id처럼 생긴 값이라 보고 ID 해석 시도
            resolved = _resolve_project_id(explicit_path)
            if resolved:
                return resolved

    # 4) 안전망 — thread_context
    print(
        f"[ibl_routing] WARN: project_path 안전망 발동 (입력={project_path!r}). "
        "호출자가 명시 전달하지 못함 — thread_context.project_id로 복구 시도."
    )
    try:
        from thread_context import get_current_project_id
        project_id = get_current_project_id()
        if project_id:
            resolved = _resolve_project_id(project_id)
            if resolved:
                return resolved
    except Exception as e:
        print(f"[ibl_routing] project_path 복구 실패: {e}")

    return None


def _resolve_project_id(project_id: str) -> Optional[str]:
    """project_id 문자열 → 절대경로 (ProjectManager 경유)."""
    try:
        from project_manager import ProjectManager
        pm = ProjectManager()
        path = pm.get_project_path(project_id)
        if path and path.exists():
            return str(path.resolve())
    except Exception as e:
        print(f"[ibl_routing] project_id '{project_id}' 해석 실패: {e}")
    return None


_SCALAR_TYPES = ("string", "number", "integer", "boolean")

def _coerce_declared_scalar(v, declared):
    """B35-1·B35-2 (2026-08-24 #repair): 선언 타입 대비 값 하나를 **3값**으로 판정.

    반환 (ok, value, why)
      ok=True  손실 없이 declared 로 맞췄다(또는 이미 맞다) → value 로 진행
      ok=False 변환이 손실·모호하다 → 정직 거절, why 가 사유

    ★왜 이분법(전부 통과 / 전부 거절)이 아닌가 — 둘 다 실측으로 틀렸다.
      · 전부 통과 = 수리 전 상태 = B35-2. `[table:take]{n: 3.7}` 이 10행을 3행으로
        조용히 깎고 success:true 를 냈고, `regex: \"false\"` 는 파이썬 진리값 규칙에 걸려
        **참**으로 읽혀 같은 질의가 70건 vs 79건으로 갈렸다(경고 한 줄 없음).
      · 전부 거절 = 코퍼스 33건 파괴(3,610문장 전수 대조). 그런데 그 33건은 전부
        `memory_id: \"23\"`·`business_id: 2`·`volume: \"80\"`·`enabled: \"true\"` 같은
        **손실 없는 표기 차이**라 안전 이득이 0이고 사용자만 잃는다.
        (35회차 문서는 이를 '79건 파괴·파괴적 변경'으로 적었으나 실측이 반증했다 —
         그 79건에 포함된 `[limbs:screen]{x,y}` 45건은 애초에 선언이 없어 불검사다.)
      그래서 가르는 자리는 타입이 아니라 **손실 여부**다. 되돌릴 수 있으면 맞춰 주고,
      버림·모호가 생기면 거절한다.
    """
    if isinstance(v, (list, dict)):
        return False, None, (f"{len(v)}개짜리 "
                             f"{'목록' if isinstance(v, list) else '사전'}이 왔습니다")
    _isbool = isinstance(v, bool)          # bool 은 int 의 하위형 — 먼저 갈라야 한다

    if declared == "string":
        if isinstance(v, str):
            return True, v, None
        if _isbool:
            return False, None, f"참거짓값({v})이 왔습니다 — 문자열 표기가 모호합니다"
        if isinstance(v, (int, float)):
            return True, str(v), None      # 12345 → "12345" (되돌릴 수 있다)
        return False, None, f"{type(v).__name__} 이 왔습니다"

    if declared == "boolean":
        if _isbool:
            return True, v, None
        if isinstance(v, str) and v.strip().lower() in ("true", "false"):
            return True, v.strip().lower() == "true", None
        return False, None, (f"{v!r} 가 왔습니다 — true/false 만 참거짓으로 읽습니다"
                             f" (yes·1 은 모호해서 받지 않습니다)")

    if declared in ("integer", "number"):
        if _isbool:
            return False, None, f"참거짓값({v})이 왔습니다"
        if isinstance(v, str):
            _s = v.strip()
            try:
                v = float(_s) if ("." in _s or "e" in _s.lower()) else int(_s)
            except ValueError:
                return False, None, f"{v!r} 는 숫자로 읽을 수 없습니다"
        if declared == "number":
            return True, v, None
        if isinstance(v, int):
            return True, v, None
        if isinstance(v, float) and v.is_integer():
            return True, int(v), None      # 3.0 → 3 (버리는 게 없다)
        return False, None, (f"{v} 는 정수가 아닙니다 — 버림이 생기면 "
                             f"답이 조용히 달라집니다")

    return True, v, None


def _route_handler(mapped_tool: str, params: dict,
                   project_path: str, agent_id: str = None,
                   scope: str = "project") -> Any:
    """handler.py로 위임 (타임아웃 적용).

    표준 시그니처: execute(tool_input, context: ToolContext).
    구 시그니처(tool_name, tool_input, project_path, [agent_id])는 더 이상 지원하지 않는다.

    scope (Phase 30):
        - "project" (기본): project_path 필요. 없으면 에러.
        - "workspace"/"system": project_path 무시, get_base_path()를 ToolContext에 주입.
    """
    from tool_loader import load_tool_handler

    if not mapped_tool:
        return {"error": "매핑된 도구가 없습니다."}

    handler = load_tool_handler(mapped_tool)
    if not handler or not hasattr(handler, "execute"):
        return {"error": f"도구 핸들러를 찾을 수 없습니다: {mapped_tool}"}

    merged_params = dict(params)

    # ★B34-1 (2026-08-23 #repair): 스칼라를 선언한 param 에 목록·사전이 오면 정직하게 거절한다.
    #   실측 3종 — [sense:stock]{ticker: ["AAPL","MSFT"]} 는 에러도 없이 **태국 증시**
    #   AAPL19.BK 를 돌려줬고(str() 로 뭉개진 "['AAPL', 'MSFT']" 가 종목명 검색어가 됐다),
    #   [sense:weather]{city: [...]} 는 'list' object has no attribute 'lower',
    #   [sense:stock]{op:"search", query: [...]} 는 'attribute strip' 이라는 파이썬 예외를
    #   그대로 샜다. 실사용 원장에도 같은 계열이 남아 있었다('attribute upper').
    #   조용한 오답이 예외보다 나쁘다 — 아무도 의심하지 않기 때문이다.
    #   ★처방을 함수·액션 목록으로 적지 않는다: .upper()/.strip()/.lower() 자리만 58곳이고
    #     그런 열거는 반드시 뒤처진다. tool.json 의 input_schema 가 **이미** 타입을 선언하고
    #     있으므로 관문에서 그 진실 소스를 한 번 읽는다. array 로 선언된 param($items 통짜
    #     바인딩의 정당한 자리 — markers·items·columns·blocks…)은 그대로 통과하므로
    #     깨지는 기존 용법이 없다. 선언이 없는 param 은 검사하지 않는다(모르면 통과).
    #   ★B35-1·B35-2 로 확장 (2026-08-24 #repair): 관문이 보는 범위를 목록·사전에서
    #     **선언된 스칼라 전부**로 넓힌다. 옛 관문은 list/dict 만 봤기 때문에 같은 자리의
    #     같은 종류 위반인데 결말이 갈렸다 —
    #       [sense:weather]{city: ["수원","서울"]} → 정직 거절(무엇을 쓰라는 안내까지)
    #       [sense:weather]{city: 12345}          → 'int' object has no attribute 'lower'
    #     그리고 스칼라 쪽은 조용히 뭉개지기까지 했다: [table:take]{n: 3.7} 이 10행을
    #     3행으로 말없이 깎았고, regex: "false" 가 참으로 읽혀 같은 질의가 70 vs 79 로 갈렸다.
    #     판정은 타입이 아니라 **손실 여부**로 한다 → _coerce_declared_scalar 참조.
    #   ★비용: load_tool_schema 1회 0.45ms 실측. 액션 자체가 ms~s 단위라 무시할 수준이어서
    #     옛 '스칼라-only 면 스키마를 읽지도 않는다' 지름길은 걷어냈다(param 이 없으면 생략).
    _props = {}
    if merged_params:
        try:
            from tool_loader import load_tool_schema
            _props = (((load_tool_schema(mapped_tool) or {}).get("input_schema") or {})
                      .get("properties") or {})
        except Exception:
            _props = {}
        _refused, _had_container, _pipeline_items = [], False, False
        for _k, _v in list(merged_params.items()):
            if str(_k).startswith("_"):
                continue                  # 런타임 내부 키(_wf_stack·_prev_result…)
            # 선언은 단일 타입 또는 **타입 목록**(JSON Schema 유니온)일 수 있다 —
            # 한 param 이 문자열 DSL 과 사전을 둘 다 받는 자리가 실제로 있다
            # ([table:filter]{where: "a > 1"} 와 {where: {상태: "이동"}}).
            _tdecl = (_props.get(_k) or {}).get("type")
            _types = _tdecl if isinstance(_tdecl, list) else ([_tdecl] if _tdecl else [])
            if isinstance(_v, str) and _v.startswith("$"):
                continue                  # 미해소 바인딩은 이 관문의 일이 아니다
            # ★B35-3 3조각 (2026-08-24 #repair): 컨테이너는 **array/object 로 선언된
            #   자리에만** 들어간다. 옛 규약은 '선언 없으면 불검사' 라 미선언 자리의
            #   컨테이너가 핸들러까지 흘러 파이썬 예외로 샜다(self:read{path:[...]}).
            #   정당한 컨테이너 용법은 '선언이 없어서 보호받는' 게 아니라
            #   **object/array 로 선언되어** 통과하는 것이다 — 빌드의 param 선언
            #   완전성 검사가 그 선언을 강제한다.
            if isinstance(_v, (list, dict)):
                if "array" in _types or "object" in _types:
                    continue
                _kind = "목록" if isinstance(_v, list) else "사전"
                _decl = (f"{'/'.join(_types)} 이 와야 하는데" if _types
                         else "타입 선언이 없는 자리인데")
                _refused.append(f"`{_k}` 에는 {_decl} {len(_v)}개짜리 {_kind}이 왔습니다")
                _had_container = True
                if (_k == "items" and not _types and mapped_tool in {
                        "data_filter", "data_sort", "data_select", "data_compute",
                        "data_rename", "data_flatten", "data_dedup", "data_groupby"}):
                    _pipeline_items = True
                continue
            if len(_types) != 1 or _types[0] not in _SCALAR_TYPES:
                continue                  # 미선언·유니온 = 스칼라 강제 안 함(모르면 통과)
            _t = _types[0]
            _ok, _new, _why = _coerce_declared_scalar(_v, _t)
            if not _ok:
                _refused.append(f"`{_k}` 에는 {_t} 이 와야 하는데 {_why}")
            elif type(_new) is not type(_v) or _new != _v:
                merged_params[_k] = _new  # 되돌릴 수 있는 표기 차이는 조용히 맞춰 준다
        if _refused:
            if _pipeline_items:
                _action = mapped_tool.removeprefix("data_")
                _tail = (f"[table:{_action}] 은 items 직접 입력 대신 앞 통화를 받습니다. "
                         f"[table:take]{{items: […], n: …}} >> [table:{_action}]{{…}}처럼 이으세요.")
            elif _had_container:
                _tail = ("목록의 항목마다 실행하려면 [table:each]{do: \"…$it.필드…\"} 를 쓰세요 "
                         "($items 통짜 바인딩은 array 로 선언된 param 에만 들어갑니다).")
            else:
                _tail = ("선언된 타입으로 적어 주세요 — 되돌릴 수 있는 표기 차이"
                         "(\"23\"→23, 2→\"2\", \"true\"→true)는 관문이 알아서 맞춥니다.")
            return {"success": False,
                    "error": f"{mapped_tool}: " + "; ".join(_refused) + ". " + _tail}

    # handler.execute는 신규 시그니처 (tool_input, context)만 지원
    import inspect
    sig = inspect.signature(handler.execute)
    if "context" not in sig.parameters:
        return {"error": (
            f"도구 핸들러가 구 시그니처를 사용합니다: {mapped_tool}. "
            "신규 시그니처 execute(tool_input, context: ToolContext)로 마이그레이션이 필요합니다."
        )}

    resolved_path = _resolve_path_by_scope(scope, project_path, merged_params)
    if not resolved_path:
        if scope in WORKSPACE_SCOPES:
            return {"error": (
                f"workspace 경로를 확보할 수 없습니다: {mapped_tool}. "
                "INDIEBIZ_BASE_PATH 환경변수 또는 backend 폴더 구조를 확인하세요."
            )}
        return {"error": (
            f"활성 프로젝트 경로를 확보할 수 없어 도구를 실행할 수 없습니다: {mapped_tool}. "
            "대상 프로젝트를 params.project_id로 명시하거나 "
            "프로젝트 컨텍스트(thread_context.project_id) 안에서 호출하세요. "
            "예: execute_ibl(code='[node:action]{..., project_id: \"컨텐츠\"}') "
            "★each/폴백/병렬 가지 안까지 컨텍스트를 전파하려면 문장 param 대신 "
            "/ibl/execute 요청 body의 project_id 필드를 쓰세요 (param 방식은 그 step에만 적용)."
        )}
    from tool_context import ToolContext, ToolContextError
    try:
        context = ToolContext.from_thread_context(resolved_path, mapped_tool)
    except ToolContextError as e:
        return {"error": f"ToolContext 생성 실패: {e}"}
    # ★침묵 실패 방지: 핸들러 실행 예외(특히 의존성 미설치 ModuleNotFoundError)를 여기서
    #   잡아 사용자에게 보이는 명확한 에러로 바꾼다. 예전엔 [sense:search] 등이 없는
    #   라이브러리(ddgs)를 top-level import 하다 예외가 조용히 전파돼 빈 응답으로 뭉개졌다
    #   (browser-action 은 자기 핸들러에서 감싸 명확했지만 나머지는 아니었다 — 불일관 해소).
    try:
        # ★동기 경로 타임아웃(D6): router:handler 동기 핸들러도 무제한 행하지 않게
        #   워커 스레드 오프로드 + join(timeout). async 핸들러는 코루틴을 즉시 반환하므로
        #   여기서는 빠르게 통과하고 아래 async 경로에서 기존 타임아웃이 걸린다.
        result = _run_sync_with_timeout(
            handler.execute, (merged_params, context),
            SYNC_TOOL_EXECUTION_TIMEOUT, mapped_tool)
    except _SyncHandlerTimeout as _to_err:
        print(f"[IBL] 동기 도구 실행 타임아웃 ({SYNC_TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}")
        return {
            "success": False,
            "error": (
                f"도구 실행 시간 초과 ({SYNC_TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}. "
                "작업이 백그라운드에서 계속될 수 있으니 잠시 후 상태를 확인하거나 다른 방법을 시도하세요."
            ),
        }
    except (ModuleNotFoundError, ImportError) as _dep_err:
        _missing = getattr(_dep_err, "name", None) or str(_dep_err)
        print(f"[IBL] 도구 의존성 누락 ({mapped_tool}): {_missing}")
        return {
            "error": (
                f"도구 '{mapped_tool}' 실행에 필요한 라이브러리 '{_missing}' 가 설치돼 있지 않습니다. "
                f"사용자에게 설치할지 물어본 뒤, 승낙하면 [self:install_lib]{{package: \"{_missing}\"}} 로 "
                f"설치를 요청하고 다시 시도하세요. (설치는 사람 승인 게이트를 거칩니다 — "
                f"승인 전이면 대기열에 등록되니 사용자의 승인을 기다리세요. 거절하면 이 도구는 건너뜁니다.)"
            ),
            # 인지층/UI가 '설치할까요?' 흐름을 태울 수 있도록 기계가독 신호도 함께.
            "missing_dependency": _missing,
            "install_action": f'[self:install_lib]{{package: "{_missing}"}}',
        }
    except Exception as _exec_err:
        print(f"[IBL] 도구 실행 실패 ({mapped_tool}): {_exec_err}")
        # 파이썬 트레이스백이 str(e) 로 죽는 유일한 관문 — 씨앗 트레이스백에 꼬리를 싣는다.
        # 파이프가 이 봉투를 받으면 tb_of 로 승계해 위치 프레임을 얹는다(경계 규약).
        from ibl_traceback import build_tb, py_tail_of
        return {"error": f"도구 실행 실패 ({mapped_tool}): {_exec_err}",
                "traceback": build_tb(f"도구 실행 실패 ({mapped_tool}): {_exec_err}",
                                      "exception", py_tail=py_tail_of(_exec_err))}

    # async 핸들러 지원 (persistent 이벤트 루프 + 타임아웃)
    if asyncio.iscoroutine(result):
        async def _run_with_timeout(coro):
            return await asyncio.wait_for(coro, timeout=TOOL_EXECUTION_TIMEOUT)

        try:
            import concurrent.futures
            from ibl_engine import _get_persistent_loop
            loop = _get_persistent_loop()
            # persistent 루프에 코루틴을 제출하고 결과를 기다림
            future = asyncio.run_coroutine_threadsafe(
                _run_with_timeout(result), loop
            )
            result = future.result(timeout=TOOL_EXECUTION_TIMEOUT + 5)
        except asyncio.TimeoutError:
            print(f"[IBL] 도구 실행 타임아웃 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}")
            result = json.dumps({
                "success": False,
                "error": f"도구 실행 시간 초과 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}. 다른 방법을 시도하세요."
            })
        except concurrent.futures.TimeoutError:
            print(f"[IBL] 도구 스레드 타임아웃 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}")
            result = json.dumps({
                "success": False,
                "error": f"도구 실행 시간 초과 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}. 다른 방법을 시도하세요."
            })
        except Exception as e:
            print(f"[IBL] async 핸들러 실행 실패: {e}")
            from ibl_traceback import build_tb, py_tail_of
            result = json.dumps({"success": False, "error": f"async 실행 오류: {str(e)}",
                                 "traceback": build_tb(f"async 실행 오류: {str(e)}",
                                                       "exception", py_tail=py_tail_of(e))},
                                ensure_ascii=False)

    return result



def _route_system(func_name: str, params: dict, project_path: str, agent_id: str = None) -> Any:
    """system_tools 내장 함수 직접 호출"""
    if func_name == "send_notification":
        return _cap("send_notification")(dict(params), project_path)

    elif func_name == "delegate":
        return _cap("delegate")(params, project_path)

    elif func_name == "ask_body":
        # [others:ask] — 이웃 몸(다른 indiebizOS 기기)에 자연어 부탁 (몸 독립 소통).
        return _cap("ask_body")(dict(params))

    elif func_name == "agents":
        agent_id = params.get("agent_id", "")
        if agent_id:
            return _cap("agent_info")(agent_id)
        return _cap("list_project_agents")(dict(params))

    # [table:each] — 문장을 값으로 받는 고차 변환자. 다른 table 변환자와 달리 패키지가 아니라
    # 엔진 층에 산다(하위 문장 실행이 execute_ibl 재귀 — 패키지가 엔진을 import 하면 층 역전).
    elif func_name == "table_each":
        from ibl_executors import _execute_table_each
        return _execute_table_each(dict(params), project_path, agent_id=agent_id)
    elif func_name == "table_reduce":
        from ibl_control_blocks import _execute_table_reduce
        return _execute_table_reduce(dict(params), project_path, agent_id=agent_id)

    # (2026-08-05 감사 D12) 죽은 elif 6개 삭제 — call_agent/delegate_workflow/agent_ask/
    # agent_ask_sync/agent_list/agent_info 는 어떤 액션도 func: 로 선언하지 않았다.
    # 위임의 정본은 func:delegate(_delegate_unified) — mode 로 sync/workflow 를 분기하며
    # _agent_ask_sync/_delegate_workflow/_agent_info 는 그 경로가 직접 호출한다.

    # 출력 싱크 — 단일 액션 패턴: output {op: gui|clipboard} (2026-06-04 통합)
    # download는 획득 동작이라 별도 액션 유지.
    # (op:file 은 2026-08-05 어휘 압축으로 [self:write]에 흡수 — write 는 RED 쓰기
    #  안전판을 경유하는 정본이고, 파이프 싱크(_prev_result 폴백)도 write 가 맡는다.)
    elif func_name == "output_op":
        op = (params.get("op") or "gui").strip()  # 기본 gui (부작용 없는 표시)
        op_map = {
            "gui": "output_gui",
            "clipboard": "output_clipboard",
        }
        target_func = op_map.get(op)
        if not target_func:
            if op == "file":
                return {"success": False,
                        "error": "op:file 은 [self:write]{path, content}로 이동했습니다 (파이프에서는 content 생략 시 직전 결과 자동 저장)."}
            return {"success": False, "error": "op 파라미터가 필요합니다. (gui|clipboard)"}
        return _route_system(target_func, params, project_path, agent_id=agent_id)

    # Phase 13: 출력 노드 (순환 import 방지를 위해 lazy import)
    elif func_name == "output_gui":
        from ibl_executors import _output_gui
        return _output_gui(params.get("content", ""), params, project_path)
    elif func_name == "output_open":
        from ibl_executors import _output_open
        return _output_open(params.get("path", ""), params, project_path)
    elif func_name == "output_clipboard":
        from ibl_executors import _output_clipboard
        return _output_clipboard(params.get("content", ""), params)
    elif func_name == "output_download":
        from ibl_executors import _output_download
        return _output_download(params.get("url", ""), params, project_path)

    # Phase 17: 시스템 AI 전용 함수
    elif func_name == "list_project_agents":
        return _cap("list_project_agents")(params)

    elif func_name == "call_project_agent":
        return _cap("call_project_agent")(dict(params))

    elif func_name == "schedule":
        return _cap("schedule")(params, agent_id=agent_id, project_path=project_path)

    elif func_name == "manage_events":
        return _cap("manage_events")(params, project_path=project_path)

    elif func_name == "launcher_command":
        # 신규: params.app ("project" 등) → "open_<app>" 합성
        # 호환: params.command ("open_project" 등) 직접 지정도 허용
        launcher_action = params.get("command", "")
        if not launcher_action:
            app = params.get("app", "")
            if app:
                launcher_action = f"open_{app}"
        return _execute_launcher_command(launcher_action, params)

    elif func_name == "list_switches":
        return _cap("list_switches")(params)

    elif func_name == "run_switch":
        return _cap("run_switch")(params)

    elif func_name == "switch_op":
        # 단일 액션 패턴: switch {op: list|run}
        op = (params.get("op") or "").strip()
        if op == "list":
            return _route_system("list_switches", params, project_path, agent_id=agent_id)
        if op == "run":
            return _route_system("run_switch", params, project_path, agent_id=agent_id)
        return {"success": False, "error": "op 파라미터가 필요합니다. (list|run)"}

    elif func_name == "goal_op":
        # 단일 액션 패턴: goal {op: list|status|kill|log|attempts}
        op = (params.get("op") or "").strip()
        op_map = {
            "list": "list_goals",
            "status": "get_goal_status",
            "kill": "kill_goal",
            "delete": "delete_goal",   # F9-② (2026-08-16): 종결 목표 원장 정리
            "log": "log_attempt",
            "attempts": "get_attempts",
        }
        target_func = op_map.get(op)
        if not target_func:
            return {"success": False, "error": "op 파라미터가 필요합니다. (list|status|kill|delete|log|attempts)"}
        return _route_system(target_func, params, project_path, agent_id=agent_id)

    # World Pulse: 세계 상태 감각 — 단일 액션 패턴: world {op: snapshot|trend|refresh}
    elif func_name == "world_op":
        op = (params.get("op") or "snapshot").strip()  # 기본 snapshot
        op_map = {
            "snapshot": "world_pulse",
            "trend": "world_trend",
            "refresh": "world_refresh",
        }
        action_name = op_map.get(op)
        if not action_name:
            return {"success": False, "error": "op 파라미터가 필요합니다. (snapshot|trend|refresh)"}
        return _cap("world_pulse")(action_name, dict(params))

    # 자가점검: IBL 건강 점검 (정적+fixture+골든, AI 0) — 단일 액션 패턴: self_check {op: run|results}
    elif func_name == "self_check":
        op = (params.get("op") or "run").strip()
        if op == "results":
            # 결과 조회 (V17-1, 2026-08-20 판정): 원장은 자기 list 를 가진다 — 실행(run)만 있고
            # 결과는 REST 전용이라 "실패 항목만 알림"이 IBL 로 표현 불가하던 갭의 해소.
            # 구현은 cognition 층(routing_system._cap_self_check_results) — 층 가드가 잡은
            # ibl→cognition 직수입을 능력 등록(의존 역전)으로 끊었다.
            return _cap("self_check_results")(dict(params))
        if op != "run":
            return {"success": False, "error": "op 파라미터가 필요합니다. (run|results)"}
        return _cap("self_check")()

    # Phase 26: Goal 프로세스 관리
    elif func_name == "list_goals":
        from ibl_engine import _goal_list
        return _goal_list(params, project_path)
    elif func_name == "get_goal_status":
        from ibl_engine import _goal_status
        return _goal_status(params.get("goal_id", ""), params, project_path)
    elif func_name == "kill_goal":
        from ibl_engine import _goal_kill
        return _goal_kill(params.get("goal_id", ""), params, project_path)
    elif func_name == "delete_goal":
        from ibl_executors import _goal_delete
        return _goal_delete(params.get("goal_id", ""), params, project_path)

    # Phase 26b: 시도 기록 (전략 전환 + 라운드 메모리)
    elif func_name == "log_attempt":
        from ibl_engine import _log_attempt
        return _log_attempt(params, project_path)
    elif func_name == "get_attempts":
        from ibl_engine import _get_attempts
        return _get_attempts(params, project_path)

    # 능력 자기완결화 Phase 2: 패키지 생애주기 — self:package {op: list|info|install|remove}
    elif func_name == "package_op":
        return _package_op(dict(params))

    # 도구 의존성 런타임 자동설치 — self:install_lib {package}
    elif func_name == "install_lib":
        return _install_lib(dict(params))

    return {"error": f"알 수 없는 시스템 함수: {func_name}"}


def _install_lib(params: dict) -> dict:
    """self:install_lib — 도구가 필요로 하는 파이썬 라이브러리를 런타임에 설치.
    의존성 누락 에러('X 라이브러리 없음')를 사용자 승낙 후 그 자리에서 채우는 데 쓴다.

    ★공급망 방어 게이트(Floor #1 패턴): '사용자 승낙'을 프롬프트 문구가 아니라 코드로
    강제한다. 사람이 HTTP 채널(POST /install-approvals/approve — IBL 로는 못 닿음)로
    승인해 두지 않은 패키지는 pip 를 실행하지 않고 대기열 등록 + 알림으로 끝낸다.
    승인은 설치 성공 시 1회 소비된다. 위협 모델·한계는 install_approvals 모듈 참조."""
    package = (params.get("package") or params.get("name") or params.get("lib") or "").strip()
    if not package:
        return {"error": "설치할 라이브러리를 package 로 지정하세요. 예: [self:install_lib]{package: \"ddgs\"}"}

    import install_approvals

    if not install_approvals.is_approved(package):
        entry = install_approvals.request_approval(
            package, reason=str(params.get("reason") or ""), source="ibl")
        try:
            from notification_manager import get_notification_manager
            get_notification_manager().create(
                title="패키지 설치 승인 대기",
                message=(f"AI가 파이썬 라이브러리 '{package}' 설치를 요청했습니다. "
                         f"승인: POST /install-approvals/approve {{\"package\": \"{package}\"}}"),
                type="warning", source="install_gate",
            )
        except Exception:
            pass  # 알림 실패가 게이트 응답을 막지 않는다
        return {
            "success": False,
            "approval_required": True,
            "package": entry["package"],
            "message": (
                f"'{package}' 설치에는 사람의 사전 승인이 필요합니다(공급망 방어 게이트). "
                f"승인 대기열에 등록하고 알림을 보냈습니다. 사용자에게 이 패키지가 왜 필요한지 "
                f"알리세요. 승인은 사용자가 직접 합니다(AI가 대신 승인할 수 없습니다) — "
                f"승인 후 같은 호출을 다시 실행하면 설치됩니다."
            ),
            "how_to_approve": (
                f"curl -X POST http://localhost:8765/install-approvals/approve "
                f"-H 'Content-Type: application/json' -d '{{\"package\": \"{package}\"}}'"
            ),
        }

    from runtime_utils import install_python_dependency
    result = install_python_dependency(package)
    if result.get("success"):
        install_approvals.consume(package)  # 실패 시엔 승인 유지 → 재시도 가능
    return result


def _rebuild_ibl_vocab() -> Optional[str]:
    """build_ibl_nodes.py 재실행 + 런타임 캐시 초기화 (POST /packages/reload와 동형).

    패키지 install/remove로 ibl_actions.yaml fragment 구성이 바뀐 뒤 호출한다.
    성공하면 None, 실패하면 에러 메시지를 반환한다(호출부가 install/remove 결과에 경고로 얹음).
    """
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent.parent
    script = root / "scripts" / "build_ibl_nodes.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return f"어휘 재빌드 실패: {proc.stderr.strip()[-500:]}"
    except Exception as e:  # noqa: BLE001
        return f"어휘 재빌드 예외: {e}"

    # /packages/reload(api_packages)와 같은 절차·같은 순서.
    def _pkg_meta():
        from package_manager import package_manager
        package_manager.invalidate_cache()

    def _catalog():
        from ibl_access import invalidate_nodes_cache
        invalidate_nodes_cache()

    def _registry():
        # ★2026-08-24 발견: 여기만 이 단계가 빠져 있었다("동형"이라 적어두고 아니었다).
        # 안 비우면 reload_nodes 가 낡은 레지스트리를 재병합해 삭제된 registry 액션이
        # 실행기에 유령으로 남는다(/packages/reload 가 2026-07-03 에 고친 바로 그 병).
        from ibl_registry import reload_registry
        reload_registry()

    def _executor():
        from ibl_engine import reload_nodes
        reload_nodes()

    # ★실패를 삼키지 않는다 — 한 단계라도 못 비우면 스테일 사전인 채 "재빌드 성공"이
    #   반환돼 거짓말이 된다(침묵 클램프 부류).
    failed = []
    for name, step in (("package_meta", _pkg_meta), ("catalog", _catalog),
                       ("api_registry", _registry), ("executor", _executor),
                       ("consciousness", lambda: _cap("reset_consciousness")())):
        try:
            step()
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}({type(e).__name__})")
    if failed:
        return ("어휘는 재빌드했으나 런타임 캐시 초기화 실패 — 스테일 사전일 수 있습니다"
                f"(백엔드 재기동 권장): {', '.join(failed)}")
    return None


def _package_op(params: dict) -> dict:
    """[self:package]{op} — list/info/install/remove. package_manager 래핑 + 어휘 재빌드."""
    from package_manager import package_manager

    op = (params.get("op") or "list").strip()

    if op == "list":
        installed = package_manager.list_installed(package_type="tools")
        # list_available은 하위호환 때문에 installed+not_installed 전부 반환 — 여기선
        # 미설치만 걸러 IBL 어휘의 "list" op가 의미하는 대로(설치 후보) 좁힌다.
        not_installed = [
            p for p in package_manager.list_available(package_type="tools")
            if not p.get("installed")
        ]
        inst = [{"package_id": p.get("id") or p.get("name"), "name": p.get("name")} for p in installed]
        avail = [{"package_id": p.get("id") or p.get("name"), "name": p.get("name")} for p in not_installed]
        return {
            "success": True,
            "installed": inst,
            "available": avail,
            # items 병행 방출 — self:agents(d74461b)·self:switch(8a6aacd)와 같은 이유.
            # ★여기선 두 목록이 *같은 종류*(패키지)라 상태 필드를 달아 한 통화로 합친다
            #   (`>> [table:filter]{where: "installed == true"}` 로 갈라 쓰게). 기존 두 키는 그대로.
            "items": [{**p, "installed": True} for p in inst] + [{**p, "installed": False} for p in avail],
        }

    package_id = (params.get("package_id") or params.get("name") or "").strip()
    if not package_id:
        return {"success": False, "error": "package_id 파라미터가 필요합니다."}

    if op == "info":
        info = package_manager.get_package_info(package_id)
        if not info:
            return {"success": False, "error": f"패키지를 찾을 수 없습니다: {package_id}"}
        return {"success": True, "package": info}

    if op == "install":
        try:
            result = package_manager.install_package(package_id, skip_validation=False)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        warn = _rebuild_ibl_vocab()
        if warn:
            result.setdefault("warnings", []).append(warn)
        result["success"] = True
        return result

    if op == "remove":
        try:
            result = package_manager.uninstall_package(package_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        warn = _rebuild_ibl_vocab()
        if warn:
            result.setdefault("warnings", []).append(warn)
        result["success"] = True
        return result

    return {"success": False, "error": "op 파라미터가 필요합니다. (list|info|install|remove)"}


def _execute_launcher_command(action: str, params: dict) -> dict:
    """Launcher(Electron) 창 제어 명령 실행 (Phase 27)

    WS로 Launcher에 명령을 보내 프로젝트 창 열기, 포커스 등 수행.
    """
    import asyncio

    # 내장 도구 창 2종 — WS 런처 명령이 아니라 pending-queue 로 Electron 이 폴링해 연다.
    # (구 limbs:explorer / limbs:photo_manager 의 흡수, 2026-08-15 — 창 여는 말은 open_window 하나.
    #  큐는 base 층 window_requests 단일 저장소 — surface 모듈 직접 import 는 층 위반.)
    if action in ("open_files", "open_explorer"):
        try:
            import window_requests
            window_requests.request_window("files", params.get("path"))
            return {"success": True, "message": f"PC Manager(파일) 창 열기 요청 — 경로: {params.get('path') or '홈'}"}
        except Exception as e:
            return {"success": False, "error": f"PC Manager 창 요청 실패: {e}"}
    if action in ("open_photos", "open_photo_manager"):
        try:
            import window_requests
            window_requests.request_window("photos", params.get("path"))
            return {"success": True, "message": "Photo Manager(사진) 창 열기 요청"}
        except Exception as e:
            return {"success": False, "error": f"Photo Manager 창 요청 실패: {e}"}

    # action 이름 → Launcher 명령 매핑
    command_map = {
        "open_project": "open_project_window",
        "open_system_ai": "open_system_ai_window",
        "open_messenger": "open_messenger_window",
        "open_community": "open_community_window",
        # 레거시 별칭: 옛 IndieNet 창의 후신은 커뮤니티 계기 창(공개 피드·게시판).
        # 한때 messenger 로 매핑돼 이름-대상이 어긋나 있었음 — 2026-07-08 교정.
        "open_indienet": "open_community_window",
        "open_business": "open_business_window",
        "open_multichat": "open_multichat_window",
        "open_folder": "open_folder_window",
    }

    command = command_map.get(action)
    if not command:
        return {"success": False, "error": f"알 수 없는 launcher 액션: {action}"}

    try:
        from websocket_manager import send_launcher_command, get_launcher_ws

        if not get_launcher_ws():
            return {"success": False, "error": "Launcher WS 미연결"}

        # 비동기 함수를 동기 컨텍스트에서 실행
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    send_launcher_command(command, dict(params)),
                    loop
                )
                sent = future.result(timeout=5)
            else:
                sent = asyncio.run(send_launcher_command(command, dict(params)))
        except RuntimeError:
            sent = asyncio.run(send_launcher_command(command, dict(params)))

        if sent:
            return {"success": True, "message": f"Launcher 명령 전달: {command}"}
        else:
            return {"success": False, "error": "Launcher 명령 전달 실패"}

    except Exception as e:
        return {"success": False, "error": f"Launcher 명령 오류: {str(e)}"}


def search_guide(query: str, params: dict) -> Any:
    """가이드 DB 검색 — 복잡한 작업 전에 워크플로우/레시피 확인

    DB(guide_db.json)에서 키워드 매칭 후 data/guides/ 폴더에서 파일 읽기.
    params.read=true (기본) → 첫 번째 매칭 가이드 내용까지 반환
    params.read=false → 목록만 반환
    """
    import json as _json
    from pathlib import Path as _Path

    data_dir = _Path(__file__).parent.parent.parent / "data"
    guide_db_path = data_dir / "guide_db.json"

    if not guide_db_path.exists():
        return {"error": "guide_db.json이 없습니다."}

    with open(guide_db_path, 'r', encoding='utf-8') as f:
        db = _json.load(f)

    guides = db.get("guides", [])

    if not query:
        return {
            "guides": [{"id": g["id"], "name": g["name"], "description": g["description"]} for g in guides],
            "count": len(guides),
            "message": "가이드 전체 목록입니다. 키워드로 검색하세요.",
        }

    # ★파일명 정확 일치 빠른길 (2026-09-03): 가이드의 입구가 <execution_map> 의 `guide:` 줄로
    #   옮겨져 실행자는 지도의 파일명을 그대로 넘긴다. 파일명은 점수 경쟁 없이 그 파일이다 —
    #   토큰 점수에 맡기면 "goal.md" 가 'goal' 낱말을 가진 다른 가이드에 밀릴 수 있다.
    _q = (query or "").strip().strip("`")
    if _q.endswith(".md"):
        _hit = next((g for g in guides if (g.get("file") or "") == _q), None)
        if _hit:
            out = {"guides": [{"id": _hit["id"], "name": _hit["name"],
                               "description": _hit.get("description", ""), "file": _hit.get("file")}],
                   "count": 1, "match": "filename"}
            if params.get("read", True):
                gp = data_dir / "guides" / _q
                if gp.exists():
                    out["content"] = gp.read_text(encoding="utf-8")
                    out["file"] = _q
                else:
                    out["error"] = f"guide_db 에는 있으나 파일이 없습니다: {_q}"
            return out
    # 한국어 정규화: 조사 제거 + 복합어 분리 (korean_utils 공통 모듈)
    from korean_utils import tokenize_korean
    import re as _re
    query_stems = tokenize_korean(query)

    # 원형 토큰 — 토크나이저가 떨구는 짧은 낱말을 살린다 (2026-08-18).
    #   실측: "유튜브 AI 팁 보고서" → stems ['ai','보고','유튜브'] 로 가장 변별력 있는
    #   '팁' 이 통째로 사라져 youtube_ai_tips_report 와 youtube_relay 가 3점 동점이 됐고,
    #   정확한 제목으로 부른 정본이 순서로 밀렸다(자율주행이면 가이드 없이 진행).
    q_low = (query or "").strip().lower()
    raw_tokens = [t for t in _re.split(r"[\s/,·]+", q_low) if t]

    scored = []
    for g in guides:
        score = 0
        name_low = g.get("name", "").lower()
        kw_low = [kw.lower() for kw in g.get("keywords", [])]
        search_text = " ".join([
            g.get("name", ""),
            g.get("description", ""),
            " ".join(g.get("keywords", [])),
        ]).lower()

        for word in query_stems:
            if word in search_text:
                score += 1
            if word in kw_low:
                score += 2

        for word in raw_tokens:
            if word in query_stems:
                continue  # 위에서 이미 셈
            if word in search_text:
                score += 1
            if word in kw_low:
                score += 2

        # 제목 호명 — 사용자가 가이드 이름을 그대로 불렀으면 가장 강한 신호다.
        # 부분 점수 합산으로는 뒤집힐 수 있어(동점 → 순서 운) 명시적으로 앞세운다.
        if q_low and (q_low in name_low or name_low.startswith(q_low)):
            score += 10

        if score > 0:
            scored.append((score, g))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "query": query,
            "results": [],
            "message": f"'{query}'에 매칭되는 가이드가 없습니다.",
        }

    results = [{"id": g["id"], "name": g["name"], "description": g["description"], "score": s} for s, g in scored[:5]]

    response = {
        "query": query,
        "results": results,
        "count": len(results),
        "best_match": results[0]["name"],
    }

    # 기본적으로 첫 번째 매칭 가이드 파일을 읽어서 반환
    read_content = params.get("read", True)
    if read_content and scored:
        best = scored[0][1]
        guide_file = best.get("file", "")
        if guide_file:
            guide_path = data_dir / "guides" / guide_file
            if guide_path.exists():
                try:
                    response["guide_content"] = guide_path.read_text(encoding='utf-8')
                    response["guide_name"] = best["name"]
                except Exception:
                    pass

    return response


# 위임 기계(_delegate_unified·_delegate_workflow·_agent_ask_sync·_agent_info)는
# routing_system(인지층)으로 이동 — 능력 테이블(register_system_capabilities) 경유
# (2026-08-05 감사 ⑦ 후반부. delegate/agent_info 이름으로 등록된다).


def _route_driver(driver_type: str, node: str, action: str,
                  params: dict, project_path: str,
                  driver_node: str = None) -> Any:
    """드라이버 계층으로 라우팅 (Phase 7)

    드라이버는 프로토콜(SQLite, ADB, CDP 등)을 감추고
    통일된 execute(action, params) 인터페이스를 제공한다.

    Phase 22: driver_node 파라미터 추가.
    6-Node 통합으로 source/messenger 등 상위 노드가 photo/health/blog/contact/memory
    등의 하위 핸들러를 포함하게 됨. driver_node가 지정되면 실제 드라이버 핸들러명으로 사용.
    """
    # 드라이버 인스턴스 가져오기
    driver_registry = {
        "sqlite": ("drivers.sqlite_driver", "get_driver"),
        # 향후 확장:
        # "adb": ("drivers.adb_driver", "get_driver"),
        # "cdp": ("drivers.cdp_driver", "get_driver"),
        # "stream": ("drivers.stream_driver", "get_driver"),
    }

    entry = driver_registry.get(driver_type)
    if not entry:
        return {"error": f"알 수 없는 드라이버: {driver_type}"}

    module_path, factory_name = entry
    try:
        import importlib
        mod = importlib.import_module(module_path)
        get_driver = getattr(mod, factory_name)
        driver = get_driver()
    except Exception as e:
        return {"error": f"드라이버 로드 실패 ({driver_type}): {str(e)}"}

    # 노드 정보를 params에 전달 (driver_node 우선, 없으면 node)
    params["_node"] = driver_node or node

    # project_path 해소 — 작가가 IBL 코드에 손으로 쓴 `{project_id: "…"}` 를 핸들러
    # 라우터(_route_handler → resolve_project_path)와 **같은 규칙**으로 존중한다.
    # 종전엔 호출자 경로만 그대로 실어, 드라이버 액션에 project_id 를 적으면 조용히
    # 무시되고 *빈 결과가 success 로* 돌아왔다(실측: `[self:agents]{project_id:"study"}`
    # → "에이전트 0명", 같은 DB 직접 조회는 3명). 도구 실패 힌트 문구가 바로 그
    # `{…, project_id: "…"}` 를 안내하고 있어서 AI 는 시킨 대로 쓰고 빈손을 받았다.
    # project_id 가 없으면 종전 경로 그대로 — 프로젝트 에이전트 흐름 무변경.
    if isinstance(params.get("project_id"), str) and params["project_id"].strip():
        project_path = resolve_project_path(project_path, params) or project_path
    if project_path:
        params["project_path"] = project_path

    return driver.execute(action, params)


# (2026-08-05 감사 D11) _route_by_config 삭제 — 유일 소비자가 죽은 노드타입
# 디스패치(ibl_executors._execute_node 가족)였다. 라우팅 정본은 execute_ibl 의 라우터 스위치.
