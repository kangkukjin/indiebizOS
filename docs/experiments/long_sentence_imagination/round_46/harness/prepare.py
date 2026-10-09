"""46회차 합성 자료 — 여행 조건·계정·oracle. 포털 A(바다숙소)·B(산장숙소, 세션 만료 8요청) 는 site_server.py 가 가진 고정 자료.
사용: prepare.py → outputs/.../2026-10-09_46회차/{trainer,agent}/input(+input_flaky) + _site/{who}_{A,B} + _oracle"""
import json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_46회차'
PORTS = {"trainer": {"A": 8951, "B": 8961}, "agent": {"A": 8952, "B": 8962}, "trainer_flaky": {"A": 8953, "B": 8963}, "agent_flaky": {"A": 8954, "B": 8964}, "probe": {"A": 8959, "B": 8969}, "trainer_b": {"A": 8955, "B": 8965}}
ACCOUNT = {"user": "lsi46_traveler", "password": "<password>"}   # 훈련용 합성 계정(두 포털 공통)
TRIP = {"checkin": "2026-11-14", "nights": 2, "guests": 2, "budget_total": 260000, "criterion": "예산 안에서 총액이 가장 싼 객실(조식 무관)"}
TRIP_B = {**TRIP, "criterion": "조식 포함 객실 중 총액이 가장 싼 객실(예산 안)"}
def main():
    for sub in ("trainer", "agent", "_oracle", "_site"): shutil.rmtree(OUT / sub, ignore_errors=True)
    for who in ("trainer", "agent"):
        for variant, key in (("input", who), ("input_flaky", who + "_flaky"), ("input_b", who + "_b")):
            if variant == "input_b" and who == "agent": continue
            inp = OUT / who / variant; inp.mkdir(parents=True, exist_ok=True)
            (inp / 'portals.json').write_text(json.dumps([{"name": "가상 바다숙소", "url": f"http://127.0.0.1:{PORTS[key]['A']}/"}, {"name": "가상 산장숙소", "url": f"http://127.0.0.1:{PORTS[key]['B']}/"}], ensure_ascii=False, indent=1))
            (inp / 'account.json').write_text(json.dumps(ACCOUNT, ensure_ascii=False, indent=1))
            (inp / 'trip.json').write_text(json.dumps(TRIP_B if variant == "input_b" else TRIP, ensure_ascii=False, indent=1))
        for o in ("out", "out_flaky", "out_b"): (OUT / who / o).mkdir(parents=True, exist_ok=True)
    for key in PORTS:
        for site in ("A", "B"): (OUT / '_site' / f'{key}_{site}').mkdir(parents=True, exist_ok=True)
    exp = {"trip": TRIP, "rooms": {"A": {"A1": 190000, "A2": 250000, "A3": 420000}, "B": {"B1": 176000, "B2": 236000, "B3": "마감"}},
           "cheapest": {"site": "가상 산장숙소", "room": "B1", "total": 176000}, "breakfast_cheapest": {"site": "가상 산장숙소", "room": "B2", "total": 236000},
           "flaky": {"bumped_room": "B1", "hold_total": 198000, "compare_total": 176000}, "ports": PORTS, "account": ACCOUNT}
    (OUT / '_oracle').mkdir(exist_ok=True); (OUT / '_oracle' / 'expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1)); print(json.dumps(exp["cheapest"], ensure_ascii=False), json.dumps(exp["breakfast_cheapest"], ensure_ascii=False))
if __name__ == '__main__':
    main()
