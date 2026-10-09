"""45회차 합성 자료 — 체육센터 포털 자료(서버용 data.json)·신청자 2명·증명서 PNG·접수 코드·oracle.
사용: prepare.py → outputs/long_sentence_imagination/2026-10-09_45회차/{trainer,agent}/input(+input_flaky) + _site/{who} + _oracle"""
import json, hashlib, random, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_45회차'
PORTS = {"trainer": 8941, "agent": 8942, "trainer_flaky": 8943, "agent_flaky": 8944, "probe": 8949, "probe_flaky": 8948}
random.seed(45)
ACCOUNT = {"user": "lsi45_family", "password": "lsi45-pass-7q"}   # 훈련용 합성 계정
REGIONS = {"서울": [{"id": "S1", "name": "가상 마포체육센터"}, {"id": "S2", "name": "가상 성북체육센터"}],
           "경기": [{"id": "G1", "name": "가상 고양체육센터"}, {"id": "G2", "name": "가상 수원체육센터"}],
           "인천": [{"id": "I1", "name": "가상 부평체육센터"}]}
CENTER_NAME = {c["id"]: c["name"] for cs in REGIONS.values() for c in cs}
KINDS = ["수영 초급", "수영 중급", "요가", "필라테스", "탁구", "배드민턴", "헬스 PT", "줌바", "어린이 농구", "실버 체조"]
DAYS = ["월수금 06:00", "월수금 19:00", "화목 10:00", "화목 20:00", "토 09:00", "토 14:00", "일 10:00", "일 16:00"]

def courses():
    out = []; n = 0
    for cid in CENTER_NAME:
        for k in range(8):
            n += 1; kind = KINDS[(k + n) % len(KINDS)]
            out.append({"id": f"C{n:02d}", "name": f"{kind} {chr(65 + k)}반", "center": cid, "center_name": CENTER_NAME[cid],
                        "schedule": DAYS[(k * 3 + n) % len(DAYS)], "fee": random.choice([45000, 60000, 72000, 90000, 120000]), "capacity": random.choice([3, 5, 8])})
    return out
COURSES = courses()   # 5센터×8 = 40강좌 → 목록 페이지 요소 150+

APPLICANTS = [
  {"name": "강가상", "birth": "1988-03-14", "region": "서울", "center": "가상 마포체육센터", "course": "C03", "cert": "cert_강가상.png"},
  {"name": "이합성", "birth": "2014-11-02", "region": "경기", "center": "가상 수원체육센터", "course": "C28", "cert": "cert_이합성.png"},
]
CODES = {"강가상": "MP-4471", "이합성": "SW-9025"}

def make_png(path: Path, text: str):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (480, 320), (244, 239, 230)); d = ImageDraw.Draw(im)
    d.rectangle([10, 10, 469, 309], outline=(47, 93, 58), width=4); d.text((30, 40), "GASANG CERTIFICATE", fill=(47, 93, 58)); d.text((30, 80), text, fill=(0, 0, 0))
    im.save(path)

def main():
    for sub in ("trainer", "agent", "_oracle", "_site"): shutil.rmtree(OUT / sub, ignore_errors=True)
    for c in COURSES:
        if c["id"] == "C28": c["flaky_full"] = True   # 변형: 목록 읽은 뒤 마감
    data = {"account": ACCOUNT, "regions": REGIONS, "courses": COURSES, "codes": CODES}
    shas = {}
    for who in ("trainer", "agent"):
        for variant in ("input", "input_flaky"):
            inp = OUT / who / variant; inp.mkdir(parents=True, exist_ok=True)
            port = PORTS[who if variant == "input" else who + "_flaky"]
            (inp / 'account.json').write_text(json.dumps({"portal_url": f"http://127.0.0.1:{port}/", **ACCOUNT}, ensure_ascii=False, indent=1))
            (inp / 'applicants.json').write_text(json.dumps(APPLICANTS, ensure_ascii=False, indent=1))
            (inp / 'codes.json').write_text(json.dumps(CODES, ensure_ascii=False, indent=1))
            for a in APPLICANTS:
                p = inp / a["cert"]; make_png(p, f"{a['name']} {a['birth']} / {a['course']}"); shas[a["cert"]] = hashlib.sha256(p.read_bytes()).hexdigest()
        (OUT / who / 'out').mkdir(parents=True, exist_ok=True); (OUT / who / 'out_flaky').mkdir(parents=True, exist_ok=True)
    for who in PORTS:
        d = OUT / '_site' / who; d.mkdir(parents=True, exist_ok=True); (d / 'data.json').write_text(json.dumps(data, ensure_ascii=False, indent=1))
    by = {c["id"]: c for c in COURSES}
    exp = {"applicants": [{"name": a["name"], "course": a["course"], "course_name": by[a["course"]]["name"], "center_name": by[a["course"]]["center_name"],
                           "fee": by[a["course"]]["fee"], "cert_sha256": shas[a["cert"]], "code": CODES[a["name"]]} for a in APPLICANTS],
           "fee_total": sum(by[a["course"]]["fee"] for a in APPLICANTS), "courses_total": len(COURSES),
           "flaky": {"success": ["강가상"], "rejected": [{"name": "이합성", "reason_contains": "정원 마감"}], "code_temp_error_once": True, "fee_total_success": by["C03"]["fee"]},
           "ports": PORTS}
    o = OUT / '_oracle'; o.mkdir(parents=True, exist_ok=True); (o / 'expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1))
    print(json.dumps({k: exp[k] for k in ('applicants', 'fee_total', 'courses_total', 'flaky')}, ensure_ascii=False)[:900])

if __name__ == '__main__':
    main()
