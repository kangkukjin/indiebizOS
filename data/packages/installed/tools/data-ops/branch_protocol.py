"""union/merge 죽은 분기 규약 (2026-08-30 언어 개정, ep2355) — handler.py 형제 모듈.

★같은 죽음이 두 대접을 받았다: items:[] 를 실은 에러 봉투는 B24-1(c)가 0행+경고로
흘려보내는데, items 조차 없는 에러 봉투(crawl insufficient_content 실측)는
"통화 종류가 같아야 합니다" **오진**으로 전체를 죽였다. 죽은 분기의 대접은 한 벌:
기본 = 건너뛰고 신고(부분 결합, B24-1c 의미론의 확장), on_error:"stop" = 전부-아니면-실패.
통화를 실은 실패 봉투(items:[])는 종전대로 산 분기로 남아 _attach_branch_warning 이
신고한다(동작 불변).

_get_items/_get_table 은 handler 소유라 주입받는다(형제 → handler 역참조 금지).
"""


def split_dead_branches(objs, get_items, get_table):
    """분기 목록에서 '죽은 분기'(통화 없는 실패 봉투)를 가른다 → (산 분기, [{branch, error}])."""
    live, dead = [], []
    for i, o in enumerate(objs, 1):
        failed = isinstance(o, dict) and (o.get("success") is False
                                          or (o.get("error") and o.get("success") is not True))
        has_currency = (get_items(o)[0] is not None) or (get_table(o)[0] is not None)
        if failed and not has_currency:
            dead.append({"branch": i,
                         "error": str(o.get("error") or o.get("reason") or "실패 봉투")[:300]})
        else:
            live.append(o)
    return live, dead


def handle_dead_branches(op_name, objs, params, get_items, get_table):
    """union/merge 공용 — 죽은 분기 처리. 반환: (산 분기 목록, 죽은 분기 정보, 에러 dict|None)."""
    on_error = str(params.get("on_error") or "skip").strip().lower()
    if on_error not in ("skip", "stop"):
        return objs, [], {"success": False,
                          "error": f'{op_name}: on_error 는 "skip"(기본, 죽은 분기 건너뛰고 신고)'
                                   f' | "stop"(하나라도 실패면 전체 실패) 중 하나입니다: {on_error!r}'}
    live, dead = split_dead_branches(objs, get_items, get_table)
    if not dead:
        return objs, [], None
    if on_error == "stop":
        return objs, dead, {
            "success": False,
            "error": f"{op_name}: 분기 {len(objs)}개 중 {len(dead)}개가 실패했습니다(on_error:stop) — "
                     f"통화 불일치가 아니라 분기 실패입니다. 산 분기만 합치려면 on_error 를 빼세요(기본 skip).",
            "branches_failed": dead}
    if not live:
        return objs, dead, {
            "success": False,
            "error": f"{op_name}: 분기 {len(objs)}개가 전부 실패했습니다 — 합칠 산 분기가 없습니다.",
            "branches_failed": dead}
    return live, dead, None


def currency_kinds(objs, get_items, get_table):
    """분기별 통화 이름표 — 진짜 혼합 에러의 자가교정 단서 ("1=table, 2=없음(스칼라/평문)")."""
    kinds = []
    for i, o in enumerate(objs, 1):
        has_t = get_table(o)[0] is not None
        has_i = get_items(o)[0] is not None
        k = ("table+items" if has_t and has_i else
             "table" if has_t else "items" if has_i else "없음(스칼라/평문)")
        kinds.append(f"{i}={k}")
    return ", ".join(kinds)


def attach_dead_note(env, dead, total):
    """부분 결합의 정직 신고 — 건너뛴 분기를 구조(branches_skipped)와 경고 양쪽에 싣는다."""
    if not dead or not isinstance(env, dict):
        return env
    note = (f"분기 {total}개 중 {len(dead)}개가 실패해 건너뛰었습니다"
            f"(분기 {', '.join(str(d['branch']) for d in dead)}) — 결과는 부분입니다.")
    prev_w = env.get("warning")
    return {**env, "branches_skipped": dead,
            "warning": (prev_w + " / " + note) if prev_w else note}
