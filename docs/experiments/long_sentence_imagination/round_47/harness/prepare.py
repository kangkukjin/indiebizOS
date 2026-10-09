"""47회차 합성 자료 — 콘솔 주소·계정·정리 방침·oracle. 주문 40건은 site_server.py 의 고정 자료.
사용: prepare.py → outputs/.../2026-10-09_47회차/{trainer,agent}/input(+input_flaky,+input_b) + _site + _oracle"""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_server
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_47회차'
PORTS = {"trainer": 8971, "agent": 8972, "trainer_flaky": 8973, "agent_flaky": 8974, "trainer_b": 8975, "probe": 8979}
ACCOUNT = {"user": "lsi47_staff", "password": "<password>"}   # 훈련용 합성 계정
POLICY = {"from": "지연", "to": "오늘 처리", "memo": "10/10 오전 우선 제작", "flag_min_qty": 10}
POLICY_B = {"from": "지연", "to": "제작 중", "memo": "재작업 배정", "flag_min_qty": 20}
LOCKED = "W-1017"
def main():
    for sub in ("trainer", "agent", "_oracle", "_site"): shutil.rmtree(OUT / sub, ignore_errors=True)
    for who in ("trainer", "agent"):
        for variant, key, pol in (("input", who, POLICY), ("input_flaky", who + "_flaky", POLICY), ("input_b", who + "_b", POLICY_B)):
            if key not in PORTS: continue
            inp = OUT / who / variant; inp.mkdir(parents=True, exist_ok=True)
            (inp / 'console.json').write_text(json.dumps({"name": "가상 공방 주문 콘솔", "url": f"http://127.0.0.1:{PORTS[key]}/", "cookie_name": f"lsi47_{key}"}, ensure_ascii=False, indent=1))
            (inp / 'account.json').write_text(json.dumps(ACCOUNT, ensure_ascii=False, indent=1))
            (inp / 'policy.json').write_text(json.dumps(pol, ensure_ascii=False, indent=1))
            (OUT / who / variant.replace('input', 'out')).mkdir(parents=True, exist_ok=True)
    (OUT / '_site').mkdir(exist_ok=True); (OUT / 'runs').mkdir(exist_ok=True)
    orders = site_server.seed(); cols = {c: sum(1 for o in orders if o["status"] == c) for c in site_server.COLS}
    exp = {"total": 40, "counts_before": cols, "late": site_server.LATE, "flag_ids": sorted(k for k, v in site_server.LATE.items() if v >= 10),
           "flag_ids_b": sorted(k for k, v in site_server.LATE.items() if v >= 20), "locked": LOCKED, "policy": POLICY, "policy_b": POLICY_B, "ports": PORTS, "console_warning": "재고 경고"}
    (OUT / '_oracle').mkdir(exist_ok=True); (OUT / '_oracle' / 'expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1)); print(json.dumps(exp, ensure_ascii=False))
if __name__ == '__main__':
    main()
