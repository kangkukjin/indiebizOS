import json, os, sys, csv, re
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict

args = json.load(sys.stdin)
BASE = Path(args["base"])
IN = BASE / "input"
OUT = BASE / "out"
SRC = OUT / "_sources"
(OUT / "cases").mkdir(parents=True, exist_ok=True)

job = json.loads((IN / "job.json").read_text(encoding="utf-8"))
CONSULT = date.fromisoformat(job["consult_date"])
TH = job["thresholds"]
R_START = CONSULT - timedelta(days=7)   # 최근 7일 = 상담일 전 7일(상담일 제외)
WD = "월화수목금토일"
INTAKE = date(2026, 10, 12)


def ds(d):
    return f"{d.isoformat()}({WD[d.weekday()]})"


def r1(x):
    return None if x is None else round(x, 1)


# ---------------- 측정 ----------------
NUM = re.compile(r"^-?\d+(\.\d+)?$")
UNIT_OK = {"혈압": {"mmHg"}, "혈당": {"mg/dL", "mmol/L"}, "체온": {"℃", "℉"}}


def parse(kind, value, unit):
    v = (value or "").strip()
    u = (unit or "").strip()
    if kind not in UNIT_OK:
        return None, f"알 수 없는 종류 {kind}"
    if u not in UNIT_OK[kind]:
        return None, f"알 수 없는 단위 '{u}'"
    if kind == "혈압":
        m = re.fullmatch(r"(\d{2,3})\s*/\s*(\d{2,3})", v)
        if not m:
            return None, f"숫자 아님 '{v}'"
        return (int(m[1]), int(m[2])), None
    if not NUM.match(v):
        return None, f"숫자 아님 '{v}'"
    x = float(v)
    if kind == "혈당":
        x = x * 18 if u == "mmol/L" else x
    else:
        x = (x - 32) * 5 / 9 if u == "℉" else x
    return round(x, 6), None


def over(kind, val, strict):
    if kind == "혈압":
        s, d = val
        ts, td = TH["혈압"]["sys"], TH["혈압"]["dia"]
        return (s > ts or d > td) if strict else (s >= ts or d >= td)
    t = TH[kind]
    return val > t if strict else val >= t


raw = list(csv.DictReader(open(IN / "measurements.csv", encoding="utf-8-sig", newline="")))
meas = defaultdict(lambda: defaultdict(lambda: {"valid": [], "invalid": []}))
suspect, after_consult = [], []
for i, r in enumerate(raw, start=2):
    cid, kind = r["case_id"].strip(), r["kind"].strip()
    d = date.fromisoformat(r["measured_at"].strip()[:10])
    val, err = parse(kind, r["value"], r["unit"])
    slot = meas[cid][kind]
    if err:
        slot["invalid"].append({"line": i, "date": d.isoformat(), "value": r["value"], "unit": r["unit"], "reason": err})
        continue
    if d >= CONSULT:
        after_consult.append({"case": cid, "line": i, "date": d.isoformat()})
    if kind == "혈당" and not (30 <= val <= 600):
        suspect.append({"case": cid, "line": i, "value": r["value"], "unit": r["unit"]})
    if kind == "체온" and not (33 <= val <= 43):
        suspect.append({"case": cid, "line": i, "value": r["value"], "unit": r["unit"]})
    slot["valid"].append({"line": i, "date": d, "at": r["measured_at"].strip(), "val": val})


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def stats_for(cid):
    out, detail = {}, {}
    for kind, slot in sorted(meas[cid].items()):
        v = [x for x in slot["valid"] if x["date"] < CONSULT]
        rec = [x for x in v if x["date"] >= R_START]
        pri = [x for x in v if x["date"] < R_START]
        od_s = sorted({x["date"] for x in v if over(kind, x["val"], True)})
        od_i = sorted({x["date"] for x in v if over(kind, x["val"], False)})
        st = {"n": len(v), "invalid": len(slot["invalid"])}
        if kind == "혈압":
            st["mean_sys"] = r1(mean([x["val"][0] for x in v]))
            st["mean_dia"] = r1(mean([x["val"][1] for x in v]))
            st["recent7"] = r1(mean([x["val"][0] for x in rec]))
            st["prior"] = r1(mean([x["val"][0] for x in pri]))
            st["recent7_dia"] = r1(mean([x["val"][1] for x in rec]))
            st["prior_dia"] = r1(mean([x["val"][1] for x in pri]))
        else:
            st["mean"] = r1(mean([x["val"] for x in v]))
            st["recent7"] = r1(mean([x["val"] for x in rec]))
            st["prior"] = r1(mean([x["val"] for x in pri]))
        st["over_days"] = len(od_s)
        st["n_recent7"] = len(rec)
        st["n_prior"] = len(pri)
        st["over_days_inclusive"] = len(od_i)
        out[kind] = st
        mx = max(v, key=lambda x: x["val"]) if v else None
        detail[kind] = {"over_dates": [x.isoformat() for x in od_s], "over_dates_inclusive": [x.isoformat() for x in od_i],
                        "invalid": slot["invalid"], "first": min(x["date"] for x in v).isoformat() if v else None,
                        "last": max(x["date"] for x in v).isoformat() if v else None, "max": mx}
    return out, detail


# ---------------- 약 (e약은요) ----------------
search = {x["name"]: x for x in json.loads((SRC / "drug_search.json").read_text(encoding="utf-8"))}


def drug_info(name):
    s = search.get(name)
    info = {"found": False, "item_seq": None, "ingredients": [], "product": None, "search_url": s["search_url"] if s else None,
            "detail_url": None, "caution": [], "caution_heading": None, "note": None}
    if not s:
        info["note"] = "조회 기록 없음"
        return info
    total = next((t["text"] for t in s["rows"] if t["text"].startswith("총 ")), "")
    prod = next((t["text"][4:] for t in s["rows"] if t["text"].startswith("제품명 ")), None)
    ing = next((t["text"][3:] for t in s["rows"] if t["text"].startswith("주성분") and len(t["text"]) > 3), None)
    link = next((l for l in s["links"] if prod and l["text"] == prod), None)
    if not (prod and ing and link and prod.startswith(name)):
        info["note"] = f"e약은요 검색 결과 '{total or '결과 없음'}' — 해당 제품을 찾지 못함"
        return info
    seq = re.search(r"itemSeq=(\d+)", link["url"])[1]
    det = json.loads((SRC / f"drug_{seq}.json").read_text(encoding="utf-8"))
    info.update(found=True, item_seq=seq, product=prod, ingredients=[x.strip() for x in ing.split(",") if x.strip()],
                detail_url=det["url"], caution_heading=det.get("heading"),
                caution=[p["text"] for p in det.get("section", [])])
    if det.get("heading") and not info["caution"]:
        info["note"] = "e약은요에 이 질문 제목만 있고 답 본문이 비어 있음(원문 그대로)"
    return info


# ---------------- 포털 ----------------
def portal_quote(sn, idxs):
    p = json.loads((SRC / f"portal_{sn}.json").read_text(encoding="utf-8"))
    by = {x["paragraph_index"]: x["text"] for x in p["paragraphs"]}
    missing = [i for i in idxs if i not in by]
    assert not missing, (sn, missing)
    return {"title": p["title"].split(" | ")[0], "url": p["url"], "quote": [by[i] for i in idxs], "paragraphs": idxs}


PURL = "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn="
pub = {x["id"]: x for x in json.loads((SRC / "pubmed.json").read_text(encoding="utf-8"))}

# ---------------- 접수지에서 읽은 건별 내용 ----------------
T = INTAKE
CASES = {
 "H01": dict(person="가명 김가온(41세)", symptom="발열·인후통", urgent=False,
   timeline=[(T - timedelta(4), "'나흘 전부터'", "열이 오르내리고 목이 아프기 시작함"),
             (date(2026, 10, 8), "'10월 8일부터'", "타이레놀정500밀리그람 복용 시작(1회 2정 하루 3번, 약국 구입)"),
             (date(2026, 10, 9), "'10월 9일부터'", "타이레놀콜드-에스정 복용 시작(1회 2정 하루 3번, 약국 구입)"),
             (T, "접수일", "기침은 심하지 않고 밥은 먹는다. 체온계 2개 중 하나는 화씨로 찍힌다")],
   drugs=[("타이레놀정500밀리그람", "본인", "current", "1회 2정 하루 3번"), ("타이레놀콜드-에스정", "본인", "current", "1회 2정 하루 3번")],
   portal=("5423", [89]), portal_tried=["5726", "5232", "5285"],
   portal_note="감기 페이지의 합병증 대목이다. 인후통·발열에 대해 '바로 병원' 문구를 따로 둔 대목은 인두편도염(5726)·인플루엔자(5232)·불명열(5285) 본문에서 찾지 못했다.",
   tell=["열이 시작된 날(10월 8일경)과 측정한 체온 기록(화씨로 잰 값 포함)", "두 약을 언제부터 하루 몇 번·몇 정씩 먹었는지(접수지 기준 각각 1회 2정 하루 3번)", "기침·식사 상태"],
   ask=["지금 먹는 두 약에 같은 성분(아세트아미노펜)이 들어 있는데, 함께 먹어도 되는지", "열이 며칠 더 이어지면 다시 진료를 받아야 하는지"],
   bring=["타이레놀정500밀리그람·타이레놀콜드-에스정 상자 또는 포장", "체온 기록(두 체온계 값 모두)"]),
 "H02": dict(person="가명 박나래(63세)", symptom="아침 혈압 상승 걱정(고혈압 복약 중)", urgent=False,
   timeline=[(None, "'3년 전부터'·'2023년부터'", "혈압약(노바스크정5밀리그램 하루 1정, 병원 처방) 복용 시작 — 접수일 기준 약 2023년"),
             (None, "'요즘'", "아침 혈압이 예전보다 높게 나오는 것 같다(시작 날짜 미기재)"),
             (T, "접수일", "두통은 없다. 아침·저녁으로 재서 적어 두었다")],
   drugs=[("노바스크정5밀리그램", "본인", "current", "하루 1정")],
   portal=("6765", [46]), portal_tried=[],
   tell=["아침·저녁 혈압 기록(아침이 높게 나온다고 느끼는 점)", "노바스크정5밀리그램을 2023년부터 하루 1정 먹고 있음", "두통 없음"],
   ask=["아침 혈압이 높게 나오는 것이 지금 약으로 충분한지 확인이 필요한지", "집에서 재는 시간·방법이 맞는지"],
   bring=["혈압 기록지", "혈압계(가능하면)", "노바스크정 처방전 또는 약 봉투"]),
 "H03": dict(person="가명 이다솜(55세)", symptom="공복혈당 상승(건강검진 지적)", urgent=False,
   timeline=[(None, "'건강검진에서'", "공복혈당이 높다는 말을 들음(검진 날짜 미기재)"),
             (None, "'8월 말부터'", "아침마다 혈당 측정(측정 기록의 첫 유효 날짜는 아래 측정 요약 참조). 해외 측정기는 mmol/L로 나온다"),
             (date(2026, 9, 15), "'9월 15일부터'", "환절기 비염으로 지르텍정 하루 1정 복용 시작"),
             (T, "접수일", "체중 변화 없음")],
   drugs=[("지르텍정", "본인", "current", "하루 1정")],
   portal=("5304", [19, 20, 21, 22, 23]), portal_tried=["5305"],
   tell=["건강검진에서 공복혈당이 높다고 들은 사실(가능하면 검진 결과지)", "8월 말부터 아침 공복 측정 기록 — 두 측정기(mg/dL, mmol/L)를 썼음", "지르텍정 복용 중"],
   ask=["집에서 잰 값과 병원 검사가 어떻게 다른지, 정확한 검사가 필요한지", "두 측정기 값을 어떻게 비교해야 하는지"],
   bring=["건강검진 결과지", "혈당 기록", "두 혈당측정기", "지르텍정 포장"]),
 "H04": dict(person="가명 최라온(58세)", symptom="흉부 압박감·식은땀·왼팔 저림(운동 중), 어깨·허리 통증", urgent=True,
   urgent_reason="어제저녁(2026-10-11) 계단을 오르다 가슴이 꽉 조이듯 답답하고 식은땀이 났고 왼팔이 저렸다 — 10분쯤 쉬니 나아짐(접수지 원문 요지)",
   timeline=[(T - timedelta(14), "'2주째'", "이삿짐을 나른 뒤 어깨·허리가 쑤시기 시작(약 2주 전, 정확한 날짜 미기재). 파스도 붙인다"),
             (date(2026, 10, 1), "'10월 1일부터'", "이지엔6애니연질캡슐 복용 시작(1회 1캡슐 하루 3번)"),
             (date(2026, 10, 5), "'10월 5일부터'", "탁센연질캡슐 복용 시작(1회 1캡슐 하루 2번)"),
             (T - timedelta(1), "'어제저녁'", "계단을 오르다 가슴이 꽉 조이듯 답답하고 식은땀, 왼팔 저림. 10분쯤 쉬니 나아져서 그냥 잠. 본인은 근육통 때문이라고 생각함"),
             (T, "접수일", "혈압은 가끔 잰다")],
   drugs=[("이지엔6애니연질캡슐", "본인", "current", "1회 1캡슐 하루 3번"), ("탁센연질캡슐", "본인", "current", "1회 1캡슐 하루 2번")],
   portal=("5337", [31, 32]), portal_tried=[],
   tell=["10월 11일 저녁 계단에서 생긴 가슴 조임·식은땀·왼팔 저림과 지속 시간(약 10분), 쉬고 나아진 것", "이삿짐 뒤 어깨·허리 통증, 두 진통제를 함께 먹고 있음", "혈압 기록"],
   ask=["이 증상으로 상담일까지 기다려도 되는지, 지금 바로 진료가 필요한지", "이지엔6애니와 탁센을 함께 먹어도 되는지"],
   bring=["이지엔6애니연질캡슐·탁센연질캡슐 포장", "혈압 기록", "파스 이름"]),
 "H05": dict(person="가명 정마루(34세)", symptom="콧물·기침", urgent=False,
   timeline=[(T - timedelta(7), "'일주일째'", "콧물과 기침 시작(약 일주일 전). 열은 심하지 않다"),
             (date(2026, 10, 6), "'10월 6일부터'", "하늘맑음정 복용 시작(하루 2번 1정씩, 지인이 준 약)"),
             (date(2026, 10, 7), "'10월 7일부터'", "판콜에스내복액 복용 시작(1회 1병 하루 3번)"),
             (T, "접수일", "잠은 잘 잔다")],
   drugs=[("하늘맑음정", "본인", "current", "하루 2번 1정씩"), ("판콜에스내복액", "본인", "current", "1회 1병 하루 3번")],
   portal=("5423", [89]), portal_tried=["6253"],
   portal_note="감기 페이지의 합병증 대목이다. 기침(성인, 6253) 본문에서는 '바로 병원' 문구를 찾지 못했다.",
   tell=["콧물·기침이 시작된 시기(약 일주일 전)와 열 상태", "지인에게 받은 하늘맑음정을 먹고 있음(성분 미확인)", "판콜에스내복액 복용"],
   ask=["하늘맑음정의 성분이 무엇인지, 판콜에스내복액과 같은 성분이 겹치는지", "기침이 얼마나 더 이어지면 다시 진료를 받아야 하는지"],
   bring=["하늘맑음정 실물·포장(지인에게 받은 것)", "판콜에스내복액 병", "체온 기록"]),
 "H06": dict(person="가명 한바다(47세)", symptom="잦은 두통(한 달 이상)", urgent=False,
   timeline=[(T - timedelta(30), "'한 달 넘게'", "두통이 잦아짐(접수일 기준 한 달 넘게 전부터, 정확한 날짜 미기재). 오후에 심해진다"),
             (date(2026, 9, 30), "'9월 30일에 끊었고'", "게보린정(1회 1정씩) 복용 중단"),
             (date(2026, 10, 1), "'10월 1일부터'", "타이레놀정500밀리그람을 아플 때 1회 1정 복용 시작"),
             (T, "접수일", "커피를 하루 넉 잔 마신다")],
   drugs=[("게보린정", "본인", "stopped", "1회 1정"), ("타이레놀정500밀리그람", "본인", "current", "아플 때 1회 1정")],
   portal=("5830", [17, 18, 19, 20, 21, 22, 23, 24, 25, 51]), portal_tried=[],
   tell=["두통이 시작된 시기·하루 중 심해지는 때(오후)·빈도", "게보린정을 9월 30일에 끊고 10월 1일부터 타이레놀을 아플 때 먹는 것, 한 달에 며칠 먹었는지", "커피 하루 4잔"],
   ask=["진통제를 먹는 횟수가 두통과 관련이 있는지", "커피 양이 두통과 관련이 있는지"],
   bring=["두통 일기(날짜·시간·강도·먹은 약)", "타이레놀·게보린 포장", "체온 기록"]),
 "H07": dict(person="가명 서사랑(29세)", symptom="생리통(감기 기운 동반)", urgent=False,
   timeline=[(T - timedelta(2), "'사흘째'", "감기 기운과 생리통이 겹쳐 시작(접수일이 사흘째)"),
             (date(2026, 10, 10), "'둘 다 10월 10일부터'", "게보린정(아플 때마다, 몇 알인지 기억 안 남)·판콜에스내복액(1회 1병 하루 3번) 복용 시작"),
             (T, "접수일", "속이 조금 쓰리다")],
   drugs=[("게보린정", "본인", "current", None), ("판콜에스내복액", "본인", "current", "1회 1병 하루 3번")],
   portal=("5698", [7]), portal_tried=[],
   tell=["생리통·감기 기운이 10월 10일에 시작됨", "게보린정을 아플 때마다 먹었는데 몇 알인지 기억나지 않음 — 생각나는 대로 횟수", "판콜에스내복액을 함께 먹음, 속쓰림"],
   ask=["게보린정과 판콜에스내복액에 같은 성분이 겹치는데 함께 먹어도 되는지", "속쓰림이 약과 관련이 있는지"],
   bring=["게보린정·판콜에스내복액 포장(남은 개수 포함)", "체온 기록"]),
 "H08": dict(person="가명 윤아라(71세)", symptom="갑작스런 오른손 힘 빠짐·말 어눌함(20분 후 회복), 어지럼", urgent=True,
   urgent_reason="오늘 아침(2026-10-12) 세수하다 갑자기 오른손에 힘이 빠져 수건을 떨어뜨렸고 말이 어눌하게 나왔다(딸 목격), 20분쯤 지나 괜찮아짐 — 본인은 예약일에 가면 된다고 생각함(접수지 원문 요지)",
   timeline=[(None, "'오래됐다'", "혈압이 높다는 말을 들은 지 오래됨(날짜 미기재)"),
             (T.replace(year=T.year - 5), "'5년 전부터'", "아스피린프로텍트정100밀리그람 하루 1정 복용 시작(약 2021년)"),
             (None, "'요즘'", "어지러울 때가 있다(시작 날짜 미기재)"),
             (T, "'오늘 아침'", "세수하다 갑자기 오른손 힘이 빠져 수건을 떨어뜨림, 말이 어눌하게 나왔다고 딸이 말함. 20분쯤 지나 괜찮아짐")],
   drugs=[("아스피린프로텍트정100밀리그람", "본인", "current", "하루 1정")],
   portal=("5495", [51, 52, 53, 54, 55, 56, 57]), portal_tried=[],
   tell=["10월 12일 아침의 오른손 힘 빠짐·말 어눌함, 시작 시각과 회복까지 걸린 시간(약 20분), 목격자(딸)", "요즘 어지러움", "혈압 기록(딸이 잰 것)"],
   ask=["이 증상으로 상담일(10월 19일)까지 기다려도 되는지, 지금 바로 진료가 필요한지", "아스피린을 계속 먹는 것에 대해 확인할 점"],
   bring=["혈압 기록", "아스피린프로텍트정 포장", "증상을 본 딸(동행)"]),
 "H09": dict(person="가명 임자람(52세)", symptom="당뇨 전단계(공복혈당)", urgent=False,
   timeline=[(None, "'당뇨 전단계라는 말을 듣고'", "식단 조절 중, 아침 공복혈당 측정(날짜 미기재)"),
             (date(2026, 10, 3), "'10월 3일부터'", "두드러기로 지르텍정 하루 1정 복용 시작"),
             (T, "접수일", "다리에 쥐가 자주 난다. 같이 사는 어머니가 아스피린프로텍트정100밀리그람을 매일 드시지만 본인 약이 아님")],
   drugs=[("지르텍정", "본인", "current", "하루 1정"), ("아스피린프로텍트정100밀리그람", "타인", "current", None)],
   portal=("5304", [19, 20, 21, 22, 23]), portal_tried=["5305"],
   tell=["당뇨 전단계라고 들은 시기와 식단 조절 내용", "아침 공복혈당 기록(두 단위가 섞여 있음)", "두드러기로 지르텍정 복용, 다리 쥐가 자주 남"],
   ask=["공복혈당 기록을 보고 추가 검사가 필요한지", "다리에 쥐가 자주 나는 것에 대해 확인할 점"],
   bring=["혈당 기록", "혈당측정기", "지르텍정 포장", "이전 검사 결과지(있으면)"]),
 "H10": dict(person="가명 조차미(38세)", symptom="오른쪽 무릎 부종·계단 내려갈 때 통증", urgent=False,
   timeline=[(T - timedelta(days=T.weekday() + 7 - 1), "'지난주 화요일부터'", "오른쪽 무릎이 붓고 계단을 내려갈 때 아프기 시작. 넘어진 적은 없다"),
             (None, "'주말에'", "등산을 다녀옴(어느 주말인지 미기재 — 접수일 직전 주말이면 2026-10-10~11)"),
             (T, "접수일", "먹는 약 없음, 잰 기록 없음")],
   drugs=[], portal=("6744", [4]), portal_tried=["6748", "1988"],
   tell=["무릎이 붓기 시작한 날(10월 6일)과 아픈 동작(계단 내려갈 때)", "넘어진 적 없음, 주말 등산(날짜)"],
   ask=["붓기·통증에 어떤 검사가 필요한지", "등산·운동을 언제까지 쉬어야 하는지"],
   bring=["등산한 날짜·코스 메모", "무릎이 부은 사진(있으면)"]),
}

# 시점 환산 점검: 지난주 화요일
assert CASES["H10"]["timeline"][0][0] == date(2026, 10, 6), CASES["H10"]["timeline"][0][0]
assert INTAKE.weekday() == 0

DISC = "> ⚠️ **의료 자문·진단이 아닙니다.** 느티나무 마을 건강상담 창구의 진료 전 준비 자료입니다. 진단을 내리거나 약 복용·용량을 바꾸라는 뜻이 없으며, 약은 의사·약사와 상의하세요. 자료의 인물은 합성(가상)입니다."
UNIT = {"혈압": "mmHg", "혈당": "mg/dL", "체온": "℃"}

index, problems = [], []
for cid, c in CASES.items():
    stats, detail = stats_for(cid)
    drugs, dinfo = [], {}
    for name, whose, status, dose in c["drugs"]:
        if name not in dinfo:
            dinfo[name] = drug_info(name)
        i = dinfo[name]
        drugs.append({"name": name, "whose": whose, "status": status, "dose": dose, "found": i["found"],
                      "item_seq": i["item_seq"], "ingredients": i["ingredients"] if i["found"] else []})
    cur = [d for d in drugs if d["whose"] == "본인" and d["status"] == "current"]
    cnt = defaultdict(list)
    for d in cur:
        for g in d["ingredients"]:
            cnt[re.sub(r"\s+", "", g)].append(d["name"])
    dup = sorted(g for g, names in cnt.items() if len(set(names)) >= 2)
    unk_cur = [d["name"] for d in cur if not d["found"]]
    sn, idxs = c["portal"]
    pq = portal_quote(sn, idxs)
    papers = pub[cid]["selected"]
    over_sum = sum(s["over_days"] for s in stats.values())
    rec = {"id": cid, "urgent": c["urgent"], "stats": stats, "drugs": drugs, "duplicate_ingredients": dup,
           "pmids": [p["pmid"] for p in papers], "portal": {"status": "quoted", "url": pq["url"]},
           "file": f"cases/{cid}.md", "over_days_total": over_sum}
    index.append(rec)

    L = [f"# {cid} — 상담 준비 자료 ({c['person']})", "", DISC, "",
         f"- 접수일: {ds(INTAKE)} · 상담일: {ds(CONSULT)} · 주된 증상: {c['symptom']}"]
    if c["urgent"]:
        L += ["", "## ‼️ 지체 없이 확인이 필요해 보이는 신호 (접수지)", "",
              f"- {c['urgent_reason']}",
              "- 아래 4절의 국가건강정보포털 원문 대목과 겹친다. **상담일까지 기다리지 말고 오늘 바로 의료진(필요하면 119·응급실) 확인이 필요한지 창구에서 즉시 확인할 것.** 이 판단은 진단이 아니라 접수지 기재 내용과 공개 안내문의 대조다."]
    L += ["", "## 1. 증상 경과 (날짜순, 상대 표현은 접수일 기준으로 환산)", "", "| 날짜 | 접수지 표현 | 내용 |", "|---|---|---|"]
    tl = sorted(c["timeline"], key=lambda x: (x[0] is not None, x[0] or date.min))
    for d, expr, text in tl:
        approx = d is not None and any(k in expr for k in ("2주째", "일주일째", "한 달 넘게", "5년 전"))
        dstr = "날짜 미기재" if d is None else (("약 " if approx else "") + ds(d) + (" 이전" if "한 달 넘게" in expr else ""))
        L.append(f"| {dstr} | {expr} | {text} |")
    L += ["", "## 2. 측정 요약", ""]
    if not stats:
        L.append("- measurements.csv 에 이 건의 측정 기록이 없다(접수지에도 '잰 기록도 없다').")
    for kind, s in stats.items():
        dt = detail[kind]
        u = UNIT[kind]
        L.append(f"### {kind} ({u}로 환산, 창구 기준 {'수축기 ' + str(TH['혈압']['sys']) + ' / 이완기 ' + str(TH['혈압']['dia']) if kind == '혈압' else TH[kind]})")
        L += ["", "| 항목 | 값 |", "|---|---|", f"| 쓸 수 있는 측정 | {s['n']}건 ({dt['first']} ~ {dt['last']}) |", f"| 못 쓰는 줄 | {s['invalid']}줄 |"]
        if kind == "혈압":
            L += [f"| 평균 | {s['mean_sys']}/{s['mean_dia']} |", f"| 최근 7일 평균 ({R_START} ~ {CONSULT - timedelta(1)}) | 수축기 {s['recent7']} / 이완기 {s['recent7_dia']} ({s['n_recent7']}건) |",
                  f"| 그 전 평균 (~{R_START - timedelta(1)}) | 수축기 {s['prior']} / 이완기 {s['prior_dia']} ({s['n_prior']}건) |"]
        else:
            L += [f"| 평균 | {s['mean']} |", f"| 최근 7일 평균 ({R_START} ~ {CONSULT - timedelta(1)}) | {s['recent7']} ({s['n_recent7']}건) |",
                  f"| 그 전 평균 (~{R_START - timedelta(1)}) | {s['prior']} ({s['n_prior']}건) |"]
        L += [f"| 기준을 넘은 날 수 (초과 기준) | {s['over_days']}일 |", f"| 참고: 기준 이상(같음 포함) 날 수 | {s['over_days_inclusive']}일 |", ""]
        if dt["over_dates"]:
            L.append(f"- 기준을 넘은 날: {', '.join(dt['over_dates'])}")
        if dt["invalid"]:
            L.append("- 못 쓰는 줄(값을 지어내지 않고 제외): " + "; ".join(f"{x['date']} 값 '{x['value']}' {x['unit']} — {x['reason']}" for x in dt["invalid"]))
        L.append("")
    L += ["## 3. 약 (의약품안전나라 e약은요 조회)", ""]
    if not drugs:
        L.append("- 접수지에 적힌 약이 없다.")
    for d in drugs:
        i = dinfo[d["name"]]
        L.append(f"### {d['name']} — {d['whose']} · {'현재 복용' if d['status'] == 'current' else '끊은 약'} · 용량: {d['dose'] or '적혀 있지 않음'}")
        if i["found"]:
            L += [f"- e약은요 제품명: {i['product']} (itemSeq {i['item_seq']})", f"- 주성분: {', '.join(i['ingredients'])}",
                  f"- 출처: {i['detail_url']}", f"- \"{i['caution_heading']}\" 원문:"]
            if i["caution"]:
                L += [f"  > {t}" for t in i["caution"]]
            else:
                L.append(f"  > (비어 있음) {i['note']}")
        else:
            L += ["- **확인하지 못함** — 성분을 적지 않는다.", f"- 사유: {i['note']}", f"- 시도한 주소: {i['search_url']}"]
        L.append("")
    L.append("### 성분 겹침 (본인·현재 복용 약끼리, 주성분명 기준)")
    if dup:
        for g in dup:
            L.append(f"- **{g}**: {', '.join(sorted(set(cnt[g])))}")
    else:
        L.append("- 확인된 겹침 없음" + (" (단, 성분을 확인하지 못한 약이 있어 겹침 여부를 다 판단하지 못함)" if unk_cur else ""))
    excl = [d["name"] + ("(끊은 약)" if d["status"] == "stopped" else "(다른 사람 약)") for d in drugs if not (d["whose"] == "본인" and d["status"] == "current")]
    if excl:
        L.append(f"- 겹침 비교에서 뺀 약: {', '.join(excl)}")
    unconf = [d["name"] for d in drugs if not d["found"]] + [d["name"] + "(주의 항목 본문 비어 있음)" for d in drugs if d["found"] and not dinfo[d["name"]]["caution"]]
    L += ["", "### 확인하지 못한 것", "- " + (", ".join(unconf) if unconf else "없음"), ""]
    L += ["## 4. 바로 병원에 가야 하는 신호 (국가건강정보포털·질병관리청 원문)", "", f"- 페이지: {pq['title']} — {pq['url']}", f"- 원문 문단 번호: {pq['paragraphs']}"]
    if c.get("portal_note"):
        L.append(f"- 참고: {c['portal_note']}")
    if c["portal_tried"]:
        L.append("- 함께 읽은 다른 페이지: " + ", ".join(PURL + x for x in c["portal_tried"]))
    L += [""] + [f"> {t}" for t in pq["quote"]] + [""]
    L += ["## 5. 관련 논문 (PubMed)", "", f"- 검색어: `{pub[cid]['query']}`"]
    if papers:
        L += [f"- {p['title']} — {p['journal']} ({p['year']}), PMID {p['pmid']}, {p['url']}" for p in papers]
    else:
        L.append("- 관련 논문을 찾지 못함")
    L += ["", "## 6. 의사에게", "", "**말할 것**"] + [f"- {x}" for x in c["tell"]]
    L += ["", "**물어볼 것**"] + [f"- {x}" for x in c["ask"]]
    L += ["", "**가져갈 것**"] + [f"- {x}" for x in c["bring"]] + ["", DISC, ""]
    (OUT / "cases" / f"{cid}.md").write_text("\n".join(L), encoding="utf-8")

# ---------------- 정렬·요약 ----------------
index.sort(key=lambda r: (0, r["id"]) if r["urgent"] else (1, -r["over_days_total"], r["id"]))
(OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

S = ["# 느티나무 마을 건강상담 창구 — 상담일 준비 요약", "", DISC, "",
     f"- 상담일 {ds(CONSULT)} · 접수일 {ds(INTAKE)} · 접수 {len(index)}건",
     f"- 정렬: 접수지에 지체 없는 진료·응급 확인이 필요해 보이는 신호가 있는 건(접수번호순) → 기준을 넘은 날 수 합 내림차순(같으면 접수번호순)",
     f"- 최근 7일 = {R_START} ~ {CONSULT - timedelta(1)}(상담일 제외), 그 전 = {R_START - timedelta(1)} 이전 전부(job.json 정의)", "",
     "## 급한 순 표", "", "| 순위 | 접수번호 | 급함 | 주된 증상 | 기준 넘은 날 합 | 측정 요약 | 성분 겹침 | 메모 |", "|---|---|---|---|---|---|---|---|"]
for k, r in enumerate(index, 1):
    c = CASES[r["id"]]
    ms = []
    for kind, s in r["stats"].items():
        if kind == "혈압":
            ms.append(f"혈압 n={s['n']}/못씀 {s['invalid']} 평균 {s['mean_sys']}/{s['mean_dia']} 최근7 {s['recent7']} 이전 {s['prior']} 초과 {s['over_days']}일")
        else:
            ms.append(f"{kind} n={s['n']}/못씀 {s['invalid']} 평균 {s['mean']} 최근7 {s['recent7']} 이전 {s['prior']} 초과 {s['over_days']}일")
    S.append(f"| {k} | {r['id']} | {'**지금 확인**' if r['urgent'] else '-'} | {c['symptom']} | {r['over_days_total']} | {'<br>'.join(ms) or '측정 없음'} | {', '.join(r['duplicate_ingredients']) or '-'} | [cases/{r['id']}.md](cases/{r['id']}.md) |")
S += ["", "## 급한 신호 (접수지 근거)", ""] + [f"- **{r['id']}**: {CASES[r['id']]['urgent_reason']}" for r in index if r["urgent"]]
S += ["", "## 확인하지 못한 것", ""]
for r in index:
    for d in r["drugs"]:
        if not d["found"]:
            S.append(f"- {r['id']} {d['name']}: e약은요 검색 0건 — 성분·주의 원문 확인하지 못함 (시도: {drug_info(d['name'])['search_url']})")
seen = set()
for r in index:
    for d in r["drugs"]:
        if d["found"] and not drug_info(d["name"])["caution"] and (r["id"], d["name"]) not in seen:
            seen.add((r["id"], d["name"]))
            S.append(f"- {r['id']} {d['name']}: e약은요의 '사용하기 전에 반드시 알아야 할 내용' 항목은 제목만 있고 본문이 비어 있음(옮길 원문 없음)")
for r in index:
    c = CASES[r["id"]]
    cur_unknown = [d["name"] for d in r["drugs"] if d["whose"] == "본인" and d["status"] == "current" and not d["found"]]
    if cur_unknown and any(d["found"] for d in r["drugs"] if d["whose"] == "본인" and d["status"] == "current"):
        S.append(f"- {r['id']}: {', '.join(cur_unknown)}의 성분을 몰라 다른 현재 복용 약과의 성분 겹침을 다 판단하지 못함")
    if c.get("portal_note"):
        S.append(f"- {r['id']} 포털: {c['portal_note']}")
for r in index:
    if len(r["pmids"]) < 2:
        S.append(f"- {r['id']} 논문: 관련도가 맞는 논문을 {len(r['pmids'])}편만 골랐다(검색 상위 3건 중 나머지는 주제가 맞지 않음).")
S.append("- H10: 측정 기록 없음(measurements.csv 에 행이 없고 접수지에도 '잰 기록도 없다').")
S.append("- 날짜가 적혀 있지 않은 경과(예: '요즘', '오래됐다', 검진 시점)는 날짜를 만들지 않고 '날짜 미기재'로 두었다. '2주째'·'일주일째'·'한 달 넘게'·'5년 전'은 접수일에서 뺀 근사 날짜다. H10의 '주말 등산'은 어느 주말인지 적혀 있지 않다.")
S.append("- '기준을 넘은 날'은 기준값을 **초과**한 날(혈압은 수축기 또는 이완기 중 하나라도)로 셌다. 같은 값(예: 체온 38.0℃, 혈압 140/…, …/90)까지 넣은 날 수는 건별 메모와 index.json 의 over_days_inclusive 에 따로 적었다.")
inv_total = sum(s["invalid"] for r in index for s in r["stats"].values())
S.append(f"- 못 쓰는 측정 줄 {inv_total}줄('측정 실패', 'Err', '약 130', 빈 값)은 값을 짐작하지 않고 계산에서 뺐다.")
S.append("- 측정 기록에는 접수일(10-12) 뒤 상담일 전(10-13~10-18) 값도 있다 — 계산에는 넣었다(최근 7일 창 안).")
if after_consult:
    S.append(f"- 상담일 당일 이후 측정 {len(after_consult)}건은 계산에서 뺐다.")
if suspect:
    S.append("- 단위가 의심스러운 값: " + "; ".join(f"{x['case']} {x['line']}행 {x['value']} {x['unit']}" for x in suspect))
S.append("- PubMed 조회는 첫 병렬 요청에서 429(요청 과다)가 났고, 순차 재조회로 받은 결과를 썼다.")
S += ["", "## 자료·출처", "", "- 약: 의약품안전나라 e약은요 검색(searchEasyDrug)·상세(getItemDetail) — 원문 보관 out/_sources/drug_search.json, drug_<itemSeq>.json",
      "- 포털: 국가건강정보포털(health.kdca.go.kr) 건강정보 본문 — out/_sources/portal_<번호>.json", "- 논문: PubMed 검색 결과 — out/_sources/pubmed.json", "- 계산·조립 스크립트: out/_build/make_outputs.py", ""]
(OUT / "summary.md").write_text("\n".join(S), encoding="utf-8")

# ---------------- 자체 검증 ----------------
back = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
ids = [r["id"] for r in back]
chk = {"count": len(back), "order": ids, "files_exist": all((OUT / r["file"]).exists() for r in back),
       "urgent_first": all(r["urgent"] for r in back[:sum(1 for x in back if x["urgent"])]),
       "notfound_no_ingredients": all(not d["ingredients"] for r in back for d in r["drugs"] if not d["found"]),
       "disclaimer_in_cases": all("의료 자문·진단이 아닙니다" in (OUT / r["file"]).read_text(encoding="utf-8") for r in back)}
print(json.dumps(chk, ensure_ascii=False), file=sys.stderr)
res = {"check": chk, "index": [{"id": r["id"], "urgent": r["urgent"], "over": r["over_days_total"], "stats": r["stats"], "dup": r["duplicate_ingredients"],
        "drugs": [(d["name"], d["found"], d["ingredients"]) for d in r["drugs"]]} for r in back],
       "invalid_total": inv_total, "after_consult": after_consult, "suspect": suspect}
p = Path(os.environ["INDIEBIZ_SCRIPT_RESULT"])
tmp = p.with_suffix(".tmp")
tmp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
tmp.replace(p)
