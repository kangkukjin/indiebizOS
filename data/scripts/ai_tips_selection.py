"""영상 출처와 반응 지표의 표시. 미확인 수치는 0으로 만들지 않는다."""

METRICS = ("view_count", "like_count", "comment_count", "channel_follower_count")

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

def popularity_text(video):
    labels = {"view_count": "조회", "like_count": "좋아요", "comment_count": "댓글", "channel_follower_count": "채널 구독자"}
    values = [label + " " + (f"{video[key]:,}" if type(video.get(key)) is int else "미확인")
              for key, label in labels.items()]
    return " · ".join(values) + " (조회 시점: " + (video.get("observed_at") or "미확인") + ")"
