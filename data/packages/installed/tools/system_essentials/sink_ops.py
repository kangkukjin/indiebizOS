"""파이프 싱크 — [self:write] 의 본체 (2026-09-02, 1500줄 규칙으로 handler.py 에서 분리).

경로 해소(resolve_output_path)·RED 격리(_red_stage)는 handler 가 끝내고 여기엔 **쓸 경로와 내용**만 온다.
11회차 규칙(message 있으면 산문)·F18-2(자백된 형제 제외)·B53-4(정직 표지 제외)·V53-1 ⓑ(format:"json"
통화 보존 스위치)·스필 싱크가 이 한 함수에 산다 — 싱크의 규약이 한 자리에 있어야 다음 변경이 갈라지지 않는다.
"""
import json
import os


def write_sink(tool_input: dict, path: str, _live_target: str, redirected: bool, *,
               _red_write_prepare, _red_write_finalize, _vocab_enforce) -> str:
    """쓸 경로가 정해진 뒤의 싱크 본체. 반환 = 결과 봉투 JSON 문자열(핸들러 계약)."""
    content = tool_input.get("content")  # 파이프 싱크(구 output op:file 흡수 2026-08-05): 생략 시 _prev_result, ""는 유효
    piped = False
    # ★V53-1 ⓑ (2026-09-02 사용자 판정): `format: "json"` = 통화 보존 스위치. 파이프 싱크의
    #   텍스트/JSON 갈림(11회차 규칙 — message 가 있으면 산문)은 그대로 두고, 이 스위치가
    #   있을 때만 통화(items)를 JSON 원장으로 쓴다(원장 누적 관용구의 첫 저장이 이것으로 선다).
    _fmt = str(tool_input.get("format") or "").strip().lower()
    _json_mode = _fmt == "json"
    if content is None:
        content = tool_input.get("_prev_result")
        piped = content is not None
        if piped:
            # 스필 참조 봉투(M5)면 본문을 저장 — 참조 JSON 이 파일이 되면 침묵 오답
            try:
                from common.spill import resolve_ref_str
                _resolved, _ref_err = resolve_ref_str(content)
                if _ref_err:
                    return json.dumps({"success": False, "error": _ref_err}, ensure_ascii=False)
                content = _resolved
            except ImportError:
                pass
    if content is None:
        return json.dumps({"success": False, "error": "content가 필요합니다 (파이프에서는 직전 step 결과가 자동 저장됨)."}, ensure_ascii=False)
    extracted = None
    items_alongside = None
    probe = None
    if piped:
        probe = content
        if isinstance(probe, str):
            try:
                probe = json.loads(probe)
            except Exception:
                probe = None
    if piped and not _json_mode:
        # ★2026-08-17 상상훈련 11회차 판정: 파이프 통화에 message(str)가 실존하면
        # 그것이 산문 정본이다 — _emit_items 가 변환 때 message 를 pop 하는 이유가
        # 바로 "message=현재 내용의 산문판" 계약이라, message 를 두고 봉투 JSON 을
        # 쓰면 원시 배관이 파일이 된다(devdocs 검색 저장이 {"success": true, ...}
        # 8.5KB 봉투가 되던 꼬임 실측). 변환 뒤 봉투(message 없음)·items 만 내는
        # 생산자는 현행(JSON=구조가 내용) 유지. 명시 content 는 건드리지 않고,
        # 추출·동반 items 는 결과에 신고(침묵 변형 금지).
        if (isinstance(probe, dict) and isinstance(probe.get("message"), str)
                and probe["message"].strip()):
            # ★12회차 정련 v4 (스텁 감사 판정 2026-08-17): 짧은 한 줄 message+items 는
            # 계약 위반이 아니라 생산자 요약 관례("총 20건" — 내용=items)라 봉투 JSON
            # 유지가 정답. message 추출은 message 가 *문서 모양*(다행 또는 장문)이고
            # items 밖 dict/list 페이로드가 없을 때만(devdocs 문서·entity 산문 목록 부류).
            # 오분류는 항상 안전 방향(JSON=구조 보존)으로 떨어진다.
            _msg = probe["message"]
            _other_payload = any(
                isinstance(v, (dict, list)) and v
                for k, v in probe.items() if k != "items")
            _doc_shaped = ("\n" in _msg.strip()) or (len(_msg) >= 200)
            # ★2026-08-21: AI 산문 emitter([table:brief] 등, _ai:true)의 message 는 길이와
            # 무관하게 산문 정본 — 2문장 brief(190자)가 봉투 JSON 으로 저장되던 구멍.
            _ai_prose = bool(probe.get("_ai")) and not isinstance(probe.get("items"), list)
            if not _other_payload and (_doc_shaped or _ai_prose):
                if isinstance(probe.get("items"), list) and probe["items"]:
                    items_alongside = len(probe["items"])
                content = _msg
                extracted = "message"
    # ★F18-2 (2026-08-22 상상훈련 18회차): 변환자는 따라오지 못한 형제 컬렉션을
    #   `_untransformed` 로 **자백**한다(2026-08-20 판정된 설계). 그 자백을 싱크가
    #   안 읽으면 "골라서 저장"이 **전량 저장**이 된다 — 실측: trigger list >> filter
    #   >> write 가 필터에서 걸러낸 WorldPulse 항목을 파일에 그대로 박았다.
    #   B15-1("골라서 알림"이 전량 발송)의 저장판이라 같은 규율로 닫는다.
    #   버리는 게 아니라 **이번 저장의 대상이 아님**을 밝히고 빼는 것이라, 무엇을
    #   뺐는지 결과에 신고한다(침묵 변형 금지 — 이 파일의 extracted 신고와 동형).
    excluded_untransformed = None
    if piped and extracted is None and isinstance(probe, dict):
        _untouched = [k for k in (probe.get("_untransformed") or []) if k in probe]
        if _untouched:
            content = {k: v for k, v in probe.items() if k not in _untouched}
            excluded_untransformed = sorted(_untouched)
            content["_untransformed_excluded"] = excluded_untransformed
    # ★B53-4 (53회차 상상훈련, 2026-09-02): 정직 표지(warning·_untransformed·errors…)와
    #   `_`메타는 **한 실행의 사실**이지 원장의 내용이 아니다 — 파일에 남기면 다음 [self:read]
    #   가 옛 경고를 현재 사건처럼 다시 낸다(실측: 평범한 읽기에 "분기 2개 중 1개가 실패").
    #   위 F18-2 가 `branches_skipped` 하나만 손으로 뺐던 것이 부류의 씨앗(손 목록은 샌다) —
    #   목록의 정본은 ibl_honesty.HONESTY_KEYS 다.
    excluded_meta = None
    if piped and extracted is None and isinstance(probe, dict):
        _c = content if isinstance(content, dict) else dict(probe)
        content, excluded_meta = _strip_envelope_meta(_c)
    if _json_mode:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                return json.dumps({"success": False, "error": (
                    "format: \"json\" 인데 content 가 JSON 이 아닙니다 — 통화(items)를 저장하려면 "
                    "파이프 싱크(… >> [self:write]{path, format: \"json\"})로 주거나 JSON 문자열을 주세요.")},
                    ensure_ascii=False)
        if isinstance(content, dict):
            try:
                from common.currency import derive_items as _derive_items
                _d = _derive_items(dict(content))
            except ImportError:
                _d = content
            if isinstance(_d, dict) and isinstance(_d.get("items"), list):
                content = {"items": _d["items"], "count": len(_d["items"])}
            else:
                content, _m2 = _strip_envelope_meta(content)
                if _m2:
                    excluded_meta = sorted(set(excluded_meta or []) | set(_m2))
        elif isinstance(content, list):
            content = {"items": content, "count": len(content)}
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2) if isinstance(content, (dict, list)) else str(content)
    _red_err = _red_write_prepare(path, content)  # 그랜트된 RED 쓰기 안전판(구문검증+백업)
    if _red_err:
        return _red_err
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    _red_write_finalize(path)  # backend .py 면 워치독(헬스체크·자동 롤백) 보장
    # 쓰기 관문 원장 — 행위자 동반 사건 기록(관측일 뿐, 실패해도 본 쓰기 무영향)
    try:
        from write_ledger import log_write
        log_write(path, event="write", gate="self_write", size=len(content))
    except Exception:
        pass
    abs_path = os.path.abspath(path)
    result = {"success": True, "path": abs_path, "size": len(content)}
    if _json_mode:
        result["format"] = "json"
    if excluded_meta:
        result["excluded_meta"] = excluded_meta   # 원장에서 뺀 실행 메타·정직 표지(신고, B53-4)
    if (_vg := _vocab_enforce(path)):   # 어휘 빌드 입력이면 파생물 재생성(09-01)
        result["live_derived"] = _vg
    if path != _live_target:   # 격리 사본에 쌓였다 — 라이브는 아직 무변경
        result.update({
            "staged": True, "live_path": os.path.abspath(_live_target),
            "note": ("격리 사본에 기록했습니다 — 라이브는 무변경입니다(리로드 없음). "
                     "검증 후 실제로 반영하려면 [self:patch]{op:\"apply\"} 를 "
                     "호출하세요. 적용하지 않으면 이 수정은 라이브에 없습니다."),
        })
    if excluded_untransformed:
        result["excluded_untransformed"] = excluded_untransformed
        result["note"] = (f"변환을 따라오지 못한 형제 키 {', '.join(excluded_untransformed)} 는 "
                          "저장에서 제외했습니다(필터 밖 항목이 파일에 섞이지 않게). "
                          "원본째 저장하려면 앞 step 결과를 content 로 명시하세요.")
    if extracted:
        result["extracted"] = extracted  # message 본문만 저장했음을 신고
        if items_alongside:
            result["note"] = (f"동반 items {items_alongside}건은 저장하지 않았습니다 — "
                              "통화(items)를 JSON 원장으로 저장하려면 format: \"json\" 을 주세요"
                              "(표·문서 산출은 table:spreadsheet/structure).")
    if redirected:
        result["redirected_to"] = "outputs/"
    if tool_input.get("spill"):
        # 스필 싱크 (2026-08-22 프로그램급 IBL M1 / 설계 §2.5-1): 뒤 step 에는 통화 대신
        # *참조*만 흐른다 — {items: [], ref: {path, kind, count, bytes}}. 다음 step 이 데이터가
        # 필요하면 [self:read]{path} 로 재개(결정론). 자동 ref 해소는 M5(변환자 _get_items).
        _kind = "text"
        _count = None
        if piped and isinstance(probe, dict) and isinstance(probe.get("items"), list) and extracted is None:
            _kind, _count = "items", len(probe["items"])
        elif extracted == "message":
            _kind = "message"
        result["items"] = []
        result["ref"] = {"path": abs_path, "kind": _kind, "count": _count, "bytes": len(content)}
        result["spilled"] = True
    return json.dumps(result, ensure_ascii=False)




def _strip_envelope_meta(d: dict):
    """저장 직전의 봉투에서 **실행 메타·정직 표지**를 뺀다 (B53-4, 2026-09-02).

    표지의 수명은 한 실행이다 — 파일이 그것을 영구화하면 다음 [self:read] 가 옛 경고를
    현재 사건처럼 낸다. 무엇을 뺐는지는 호출부가 `excluded_meta` 로 신고한다(침묵 변형 금지).
    목록의 정본은 ibl_honesty.HONESTY_KEYS 하나(손 목록 금지 — check_honesty_propagation 규칙 [A]);
    `warning` 은 표지의 엔진 번역문, `_`접두는 엔진 메타라 함께 뺀다.
    """
    try:
        from ibl_honesty import HONESTY_KEYS as _hk
    except ImportError:
        _hk = ()
    drop = [k for k in d if k in _hk or k == "warning" or str(k).startswith("_")]
    if not drop:
        return d, None
    return {k: v for k, v in d.items() if k not in drop}, sorted(drop)
