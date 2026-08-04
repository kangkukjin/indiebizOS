"""http_fetch.py — 크롬 TLS 위장 HTTP 단일 소스 (2026-08-05 감사 부채 ⑥ 복붙 정리).

봇탐지(TLS 지문)를 넘는 curl_cffi impersonate="chrome" 주문이 5개 패키지
(web/real-estate/location-services/shopping-assistant×2)에 복붙돼 있던 것을 수렴.

폰(Chaquopy)엔 curl_cffi 가 없다 → 가드된 import. 호출자는 폴백 축을 고른다:
  * TLS 위장 필수 소스(네이버부동산·여기어때·크몽): has_curl_cffi() 로 먼저 확인해 안내 반환
  * 순한 소스(다나와): chrome_get(..., fallback="urllib") — stdlib 로 폰에서도 동작

backend/common 은 폰 zip 에 통째 포함(phone-companion build.gradle bundleIndiebizBase)
— 폰 몸에서도 이 모듈 import 는 항상 안전하다.
"""
import gzip
import json as _json
import urllib.error
import urllib.parse
import urllib.request

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # 폰(Chaquopy) 등 curl_cffi 없는 몸
    cffi_requests = None

# requests/urllib 폴백용 UA (curl_cffi 는 impersonate 가 헤더 일체를 관리하므로 불필요)
CHROME_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

_MISSING_MSG = "curl_cffi 미설치 — TLS 크롬 위장이 필요합니다 (pip install curl_cffi)."


def has_curl_cffi() -> bool:
    return cffi_requests is not None


def chrome_session():
    """쿠키·토큰이 요청 간 이어지는 크롬 위장 세션 (네이버부동산 익명 JWT 등).

    미설치면 RuntimeError — 위장 필수 소스는 세션 없이는 원리적으로 불가.
    """
    if cffi_requests is None:
        raise RuntimeError(_MISSING_MSG)
    return cffi_requests.Session(impersonate="chrome")


class _UrllibResponse:
    """urllib 폴백 응답 — curl_cffi 응답의 소비면(.status_code/.text/.content/.json()/.url)만 흉내."""

    def __init__(self, status: int, content: bytes, url: str):
        self.status_code = status
        self.content = content
        self.url = url

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self):
        return _json.loads(self.text)


def chrome_get(url, *, params=None, headers=None, timeout=20,
               allow_redirects=True, fallback="error"):
    """크롬 위장 GET. curl_cffi 응답 객체를 그대로 반환 (.status_code/.text/.json()).

    fallback — curl_cffi 미설치(폰) 시 동작:
      "error"  → RuntimeError (위장 필수 소스. 호출자는 has_curl_cffi() 로 먼저 안내 가능)
      "urllib" → stdlib urllib 시도 (위장이 실제론 불필요한 순한 소스 — 폰에서도 동작.
                 gzip 해제 포함, 4xx/5xx 도 예외 아닌 응답으로 반환해 curl_cffi 와 동형)
    """
    if cffi_requests is not None:
        return cffi_requests.get(url, params=params, headers=headers,
                                 impersonate="chrome", timeout=timeout,
                                 allow_redirects=allow_redirects)
    if fallback != "urllib":
        raise RuntimeError(_MISSING_MSG)

    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    hdrs = {"User-Agent": CHROME_UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(full, headers=hdrs)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:  # 상태코드 판정은 호출자 몫 (curl_cffi 동형)
        return _UrllibResponse(e.code, e.read() or b"", full)
    with resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return _UrllibResponse(getattr(resp, "status", 200), raw, str(resp.url))
