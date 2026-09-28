"""Builder seam for the edition 2 contract validator (runtime owns semantics)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_v2_adapters import validate_contract


def validate_v2_contracts(data):
    issues = []
    for name, node in (data.get("nodes") or {}).items():
        if not isinstance(node, dict):
            continue
        for action, entry in (node.get("actions") or {}).items():
            if not isinstance(entry, dict):
                continue
            if entry.get("pipe_in"):
                from ibl_v2_contracts import handler_contract
                contract = entry.get("callable_contract") or handler_contract(name, action, entry, set((entry.get("params") or {})))
                if not contract.get("pipe_input"):
                    issues.append(f"{name}:{action}: pipe_in 소비자에는 파이프 입력 계약이 필요합니다")
            # Multi-source consumers already declare their input topology. An
            # opaque JSON fallback cannot carry that topology into current IBL.
            flow = entry.get('flow') or {}
            if (flow.get('accepts') in {'items', 'prose', 'prose|items', 'items|prose'}
                    and entry.get('func') != 'table_each'):
                contract = entry.get('callable_contract') or {}
                receiver = contract.get('pipe_input')
                if not receiver or receiver not in contract.get('params', {}):
                    issues.append(f'{name}:{action}: 단항 flow에 callable_contract.pipe_input과 입력 인자 선언이 필요합니다')
                adapter = contract.get('adapter', {})
                if (adapter.get('protocol') == 'legacy-envelope'
                        and receiver not in adapter.get('input_envelopes', [])):
                    issues.append(f'{name}:{action}: 단항 봉투 입력의 근거를 adapter.input_envelopes에 연결하세요')
            if flow.get('accepts') in {'pair', 'same-kind'}:
                qualified = f'{name}:{action}'
                contract = entry.get('callable_contract') or {}
                bundle = flow.get('input_bundle_param')
                if not bundle or contract.get('pipe_input') != bundle:
                    issues.append(f'{qualified}: 결합 flow의 input_bundle_param을 callable_contract.pipe_input으로 연결하세요')
                params = entry.get('params') or {}
                for key in [bundle, *(flow.get('input_params') or [])]:
                    if not key:
                        continue
                    declared = params.get(key)
                    kinds = declared if isinstance(declared, list) else [declared]
                    if 'array' not in kinds or (key != bundle and 'object' not in kinds):
                        issues.append(f'{qualified}: 결합 입력 {key}에 컨테이너 타입(array/object)을 선언하세요')
                    if key not in contract.get('params', {}):
                        issues.append(f'{qualified}: 결합 입력 {key}가 callable_contract.params에 없습니다')
            if isinstance(entry, dict) and "callable_contract" in entry:
                try:
                    validate_contract(entry["callable_contract"])
                except (ValueError, KeyError, TypeError) as exc:
                    issues.append(f"{name}:{action} callable_contract: {exc}")
    return issues


def check_v2_corpus(code, entry, issues, origin, session=None):
    from ibl_edition import source_edition
    try:
        if source_edition(code, entry.get("edition")) != 2:
            return False
        from ibl_v2_learning import check_source
        kwargs = {}
        if session is not None:
            if not session:
                try:
                    from ibl_v2_adapters import load_registry
                    from ibl_v2_store import definitions
                    session.update(registry=load_registry(), library=definitions())
                except Exception as exc:
                    session['error'] = exc
            if 'error' in session:
                raise session['error']
            kwargs = session
        why = check_source(code, bool(entry.get("alias")) or entry.get("category") == "phrase", **kwargs)
        if why:
            issues.append(f"{origin}: 판본 2 용례 검사 — {why}")
    except Exception as exc:
        issues.append(f"{origin}: 판본 2 검사 불가 — {exc}")
    return True


def corpus_entries(root: Path, include_db: bool = False):
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
    import json
    from corpus_policy import review_exclusion_reason
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
                if isinstance(e, dict) and not review_exclusion_reason(e):
                    yield f.name, e
    if not include_db:
        return
    db = root / "data" / "ibl_usage.db"
    if not db.is_file():
        return
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        # alias·category 도 낸다 — 관용구 골격은 함수 몸으로 읽어야 한다(언어 개정 2026-09-07).
        columns = {r[1] for r in con.execute("PRAGMA table_info(ibl_examples)")}
        provenance = "provenance" if "provenance" in columns else "'{}'"
        rows = con.execute("SELECT intent, ibl_code, COALESCE(alias,''), COALESCE(category,''), "
                           + provenance + " FROM ibl_examples").fetchall()
        con.close()
    except Exception:
        return
    for intent, code, alias, category, provenance in rows:
        entry = {"intent": intent, "ibl_code": code, "alias": alias, "category": category,
                 "provenance": provenance}
        if not review_exclusion_reason(entry):
            yield "ibl_usage.db", entry
