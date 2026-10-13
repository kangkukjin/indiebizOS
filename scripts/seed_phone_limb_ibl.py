"""IndieBiz OS 손발(설치 때 등록한 폰)에 IBL 하달 용례를 해마와 재학습 코퍼스에 멱등 시딩 (2026-10-13).

설계: docs/INDIEBIZ_BODY_AS_LIMB_DESIGN_2026_10_13.md. 낱말 = [limbs:guestpc]{op:"ibl", limb, code}.
code 안의 문자열은 작은따옴표 — 바깥 큰따옴표와 안 부딪힌다(허브 /ibl/execute check 로 파싱 확인 2026-10-13).
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

SEEDS = [
    ("삼성1 폰을 진동시켜", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:phone]{op:\'vibrate\'}"}'),
    ("삼성1에게 라디오 틀라고 해", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:radio]{op:\'play\', station_id:\'kbs_1radio\'}"}'),
    ("삼성1에서 KBS 쿨FM 틀어", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:radio]{op:\'play\', station_id:\'kbs_coolfm\'}"}'),
    ("삼성1 라디오 꺼", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:radio]{op:\'stop\'}"}'),
    ("삼성1에서 지금 뭐 나오고 있어", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:radio]{op:\'status\'}"}'),
    ("삼성1 볼륨 30으로", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:radio]{op:\'volume\', volume:30}"}'),
    ("삼성1으로 30초 녹음해", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[sense:listen]{op:\'record\', duration_sec:30}", timeout:90}'),
    ("삼성1에서 3분 녹음 맡겨 놔", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[sense:listen]{op:\'record\', duration_sec:180}", background:true, timeout:300}'),
    ("삼성1 카메라로 사진 찍어", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[sense:see]{facing:\'back\'}"}'),
    ("삼성1 폰에 알림 띄워: 저녁 7시 회의", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:phone]{op:\'notify\', title:\'회의\', body:\'저녁 7시 회의\'}"}'),
    ("삼성1 폰이 지금 어디 있어", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[sense:here]{}"}'),
    ("삼성1에서 \"회의 시작합니다\" 라고 말하게 해", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:phone]{op:\'speak\', text:\'회의 시작합니다\'}"}'),
    ("등록된 폰 손발 목록 보여줘", '[self:limb]{op:"list"}'),
    ("삼성1 손발 등록 해제해", '[self:limb]{op:"remove", target:"삼성1"}'),
    ("Make the phone 삼성1 vibrate", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:phone]{op:\'vibrate\'}"}'),
    ("Play KBS radio on the phone named 삼성1", '[limbs:guestpc]{op:"ibl", limb:"삼성1", code:"[limbs:radio]{op:\'play\', station_id:\'kbs_1radio\'}"}'),
]


def main():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패"
    with sqlite3.connect(ROOT / "data/ibl_usage.db") as conn:
        have = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    rows = [{"intent": intent, "ibl_code": code,
             "nodes": "self" if code.startswith("[self:") else "limbs",
             "source": "manual_seed", "category": "single",
             "tags": "phone-limb,손발,원격폰,guestpc-ibl"} for intent, code in SEEDS if intent not in have]
    added = db.add_examples_batch(rows)
    assert added == len(rows), f"시드 일부가 거부되었습니다 ({added}/{len(rows)})"
    target = ROOT / "data/training/ibl_distilled.json"
    corpus = json.loads(target.read_text())
    known = {(r.get("intent"), r.get("ibl_code")) for r in corpus}
    for intent, code in SEEDS:
        if (intent, code) not in known:
            corpus.append({"intent": intent, "ibl_code": code, "source": "manual_seed"})
    target.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    with sqlite3.connect(ROOT / "data/ibl_usage.db") as conn:
        n_ex = conn.execute("SELECT count(*) FROM ibl_examples WHERE tags LIKE '%phone-limb%'").fetchone()[0]
        ids = [r[0] for r in conn.execute("SELECT id FROM ibl_examples WHERE tags LIKE '%phone-limb%'")]
        try:
            n_vec = conn.execute("SELECT count(*) FROM ibl_examples_vec WHERE rowid IN (%s)" % ",".join(map(str, ids)) or "0").fetchone()[0]
        except sqlite3.OperationalError:
            n_vec = "?"
    print(f"phone limb: {added} added · tagged={n_ex} · vectors={n_vec}")
    for query in ("삼성1에게 라디오 틀라고 해", "삼성1 폰으로 녹음 시켜"):
        hits = db.search_hybrid(query, top_k=2)
        print(query, "→", [(h.get("intent") if isinstance(h, dict) else h) for h in hits][:2])


if __name__ == "__main__":
    main()
