"""연상 회상의 공통 흐름 — 요청을 받고, 정책대로 기억을 조회하고, 문맥에 담고, 무엇을 제시했는지 남긴다.

정본 설계: docs/ASSOCIATIVE_RECALL_COMMON_FLOW_2026_09_18.md. 사용자 판정(2026-09-18):
「네 기억을 최소한의 공통 기반 위에 놓고, 차이는 의미상 필요하거나 성능으로 입증된 것만 유지한다.」

무엇이 공통인가(이 모듈): 주체 관문, 어느 채널에서 어느 기억이 자동으로 도는가(정책 표 `SOURCES`), 조회 순서와
문맥 조립, 반사 신호의 이름 붙은 출력, 제시 기록(`recall.presented` 사건). 무엇이 기억별인가(공급원 함수가
부르는 각 저장소): 검색기(해마는 전용 인코더, 트리 기억은 `tree_recall`), 후보의 뜻, 성공의 정의와 학습.

두 상(相): 1상은 분류 전(반사 신호가 분류에 쓰인다), 2상은 분류 뒤(세계 지도의 글자 채널은 request_type 을 본다).
그래서 `begin()` 은 1상만 돌고, 호출자는 반드시 `route(request_type)` 로 2상을 닫는다 — `text()` 는 그 전엔 거부한다
(`scripts/check_recall_assembly.py` 가 호출 자리마다 정적으로 확인한다). 공급원 호출은 이 모듈 밖에서 금지다 —
세 조립 지점이 각자 부분집합을 부르다 갈라진 것(agent_pipeline/agent_communication/recall-preview)이 이 모듈의 출생 이유다.

포식 기억은 정책 표에 `auto=False` 로 실린다 — 어휘가 기억의 입구라는 판정(2026-09-03)은 데이터로 보존된다.
"""
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ─────────────────────────── 계약 ───────────────────────────

@dataclass
class RecallRequest:
    runner: Any                      # config(allowed_nodes)·project_path·agent_id 를 가진 러너(없어도 된다: 표본 조립)
    message: str
    history: list
    channel: str = "pipeline"        # pipeline | agent_message | preview | sample
    action_hint: Optional[str] = None
    deep: bool = True                # 심층기억(지도·선택) 자동 주입 — 포식 표면은 끈다(필터버블 드리프트 방지)


@dataclass
class ReflexSignal:
    """반사 분기가 읽는 이름 붙은 출력. 지금은 해마 낱말 채널의 최고 점수·코드 하나다."""
    score: float = 0.0
    code: str = ""


@dataclass
class Block:
    source: str                      # 정책 표의 공급원 이름
    tag: str                         # 최상위 XML 태그(주입 표시·프리뷰 절 분리용)
    text: str
    status: str = "ok"               # ok | empty | closed | error | skipped
    ids: List[str] = field(default_factory=list)   # 제시된 후보의 식별자(기억별 뜻은 다르다 — 사건에 그대로 남긴다)
    ms: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)
    join: Dict[str, Any] = field(default_factory=dict)   # 제시→사용 결합 키(사건엔 싣지 않고 턴 끝 payload 로 간다)


@dataclass(frozen=True)
class Source:
    name: str
    tag: str
    phase: int                       # 1 = 분류 전, 2 = 분류 뒤
    personal: bool                   # 주인 것 — 주체 관문(owner)만 통과
    fn: Optional[Callable] = None    # (req, recall) -> Block | None. None 이면 자동으로 돌지 않는다.
    auto: bool = True
    needs: str = ""                  # RecallRequest 의 불 필드 이름 — 거짓이면 건너뛴다


class Recall:
    """한 턴의 회상. blocks 순서 = 주입 순서."""

    def __init__(self, request: RecallRequest):
        self.request = request
        self.reflex = ReflexSignal()
        self.blocks: List[Block] = []
        self.routed = False
        self.request_type: Optional[str] = None

    # 파이프라인이 두 상 사이에 끼우는 블록(과제 원장·문맥 갱신 표식) — 조립은 여기 한 곳이다.
    def attach(self, source: str, text: str, tag: str = "") -> None:
        if text:
            self.blocks.append(Block(source, tag or source, text))

    def route(self, request_type: Optional[str], *, reflex_hint=None, force_role=None, context_update=False) -> "Recall":
        """2상 — 분류 뒤에 도는 공급원(세계 지도·세계의 기억). request_type=None 은 분류 없는 채널."""
        if self.routed:
            return self
        self.request_type = request_type
        _run_phase(self, 2, request_type=request_type, reflex_hint=reflex_hint, force_role=force_role,
                   context_update=context_update)
        self.routed = True
        _record_presented(self)
        _print_summary(self)
        return self

    def text(self) -> str:
        if not self.routed:
            raise RuntimeError("associative_recall: route(request_type) 전에 text() 를 불렀다 — 2상(세계 지도)이 빠진 주입")
        return "\n".join(b.text for b in self.blocks if b.text)

    def presented(self) -> List[Dict[str, Any]]:
        return [{"source": b.source, "tag": b.tag, "status": b.status, "ids": b.ids[:10],
                 "chars": len(b.text), "ms": round(b.ms, 1), **({"meta": b.meta} if b.meta else {})}
                for b in self.blocks]

    def usage_payload(self) -> List[Dict[str, Any]]:
        """턴 끝 결합용 — 사용 해석기가 있는 공급원의 제시 id 와 결합 키. 값으로 넘긴다(증류 큐는 스레드를 넘는다)."""
        return [{"source": b.source, "ids": list(b.ids), "join": b.join}
                for b in self.blocks if b.ids and b.source in USAGE]


def begin(runner, message: str, *, history: Optional[list] = None, channel: str = "pipeline",
          action_hint: Optional[str] = None, deep: bool = True) -> Recall:
    """1상 — 분류 전에 도는 공급원 전부. 반사 신호는 `recall.reflex` 로 나온다. 호출자는 `route()` 로 닫는다."""
    req = RecallRequest(runner, message or "", history or [], channel, action_hint, deep)
    recall = Recall(req)
    _run_phase(recall, 1)
    return recall


def stub(text: str = "", score: float = 0.0, code: str = "") -> Callable:
    """시험·회원 러너용 `_associate` 대역 — 1상을 주어진 값으로 대신하고 2상은 실제로 돈다."""
    def _associate(runner, message, *, history=None, channel="pipeline", action_hint=None, deep=True):
        r = Recall(RecallRequest(runner, message or "", history or [], channel, action_hint, deep))
        if text:
            r.blocks.append(Block("stub", "stub", text))
        r.reflex = ReflexSignal(float(score or 0.0), code or "")
        return r
    return _associate


# ─────────────────────────── 실행 ───────────────────────────

def _principal_ok() -> bool:
    try:
        import principal
        return principal.recall_allowed("associative")
    except ImportError:
        return True


def _step(name: str, call: Callable):
    """회상 정지가 감독에 보이게 — 모델 호출 없는 준비 단계로 표시한다."""
    from contextlib import nullcontext
    try:
        from supervision_bus import current
        controller = current()
    except Exception:
        controller = None
    with controller.preparation(name) if controller else nullcontext():
        return call()


def _run_phase(recall: Recall, phase: int, **route_kw) -> None:
    req = recall.request
    owner = _principal_ok()
    for src in SOURCES:
        if src.phase != phase or not src.auto or src.fn is None:
            continue
        if not _enabled(req.channel, src.name):
            continue
        if src.needs and not getattr(req, src.needs, False):
            continue
        if src.personal and not owner:
            # 주인 것은 통째로 닫힌다(2026-09-14 주체 관문). 회원 자기 기억은 손발 회상(1단계)이 맡는다.
            continue
        t0 = time.monotonic()
        try:
            block = src.fn(req, recall, **route_kw) if phase == 2 else src.fn(req, recall)
        except Exception as e:  # noqa: BLE001 — 한 기억의 실패가 다른 기억을 막지 않는다
            print(f"[연상:{src.name}] 실패 (무시): {e}")
            block = Block(src.name, src.tag, "", status="error", meta={"error": type(e).__name__})
        if block is None:
            continue
        block.ms = (time.monotonic() - t0) * 1000
        recall.blocks.append(block)


def _record_presented(recall: Recall) -> None:
    try:
        from episode_logger import record_trajectory_event
        record_trajectory_event("recall.presented", {
            "channel": recall.request.channel, "request_type": recall.request_type,
            "reflex": {"score": round(float(recall.reflex.score or 0.0), 4), "code": (recall.reflex.code or "")[:120]},
            "blocks": recall.presented(),
        })
    except Exception:
        pass


_LABELS = [("execution_memory", "실행기억"), ("memory_map", "기억지도"), ("recalled_memory", "선택기억"),
           ("guide_map", "가이드목차"), ("forage_memory", "포식기억"), ("connected_limbs", "손발"), ("repair_outcome", "수리결말"),
           ("decision_ledger", "결정원장"), ("method_map", "세계지도"), ("world_memory", "세계기억")]


def _print_summary(recall: Recall) -> None:
    text = recall.text()
    parts = [label for tag, label in _LABELS if f"<{tag}" in text]
    head = (recall.request.message or "")[:40]
    print(f"[연상] {'+'.join(parts)}: \"{head}\"" if parts else f"[연상] 빈 결과: \"{head}\"")


# ─────────────────────────── 러너에서 읽는 것 ───────────────────────────

def _allowed_set(runner):
    allowed_nodes = (getattr(runner, "config", None) or {}).get("allowed_nodes")
    if not allowed_nodes:
        return None
    from ibl_access import resolve_allowed_nodes
    return resolve_allowed_nodes(allowed_nodes)


def deep_memory_db(runner) -> str:
    """이 자아의 심층기억 DB 경로(없으면 ""). memory 패키지를 import 경로에 올린다."""
    import os
    import sys
    if runner is None or not getattr(runner, "project_path", None):
        return ""
    mem_pkg = os.path.normpath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..",
        "data", "packages", "installed", "tools", "memory"))
    if mem_pkg not in sys.path:
        sys.path.insert(0, mem_pkg)
    import memory_db
    from thread_context import get_current_agent_id
    agent_id = get_current_agent_id() or getattr(runner, "agent_id", None)
    db_path = memory_db._get_db_path(str(runner.project_path), agent_id)
    return db_path if os.path.exists(db_path) else ""


# ─────────────────────────── 공급원 (1상) ───────────────────────────

def _hippocampus(req: RecallRequest, recall: Recall) -> Optional[Block]:
    """실행기억 — 해마. 검색기·검증(별칭·관용구·구현 조회·액션 검증)은 ibl_usage_rag 의 몫이고 여기선 부르기만 한다.
    action_hint(마법책에서 고른 액션)는 검색을 건너뛰어 그 액션을 Top-1 로 합성한다. 무효하면 검색으로 폴백."""
    from ibl_usage_rag import build_execution_memory_detail, build_execution_memory_from_hint
    xml, score, code, presented = ("", 0.0, "", [])
    if req.action_hint:
        xml, score, code = build_execution_memory_from_hint(req.action_hint)
        if xml:
            presented = [{"id": "hint", "code": code, "kind": "hint", "alias": ""}]
        else:
            print(f"[연상] action_hint='{req.action_hint}' 유효하지 않음 — 해마 검색으로 폴백")
    if not xml:
        allowed = _allowed_set(req.runner)
        d = _step("execution_memory", lambda: build_execution_memory_detail(req.message, allowed))
        xml, score, code, presented = d["xml"], d["top_score"], d["top_code"], d["presented"]
    recall.reflex = ReflexSignal(float(score or 0.0), code or "")
    if not xml:
        return Block("hippocampus", "execution_memory", "", status="empty", meta={"top_code": code or ""})
    return Block("hippocampus", "execution_memory", xml, ids=[p["id"] for p in presented],
                 meta={"refs": xml.count("<ref "), "top_code": (code or "")[:120]},
                 join={"items": presented})


def _memory_map(req: RecallRequest, recall: Recall) -> Optional[Block]:
    """심층기억의 지도(목차) — 가지·건수·요약만. 크면 최상위만. 문서가 손으로 고쳐졌으면 먼저 색인 반영(mtime 대조)."""
    def run():
        db_path = deep_memory_db(req.runner)
        if not db_path:
            return Block("memory_map", "memory_map", "", status="empty")
        import memory_tree
        memory_tree.sync_all(db_path)
        text = memory_tree.map_text(db_path, max_chars=memory_tree.MAP_FULL_CHARS)
        if not text:
            return Block("memory_map", "memory_map", "", status="empty")
        xml = (
            '<memory_map note="이 자아의 심층 기억 지도(목차) — 가지 (건수) — 요약. 지도가 크면 최상위 가지만 실린다. '
            '이 질문에 맞춰 기계가 고른 기억은 아래 <recalled_memory> 에 있다 — 그것으로 모자라고 관련 가지가 보이면 '
            '답하기 전에 [self:memory]{op:\"recall\", node:\"<가지>\"} 로 연다. 지속 가치가 있는 사용자 사실은 최종 응답 후 자동 선별된다. save 호출은 필요 없다.">\n'
            + text + "\n</memory_map>"
        )
        print(f"[연상:기억지도] {text.count(chr(10)) + 1}가지")
        return Block("memory_map", "memory_map", xml, meta={"branches": text.count(chr(10)) + 1})
    return _step("memory_map", run)


def _recalled_memory(req: RecallRequest, recall: Recall) -> Optional[Block]:
    """이 질문에 맞춰 고른 심층기억 — 가지 2 → 그 안 2건 + 밖 1건(공통 회상 tree_recall, 설계 2026-09-17).
    관련 없음은 기계가 가르지 못한다 — 작게 싣고 판단은 받는 AI 가 한다. 인코더 적재 중이면 0토큰."""
    def run():
        db_path = deep_memory_db(req.runner)
        if not db_path:
            return Block("recalled_memory", "recalled_memory", "", status="empty")
        import tree_recall
        from recall_store import DeepMemoryStore
        store = DeepMemoryStore(db_path)
        r = tree_recall.recall(store, req.message)
        picked = r["items"] + r["outside"]
        if not picked:
            print(f"[연상:선택기억] {r['status']}")
            return Block("recalled_memory", "recalled_memory", "", status=r["status"])
        if r.get("outside_beats_inside"):
            note_outside_hit(store.key, req.message, r)
        branches = ", ".join("/".join(b) for b in r["branches"]) or "(가지 고르기 생략)"
        xml = (
            '<recalled_memory note="이 질문에 맞춰 기계가 고른 심층기억 후보 — 고른 가지 안에서 2건, 밖에서 1건. '
            '관련 없으면 무시한다. 긴 기억은 잘려 있다(…): 전문과 같은 가지의 다른 기억은 '
            '[self:memory]{op:\"recall\", node:\"<가지>\"} 로 연다.">\n'
            f"고른 가지: {branches}\n" + "\n".join(it.label for it in picked) + "\n</recalled_memory>"
        )
        print(f"[연상:선택기억] {r['status']} 가지={branches} 건수={len(picked)}")
        return Block("recalled_memory", "recalled_memory", xml, status=r["status"], ids=[it.id for it in picked],
                     meta={"branches": ["/".join(b) for b in r["branches"]],
                           "outside_beats_inside": bool(r.get("outside_beats_inside"))},
                     join={"paths": {it.id: "/".join(it.path) for it in picked}, "db": db_path})
    return _step("recalled_memory", run)


def note_outside_hit(store_key: str, user_message: str, r: dict) -> None:
    """되먹임 원장(공통 회상 설계 §5.5): 가지 밖 항목이 가지 안보다 앞선 턴 = 사전이 모르는 흩어짐의 신호.
    정리 패스에서 AI 가 읽고 '함께 볼 가지'·'찾는 말'을 고친다. 개인 데이터라 git 밖(data/recall_index/)."""
    try:
        import json
        import os
        from datetime import datetime
        import tree_recall
        path = os.path.join(tree_recall._index_dir(), "outside_hits.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {"at": datetime.now().isoformat(timespec="seconds"), "store": store_key,
               "query": (user_message or "")[:80], "chosen": ["/".join(b) for b in r["branches"]],
               "outside": ["/".join(it.path) for it in r["outside"]]}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _guide_map(req: RecallRequest, recall: Recall) -> Optional[Block]:
    """가이드 목차 — 가이드가 달린 실행기억 가지와 파일명만(실행기억 지도의 자동 주입은 2026-09-17 폐지)."""
    def run():
        import hippo_tree
        hippo_tree.sync_all()
        text = hippo_tree.guide_map_text()
        if not text:
            return Block("guide_map", "guide_map", "", status="empty")
        xml = (
            '<guide_map note="가이드 목차 — 주제 가지: 가이드 파일명. 가이드의 유일한 목차이니 일이 속한 가지의 파일명을 '
            'read_guide 에 그대로 넣어 연다(의식은 guide_files 로 지목). 성공한 IBL 문장의 주제별 모음은 여기 실리지 않는다 — '
            '위 <execution_memory> 의 닮은 용례로 부족한 큰 일이면 [self:memory]{op:\"recall\", node:\"<가지>\", store:\"실행\"} 로 '
            '가지를 열고, node 를 생략하면 실행기억 지도 전체가 나온다.">\n'
            + text + "\n</guide_map>"
        )
        print(f"[연상:가이드목차] {text.count(chr(10)) + 1}가지")
        return Block("guide_map", "guide_map", xml, meta={"branches": text.count(chr(10)) + 1})
    return _step("guide_map", run)


def _connected_limbs(req: RecallRequest, recall: Recall) -> Optional[Block]:
    """연결된 USB 손발(게스트 PC)의 이름+뜻 — 질의 무관 강제 주입(라이브일 때만). 별칭은 런타임 상태라 어휘·해마가 모른다(ep840).
    limbs 노드가 이 에이전트 어휘 밖이면 생략(쓸 수 없는 길 안내=오도)."""
    def run():
        allowed = _allowed_set(req.runner)
        if allowed is not None and "limbs" not in allowed:
            return None
        import device_registry as dr
        import limb_keys
        live = dr.live_with_capability(limb_keys.GUEST_PC_CLASS)
        if not live:
            return None
        rows, names = [], []
        for e in live:
            alias = e.get("alias") or e.get("device_id") or "?"
            rec = limb_keys.get_by_device(e.get("device_id") or "") or {}
            host = rec.get("last_host") or ""
            host_attr = f' host="{host}"' if host else ""
            rows.append(f'  <limb name="{alias}"{host_attr}/>')
            names.append(alias)
        note = ("USB 손발(게스트 PC)이 지금 연결되어 있다. 명령에 아래 이름이 나오면 그 PC를 뜻한다 — "
                "그 PC의 셸·파일·시스템 상태 조회는 [limbs:guestpc]{limb: \"이름\", op: shell/read/write/list/info}. "
                "이름 언급 없는 시스템 상태는 본체([sense:host]).")
        return Block("connected_limbs", "connected_limbs",
                     f"<connected_limbs note='{note}'>\n" + "\n".join(rows) + "\n</connected_limbs>", ids=names)
    return _step("limb_presence", run)


def _pending_repair(req: RecallRequest, recall: Recall) -> Optional[Block]:
    """직전 자기수리의 미보고 판정 — 질의 무관 강제 주입. 주인 것만 줍는다(2026-08-25 — 물음은 신원이 아니라 소유)."""
    def run():
        from runtime_utils import get_base_path
        import red_report
        text = red_report.pending_scent(str(get_base_path()), owner=red_report.current_owner())
        return Block("pending_repair", "repair_outcome", text) if text else None
    return _step("pending_repair", run)


def _decision_ledger(req: RecallRequest, recall: Recall) -> Optional[Block]:
    """사용자 판정 원장 — 상시 다이제스트 + 질의 일치 상세. 원장이 비면 0토큰."""
    def run():
        import decision_ledger
        text = decision_ledger.scent_xml(req.message)
        return Block("decision_ledger", "decision_ledger", text) if text else None
    return _step("decisions", run)


# ─────────────────────────── 공급원 (2상) ───────────────────────────

def _method_map(req: RecallRequest, recall: Recall, *, request_type=None, reflex_hint=None, force_role=None,
                context_update=False) -> Optional[Block]:
    """세계 지도의 글자 채널 — 이름을 실제로 말했을 때의 정밀한 길. 개인 기억이 아니라 주체로 막지 않는다."""
    from catalog_recall import recall_for_turn_detail
    text, event, names = recall_for_turn_detail(req.runner, req.message, req.history, request_type=request_type,
                                                reflex_hint=reflex_hint, force_role=force_role,
                                                context_update=context_update)
    if not text:
        return Block("method_map", "method_map", "", status=event.get("status") or "empty")
    return Block("method_map", "method_map", text, status=event.get("status") or "ok", ids=list(event.get("ids") or []),
                 join={"names": names})


def _world_memory(req: RecallRequest, recall: Recall, **_route_kw) -> Optional[Block]:
    """세계의 기억 — 지도 + 가지 먼저 고른 어휘 3건(의미 채널). 글자 채널에 이미 나온 이름은 뺀다."""
    from catalog_recall import world_memory_detail
    lexical = next((b.text for b in recall.blocks if b.source == "method_map"), "")
    text, event, names = world_memory_detail(req.message, lexical)
    if not text:
        return Block("world_memory", "world_map", "", status=event.get("status") or "empty")
    return Block("world_memory", "world_map", text, status=event.get("status") or "ok", ids=list(event.get("ids") or []),
                 meta={"picked": len(event.get("ids") or [])}, join={"names": names})


# ─────────────────────────── 제시 → 사용 결합 (2026-09-18, 2단계 ①) ───────────────────────────
# 형식은 공통(사건 `recall.used`: 공급원별 제시 id·사용 id·증거 종류), 해석은 기억별(아래 USAGE 표의 함수).
# 갱신 규칙은 각 기억의 것 그대로다 — 해마 success_rate 는 record_recall_outcome, 심층 used_at 은 증류 SAME/UPDATE·
# 명시 조회(touch). 여기서는 무엇이 제시됐고 무엇이 쓰였는지를 한 경로로 남길 뿐, 점수·성공률을 고치지 않는다.

_PAIR_RE = re.compile(r"\[([a-z_-]+):([a-z_-]+)\]")
_FN_RE = re.compile(r"\[fn:\s*([^\]\s]+)\s*\]")
_DEEP_RECALL_RE = re.compile(r"\[self:memory\]\s*\{([^}]*)\}")
_QUOTED_RE = re.compile(r'(\w+)\s*:\s*"([^"]*)"')


def _ibl_codes(tool_calls) -> List[str]:
    out = []
    for tc in tool_calls or []:
        if isinstance(tc, dict) and tc.get("tool_name") == "execute_ibl":
            code = (tc.get("input") or {}).get("code", "")
            if code:
                out.append(code)
    return out


def _used_hippocampus(ids, join, ev) -> Dict[str, Any]:
    """실행 절차 — 제시 용례의 [node:action] 쌍이 이 턴의 execute_ibl 에 실제로 등장했나(record_recall_outcome 과 같은 규칙).
    관용구는 `[fn:이름]` 호출로도 쓰인다. 증거 = executed."""
    codes = ev.get("ibl_codes") or []
    run_pairs = set()
    for c in codes:
        run_pairs |= set(_PAIR_RE.findall(c))
    called = set()
    for c in codes:
        called |= set(_FN_RE.findall(c))
    used = []
    for it in join.get("items") or []:
        pairs = set(_PAIR_RE.findall(it.get("code") or ""))
        alias = it.get("alias") or ""
        if (pairs and pairs & run_pairs) or (alias and alias in called):
            used.append(it["id"])
    return {"used": used, "evidence": "executed", "ibl_calls": len(codes)}


def _used_names(ids, join, ev) -> Dict[str, Any]:
    """지식의 단서(세계 지도 두 채널) — 이름·별칭이 응답 본문이나 실행 코드에 나타났나. 증거 = mentioned.
    '언급'은 약한 증거다(모델이 이미 알던 이름일 수 있다) — 그래서 종류를 붙여 남기고 점수엔 쓰지 않는다."""
    from common.value_semantics import text_match
    hay = (ev.get("response") or "") + "\n" + "\n".join(ev.get("ibl_codes") or [])
    used = []
    for i, names in (join.get("names") or {}).items():
        if any(len(n) >= 2 and text_match("contains", hay, n) for n in names if isinstance(n, str)):
            used.append(i)
    return {"used": used, "evidence": "mentioned"}


def _used_deep(ids, join, ev) -> Dict[str, Any]:
    """사용자 사실 — ① 명시 조회: 이 턴의 `[self:memory]{op:"recall", node|expand}` 가 제시 항목의 가지·id 를 열었다(expanded).
    ② 확인: 턴 끝 증류가 그 항목을 SAME/UPDATE 로 다시 만나 used_at 을 올렸다(confirmed — 호출자가 전후 대조로 준다)."""
    paths = join.get("paths") or {}
    opened, expanded_ids = [], set()
    for c in ev.get("ibl_codes") or []:
        for m in _DEEP_RECALL_RE.finditer(c):
            args = dict(_QUOTED_RE.findall(m.group(1)))
            if args.get("op") != "recall" or args.get("store") == "실행":
                continue
            if args.get("node"):
                opened.append(args["node"].strip("/"))
            for x in re.findall(r"#(\d+)", args.get("expand") or ""):
                expanded_ids.add(x)
    used, evidence = [], []
    for i in ids:
        p = paths.get(i, "")
        if i in expanded_ids or any(p == o or p.startswith(o + "/") for o in opened if o):
            used.append(i); evidence.append("expanded")
        elif i in set(ev.get("deep_touched") or []):
            used.append(i); evidence.append("confirmed")
    return {"used": used, "evidence": "+".join(sorted(set(evidence))) or "none", "opened": opened[:5]}


USAGE: Dict[str, Callable] = {
    "hippocampus": _used_hippocampus,
    "recalled_memory": _used_deep,
    "method_map": _used_names,
    "world_memory": _used_names,
}


def deep_used_at(db_path: str, ids) -> Dict[str, Any]:
    """제시된 심층기억 id 의 used_at 스냅샷 — 턴 끝 증류 전후를 대조해 confirmed 를 가른다."""
    if not db_path or not ids:
        return {}
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            marks = ",".join("?" * len(ids))
            rows = conn.execute(f"SELECT id, used_at FROM memories WHERE id IN ({marks})", [int(i) for i in ids]).fetchall()
        finally:
            conn.close()
        return {str(i): u for i, u in rows}
    except Exception:
        return {}


def record_usage(presented, *, tool_calls=None, response: str = "", deep_touched=None) -> List[Dict[str, Any]]:
    """턴 끝 — 제시된 후보 중 무엇이 쓰였는지 기억별 해석기로 가르고 `recall.used` 사건 하나로 남긴다. 실패는 무시."""
    if not presented:
        return []
    ev = {"ibl_codes": _ibl_codes(tool_calls), "response": response or "", "deep_touched": list(deep_touched or [])}
    out = []
    for p in presented:
        fn = USAGE.get(p.get("source"))
        if fn is None or not p.get("ids"):
            continue
        try:
            r = fn(list(p["ids"]), p.get("join") or {}, ev)
        except Exception as e:  # noqa: BLE001
            r = {"used": [], "evidence": "error", "error": type(e).__name__}
        out.append({"source": p["source"], "presented": list(p["ids"])[:10], "used": list(r.get("used") or [])[:10],
                    "evidence": r.get("evidence", ""), **{k: v for k, v in r.items() if k not in ("used", "evidence")}})
    if out:
        try:
            from episode_logger import record_trajectory_event
            record_trajectory_event("recall.used", {"blocks": out})
        except Exception:
            pass
        print("[연상:사용] " + " · ".join(f"{o['source']} {len(o['used'])}/{len(o['presented'])}({o['evidence']})" for o in out))
    return out


# ─────────────────────────── 정책 표 ───────────────────────────
# 순서 = 주입 순서. 새 기억·새 채널은 여기 한 줄이다 — 파이프라인·통신·프리뷰·스위치는 이 표를 모른다.
# personal: 주인 것(주체 관문). needs: 요청의 불 필드(deep=심층기억 자동 주입 — 포식 표면은 False).

SOURCES = (
    Source("hippocampus", "execution_memory", 1, True, _hippocampus),
    Source("memory_map", "memory_map", 1, True, _memory_map, needs="deep"),
    Source("recalled_memory", "recalled_memory", 1, True, _recalled_memory, needs="deep"),
    Source("guide_map", "guide_map", 1, True, _guide_map),
    Source("forage_memory", "forage_memory", 1, True, None, auto=False),   # 어휘가 입구: [self:forage]{op:"recall"} 로만
    Source("connected_limbs", "connected_limbs", 1, True, _connected_limbs),
    Source("pending_repair", "repair_outcome", 1, True, _pending_repair),
    Source("decision_ledger", "decision_ledger", 1, True, _decision_ledger),
    Source("method_map", "method_map", 2, False, _method_map),
    Source("world_memory", "world_map", 2, False, _world_memory),
)

# 채널별 정책 — 어느 공급원이 자동으로 도는가. None = 전부. 종전 동작을 그대로 옮긴 값이며(2026-09-18 구조 통합 = 동작 불변),
# 바꾸는 일은 2단계(검색·정책 실험)의 몫이다.
#   agent_message: 에이전트 간 위임 경로 — 분류가 없어 글자 채널(method_map)이 빠져 있었다.
#   switch: 스위치 실행 — 해마만 받았다(심층·가이드·세계 없음).
CHANNELS: Dict[str, Optional[Dict[str, set]]] = {
    "pipeline": None,
    "preview": None,
    "sample": None,
    "agent_message": {"exclude": {"method_map"}},
    "switch": {"only": {"hippocampus"}},
}


def _enabled(channel: str, source: str) -> bool:
    policy = CHANNELS.get(channel)
    if channel not in CHANNELS:
        raise ValueError(f"associative_recall: 모르는 채널 {channel!r} — CHANNELS 에 정책을 적어라")
    if policy is None:
        return True
    if "only" in policy:
        return source in policy["only"]
    return source not in policy.get("exclude", set())
