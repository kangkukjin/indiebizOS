"""geocode.py — 키리스 지오코딩(Nominatim) 단일 소스 (2026-08-05 감사 부채 ⑥ 복붙 정리).

같은 Nominatim 호출 블록이 real-estate(상권·직방 폴백)와 location-services(날씨)에
복붙돼 있던 것을 수렴. stdlib urllib 만 사용 — 폰(Chaquopy)에서도 안전.

지명 후보 구성(업종 접미어 제거 등)·폴백 순서는 호출자 몫 — 여기는 호출 한 번의 정본만.
"""
import json
import time
import urllib.parse
import urllib.request


def nominatim_search(query, *, countrycodes="kr", accept_language=None,
                     timeout=10, retries=0, user_agent="indiebizOS/1.0"):
    """Nominatim 검색 1건 → {"lat": float, "lng": float, "matched": str} | None.

    - countrycodes: "kr"=국내 한정(기본), None=전세계(한글 외국 도시 폴백용)
    - retries: *예외(일시 장애)* 에만 재시도(0.6s 백오프). 정상 응답인데 결과가 없으면
      재시도 무의미 — 즉시 None (침묵 오답보다 명시적 실패가 낫다는 날씨 지오코더 선례).
    """
    q = str(query or "").strip()
    if not q:
        return None
    params = {"q": q, "format": "json", "limit": 1}
    if countrycodes:
        params["countrycodes"] = countrycodes
    if accept_language:
        params["accept-language"] = accept_language
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data:
                return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"]),
                        "matched": data[0].get("display_name", q)}
            return None  # 정상 응답·결과 없음 — 재시도 무의미
        except Exception:
            if attempt < retries:
                time.sleep(0.6)  # 일시 장애(rate-limit/타임아웃) — 짧은 백오프 후 재시도
    return None
