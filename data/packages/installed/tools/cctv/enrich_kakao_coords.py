"""
카카오 CCTV 캐시 좌표 보강 (1회성 마이그레이션)

kakao_cctv_list.json 의 각 항목은 WCONGNAMUL 좌표(x, y)만 갖고 있어 지도에 표시할 수 없다.
카카오 transcoord API(WCONGNAMUL→WGS84)로 lat/lng 를 채워 캐시에 다시 저장한다.

- 권위 있는 변환(카카오 공식 API). pyproj 의존 없음.
- 멱등: 이미 lat/lng 가 있으면 건너뜀 (--force 로 전체 재변환).
- 캐시는 거의 정적이라(드물게 cctv_refresh 시 갱신) 1회 실행으로 충분.

실행:
    KAKAO_REST_API_KEY 가 환경에 있거나 프로젝트 루트 .env 에 있으면 자동 로드.
    python3 enrich_kakao_coords.py [--force]
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

_DIR = Path(__file__).resolve().parent
_CACHE_FILE = _DIR / "kakao_cctv_list.json"
_TRANSCOORD_URL = "https://dapi.kakao.com/v2/local/geo/transcoord.json"


def _load_key() -> str:
    key = os.environ.get("KAKAO_REST_API_KEY", "")
    if key:
        return key
    # 프로젝트 루트 .env 탐색 (cctv → tools → installed → packages → data → indiebizOS)
    for parent in _DIR.parents:
        env = parent / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("KAKAO_REST_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""


def _convert(session: requests.Session, key: str, x: float, y: float):
    """WCONGNAMUL (x, y) → (lng, lat). 실패 시 None."""
    try:
        r = session.get(
            _TRANSCOORD_URL,
            params={"x": x, "y": y, "input_coord": "WCONGNAMUL", "output_coord": "WGS84"},
            headers={"Authorization": f"KakaoAK {key}"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        docs = r.json().get("documents", [])
        if not docs:
            return None
        return float(docs[0]["x"]), float(docs[0]["y"])  # lng, lat
    except Exception:
        return None


def main():
    force = "--force" in sys.argv
    key = _load_key()
    if not key:
        print("ERROR: KAKAO_REST_API_KEY 를 찾을 수 없습니다.")
        sys.exit(1)
    if not _CACHE_FILE.exists():
        print(f"ERROR: 캐시 파일 없음: {_CACHE_FILE}")
        sys.exit(1)

    cctvs = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    todo = [
        c for c in cctvs
        if c.get("x") and c.get("y") and (force or not (c.get("lat") and c.get("lng")))
    ]
    print(f"총 {len(cctvs)}대 · 변환 대상 {len(todo)}대 (force={force})")
    if not todo:
        print("이미 모두 보강됨. 종료.")
        return

    ok = 0
    fail = 0
    session = requests.Session()
    t0 = time.time()

    def work(c):
        res = _convert(session, key, c["x"], c["y"])
        if res:
            c["lng"], c["lat"] = res
            return True
        return False

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(work, c): c for c in todo}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if fut.result():
                ok += 1
            else:
                fail += 1
            if done % 500 == 0:
                print(f"  진행 {done}/{len(todo)} (성공 {ok}, 실패 {fail}, {time.time()-t0:.0f}s)")

    _CACHE_FILE.write_text(json.dumps(cctvs, ensure_ascii=False), encoding="utf-8")
    print(f"완료: 성공 {ok}, 실패 {fail} · {time.time()-t0:.0f}s · 저장 {_CACHE_FILE}")


if __name__ == "__main__":
    main()
