"""tool_watch.py — 유튜브 시청 앱(yttv 계기)의 조회 면: 추천 피드·시청 페이지·시청 기록.

재생 자체는 서버 릴레이(/yt/relay, backend/api_ytrelay.py — 유튜브 직접 접속 없는
받으면서-서빙)가 담당하고, 여기는 '무엇을 볼지'를 만든다.

추천의 정직한 경계: 유튜브 계정의 개인화 추천은 로그인 쿠키 없인 불가, 인기 급상승
페이지는 2025년 유튜브가 제거(실측: home 으로 redirect). 그래서 피드는 전부
비로그인 재료로 짠다 —
  ① 시청 기록의 채널 최신 영상 (채널 RSS, 로그인 불요·빠름)
  ② 시청 제목 연관 검색 (yt-dlp ytsearch)
  ③ 콜드스타트(기록 없음): 기본 카테고리 검색 믹스
시청 기록은 릴레이 서버가 재생 시점에 쌓는다(data/youtube_watch.json) —
시청할수록 피드가 개인화되는 자기강화 루프.
"""

import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

WATCH_LOG = Path(__file__).resolve().parents[4] / "youtube_watch.json"

# 콜드스타트 기본 카테고리 — 기록이 쌓이면 자연히 밀려난다
DEFAULT_QUERIES = ["오늘 주요 뉴스", "인기 뮤직비디오", "다큐멘터리", "여행 브이로그", "스포츠 하이라이트", "요리 레시피"]

_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"


def _thumb(vid: str) -> str:
    return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"


def _fmt_dur(seconds) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _read_log() -> list:
    try:
        with open(WATCH_LOG, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _clean_title(title: str) -> str:
    """제목 → 연관 검색어. 괄호 장식([MV]·(Official…)·【】)과 상투어를 벗기고 앞말만."""
    t = re.sub(r"[\[\(【][^\]\)】]*[\]\)】]", " ", title or "")
    t = re.sub(r"(?i)\b(official|video|lyrics|가사|mv|m/v|full|hd|4k|shorts)\b", " ", t)
    t = re.sub(r"[|/·—-]+", " ", t)
    words = t.split()
    return " ".join(words[:5]).strip()


def _ytsearch(query: str, n: int = 4) -> list:
    """yt-dlp flat 검색 → 통일 항목. 실패는 빈 목록(피드는 소스 하나쯤 죽어도 산다)."""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
            result = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
        items = []
        for e in result.get("entries") or []:
            vid = e.get("id") or ""
            if not vid or vid.startswith("UC") or len(vid) > 16:
                continue
            items.append({
                "video_id": vid,
                "title": e.get("title", ""),
                "channel": e.get("channel", e.get("uploader", "")) or "",
                "duration": _fmt_dur(e.get("duration")),
                "thumb": _thumb(vid),
            })
        return items
    except Exception:
        return []


def _rss_latest(channel_id: str, channel_name: str, n: int = 4) -> list:
    """채널 RSS(Atom) 최신 영상 — 로그인 불요, ~300ms. 실패는 빈 목록."""
    try:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        with urllib.request.urlopen(url, timeout=6) as r:
            root = ET.fromstring(r.read())
        items = []
        for entry in root.findall(f"{_ATOM}entry")[:n]:
            vid = entry.findtext(f"{_YT}videoId") or ""
            if not vid:
                continue
            items.append({
                "video_id": vid,
                "title": entry.findtext(f"{_ATOM}title") or "",
                "channel": channel_name,
                "duration": "",
                "thumb": _thumb(vid),
            })
        return items
    except Exception:
        return []


def feed(limit: int = 24) -> dict:
    """추천 홈 피드 — 시청 기록 기반(채널 RSS + 연관 검색), 기록 없으면 콜드스타트."""
    log = [e for e in reversed(_read_log()) if e.get("kind") == "video"]  # 최신 먼저
    watched = {e.get("video_id") for e in log}

    # 시청 기록에서 재료 추출 — 채널(최신순 dedup 4개)·주제(제목 3개)
    channels, seen_ch = [], set()
    for e in log:
        cid = e.get("channel_id")
        if cid and cid not in seen_ch:
            seen_ch.add(cid)
            channels.append((cid, e.get("channel") or ""))
        if len(channels) >= 4:
            break
    topics, seen_t = [], set()
    for e in log:
        q = _clean_title(e.get("title") or "")
        if q and q not in seen_t:
            seen_t.add(q)
            topics.append(q)
        if len(topics) >= 3:
            break

    cold = not (channels or topics)
    tasks = []   # (label, callable)
    if cold:
        for q in DEFAULT_QUERIES:
            tasks.append((f"검색 · {q}", lambda q=q: _ytsearch(q, 4)))
    else:
        for cid, name in channels:
            tasks.append((f"구독 · {name}", lambda cid=cid, name=name: _rss_latest(cid, name, 4)))
        for q in topics:
            tasks.append((f"연관 · {q}", lambda q=q: _ytsearch(q, 4)))

    buckets = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fn): label for label, fn in tasks}
        for fut in as_completed(futs):
            label = futs[fut]
            got = fut.result() or []
            for it in got:
                it["src"] = label
            if got:
                buckets.append(got)

    # 라운드로빈 병합 — 한 소스가 피드를 독점하지 않게. 본 것·중복 제외.
    items, seen = [], set(watched)
    idx = 0
    while len(items) < limit and any(idx < len(b) for b in buckets):
        for b in buckets:
            if idx < len(b):
                it = b[idx]
                if it["video_id"] not in seen:
                    seen.add(it["video_id"])
                    items.append(it)
                    if len(items) >= limit:
                        break
        idx += 1

    if cold:
        msg = f"추천 {len(items)}건 — 아직 시청 기록이 없어 기본 카테고리로 채웠습니다. 보실수록 채널·주제 기반으로 개인화됩니다."
    else:
        msg = f"추천 {len(items)}건 — 최근 본 채널 {len(channels)}곳의 새 영상 + 본 주제 연관 검색."
    return {"success": True, "items": items, "message": msg}


def _prewarm_relay(video_id: str) -> None:
    """릴레이 해소 예열(fire-and-forget) — 시청 페이지를 여는 동안 백그라운드에서
    화질 사다리를 미리 해소해 두면(45분 캐시) 재생 버튼이 거의 즉시 시작된다
    (HLS master·세그먼트가 같은 사다리 캐시를 문다). 폰 프로파일 등 api_ytrelay 가
    없는 몸에선 조용히 건너뛴다(재생 시 자체 해소)."""
    def _run():
        try:
            import api_ytrelay
            try:
                api_ytrelay._resolve_ladder(video_id)      # HLS 적응형 (기본 경로)
            except Exception:
                api_ytrelay._resolve_cached(video_id, "video")   # 사다리 없는 영상 — 프로그레시브 폴백
        except Exception:
            pass
    import threading
    threading.Thread(target=_run, daemon=True).start()


def watch(video_id: str) -> dict:
    """시청 페이지 — 릴레이 스트림을 문 플레이어 한 편 + 연관 동영상 목록."""
    _prewarm_relay(video_id)
    title, channel, dur = video_id, "", ""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True,
                               "extract_flat": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        title = info.get("title") or video_id
        channel = info.get("channel") or info.get("uploader") or ""
        dur = _fmt_dur(info.get("duration"))
    except Exception:
        pass   # 메타 실패해도 재생은 된다(릴레이가 자체 해소)

    item = {
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "duration": dur,
        "stream": f"/yt/relay/{video_id}?kind=video",
        # 저대역 판(≤480p) — 느린 회선 표면(테슬라)이 자동 선택(media_player src_low)
        "stream_low": f"/yt/relay/{video_id}?kind=video&q=low",
        # 적응형(HLS) — hls.js 있는 표면은 이걸 우선(조각마다 화질 자동 전환, 넷플릭스식)
        "stream_hls": f"/yt/hls/{video_id}/master.m3u8",
        "thumb": _thumb(video_id),
        "is_video": True,
    }
    q = _clean_title(title) or channel or title
    related = [r for r in _ytsearch(q, 10) if r["video_id"] != video_id][:8]
    return {"success": True, "items": [item], "related": related,
            "message": f"{title} · 연관 {len(related)}건"}


def history(limit: int = 40) -> dict:
    """시청 기록 — 최신 먼저, 같은 영상은 한 번만."""
    items, seen = [], set()
    for e in reversed(_read_log()):
        if e.get("kind") != "video":
            continue
        vid = e.get("video_id") or ""
        if not vid or vid in seen:
            continue
        seen.add(vid)
        ts = (e.get("ts") or "")[:16].replace("T", " ")
        items.append({
            "video_id": vid,
            "title": e.get("title") or vid,
            "channel": e.get("channel") or "",
            "duration": ts,   # 카드 둘째 줄 자리 — 본 시각이 더 유용
            "thumb": _thumb(vid),
        })
        if len(items) >= limit:
            break
    msg = f"시청 기록 {len(items)}건" if items else "아직 시청 기록이 없습니다 — 홈이나 검색에서 영상을 보면 여기 쌓입니다."
    return {"success": True, "items": items, "message": msg}
