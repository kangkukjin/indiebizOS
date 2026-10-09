"""44회차 합성 자료 — 가상 도서관 대출 포털 자료(서버용 loans.json)·내 목록 CSV·계정·oracle.
사용: prepare.py → outputs/long_sentence_imagination/2026-10-09_44회차/{trainer,agent}/input + _site/{who}(서버 자료·상태, 입력 밖) + _oracle"""
import csv, json, datetime, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_44회차'
TODAY = datetime.date(2026, 10, 9)
PORTS = {"trainer": 8931, "agent": 8932, "trainer_flaky": 8933, "agent_flaky": 8934}

def d(n): return (TODAY + datetime.timedelta(days=n)).isoformat()
LOANS = [
  {"id": "L01", "title": "바느질의 기초", "author": "김수선", "due": d(0)},
  {"id": "L02", "title": "토요일의 수리교실", "author": "박고침", "due": d(1), "reserved": 1},
  {"id": "L03", "title": "옷장 정리의 기술", "author": "이정리", "due": d(2), "fail_flaky": True},
  {"id": "L04", "title": "단추, 구멍, 밑단", "author": "최단추", "due": d(3)},
  {"id": "L05", "title": "작은 가게 회계", "author": "정장부", "due": d(4)},
  {"id": "L06", "title": "동네 신문 만들기", "author": "한기사", "due": d(6)},
  {"id": "L07", "title": "느린 여행", "author": "오느림", "due": d(8), "reserved": 2},
  {"id": "L08", "title": "집에서 하는 수선 100", "author": "백수선", "due": d(10)},
  {"id": "L09", "title": "재봉틀 입문", "author": "서재봉", "due": d(12), "extended": True, "ext_count": 1},
  {"id": "L10", "title": "환경과 옷", "author": "지구름", "due": d(14)},
  {"id": "L11", "title": "마을회관 운영기", "author": "구마을", "due": d(16)},
  {"id": "L12", "title": "손으로 쓰는 편지", "author": "편지은", "due": d(19)},
]
ACCOUNT = {"user": "lsi44_reader", "password": "lsi44-pass-9x"}   # 훈련용 합성 계정 — 실제 서비스 아님

def my_books():
    rows = []
    for l in LOANS:
        if l["id"] == "L08": continue                        # 포털에만 있음
        due = l["due"]
        if l["id"] == "L05": due = d(5)                      # 반납일 불일치 (내 목록 10-14 vs 포털 10-13)
        if l["id"] == "L11": due = d(15)                     # 반납일 불일치
        rows.append({"id": l["id"], "title": l["title"], "due": due})
    rows.append({"id": "L99", "title": "내 목록에만 있는 책", "due": d(9)})   # 내 목록에만
    return rows

def main():
    if OUT.exists():
        for sub in ("trainer", "agent", "_oracle", "_site"): shutil.rmtree(OUT / sub, ignore_errors=True)
    for who in ("trainer", "agent"):
        inp = OUT / who / 'input'; site = OUT / '_site' / who; (OUT / who / 'out').mkdir(parents=True, exist_ok=True)
        inp.mkdir(parents=True, exist_ok=True); site.mkdir(parents=True, exist_ok=True)
        (site / 'loans.json').write_text(json.dumps({"account": ACCOUNT, "loans": LOANS}, ensure_ascii=False, indent=1))
        (inp / 'account.json').write_text(json.dumps({"portal_url": f"http://127.0.0.1:{PORTS[who]}/", **ACCOUNT}, ensure_ascii=False, indent=1))
        with open(inp / 'my_books.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=["id", "title", "due"]); w.writeheader(); w.writerows(my_books())
    o = OUT / '_oracle'; o.mkdir(parents=True, exist_ok=True)
    urgent = [l["id"] for l in LOANS if (datetime.date.fromisoformat(l["due"]) - TODAY).days <= 3]
    exp = {
      "today": TODAY.isoformat(), "portal_count": len(LOANS), "pages": 3,
      "portal_only": ["L08"], "mine_only": ["L99"],
      "due_mismatch": [{"id": "L05", "portal": d(4), "mine": d(5)}, {"id": "L11", "portal": d(16), "mine": d(15)}],
      "urgent": urgent, "extend_ok": ["L01", "L03", "L04"], "extend_skip": [{"id": "L02", "reason": "예약 대기"}],
      "new_due": {"L01": d(14), "L03": d(16), "L04": d(17)},
      "notice": "휴관일 안내: 10월 13일(월)은 정기 휴관일이며, 10월 24일(금)은 장서 점검으로 오후 1시부터 문을 닫습니다.",
      "flaky": {"extend_ok": ["L01", "L04"], "extend_fail": [{"id": "L03", "reason": "연장 횟수 초과"}], "page2_first_503": True},
      "ports": PORTS,
    }
    (o / 'expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1))
    print(json.dumps(exp, ensure_ascii=False)[:600])

if __name__ == '__main__':
    main()
