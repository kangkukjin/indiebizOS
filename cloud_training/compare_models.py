#!/usr/bin/env python3
"""사과-대-사과 모델 비교 + 신어휘 프로브.

사용: python cloud_training/compare_models.py <A_dir> <B_dir>
  A = 현 라이브/백업, B = 새 모델.
동일 seed42 분할(현재 코퍼스)에서 code/desc Top-k + 신어휘 프로브를 둘 다 측정.
채택 판정: B가 aggregate desc-Top5에서 이기거나, aggregate 회귀 없이 신어휘 프로브를 더 맞히면 채택.

★2026-08-23 실측 — 이 판정 규칙을 읽는 사람이 알아야 할 것 (규칙 자체는 안 바꿨다):
  **desc Top-k 는 런타임과 결합돼 있지 않다.** 라이브 해마 색인이 임베딩하는 것은
  `_prepare_search_text` = `intent × N + ibl_code` 뿐이고, 액션 description 을 임베딩해
  질의와 비교하는 런타임 경로는 **하나도 없다**(폰 렌트 /ibl/embed 도 같은 공간,
  api_ibl `_action_description` 은 YAML 조회일 뿐이다). 실증도 양방향으로 났다 —
  08-23 오전: 프로브(desc 공간) 2건을 잃었는데 라이브 회상은 멀쩡했고,
  08-23 오후: desc T1 −5.7p 인데 라이브 8종이 전건 동일했다.
  런타임과 같은 공간을 재는 것은 **code Top-k** 와 트레이너의 `_eval_on_test` 다.
  desc 지표는 여전히 유용하다(학습 신호의 건강·낱말별 변별) — 다만 그것만으로 채택을
  가르면 런타임에 없는 손익으로 판정하게 된다. 두 축을 따로 읽을 것.
"""
import os
import sys
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ["IBL_DATA_DIR"] = str(REPO / "data")
sys.path.insert(0, str(REPO / "cloud_training"))

import ibl_embedding_trainer_cloud as T  # noqa: E402
T.DEVICE = "cpu"  # 평가는 CPU (메모리 안전)

from sentence_transformers import SentenceTransformer  # noqa: E402
from sentence_transformers.util import cos_sim  # noqa: E402

# 옛 모델이 약하던 신어휘 질의 → 기대 액션
PROBES = [
    # ★2026-08-04 정리: sense:travel 3건·limbs:iframe 1건 제거 — 그 액션들이 은퇴해
    #   어휘에 없다. 존재하지 않는 기대값은 영원히 못 맞히고 프로브 점수만 깎는다.
    #   (어휘 은퇴 시 여기도 함께 정리할 것. 국내 숙박은 아래 sense:stay 프로브가 승계)
    ("이 트리거 삭제해", "self:trigger"),
    ("매일 아침 자동실행 트리거 등록", "self:trigger"),
    ("삼성전자 주가 알려줘", "sense:stock"),
    ("비트코인 시세", "sense:crypto"),
    # ★2026-08-17 정리: sense:pew_research 는 08-15 [sense:feed] 로 일반화 은퇴 — 승계 프로브로 교체.
    ("퓨리서치 데이터 좀", "sense:feed"),
    ("세계은행 한국 GDP", "sense:world_bank"),
    # 2026-07-21 추가 — 07-13 재학습 이후 신어휘 (이번 재학습의 흡수 대상)
    ("자유게시판 하나 만들어줘", "others:bulletin"),
    ("포털에 회원 등급 올려줘", "others:portal"),
    ("가족신문 새 판 발행해", "others:family_news"),
    ("제주 호텔 이번 주말 요금", "sense:stay"),
    ("서울 한달살기 방 알아봐", "sense:stay"),
    ("신문 발행 스케줄 꺼줘", "self:manage_events"),
    # 2026-08-04 추가 — 07-21 재학습 이후 쌓인 대기열(이번 재학습의 흡수 대상)
    ("내 음악 라이브러리에서 김광석 찾아줘", "self:music"),
    ("USB 꽂은 저 PC 화면 좀 보여줘", "limbs:guestpc"),
    ("내가 만든 웹앱들 살아있는지 확인해줘", "self:webapp"),
    ("프리랜서한테 번역 맡기고 싶은데", "sense:freelance"),
    ("명함 만들어줄 업체 찾아줘", "sense:freelance"),
    # ★2026-08-04 site="used" 은퇴 — 중고+가격 표현이 search_shopping 으로 새던 구간.
    #   코퍼스에선 오염 2건을 지우고 교정 7건을 심었다. 가중치가 그걸 흡수했는지 본다.
    ("중고 맥북 얼마야", "sense:used"),
    ("중고 아이패드 시세 알려줘", "sense:used"),
    ("중고 카메라 얼마에 올라와 있어", "sense:used"),
    # 경계 반대편 — 새 상품은 여전히 가격비교로 가야 한다(중고를 당기다 밀어내지 않았는지).
    ("맥북 최저가 알려줘", "sense:search_shopping"),
    ("에어팟 가격 비교해줘", "sense:search_shopping"),
    # 2026-08-05 검색 통합(어휘 압축 2단계) — 구 5액션(search_ddg/naver/gnews/hn/guardian)이
    # [sense:search]{source} 로 병합. 구 이름 표현이 신형으로 직행하는지 본다.
    ("웹에서 검색해줘", "sense:search"),
    ("네이버 블로그에서 후기 찾아줘", "sense:search"),
    ("가디언 기사 검색해줘", "sense:search"),
    ("해커뉴스에 뭐 떴는지 보여줘", "sense:search"),
    ("구글 뉴스에서 경제 소식 검색", "sense:search"),
    # 2026-08-06 슬라이드 2축 개편 — render 파라미터·image_<톤> 덱 신어휘 흡수 대상
    ("가볍게 HTML 방식으로 슬라이드 한 장", "self:slide"),
    ("이미지+글자 합성 방식으로 슬라이드 만들어줘", "self:slide"),
    ("잉크+청사진 톤으로 강의 덱 만들어줘", "self:lecture"),
    ("시네마틱 3D 톤 발표 덱 새로", "self:lecture"),
    # 2026-08-07 sheet(장부 부분 편집)·script(등록 스크립트)·PDF 표 추출 — 이번 재학습 흡수 대상
    ("재고장 엑셀에 오늘 입고 행 추가해줘", "self:sheet"),
    ("장부에서 B형 부품 수량 45로 수정", "self:sheet"),
    ("완성한 스크립트 등록해서 자동화에 굳혀줘", "self:script"),
    ("등록된 폴더용량 스크립트 실행해", "self:script"),
    ("거래명세서 PDF에서 표 뽑아줘", "self:read"),
    # 2026-08-17 추가 — params 개통·[table:since] 신설(이번 재학습 흡수 대상)
    ("긱뉴스에 새 글 올라온 것만 보여줘", "table:since"),
    ("관심 매물 가격 변동 있으면 알려줘", "table:since"),
    ("주간보고 워크플로우 청주 버전으로 돌려줘", "self:workflow"),
    # 2026-08-19 추가 — 원샷 낱말 세 자리(ai-ops: struct/ai/brief, 이번 재학습 흡수 대상)
    ("영수증 사진에서 지출 내역 뽑아 정리해줘", "self:struct"),
    ("검색 결과에서 광고성 글은 빼줘", "table:ai"),
    ("시세 조회해서 세 문장으로 보고해줘", "table:brief"),
    ("매물 중에 어떤 게 제일 나은지 판단해줘", "table:brief"),
    # 경계 반대편 — 기존 어휘 영토 보존(struct/brief 가 당기다 밀어내지 않았는지)
    ("이 PDF에서 표를 뽑아줘", "self:read"),
    ("이 글 요약해줘", "self:ask"),
    # 2026-08-22 추가 — V18-2 가 연 self_check `source` 축(자가점검|실사용|둘 다) 시드 16건,
    # 이번 재학습의 흡수 대상. 시드 intent 를 그대로 쓰지 않고 바꿔 물어 암기가 아닌 일반화를 본다.
    ("실제로 쓰다가 실패한 게 뭐야", "sense:self_check"),
    ("만성 실패 경보가 뭘 보고 울린 거야", "sense:self_check"),
    ("점검이랑 실사용 합쳐서 최근 실패 보여줘", "sense:self_check"),
    # 2026-08-23 추가 — [table:each] 통화 계약 개정으로 **description 을 통째로 다시 썼다**
    #   (봉투 설명 → 통화 직결·errors 봉투·keep). 설명이 바뀌면 그 낱말이 여전히 같은 질문에
    #   불려 나오는지가 흡수의 핵심이다. 코퍼스 쪽 이관 15문장은 code 지표가 잰다.
    #   ★암기가 아닌 일반화를 보려고 코퍼스 intent 를 그대로 쓰지 않는다.
    ("지역 세 곳을 각각 조회해서 한 표로 모아줘", "table:each"),
    ("목록의 항목마다 상세를 따로 받아와줘", "table:each"),
    # 경계 반대편 — '기록 조회'가 self_check 로 빨려들지 않는지(대화 로그·기계 상태는 남의 영토)
    ("어제 나눈 대화 기록 보여줘", "self:recent_chats"),
    ("지금 이 기계 상태 어때", "sense:host"),
    # 2026-08-22 19회차 B19-1 — 조건 문형이 filter 로 곧게 가는지(워드 연산자 수리의 짝)
    ("단지명에 자이 들어간 것만 걸러줘", "table:filter"),
    # 2026-09-18 추가 — 실행기억 다듬기(09-17~18) 뒤의 재학습. 조합 용례 73건을 단발뿐이던 생산자 28종에 붙였다
    #   (tags: compose_2026_09_18). 조합 꼴로 물어도 그 생산자가 불려 나오는지 — 시드 의도를 그대로 쓰지 않는다.
    ("지난달에 돈을 제일 많이 쓴 데가 어디야", "self:finance"),
    ("이번 주에 비 오는 날 있어", "sense:weather"),
    ("최근에 나온 언어모델 논문 몇 편만 추려서 표로", "sense:paper"),
    ("현대차가 최근에 공시한 것 중에 배당 얘기만", "sense:company"),
    ("앞으로 있을 일정만 날짜 순서로 보여줘", "self:manage_events"),
    ("마감이 얼마 안 남은 지원사업 알려줘", "sense:startup"),
    ("평 좋은 제주 숙소 몇 군데만 골라줘", "sense:stay"),
    ("걸어갈 만한 거리에 약국 있어", "sense:place"),
    # 경계 — 죽은 이음매를 고친 자리(`$위치 = [sense:here]` 꼴·music query)가 여전히 같은 질문에 불려 나오는지
    ("이 근처에서 밥 먹을 데 찾아줘", "sense:restaurant"),
    ("유튜브에서 재즈 찾아서 틀어줘", "limbs:music"),
    ("검색한 거 요약해서 나한테 알림으로 보내줘", "self:notify_user"),
    # 경계 — 조합 용례가 늘면서 단순 조회가 밀려나지 않았는지
    ("일정 뭐 있어", "self:manage_events"),
    ("서울 날씨", "sense:weather"),
]


def build_split():
    random.seed(42)
    examples = T.extract_examples_from_db()
    variations = []
    training_dir = T.DATA_DIR / "training"
    for f in (sorted(training_dir.glob("*.json")) if training_dir.exists() else []):
        try:
            d = json.load(open(f, encoding="utf-8"))
            if isinstance(d, list) and d:
                variations.extend(T.current_examples(d)[0])
        except Exception:
            pass
    variations = T.balance_by_action(variations)
    train_pairs, test_pairs, code_to_intents = T.prepare_training_data(
        examples, variations, normalize=True)
    action_descs = T.load_action_descriptions()
    return test_pairs, list(code_to_intents.keys()), action_descs


def eval_model(path, test_pairs, all_codes, action_descs):
    m = SentenceTransformer(path, device="cpu")
    res = T.evaluate_model(m, test_pairs, all_codes, Path(path).name, action_descs)

    action_list = list(action_descs.keys())
    desc_list = [action_descs[a] for a in action_list]
    qe = m.encode([p[0] for p in PROBES], convert_to_tensor=True, device="cpu", show_progress_bar=False)
    de = m.encode(desc_list, convert_to_tensor=True, device="cpu", show_progress_bar=False)
    sims = cos_sim(qe, de)
    rows, hit = [], 0
    for i, (query, exp) in enumerate(PROBES):
        top5 = [action_list[idx] for idx in sims[i].topk(5).indices.tolist()]
        ok = exp in top5
        hit += ok
        rows.append((query, exp, ok, top5[0]))
    return res, hit, rows


def main():
    A, B = sys.argv[1], sys.argv[2]
    test_pairs, all_codes, action_descs = build_split()
    print(f"[비교] test 쌍 {len(test_pairs)}, 고유 패턴 {len(set(all_codes))}, 액션desc {len(action_descs)}\n")

    print("########## A (현 라이브/백업) ##########")
    resA, hitA, rowsA = eval_model(A, test_pairs, all_codes, action_descs)
    print("\n########## B (새 모델) ##########")
    resB, hitB, rowsB = eval_model(B, test_pairs, all_codes, action_descs)

    print("\n================= 요약 (aggregate, 동일 test 분할) =================")
    for label, r in (("A 라이브", resA), ("B 새모델", resB)):
        ph = r.get("phrase") or {"n": 0}
        ph_s = f"phrase T5 = {ph[5]:.1f} (n={ph['n']})" if ph.get("n") else "phrase n=0"
        print(f"  {label}: code T1/3/5 = {r[1]:.1f}/{r[3]:.1f}/{r[5]:.1f}  | "
              f"desc T1/3/5 = {r['desc'][1]:.1f}/{r['desc'][3]:.1f}/{r['desc'][5]:.1f}  | {ph_s}")
    print(f"\n  Δ desc-Top5 (B-A): {resB['desc'][5]-resA['desc'][5]:+.1f}p  | "
          f"Δ code-Top5: {resB[5]-resA[5]:+.1f}p  | Δ desc-Top1: {resB['desc'][1]-resA['desc'][1]:+.1f}p")

    print(f"\n================= 신어휘 프로브 ({len(PROBES)}개) =================")
    print(f"  A 적중: {hitA}/{len(PROBES)}   B 적중: {hitB}/{len(PROBES)}   Δ: {hitB-hitA:+d}")
    print(f"  {'질의':28} {'기대':22} A  B")
    for (q, exp, okA, _), (_, _, okB, _) in zip(rowsA, rowsB):
        print(f"  {q:28} {exp:22} {'✓' if okA else '✗'}  {'✓' if okB else '✗'}")

    print("\n================= 권고 =================")
    desc5_win = resB['desc'][5] >= resA['desc'][5]
    no_regress = resB['desc'][5] >= resA['desc'][5] - 0.5 and resB[5] >= resA[5] - 0.5
    probe_win = hitB > hitA
    # 관용구 회귀 없음(2026-09-04, docs/IBL_IDIOM_TIER_HANDOFF.md §2-d): 관용구 쌍이 있으면 그 Top-5 가
    # 0.5p 넘게 떨어진 모델은 채택하지 않는다 — 낱말 지표가 좋아도 관용구 회상을 잃으면 사다리 한 칸이 무너진다.
    phA, phB = resA.get("phrase") or {"n": 0}, resB.get("phrase") or {"n": 0}
    phrase_ok = (not phA.get("n")) or (phB.get(5) is not None and phB[5] >= phA[5] - 0.5)
    if not phrase_ok:
        print(f"  → 보류 권고: 관용구 Top-5 회귀 ({phA[5]:.1f} → {phB[5]:.1f}, n={phA['n']}). 현 모델 유지.")
    elif desc5_win:
        print("  → 채택 권고: B가 aggregate desc-Top5에서 동급 이상" + (" (관용구 회귀 없음)." if phA.get("n") else "."))
    elif probe_win and no_regress:
        print("  → 채택 권고: aggregate 회귀 미미 + 신어휘 프로브 개선.")
    else:
        print("  → 보류 권고: aggregate 회귀 + 프로브 개선 불충분. 현 모델 유지.")


if __name__ == "__main__":
    main()
