"""43회차 합성 자료 생성 — 가상 동네 수리교실 홍보. 정답(oracle)은 입력 폴더 밖 _oracle/ 에만 둔다.
사용: prepare.py  → outputs/long_sentence_imagination/2026-10-09_43회차/{trainer,agent}/input + _oracle"""
import csv, json, random, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_43회차'
random.seed(43)

COMPANY = {
  "name": "가상 동네 수리교실",
  "one_line": "버리기 전에 함께 고치는 토요일 오후 두 시의 동네 수선 교실",
  "offer": [
    {"item": "1회 체험 (재료 포함)", "price_krw": 10000},
    {"item": "3회 패키지", "price_krw": 25000}
  ],
  "when_where": "매주 토요일 14:00~16:00, 가상 마을회관 2층",
  "usp": [
    "가져온 옷을 그 자리에서 고쳐 입고 돌아간다 (연습용 천이 아니라 내 옷)",
    "1회 1만원·재료 포함, 등록 기간 없음 — 한 번 와 보고 결정",
    "초보 전용: 단추·구멍·밑단 세 가지만 가르친다"
  ],
  "tone": {"style": "담백하고 친근하게, 짧은 문장", "banned_words": ["최고", "1등", "완벽", "혁신", "프리미엄", "국내 유일"]},
  "colors": {"primary": "#2F5D3A", "secondary": "#F4EFE6", "avoid": ["네온", "형광"]},
  "rtb": [
    {"fact": "2026-09 시범 운영 4회, 참가 27명, 재참가 11명", "source": "출석부 2026-09", "verified": True},
    {"fact": "참가자 설문 23명 만족도 평균 4.6/5", "source": "설문 2026-09-27", "verified": True},
    {"fact": "지역 신문 소개", "source": "없음 — 후보일 뿐", "verified": False}
  ],
  "kpi": {"window_days": 14, "inquiries_target": 20, "inquiry_channel": "게시판 글·포털 문의"},
  "publish_channels": ["게시판(/b/)", "포털(/h/)", "쇼케이스(/s/)", "Nostr 장문"]
}

PAINS = {
  "time": {"label": "시간이 없다", "templates": [
    "평일엔 야근이라 뭘 배울 시간이 없어요. 주말에 두어 시간만 쓸 수 있으면 좋겠는데",
    "8주 과정은 부담돼요. 한 번 가 보고 맞으면 계속하는 식이면 좋겠어요",
    "아이 재우고 나면 열 시. 수선 배우고 싶은데 저녁 수업은 못 가요",
    "토요일 오후만 비어요. 그 시간에 하는 동네 수업 있나요",
    "등록하면 매주 가야 한다는 게 제일 큰 벽이에요",
    "짧게 한 번 체험할 수 있는 수선 클래스 찾는 중. 장기 과정은 사양",
    "시간 맞추기가 제일 어려워요. 한 번에 두 시간 넘으면 못 갑니다",
    "주중엔 시간이 안 나서 미루다 옷장에 수선할 옷만 쌓였어요"
  ]},
  "confidence": {"label": "손재주가 없다", "templates": [
    "바느질 한 번도 안 해봤는데 가도 되나요. 괜히 민폐일까 봐",
    "유튜브 보고 단추 달다가 실이 다 엉켰어요. 옆에서 봐주는 사람이 필요해요",
    "손재주가 없어서 시작할 엄두가 안 나요",
    "초보도 되는 수업인지가 제일 궁금해요. 다들 잘하는 사람만 올 것 같아서",
    "구멍 난 니트 꿰매려다 더 크게 만들었어요. 기초부터 누가 가르쳐 줬으면",
    "밑단 줄이기 혼자 하다가 삐뚤어졌어요. 처음 하는 사람 눈높이 수업이 있나",
    "손으로 하는 건 다 서툴러요. 그래도 배울 수 있을까요",
    "실패하면 옷 버릴까 봐 못 건드리겠어요"
  ]},
  "cost_waste": {"label": "버리기 아깝다/비용", "templates": [
    "단추 하나 떨어졌다고 세탁소 가면 오천 원. 내가 달 수 있으면 좋겠어요",
    "멀쩡한 옷을 구멍 하나 때문에 버리는 게 너무 아까워요",
    "수선비가 옷값보다 비쌀 때가 있어요. 간단한 건 직접 하고 싶어요",
    "옷 버리는 게 환경에도 안 좋다는데, 고쳐 입는 법을 배우고 싶어요",
    "아이 옷은 금방 작아져서 밑단만 늘릴 수 있어도 반년은 더 입히겠어요",
    "학원비 12만원은 부담이에요. 재료비 포함 만원 정도면 가 볼 텐데",
    "수선집 맡기면 일주일 걸려요. 급한 건 내가 하고 싶어요",
    "쓸 만한 옷을 못 버리고 쌓아두기만 해요. 고칠 줄 알면 입을 텐데"
  ]},
  "noise": {"label": "무관/광고", "templates": [
    "[광고] 재봉틀 특가 세일! 지금 구매하시면 사은품 증정",
    "오늘 날씨 좋네요. 다들 주말 잘 보내세요",
    "미싱 수리점 추천 부탁드려요. 모터 소리가 이상해요",
    "옷 정리 팁 공유합니다. 계절별로 상자에 라벨 붙이기",
    "수선 교실 말고 가죽공예 수업은 어디서 하나요",
    "[홍보] 원단 도매 창고 오픈, 사장님 환영"
  ]}
}
SOURCES = ["blog", "cafe", "kin", "survey"]

def make_reviews():
    plan = [("time", 48), ("confidence", 36), ("cost_waste", 24), ("noise", 12)]
    rows, labels = [], []
    rid = 0
    for key, n in plan:
        t = PAINS[key]["templates"]
        for k in range(n):
            rid += 1
            text = t[k % len(t)]
            if k >= len(t):
                text = text + f" ({['정말','진짜','솔직히','요즘'][k % 4]} 그래요)"
            rows.append({"id": f"R{rid:03d}", "source": SOURCES[rid % 4], "date": f"2026-{8 + (rid % 2):02d}-{1 + (rid % 27):02d}", "text": text})
            labels.append({"id": f"R{rid:03d}", "label": key})
    # 경계 표본: 쉼표·따옴표·줄바꿈이 든 본문 3건 (라벨은 time/confidence/cost_waste)
    extras = [("time", '주말에, 딱 "두 시간"만 쓸 수 있어요. 평일은 불가능'),
              ("confidence", '처음이라 겁나요.\n옆에서 봐주면 할 수 있을 것 같아요'),
              ("cost_waste", '세탁소 수선비 5,000원, 옷값 9,900원. "그냥 버릴까" 싶다가도 아까워요')]
    for key, text in extras:
        rid += 1
        rows.append({"id": f"R{rid:03d}", "source": "cafe", "date": "2026-09-28", "text": text})
        labels.append({"id": f"R{rid:03d}", "label": key})
    random.shuffle(rows)
    order = {r["id"]: i for i, r in enumerate(rows)}
    labels.sort(key=lambda l: order[l["id"]])
    return rows, labels

COMPETITORS = {
  "competitor_a_culture_center.txt": """○○문화센터 바느질 기초반 안내
8주 완성 정규 과정 | 수강료 120,000원 (재료비 별도 15,000원)
전문 강사진의 체계적인 커리큘럼으로 홈패션의 기초부터 완성까지.
1주차 재봉틀 구조 이해, 2주차 직선 박기, 3주차 지퍼 달기 ... 8주차 파우치 완성.
매주 화요일 19:00~21:00, 정원 12명, 개강 2026-10-14. 전 과정 수강 시 수료증 발급.
문화센터 회원 10% 할인. 재봉틀은 센터 비치분 사용.
""",
  "competitor_b_online_class.txt": """온라인 수선 클래스 — 월 9,900원 무제한
언제 어디서나 스마트폰으로 배우는 옷 수선. 영상 120편, 매주 신규 업데이트.
단추 달기부터 청바지 밑단까지. 가입 첫 달 50% 할인 이벤트 진행 중!
1:1 질문 게시판 운영(답변 평균 2일). 수강 기간 제한 없음.
국내 최대 수선 영상 라이브러리. 지금 가입하고 첫 영상 무료로 보세요.
""",
}

SEARCH_TERMS = {"note": "검색어 근거는 네이버 blog/cafe/kin 결과 건수 비교의 간접 추정이다. 검색량 소스는 없다.",
                "queries": ["옷 수선 배우기", "바느질 기초 클래스", "단추 달기 방법"]}

def write_inputs(base: Path):
    (base / 'competitors').mkdir(parents=True, exist_ok=True)
    (base / 'voice').mkdir(exist_ok=True)
    (base / 'company.json').write_text(json.dumps(COMPANY, ensure_ascii=False, indent=2))
    for name, text in COMPETITORS.items():
        (base / 'competitors' / name).write_text(text)
    (base / 'search_terms.json').write_text(json.dumps(SEARCH_TERMS, ensure_ascii=False, indent=2))
    rows, labels = make_reviews()
    with open(base / 'voice' / 'reviews.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=["id", "source", "date", "text"], quoting=csv.QUOTE_MINIMAL)
        w.writeheader(); w.writerows(rows)
    return rows, labels

def make_reactions(base: Path):
    """변형 자료: 2주 × 소재 3(A1~A3=앵글 순위 1~3) × 채널 2 일별 노출·클릭·문의. 쇼케이스 채널은 미측정(행 없음)."""
    (base / 'reactions').mkdir(parents=True, exist_ok=True)
    rows = []
    rates = {"A1": (0.030, 0.25), "A2": (0.055, 0.40), "A3": (0.018, 0.10)}  # (CTR, 문의/클릭) — 2위 앵글이 실제 위닝
    for d in range(14):
        date = f"2026-10-{10 + d:02d}"
        for a, (ctr, inq) in rates.items():
            for ch, imp0 in (("게시판", 180), ("포털", 90)):
                if a == "A1" and ch == "포털" and d == 5:
                    continue  # 결측일 1건
                imp = 0 if (a == "A3" and ch == "포털" and d == 2) else int(imp0 * (0.8 + 0.4 * random.random()))
                clicks = 0 if imp == 0 else max(0, int(round(imp * ctr * (0.7 + 0.6 * random.random()))))
                inquiries = 0 if clicks == 0 else int(round(clicks * inq * (0.5 + random.random())))
                rows.append({"date": date, "asset_id": a, "channel": ch, "impressions": imp, "clicks": clicks, "inquiries": inquiries})
    with open(base / 'reactions' / 'reactions.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=["date", "asset_id", "channel", "impressions", "clicks", "inquiries"])
        w.writeheader(); w.writerows(rows)
    (base / 'reactions' / 'README.txt').write_text("2026-10-10~23 게시판·포털 소재별 일별 노출/클릭/문의. 쇼케이스 채널은 집계 수단이 없어 행이 없다(미측정). A1~A3 는 campaign_ledger 의 asset_id.")
    return rows

def oracle(rows, labels, reactions, path: Path):
    path.mkdir(parents=True, exist_ok=True)
    with open(path / 'labels.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=["id", "label"]); w.writeheader(); w.writerows(labels)
    counts = {}
    for l in labels: counts[l["label"]] = counts.get(l["label"], 0) + 1
    by_asset = {}
    for r in reactions:
        b = by_asset.setdefault(r["asset_id"], {"impressions": 0, "clicks": 0, "inquiries": 0, "rows": 0})
        for k in ("impressions", "clicks", "inquiries"): b[k] += r[k]
        b["rows"] += 1
    for a, b in by_asset.items():
        b["ctr"] = round(b["clicks"] / b["impressions"], 4) if b["impressions"] else None
        b["inq_per_click"] = round(b["inquiries"] / b["clicks"], 4) if b["clicks"] else None
    total_inq = sum(b["inquiries"] for b in by_asset.values())
    exp = {"review_rows": len(rows), "label_counts": counts,
           "expected_angle_order": ["time", "confidence", "cost_waste"],
           "banned_words": COMPANY["tone"]["banned_words"],
           "competitor_expected": {"competitor_a": ["8주", "120,000", "전문 강사", "수료증"], "competitor_b": ["9,900", "무제한", "영상", "국내 최대"]},
           "reactions": {"rows": len(reactions), "by_asset": by_asset, "total_inquiries": total_inq, "kpi_target": 20,
                         "kpi_met": total_inq >= 20, "winning_by_inquiries": max(by_asset, key=lambda a: by_asset[a]["inquiries"]),
                         "unmeasured_channels": ["쇼케이스(/s/)", "Nostr 장문"], "missing_day": {"asset_id": "A1", "channel": "포털", "date": "2026-10-15"},
                         "zero_impression_row": {"asset_id": "A3", "channel": "포털", "date": "2026-10-12"}}}
    (path / 'expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=2))
    return exp

if __name__ == '__main__':
    tr = OUT / 'trainer' / 'input'
    rows, labels = write_inputs(tr)
    reactions = make_reactions(OUT / '_staging')   # 변형 자료는 기본 실행 뒤에 input/reactions 로 옮긴다
    exp = oracle(rows, labels, reactions, OUT / '_oracle')
    ag = OUT / 'agent' / 'input'
    if ag.exists(): shutil.rmtree(ag)
    shutil.copytree(tr, ag)
    print(json.dumps({"reviews": len(rows), "labels": exp["label_counts"], "reactions": exp["reactions"]["rows"],
                      "total_inquiries": exp["reactions"]["total_inquiries"], "winning": exp["reactions"]["winning_by_inquiries"],
                      "by_asset": exp["reactions"]["by_asset"]}, ensure_ascii=False))
