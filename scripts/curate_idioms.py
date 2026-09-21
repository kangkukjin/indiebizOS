#!/usr/bin/env python3
"""수동 선정집 검증·등록. 기본은 검사만, --apply 로 명시 반영한다.

선정집은 재현 가능한 등록 입력이자 호출 교재다. 실행 정본은 해마 원장/가지 문서이며
자동 동기화하지 않는다. 기존 본문 교체는 실행 이력이 없는 이름에만 허용한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import json
import sqlite3
from datetime import datetime

from register_idiom import _gates, refresh_idiom_metadata

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "data" / "idioms" / "curated.json"


def validate_catalog(catalog):
    from ibl_parser import parse, parse_function_body
    from workflow_contract import call_signature, pipe_input_param
    from ibl_typecheck import typecheck_code
    from ibl_usage_rag import _validate_ibl_actions
    from ibl_param_vocab import check_code_params
    entries = catalog["idioms"]
    names = [e["name"] for e in entries]
    active = {e['name'] for e in entries if e.get('always_on', True)}
    if len(names) != len(set(names)) or active & set(catalog.get("demote", {})):
        raise ValueError("중복 이름 또는 승격/강등 충돌")
    definitions = "\n".join(f"[def: {e['name']}]{{\n{e['body']}\n}}" for e in entries)
    infos = {}
    for e in entries:
        if not e.get("inputs") or not e.get("example"):
            raise ValueError(f"{e['name']}: 입력 계약과 조합 용례가 필요하다")
        info, why = _gates(e["name"], e["when"], e["body"])
        if why:
            raise ValueError(f"{e['name']}: {why}")
        # 대표 용례(example)와 생산자가 다른 용례(examples[].code)는 같은 관문을 지난다(2026-09-09).
        for sample in [e["example"]] + [x["code"] for x in e.get("examples", [])]:
            code = definitions + "\n" + sample
            if not _validate_ibl_actions(code) or check_code_params(code):
                raise ValueError(f"{e['name']}: 존재하지 않는 어휘 또는 인자 — {check_code_params(code)}")
            steps = parse(code)
            calls = []
            def walk(obj, has_prev=False):
                if isinstance(obj, dict):
                    if obj.get("_def"):
                        return
                    if obj.get("_node") == "fn":
                        calls.append((obj, has_prev))
                    for v in obj.values():
                        walk(v)
                elif isinstance(obj, list):
                    for i, v in enumerate(obj):
                        linked = (i > 0 and isinstance(v, dict) and not v.get('_seq_boundary')
                                  and isinstance(obj[i - 1], dict) and not obj[i - 1].get('_def'))
                        walk(v, linked)
            walk(steps)
            if not any(c.get("action") == e["name"] for c, _ in calls):
                raise ValueError(f"{e['name']}: 용례가 자신의 이름을 부르지 않는다")
            for call, has_prev in calls:
                target = next((x for x in entries if x["name"] == call["action"]), None)
                if target is None:
                    raise ValueError(f"선정집 밖 호출: {call['action']}")
                required = set(call_signature(target["body"]))
                supplied = {k for k in call.get("params", {}) if not k.startswith("_")}
                pipe = pipe_input_param(parse_function_body(target["body"])) if has_prev else None
                missing = required - supplied - ({pipe} if pipe else set())
                if missing or supplied - required:
                    raise ValueError(f"{e['name']}: {call['action']} 인자 {supplied} != {required}")
            tc = typecheck_code(code)
            errors = [i for i in tc.get("issues", []) if i.get("severity", i.get("level")) == "error"]
            if tc.get("syntax_error") or errors:
                raise ValueError(f"{e['name']}: 조합 용례 타입 오류 {tc.get('syntax_error') or errors}")
        infos[e["name"]] = info
    return infos


def apply_catalog(catalog, infos, local_encoder=False):
    from ibl_usage_db import IBLUsageDB
    from ibl_name_search import replace_example
    db = IBLUsageDB()
    if local_encoder:
        # 등록 원장은 그대로 쓰고 인코더만 이미 떠 있는 몸에서 빌린다.
        # 프로세스 안에서만 유효하며 /ibl/embed와 같은 벡터 공간이다.
        import urllib.request
        import numpy as np
        class RunningEncoder:
            def encode(self, texts, **kwargs):
                req = urllib.request.Request("http://127.0.0.1:8765/ibl/embed",
                      data=json.dumps({"texts": texts}).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as response:
                    return np.asarray(json.load(response)["vectors"], dtype="float32")
        encoder = RunningEncoder()
        encoder.encode(["관용구 등록 인코더 확인"])
        IBLUsageDB._model = encoder
    entries = catalog["idioms"]
    existing = {e["name"]: db.find_phrase_by_alias(e["name"]) for e in entries}
    for e in entries:
        old = existing[e["name"]]
        if old and old["ibl_code"].strip() != e["body"].strip() and (old["success_count"] or old["fail_count"]):
            raise ValueError(f"{e['name']}: 실행된 정의를 덮을 수 없다 — 별도 개정 필요")
    # 라이브 DB는 SQLite backup API로 일관된 스냅샷을 얻는다.
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_관용구선정")
    backup = ROOT / "data" / "_backups" / stamp
    backup.mkdir(parents=True)
    with sqlite3.connect(ROOT / "data" / "ibl_usage.db") as src:
        with sqlite3.connect(backup / "ibl_usage.db") as dst:
            src.backup(dst)
    for e in entries:
        old = existing[e["name"]]
        kw = dict(intent=e["when"], ibl_code=e["body"], topic=e["topic"], alias=e["name"],
                  returns=infos[e["name"]]["returns"])
        if old is None:
            rid = db.add_example(**kw, category="phrase", source="manual_registry", tags="manual,curated")
        elif old["ibl_code"].strip() != e["body"].strip():
            rid = replace_example(db, old["id"], **kw)
        else:
            rid = old["id"]
            if old["intent"] != e["when"]:
                db.update_intent(rid, e["when"])
        if not rid:
            raise RuntimeError(f"{e['name']}: 등록 거절 — 백업 {backup}")
        # 호출 용례는 add_examples_batch 단일 입구. 실제 조합 용례를 중복 없이 심는다.
        with db._get_connection() as con:
            seeded = con.execute("SELECT id FROM ibl_examples WHERE source='idiom_registry' AND ibl_code=?",
                                 (e["example"],)).fetchone()
        if not seeded:
            n = db.add_examples_batch([dict(intent=e["when"], ibl_code=e["example"], nodes="fn",
                                           category="phrase", source="idiom_registry", tags="manual,composed",
                                           topic=e["topic"])])
            if n != 1:
                raise RuntimeError(f"{e['name']}: 조합 용례 저장 실패")
        # 생산자가 다른 조합 용례(2026-09-09 지렛대 3): 낱말은 문장 안에 있는 모습을 본 적 있어야 불린다 —
        # 한 생산자(grep)만 보면 다른 생산자(JSON 읽기·filter 결과) 앞에서 안 부른다. 각 항목은 {intent, code}.
        for extra in e.get("examples", []):
            with db._get_connection() as con:
                dup = con.execute("SELECT id FROM ibl_examples WHERE source='idiom_registry' AND ibl_code=?",
                                  (extra["code"],)).fetchone()
            if dup:
                continue
            n = db.add_examples_batch([dict(intent=extra["intent"], ibl_code=extra["code"], nodes="fn",
                                           category="phrase", source="idiom_registry", tags="manual,composed",
                                           topic=e["topic"])])
            if n != 1:
                raise RuntimeError(f"{e['name']}: 조합 용례 저장 실패 — {extra['code'][:80]}")
            print(f"  용례 심음: {extra['code'][:80]}")
        with db._get_connection() as con:
            con.execute("UPDATE ibl_examples SET always_on=? WHERE id=?", (int(e.get('always_on', True)), rid))
            con.commit()
            seed_id = con.execute("SELECT id FROM ibl_examples WHERE source='idiom_registry' AND ibl_code=?",
                                  (e["example"],)).fetchone()[0]
        # 멱등 재적용에서도 벡터 신선도를 회복한다. 원장 저장과 색인 성공은 별개다.
        db._index_single(rid, f"{e['name']} {e['when']}", e["body"])
        db._index_single(seed_id, e["when"], e["example"])
        # 이전 등록기가 만든 값 없는 호출은 용례가 아니다. 실행 이력이 없는
        # 전용 출처의 placeholder만 회수한다(사용자 용례·실행 증거는 대상 아님).
        with db._get_connection() as con:
            obsolete = con.execute(
                "SELECT id,ibl_code FROM ibl_examples WHERE source='idiom_registry' "
                "AND success_count=0 AND fail_count=0").fetchall()
        ids = [r["id"] for r in obsolete if r["ibl_code"].startswith(f"[fn:{e['name']}]")
               and '"…"' in r["ibl_code"]]
        if ids:
            vec = db._get_vec_connection()
            if vec is not None:
                try:
                    vec.executemany("DELETE FROM ibl_examples_vec WHERE rowid=?", [(i,) for i in ids])
                    vec.commit()
                finally:
                    vec.close()
            with db._get_connection() as con:
                con.executemany("DELETE FROM ibl_examples WHERE id=?", [(i,) for i in ids])
                con.commit()
            print(f"  값 없는 옛 호출 용례 {len(ids)}건 회수")
        refresh_idiom_metadata(db, e["name"])
        print(f"등록 #{rid}: {e['name']} · 인자 {len(infos[e['name']]['signature'])}개")
    with db._get_connection() as con:
        for name, why in catalog.get("demote", {}).items():
            con.execute("UPDATE ibl_examples SET always_on=0 WHERE alias=?", (name,))
            print(f"상시 소개 제외: {name} — {why}")
        con.commit()
    print(f"반영 완료. 백업: {backup}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", type=Path, default=DEFAULT)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--local-encoder", action="store_true", help="실행 중인 로컬 백엔드의 /ibl/embed 사용")
    a = p.parse_args()
    catalog = json.loads(a.catalog.read_text(encoding="utf-8"))
    infos = validate_catalog(catalog)
    print(f"관용구 {len(infos)}개: 등록 계약·조합 용례 검증 통과")
    if a.apply:
        apply_catalog(catalog, infos, a.local_encoder)


if __name__ == "__main__":
    main()
