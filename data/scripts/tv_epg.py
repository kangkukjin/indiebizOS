"""KT 편성표: TV 제어와 독립적인 공개 방송 정보·날짜별 캐시."""
import json
import os
import time
import urllib.request
from pathlib import Path

CACHE_ROOT = Path(os.environ.get("INDIEBIZ_BASE_PATH", ".")) / "data" / "tv_epg"

EPG_URL = "https://tv.kt.com/tv/channel/pSchedule.asp"
EPG_SCAN_MAX = 999
EPG_PAGE_SIZE = 40
EPG_LEDGER_DAYS = 30      # 원장이 이보다 오래되면 epg_now 가 다시 훑는다


def _strip(x):
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()


def epg_fetch(ch, day):
    import re, urllib.parse
    data = urllib.parse.urlencode({"ch_type": 1, "view_type": 1, "service_ch_no": ch, "seldate": day}).encode()
    h = urllib.request.urlopen(EPG_URL, data, timeout=15).read().decode("utf-8", "replace")
    m = re.search(r'([^<>"]+) 일간 편성표\|', h)
    progs = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        tds = re.findall(r'<td class="(\w+)">(.*?)</td>', tr, re.S)
        if len(tds) < 3:
            continue
        cats = [_strip(x) for x in re.findall(r"<p>(.*?)</p>", tds[3][1], re.S)] if len(tds) > 3 else []
        mins = [_strip(x) for x in re.findall(r"<p>(.*?)</p>", tds[1][1], re.S)]
        titles = [_strip(x).replace("방송중", "").strip() for x in re.findall(r"<p>(.*?)</p>", tds[2][1], re.S)]
        for i, (mm, t) in enumerate(zip(mins, titles)):
            progs.append({"start": "%s:%s" % (_strip(tds[0][1]), mm), "title": t,
                          "genre": cats[i] if i < len(cats) else ""})
    return {"ch": ch, "name": _strip(m.group(1)) if m else str(ch), "programs": progs}


def _epg_dir():
    d = os.path.join(str(CACHE_ROOT), "epg_cache"); os.makedirs(d, exist_ok=True)
    return d


def _save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def epg_scan(day):
    """채널 원장 — 편성 행이 1개 이상인 번호만 채널로 친다(빈 표도 HTTP 200). 실패 번호는 failed 로 따로."""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    def one(c):
        try:
            return c, epg_fetch(c, day), None
        except Exception as e:
            return c, None, "%s: %s" % (type(e).__name__, e)
    found, failed = {}, {}
    with ThreadPoolExecutor(32) as ex:
        for c, v, err in ex.map(one, range(1, EPG_SCAN_MAX + 1)):
            if err:
                failed[str(c)] = err
            elif v["programs"]:
                found[str(c)] = v
    ledger = {"scanned_at": time.strftime("%Y-%m-%d %H:%M"), "range": [1, EPG_SCAN_MAX],
              "channels": [{"ch": int(c), "name": v["name"]} for c, v in sorted(found.items(), key=lambda x: int(x[0]))],
              "failed": failed, "seconds": round(time.time() - t0, 1)}
    _save_json(os.path.join(_epg_dir(), "channels.json"), ledger)
    path = os.path.join(_epg_dir(), day + ".json")  # 훑으며 받은 오늘 편성도 그대로 캐시
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
    cache.update(found)
    _save_json(path, cache)
    return ledger


def epg_ledger(day):
    path = os.path.join(_epg_dir(), "channels.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            led = json.load(f)
        age = time.time() - time.mktime(time.strptime(led["scanned_at"], "%Y-%m-%d %H:%M"))
        if age < EPG_LEDGER_DAYS * 86400 and not led.get("failed"):
            return led
    return epg_scan(day)


def epg_day(day, channels, refresh=False):
    from concurrent.futures import ThreadPoolExecutor
    d = _epg_dir()
    path = os.path.join(d, day + ".json")
    cache = {}
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
    miss = [c for c in channels if str(c) not in cache]
    errors = {}
    if miss:
        def one(c):
            try:
                return c, epg_fetch(c, day), None
            except Exception as e:
                return c, None, "%s: %s" % (type(e).__name__, e)
        with ThreadPoolExecutor(16) as ex:
            for c, v, err in ex.map(one, miss):
                if v and v["programs"]:
                    cache[str(c)] = v
                else:
                    errors[str(c)] = err or "편성 행 없음"
        _save_json(path, cache)
        for old in os.listdir(d):  # 지난 날짜 캐시 정리(channels.json 원장은 남김)
            if old.endswith(".json") and old[:8].isdigit() and old < day:
                os.remove(os.path.join(d, old))
    return cache, errors, len(miss)


def epg_op(a):
    t0 = time.time()
    day = time.strftime("%Y%m%d"); now = time.strftime("%H:%M")
    if a.get("op") == "epg_scan":
        led = epg_scan(day)
        return {"date": day, "now": now, "total_channels": len(led["channels"]), "range": led["range"],
                "failed": led["failed"], "seconds": led["seconds"], "items": led["channels"]}
    led = None
    if a.get("channels"):
        chans = [int(c) for c in a["channels"]]
        page = pages = 1
    else:
        led = epg_ledger(day)
        allc = [c["ch"] for c in led["channels"]]
        size = max(1, int(a.get("page_size") or EPG_PAGE_SIZE))
        pages = max(1, -(-len(allc) // size))
        page = min(max(1, int(a.get("page") or 1)), pages)
        chans = allc[(page - 1) * size:page * size]
    cache, errors, fetched = epg_day(day, chans, bool(a.get("refresh")))
    if a.get("op") == "epg_channel":
        v = cache.get(str(chans[0])) or {}
        return {"date": day, "now": now, "ch": chans[0], "name": v.get("name"),
                "items": v.get("programs", []), "errors": errors}
    items = []
    for c in chans:
        v = cache.get(str(c))
        if not v:
            continue
        cur = nxt = None
        for p in v["programs"]:
            if p["start"] <= now:
                cur = p
            elif nxt is None:
                nxt = p
        cur = cur or {"start": "", "title": "(오늘 편성 시작 전)", "genre": ""}  # 원장 채널은 빠짐없이
        items.append({"ch": c, "name": v["name"], "start": cur["start"], "title": cur["title"],
                      "genre": cur["genre"], "next": ("%s %s" % (nxt["start"], nxt["title"])) if nxt else ""})
    out = {"date": day, "now": now, "items": items, "count": len(items), "fetched_channels": fetched,
           "errors": errors, "page": page, "pages": pages,
           "span": "%s~%s번" % (chans[0], chans[-1]) if chans else "",
           "seconds": round(time.time() - t0, 2),
           "source": "tv.kt.com 지니TV 편성표(전국 기준, 지역 지상파 시간대 차이 가능)"}
    if led:
        out.update({"total_channels": len(led["channels"]), "ledger_scanned_at": led["scanned_at"]})
    out["errors_text"] = ", ".join("%s(%s)" % kv for kv in errors.items()) or "없음"
    return out
