"""48회차 합성 자료 — 콘솔 주소·개편 방침·oracle. 상품 24종은 site_server.py 의 고정 자료.
사용: prepare.py → outputs/.../2026-10-10_48회차/{trainer,agent}/input(+input_flaky,+input_b) + _site + _oracle"""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_server
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-10_48회차'
PORTS = {"trainer": 8981, "trainer_flaky": 8983, "agent_flaky": 8984, "trainer_b": 8985, "probe": 8989}
POLICY = {"edits": [{"name": "호두 도마", "price": 42000, "desc": "가을 한정 — 10/17까지 무료 각인"}, {"name": "유리 화병 대", "price": 28000, "desc": "재입고 기념 특가"}],
          "display_top": ["유리 화병 대", "밀랍 초 2P", "호두 도마"]}
POLICY_B = {"edits": [{"name": "도자 머그 청", "price": 22000, "desc": "신규 유약 — 소량 입고"}, {"name": "옻칠 젓가락", "price": 20000, "desc": "선물 포장 무료"}, {"name": "편백 도마", "price": 49000, "desc": "주말 한정가"}],
            "display_top": ["옻칠 젓가락", "도자 머그 백", "편백 도마", "황동 촛대"]}
FAIL_ONCE = "P-05"   # 유리 화병 대


def expect(pol):
    ps = site_server.seed(); by = {p["name"]: p["id"] for p in ps.values()}
    top = [by[n] for n in pol["display_top"]]
    return {"edit_ids": {e["name"]: by[e["name"]] for e in pol["edits"]}, "order": top + [i for i in site_server.DISPLAY0 if i not in top]}


def main():
    for sub in ("trainer", "agent", "_oracle", "_site"): shutil.rmtree(OUT / sub, ignore_errors=True)
    for who in ("trainer", "agent"):
        for variant, key, pol in (("input", who, POLICY), ("input_flaky", who + "_flaky", POLICY), ("input_b", who + "_b", POLICY_B)):
            if key not in PORTS: continue
            inp = OUT / who / variant; inp.mkdir(parents=True, exist_ok=True)
            (inp / 'console.json').write_text(json.dumps({"name": "가상 상점 관리 콘솔", "url": f"http://127.0.0.1:{PORTS[key]}/"}, ensure_ascii=False, indent=1))
            (inp / 'policy.json').write_text(json.dumps(pol, ensure_ascii=False, indent=1))
            (OUT / who / variant.replace('input', 'out')).mkdir(parents=True, exist_ok=True)
    (OUT / '_site').mkdir(exist_ok=True); (OUT / 'runs').mkdir(exist_ok=True); (OUT / '_oracle').mkdir(exist_ok=True)
    exp = {"policy": POLICY, "policy_b": POLICY_B, "base": expect(POLICY), "b": expect(POLICY_B), "fail_once": FAIL_ONCE, "display0": site_server.DISPLAY0, "ports": PORTS}
    (OUT / '_oracle' / 'expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1)); print(json.dumps(exp, ensure_ascii=False))


if __name__ == '__main__':
    main()
