"""파이프별 실행 상태와 실패·재개·스필의 소유자.

execute_pipeline 호출마다 별도의 상태를 가진다. 부모·자식·병렬 실행의 변수·실패·진행을
공유하지 않는다. 통화와 정직성의 판정 자체는 기존 공통 모듈이 소유한다.
"""
from dataclasses import dataclass, field
from typing import Any
import json
from ibl_traceback import build_tb, attach_input
from workflow_binding import _step_label


@dataclass
class PipelineState:
    steps: list
    context: dict | None
    prev_result: Any
    total: int = field(init=False)
    results: list = field(default_factory=list)
    step_results: dict = field(default_factory=dict)
    action_count: int = 0
    ticket: Any = None
    skip_until: int = -1
    failed: int = 0
    last_mode: str | None = None
    skipped: list = field(default_factory=list)
    halted: list = field(default_factory=list)
    branches_failed: list = field(default_factory=list)
    empty_notes: list = field(default_factory=list)
    list_in_text: list = field(default_factory=list)
    fallback_used: list = field(default_factory=list)
    branch_honesty: list = field(default_factory=list)
    criteria: list = field(default_factory=list)
    var_errors: dict = field(default_factory=dict)
    derived: int = 0

    def __post_init__(self):
        self.total = len(self.steps)

    def seed_results(self):
        """진행 티켓을 확보한 뒤 재개 슬롯을 채운다. 원형 문자열과 슬롯 번호를 보존한다."""
        if isinstance(self.context, dict) and isinstance(self.context.get("_preset_results"), dict):
            for key, value in self.context["_preset_results"].items():
                self.step_results[int(key)] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    def next_boundary(self, from_idx: int) -> int:
        for j in range(from_idx, self.total):
            if isinstance(self.steps[j], dict) and self.steps[j].get("_seq_boundary"):
                return j
        return -1

    def root_note(self, out: dict) -> None:
        """실패 봉투에 뿌리(죽은 할당 문장)·연쇄를 싣는다 — error 문장 자체에도(절단 생존)."""
        if not self.var_errors:
            return
        out["root_failures"] = [{"var": n, **v} for n, v in self.var_errors.items()]
        _roots = "; ".join(f"step {v['step']} ${n} 할당 실패: {v['error'][:200]}"
                           for n, v in self.var_errors.items())
        # 긴 연쇄·try/catch 오류의 뒤에 두면 모델용 미리보기에서 최초 실패가 잘린다.
        out["error"] = f"뿌리 {len(self.var_errors)}: {_roots} — {out.get('error') or ''}"
        if self.derived:
            out["error"] += f" (연쇄 {self.derived}개는 그 변수를 읽어 죽은 문장)"

    def live_vars(self) -> dict:
        """살아 있는 `$변수` 원형 — 성공한 할당 문장의 최종 step 결과(죽은 할당은 제외)."""
        live = {}
        for _i, _st in enumerate(self.steps):
            _nm = _st.get("_assign_name") if isinstance(_st, dict) else None
            if _nm and _nm != "return" and _i in self.step_results and _nm not in self.var_errors:
                live[_nm] = self.step_results[_i]
        return live

    def attach_live_vars(self, out: dict) -> None:
        """★턴 범위 변수(언어 개정 2026-09-06): 최상위 호출자(execute_ibl 표면)가 `_want_live_vars` 로 원할 때만
        산 변수 원형을 내부 키로 싣는다 — 중첩 파이프(fn·each·goal·workflow)의 봉투를 부풀리지 않는다.
        표면이 키를 떼어 턴 저장소(ibl_turn_vars)에 합치고, 같은 턴의 다음 호출이 `$이름` 으로 그대로 본다."""
        if isinstance(self.context, dict) and self.context.get("_want_live_vars"):
            out["_live_vars"] = self.live_vars()

    def resume_vars_note(self, out: dict) -> None:
        """★부분 성공 봉투 재사용(2026-09-06, ep2882): 문장 하나가 죽었을 때 살아 있는 `$변수` 를 버리지
        않는다 — 성공한 할당의 원형을 스필해 `resume_vars` 로 싣는다. 실행자는 죽은 문장만 고쳐
        그 문장(들)을 code 로 보내고 `resume: {vars_ref}` 를 실으면 산 변수가 재실행 없이 주입된다.
        옛 판은 39/39 step 이 살아 있어도 실행자가 전체를 다시 돌려 같은 검색·[table:ai] 를 두 번 지불했다.
        (같은 턴 안에서는 턴 범위 변수가 이 일을 암시적으로 한다 — 이 명시판은 턴을 넘는 24h 회수 자리.)"""
        live = self.live_vars()
        if not live:
            return
        try:
            from common.spill import spill_write
            ref = spill_write(json.dumps(live, ensure_ascii=False), tag="resume_vars")["ref"]
        except Exception:
            return
        _dead = sorted(self.var_errors)
        out["resume_vars"] = {
            "vars_ref": ref["path"], "vars": sorted(live), "failed_vars": _dead,
            "note": (f"산 변수 {', '.join('$' + n for n in sorted(live))} 은(는) 재실행하지 않아도 됩니다 — "
                     f"죽은 문장{'(' + ', '.join('$' + n for n in _dead) + ')' if _dead else ''}만 고쳐 그 문장(들)과 뒤 문장을 "
                     f"code 로 보내고 resume: {{vars_ref: \"{ref['path']}\"}} 를 실으세요(24h 유효). 전체 재실행 금지."),
        }

    def handle_failure(self, idx: int, abort_payload: dict, tb=None):
        """실패 처리. ①그 step 의 문장이 [on_error: skip|null] 이면 건너뛰고 계속(신고 동반),
        ②뒤에 독립 문장이 있으면 거기로 건너뛰고 계속(None 반환),
        ③없으면 중단 payload — 2단 이상 진행했으면 재개 지점(resume)을 스필해 싣는다(M5 §2.6)."""
        st = self.steps[idx] if isinstance(self.steps[idx], dict) else {}
        # ── 트레이스백 조립의 단일 지점 (docs/IBL_TRACEBACK_HANDOFF.md) ──
        # 호출부가 tb 를 안 만든 실패(앞으로 생길 새 실패 지점 포함)도 여기서 기본
        # 프레임을 얻는다 — 등록 목록이 아니라 통과 지점이 규약을 강제한다(B48-1).
        # 실패 프레임의 입력 통화(prev_result)도 여기 한 곳에서만 단다.
        if tb is None:
            _n, _a = _step_label(st)
            tb = build_tb(abort_payload.get("error"),
                          frame={"kind": "pipeline", "step": idx + 1, "of": self.total,
                                 "node": _n, "action": _a})
        attach_input(tb, self.prev_result)
        abort_payload["traceback"] = tb
        # 계속-실행 경로(문장 건너뛰기·on_error)에서도 실패 step 기록에 남긴다 —
        # 봉투 다이어트(summarize_step)는 result 외 키를 보존하므로 그대로 살아남는다.
        if self.results and isinstance(self.results[-1], dict) and self.results[-1].get("step") == idx + 1:
            self.results[-1].setdefault("traceback", tb)
        mode = st.get("_on_error")
        if mode in ("skip", "null"):
            self.last_mode = mode
            self.skipped.append(idx + 1)
            if self.results and isinstance(self.results[-1], dict) and self.results[-1].get("step") == idx + 1:
                self.results[-1]["skipped"] = mode
            return None
        self.last_mode = None
        # ★F24-1(24회차): 중단 payload 는 봉투 조립부를 거치지 않아 앞 step 에서 죽은 병렬
        # 분기가 통째로 사라졌다 — 괄호 분기가 죽으면 union 의 2차 증상("통화 종류가 다릅니다")
        # 만 보이고 진짜 원인(분기 사망)은 어디에도 없었다. 중단 경로에도 같이 싣는다.
        if self.branches_failed:
            abort_payload["branches_failed"] = list(self.branches_failed)
        b = self.next_boundary(idx + 1)
        if b < 0:
            # 죽은 마지막 문장이 `$이름 = …` 이면 그 슬롯을 비운다 — 오류 봉투가 산 변수로 둔갑해
            # 턴 변수·resume_vars 에 실리지 않게(중간 문장 실패 경로의 pop 과 한 벌, 2026-09-06).
            for _j in range(idx, len(self.steps)):
                _sj = self.steps[_j] if isinstance(self.steps[_j], dict) else {}
                if _sj.get("_assign_name"):
                    self.step_results.pop(_j, None)
                    break
            # 마지막 문장의 실패로 중단해도 앞 문장들의 독립 실패 수·뿌리는 봉투에 남는다
            # (종전엔 중단 payload 가 _seq 누산을 통째로 버려 "8개 실패" 사실이 사라졌다).
            if self.failed:
                abort_payload["statements_failed"] = self.failed + 1
            _fr0 = abort_payload.get("final_result")
            if isinstance(_fr0, str) and _fr0[:1] == "{":
                try:
                    _fr0 = json.loads(_fr0)
                except Exception:
                    _fr0 = None
            if isinstance(_fr0, dict) and _fr0.get("_derived_from"):
                self.derived += 1
            self.root_note(abort_payload)
            self.resume_vars_note(abort_payload)
            self.attach_live_vars(abort_payload)
            if idx >= 1 and self.prev_result and not st.get("_seq_boundary"):
                try:
                    from common.spill import spill_write
                    ref = spill_write(self.prev_result, tag=f"resume_step{idx + 1}")["ref"]
                    abort_payload["resume"] = {
                        "from_step": idx + 1, "prev_ref": ref,
                        "note": (f"step {idx + 1} 부터 다시 돌리려면 execute_ibl(code, resume={{from_step: {idx + 1}, "
                                 f"prev_ref: \"{ref['path']}\"}}) — 1~{idx} 단은 재실행하지 않습니다(스필 24h 유효)."),
                    }
                except Exception:
                    pass
            return abort_payload
        self.skip_until = b
        self.failed += 1
        # 실패한 문장이 `$이름 = …` 이면 원인을 이름에 남긴다(뒤 문장의 참조가 인용한다).
        for _j in range(idx, b):
            _sj = self.steps[_j] if isinstance(self.steps[_j], dict) else {}
            if _sj.get("_assign_name"):
                self.var_errors.setdefault(_sj["_assign_name"], {
                    "step": idx + 1, "error": str(abort_payload.get("error") or "")[:300]})
                # 죽은 할당의 슬롯은 비운다 — 오류 봉투가 값으로 남으면 뒤 참조가 그 봉투를
                # 다시 내어 "그 문장 자신의 실패"처럼 보이고 연쇄가 뿌리와 안 갈린다.
                self.step_results.pop(_j, None)
                break
        _fr = abort_payload.get("final_result")
        if isinstance(_fr, str) and _fr[:1] == "{":
            try:
                _fr = json.loads(_fr)
            except Exception:
                _fr = None
        if isinstance(_fr, dict) and _fr.get("_derived_from"):
            self.derived += 1          # 뿌리가 아니라 죽은 변수를 읽어서 죽은 문장
        return None

    def after_failure(self, prev: str) -> str:
        """실패 뒤 다음 step 에 넘길 통화 — skip=직전 통화 그대로, null=빈 items, 그 외=끊김."""
        m = self.last_mode
        if m == "skip":
            return prev
        if m == "null":
            return '{"items": []}'
        return ""

    def spill_if_large(self, prev: str, idx: int) -> str:
        """자동 스필(M5 §2.5-3): 이음매 통화가 임계를 넘으면 파일로 내리고 참조만 흘린다 — 신고 동반."""
        try:
            from common.spill import AUTO_SPILL_THRESHOLD, spill_write
            if idx < self.total - 1 and isinstance(prev, str) and len(prev) > AUTO_SPILL_THRESHOLD:
                env = spill_write(prev, tag=f"step{idx + 1}")
                if self.results and isinstance(self.results[-1], dict):
                    self.results[-1]["spilled"] = env["ref"]
                    self.results[-1]["note"] = (f"통화 {len(prev):,}자 > 임계 {AUTO_SPILL_THRESHOLD:,} — 스필 파일로 내리고 "
                                           "참조만 다음 step 에 넘겼습니다(변환자·each·$items·write 는 투명하게 읽음)")
                return json.dumps(env, ensure_ascii=False)
        except Exception:
            pass
        return prev

