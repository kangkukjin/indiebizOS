"""출처·반응 지표를 영상 선별부터 팁의 가치 판단까지 인계한다. 순위는 AI가 판단한다."""

METRICS = ("view_count", "like_count", "comment_count", "channel_follower_count")
SOURCE_RULE = (
    "누구의 팁인지와 영상의 인기를 팁 가치의 판단 재료로 사용한다. "
    "채널·업로더는 발행자이며 영상 속 발언자와 동일하다고 단정하지 않는다. "
    "설명문은 발행자의 자기소개·자기주장이고 excerpt는 일부다. 확인된 전문성·실무 경험·"
    "원저자/직접 시연·근거 제시와 재전달/홍보 여부를 구분하며 모르는 경력·평판·소속을 만들지 않는다. "
    "조회수·좋아요·댓글·구독자와 업로드 후 경과일을 함께 보고 주제·언어·채널 규모도 고려한다. "
    "숫자만으로 고정 순위를 매기지 않으며 반응 지표는 인기의 단서이지 정확성이나 효용의 증명이 아니다. "
    "인증 표시는 신원 신호일 뿐 전문성 보증이 아니다. null은 미확인, 0은 확인된 0이다. "
    "미확인을 낮은 인기나 낮은 신뢰도로 바꾸지 말고 판단 한계로 남긴다. "
)


def source_fields(info):
    """원본은 input-metadata에 남는다. AI용 설명 발췌의 범위를 명시한다."""
    fields = {key: info.get(key) if type(info.get(key)) is int and info[key] >= 0 else None
              for key in METRICS}
    fields.update({key: info.get(key) if isinstance(info.get(key), str) else None for key in (
        "channel_id", "channel_url", "uploader_id", "uploader_url", "observed_at")})
    fields["channel_is_verified"] = (info.get("channel_is_verified")
                                     if type(info.get("channel_is_verified")) is bool else None)
    description = info.get("description")
    description = description if isinstance(description, str) else ""
    fields.update(description_excerpt=description[:1200], description_chars=len(description),
                  description_truncated=len(description) > 1200)
    return fields


def metadata(h, state, data):
    expected = {r["video_id"]: r for r in state["search"]["candidates"]}
    received = h.keyed(h.rows(data, failures=True), "video_id", expected)
    metadata, excluded = [], []
    today = h.date(state["config"]["date"])
    for vid, wrapper in received.items():
        try:
            infos = h.rows(wrapper.get("data")) if not wrapper.get("_error") else []
            h.require(len(infos) == 1, "영상 정보 1건 필요")
            info = infos[0]
            h.require(info.get("video_id", vid) == vid, "메타데이터 ID 변경")
            uploaded = h.text_field(info, "upload_date")
            age = (today - h.date(uploaded)).days
            duration = info.get("duration")
            h.require(isinstance(duration, (int, float)) and not isinstance(duration, bool)
                      and duration > 0, "길이 미확인")
            row = {"video_id": vid, "title": h.text_field(info, "title"),
                   "channel": info.get("channel") or info.get("uploader"),
                   "uploader": info.get("uploader"),
                   "url": "https://www.youtube.com/watch?v=" + vid,
                   "upload_date": uploaded, "age_days": age, "duration": duration,
                   "strata": expected[vid]["strata"], **source_fields(info)}
            h.text_field(row, "channel")
            if age < 0 or age > 180:
                excluded.append({**row, "verdict": "too_old" if age > 180 else "not_selected",
                                 "note": "허용 날짜 범위 밖"})
            else:
                metadata.append(row)
        except (ValueError, TypeError) as exc:
            excluded.append({"video_id": vid, "verdict": "not_selected", "metadata_error": str(exc),
                             "note": "메타데이터 확인 실패: " + str(exc)})
    h.require(len(metadata) >= 2, "180일 내 날짜가 확인된 새 영상이 2편 미만입니다")
    state["metadata"], state["excluded"] = metadata, excluded
    state["selection_policy"] = 2
    # 후보를 잘라내지 않고 설명 발췌 길이를 공평하게 조절한다. 원 수치·신원은 전부 전달한다.
    for chars in (600, 300, 150, 0):
        videos = [{**r, "description_excerpt": r["description_excerpt"][:chars],
                   "description_truncated": r["description_chars"] > chars} for r in metadata]
        request = h.task(state, "videos",
            "새 영상을 2~4편 고른다. result={selected:[영상ID],decisions:[{video_id,reason,"
            "source_assessment,popularity_assessment}]}. 모든 후보에 reason을 적는다. "
            "선정한 영상에는 source_assessment와 popularity_assessment를 각각 짧고 구체적인 한 문장으로 적는다. "
            "제외 영상은 두 평가 필드를 생략할 수 있으며 결정적 출처·인기 근거를 reason에 압축한다. "
            + SOURCE_RULE +
            "출처가 분명하고 신뢰 근거·독자 반응이 좋은 관련 영상을 우선 검토하되 "
            "소규모 전문 채널·새 영상에 더 좋은 실행법이 있으면 그 이유를 들어 고를 수 있다. "
            "최근성·독자에게 새로운 실행법·초보 관점도 고려한다. 검색 층을 섞고 관련 회의적 관점이 있으면 포함한다. "
            "60분 초과는 최대 1편. 제목·설명·인기만으로 팁의 실재를 확정하지 말고 자막 검토 대상으로 선정한다.",
            {"topic": state["config"]["topic"], "videos": videos})
        if h.request_size(request["items"][0]) < h.REQUEST_CAP:
            return request
    raise ValueError("영상의 출처·인기 기본정보가 선정 입력 상한을 넘습니다. 후보를 임의로 누락하지 않습니다")


def assessments(h, state, row, *, tip=False):
    if state.get("selection_policy", 1) >= 2:
        for field in ("source_assessment", "popularity_assessment", *(('value_assessment',) if tip else ())):
            h.text_field(row, field)


def videos(h, state, data):
    result = h.answer(data)
    selected = result.get("selected")
    h.require(isinstance(selected, list) and 2 <= len(selected) <= 4, "선정 영상은 2~4편")
    h.require(len(set(selected)) == len(selected), "선정 영상 중복")
    meta = h.keyed(state["metadata"], "video_id")
    h.require(set(selected) <= set(meta), "미확인 영상 선정")
    decisions = h.keyed(result.get("decisions", []), "video_id", meta)
    for row in decisions.values():
        h.text_field(row, "reason")
        if row["video_id"] in selected:
            assessments(h, state, row)
    h.require(sum(meta[v]["duration"] > 3600 for v in selected) <= 1, "60분 초과 영상은 최대 1편")
    strata = {s for v in selected for s in meta[v]["strata"]}
    h.require(len(strata) >= 2, "한 검색 층만 선정됐습니다")
    state["videos"] = [meta[v] for v in selected]
    state["video_decisions"] = decisions
    return {"items": state["videos"], "count": len(selected)}


def profiles(state):
    return [{**v, "selection_assessment": state.get("video_decisions", {}).get(v["video_id"])}
            for v in state["videos"]]


def tip_assessments(state, ids):
    return {cid: row for cid, row in state.get("tip_decisions", {}).items() if cid in ids}


def popularity_text(video):
    labels = {"view_count": "조회", "like_count": "좋아요", "comment_count": "댓글", "channel_follower_count": "채널 구독자"}
    values = [label + " " + (f"{video[key]:,}" if type(video.get(key)) is int else "미확인")
              for key, label in labels.items()]
    return " · ".join(values) + " (조회 시점: " + (video.get("observed_at") or "미확인") + ")"
