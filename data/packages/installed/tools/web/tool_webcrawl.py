"""
tool_webcrawl.py - 웹사이트 크롤링 도구

에스컬레이션 사다리 (도구가 자동으로 오름 — 모델 지능에 의존하지 않음):
  1. curl_cffi 정적 크롤 — TLS 지문까지 크롬으로 위장. UA만 바꾼 requests가 못 뚫는
     Akamai/Cloudflare급 봇차단(테슬라 등) 통과. 미설치 시 requests 폴백.
  2. Chrome MCP — 이미 연결돼 있으면 실제 크롬(로그인 세션 포함) 사용.
  3. Playwright — 자체 Chromium. data/browser_cookies/_auto_state.json의 로그인 상태를
     자동 복원하고, 본문이 iframe에 있는 사이트(네이버 카페/블로그)는 전 프레임 텍스트 수집.
  4. 전부 실패 시 reason(bot_blocked/login_required/...)을 명시 — 모델이 "정보가 없다"가
     아니라 "왜 못 가져왔는지"를 정확히 보고하고 우회할 수 있게 한다.

에스컬레이션 발동: HTTP 에러·짧은 본문만이 아니라 로그인 벽/봇차단 페이지 시그니처,
iframe 전용 호스트(정적 텍스트가 본문이 아닌 사이트)도 감지한다.
"""

import os
import re
import sys
import asyncio
import importlib.util
from urllib.parse import urlparse

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

import requests
from bs4 import BeautifulSoup

# TLS 지문 위장 단일 소스 (감사 ⑥) — 미설치 환경이면 requests 로 폴백.
from common.http_fetch import CHROME_UA, chrome_get, has_curl_cffi

# User-Agent 설정 (requests 폴백용 — curl_cffi는 impersonate가 헤더 일체를 관리)
HEADERS = {
    'User-Agent': CHROME_UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
}

# 폴백 판단 기준 (이 글자수 미만이면 콘텐츠 부족으로 간주)
_MIN_CONTENT_LENGTH = 200
# 이 미만 + 로그인 흔적이면 "메뉴만 나온" 로그인 벽으로 의심 (성공 반환 기준과 별개)
_SUSPICIOUS_CONTENT_LENGTH = 600

# 본문이 iframe/JS 렌더링에 있어 정적 텍스트가 본문이 아닌 호스트 — 항상 브라우저로 에스컬레이션
_RENDER_REQUIRED_HOSTS = {
    'cafe.naver.com', 'm.cafe.naver.com',
    'blog.naver.com', 'm.blog.naver.com',
    'post.naver.com', 'm.post.naver.com',
}

# 로그인 벽/봇차단 시그니처
_LOGIN_URL_RE = re.compile(
    r'nid\.naver\.com|accounts\.google\.com|logins?\.daum\.net|/(login|signin|sign-in|member/login)\b',
    re.I)
_LOGIN_TEXT_SIGNS = [
    '로그인이 필요', '로그인 후 이용', '로그인해 주세요', '로그인 해주세요', '로그인하셔야',
    '회원만 이용', '멤버 가입', 'sign in to continue', 'log in to continue',
    'please sign in', 'please log in',
]
_BLOCK_TEXT_SIGNS = [
    'access denied', 'request blocked', 'are you a robot', 'are you human',
    'unusual traffic', 'captcha', 'attention required', 'pardon our interruption',
    'verify you are', 'checking your browser',
    '비정상적인 접근', '자동 입력 방지', '자동입력 방지', '잠시 후 다시 시도',
    # Cloudflare 챌린지 (2026-08-10, ep1008): Playwright 로 열어도 이 페이지가 나오면
    # 본문 부족이 아니라 봇차단 — insufficient_content 오진이 모델에게 "빈 페이지"로 읽혔다.
    'verifying you are', 'needs to review the security',
    'enable javascript and cookies', '사람인지 확인',
    '연결의 보안을 검토', '보안을 확인해야',
]

# 챌린지 페이지 제목 시그니처 — 본문이 0자여도 제목으로 판정 (hpcwire·anl.gov 실측:
# CF 챌린지는 본문을 전부 script 에 두어 _parse_html 후 text='' 가 된다)
_CHALLENGE_TITLE_SIGNS = [
    'just a moment', '잠시만 기다리', 'attention required', 'access denied',
    'security check', 'checking your browser',
]


def _needs_render(url: str) -> bool:
    """정적 크롤로는 본문을 얻을 수 없는(iframe/SPA) 호스트인지."""
    try:
        return urlparse(url).netloc.lower() in _RENDER_REQUIRED_HOSTS
    except Exception:
        return False


def _diagnose(status: int, final_url: str, requested_url: str, text: str,
              title: str = ""):
    """크롤 결과가 '진짜 본문'인지 판정. 문제면 사유 문자열, 정상이면 None.

    사유: bot_blocked / login_required / insufficient_content
    (모양이 아니라 사유를 반환 — 최종 실패 시 모델에게 그대로 전달돼 정확한 보고·우회를 돕는다)
    title: 챌린지 페이지는 본문이 script 뿐이라 파싱 후 text='' — 제목이 유일한 단서.
    """
    text = text or ''
    low = text[:4000].lower()
    title_low = (title or '').lower()
    if title_low and any(s in title_low for s in _CHALLENGE_TITLE_SIGNS):
        return "bot_blocked"
    if status in (403, 429, 503):
        return "bot_blocked"
    if status == 401:
        return "login_required"
    # 로그인 페이지로 리다이렉트됨 (요청 자체가 로그인 URL이었던 경우 제외)
    if final_url and _LOGIN_URL_RE.search(final_url) and not _LOGIN_URL_RE.search(requested_url or ''):
        return "login_required"
    # ★문구 매칭은 '본문이 사실상 그 문구뿐'일 때만 신뢰한다 (2026-08-17 수리).
    #   진짜 챌린지·로그인 벽은 본문이 거의 없다(위 docstring 대로 script 뿐). 반면 정상
    #   페이지는 그 문구를 *언급*할 수 있다 — 실측: 자기 홈페이지 본문 11,841자의 1,807자
    #   지점에 "그래서 CAPTCHA도 없습니다"가 있어 bot_blocked 로 거부됐다. CAPTCHA 가
    #   없다고 자랑하는 페이지를 CAPTCHA 챌린지로 판정한 것 = 언급을 존재로 착각.
    #   대가는 셋이었다: 오진 후 불필요한 렌더로 30초 · 거짓 사유("가져오지 못했습니다"인데
    #   실은 200·254KB 정상 수신) · 멀쩡한 페이지를 영구히 못 읽음.
    #   ※본문이 긴 차단 페이지는 상태코드(403/429/503)와 제목 신호가 잡는다 — 그 둘은
    #     위에서 길이 조건 없이 검사하므로 커버리지가 남는다. 여기에 "앞 N자" 같은 조건을
    #     더하지 않는 이유 = CAPTCHA 를 *주제로* 다루는 글이 첫 문단부터 그 단어를 쓴다.
    if len(text) < _SUSPICIOUS_CONTENT_LENGTH:
        if any(s in low for s in _BLOCK_TEXT_SIGNS):
            return "bot_blocked"
        if any(s in low for s in _LOGIN_TEXT_SIGNS):
            return "login_required"
    if len(text) < _MIN_CONTENT_LENGTH:
        return "insufficient_content"
    # 본문이 짧은데 로그인 유도가 있으면 "메뉴만 나온" 로그인 벽 의심
    if len(text) < _SUSPICIOUS_CONTENT_LENGTH and ('로그인' in text or 'login' in low):
        return "login_required"
    return None


def _parse_html(html: str, url: str) -> tuple[str, str]:
    """HTML에서 제목과 본문 텍스트를 추출한다."""
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # 불필요한 요소 제거
    for el in soup(['script', 'style', 'nav', 'footer', 'header', 'aside',
                    'noscript', 'iframe', 'form', 'button', 'svg', 'figure', 'figcaption']):
        el.decompose()

    # 광고/관련기사/댓글 등 노이즈 제거 (class/id 기반)
    noise_patterns = ['comment', 'advert', 'sidebar', 'related', 'recommend',
                      'share', 'social', 'newsletter', 'popup', 'banner', 'cookie']
    for el in list(soup.find_all(True)):
        try:
            classes = ' '.join(el.get('class', []))
            el_id = el.get('id', '')
            combined = (classes + ' ' + el_id).lower()
            if any(p in combined for p in noise_patterns):
                el.decompose()
        except Exception:
            continue

    # 본문 추출: <article> → <main> → <body>
    container = soup.find('article') or soup.find('main') or soup.find('body') or soup
    text = container.get_text(separator='\n')

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return title, text


def _truncate(text: str, max_length: int) -> tuple[str, int, bool]:
    """텍스트를 max_length로 자르고 (text, original_length, truncated) 반환."""
    original_length = len(text)
    truncated = original_length > max_length
    if truncated:
        text = text[:max_length] + "\n\n... (내용 생략됨)"
    return text, original_length, truncated


# ─── 1단계: 정적 크롤링 (curl_cffi 우선, requests 폴백) ───

# ─── 인코딩 판별 (일본·중국·옛 한국 사이트 모지바케 방지) ───
# 함정: Content-Type 헤더에 charset 이 없고 <meta charset> 에만 선언한 사이트가 많다
#   (예: kakaku.com = Shift_JIS). curl_cffi 는 그럴 때 encoding 을 'utf-8' 로 단정하고
#   apparent_encoding 속성 자체가 없어서, 옛 가드(None|ISO-8859-1 → apparent_encoding)는
#   *발동도 안 하고* 발동해도 AttributeError 로 삼켜졌다 → 본문 전체 모지바케(에피소드 881).
_META_CHARSET_RE = re.compile(
    rb'<meta[^>]{0,200}?charset\s*=\s*["\']?\s*([a-zA-Z0-9_\-:.]+)', re.I)
# 서버가 명시해도 CJK 페이지에선 못 믿는 값 — HTTP 기본값이라 "미선언"과 사실상 같다.
_WEAK_CHARSETS = {"iso-8859-1", "latin-1", "latin1", "ascii", "us-ascii"}
_BOMS = ((b'\xef\xbb\xbf', 'utf-8-sig'), (b'\xff\xfe', 'utf-16'), (b'\xfe\xff', 'utf-16'))


def _try_decode(raw: bytes, enc: str):
    """strict 디코드 성공 시 문자열, 실패하면 None."""
    if not enc:
        return None
    try:
        return raw.decode(enc, errors="strict")
    except (UnicodeDecodeError, LookupError, TypeError):
        return None


def _header_charset(response) -> str:
    try:
        headers = getattr(response, "headers", {}) or {}
        ctype = headers.get("Content-Type") or headers.get("content-type") or ""
    except Exception:
        return ""
    m = re.search(r'charset\s*=\s*["\']?([a-zA-Z0-9_\-:.]+)', str(ctype), re.I)
    return m.group(1).strip() if m else ""


def _decode_body(response) -> str:
    """응답 바이트를 옳은 인코딩으로 디코드. 브라우저와 같은 우선순위:
    BOM → HTTP 헤더 charset → <meta charset> → 자동감지 → utf-8(대체문자).
    """
    try:
        raw = response.content or b""
    except Exception:
        raw = b""
    if not raw:
        return getattr(response, "text", "") or ""

    # 1) BOM 이 있으면 그게 결정적
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            dec = _try_decode(raw, enc)
            if dec is not None:
                return dec

    # 2) HTTP 헤더가 *구체적으로* 선언했으면 신뢰
    declared = _header_charset(response)
    if declared and declared.lower() not in _WEAK_CHARSETS:
        dec = _try_decode(raw, declared)
        if dec is not None:
            return dec

    # 3) HTML <meta charset> — 헤더에 없을 때 브라우저가 쓰는 선언
    m = _META_CHARSET_RE.search(raw[:4096])
    if m:
        try:
            meta_enc = m.group(1).decode("ascii", errors="ignore").strip()
        except Exception:
            meta_enc = ""
        dec = _try_decode(raw, meta_enc)
        if dec is not None:
            return dec

    # 4) 선언이 없거나 틀렸다 → 자동감지(charset_normalizer 는 requests 의존성이라 사실상 상주)
    for detector in ("charset_normalizer", "chardet"):
        try:
            mod = __import__(detector)
        except ImportError:
            continue
        try:
            if detector == "charset_normalizer":
                best = mod.from_bytes(raw).best()
                guess = best.encoding if best else None
            else:
                guess = (mod.detect(raw) or {}).get("encoding")
        except Exception:
            guess = None
        dec = _try_decode(raw, guess)
        if dec is not None:
            return dec

    # 5) 최후 — 깨진 바이트는 버리되 본문은 살린다(진단이라도 하게)
    return raw.decode("utf-8", errors="replace")


def _crawl_static(url: str, max_length: int) -> dict:
    """정적 크롤링. curl_cffi(TLS 크롬 위장)가 있으면 그것으로, 없으면 requests."""
    try:
        if has_curl_cffi():
            response = chrome_get(
                url, timeout=15, allow_redirects=True,
                headers={'Accept-Language': HEADERS['Accept-Language']},
            )
            method = "curl_cffi"
        else:
            response = requests.get(url, headers=HEADERS, timeout=15)
            method = "requests"

        status = response.status_code
        final_url = str(getattr(response, 'url', '') or url)
        html = _decode_body(response)

        # 에러 페이지도 파싱한다 — 봇차단/로그인 벽 진단에 본문이 필요
        title, text = _parse_html(html, url)
        reason = _diagnose(status, final_url, url, text, title)
        if reason is None and _needs_render(url):
            reason = "insufficient_content"  # iframe 전용 호스트 — 정적 텍스트는 본문이 아님

        text, original_length, truncated = _truncate(text, max_length)
        result = {
            "success": status < 400,
            "url": url,
            "title": title,
            "text": text,
            "length": original_length,
            "truncated": truncated,
            "method": method,
        }
        if status >= 400:
            result["error"] = f"HTTP 에러: {status}"
        if reason:
            result["reason"] = reason
        return result
    except Exception as e:
        # curl_cffi/requests 예외 공통 처리 (클래스 이름으로 분류)
        name = type(e).__name__
        if 'Timeout' in name:
            msg = "요청 시간 초과 (15초)"
        elif 'Connect' in name:
            msg = "연결 실패 - URL을 확인하세요"
        else:
            msg = str(e)
        return {"success": False, "error": msg, "url": url, "method": "curl_cffi" if has_curl_cffi() else "requests"}


# ─── 2단계: Chrome MCP 폴백 ───

def _get_chrome_driver():
    """browser-action 패키지의 ChromeMCPDriver 싱글톤을 가져온다. 실패 시 None."""
    try:
        chrome_path = os.path.join(
            os.path.dirname(__file__), "..", "browser-action", "browser_chrome.py"
        )
        spec = importlib.util.spec_from_file_location("browser_chrome", chrome_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        driver = mod.ChromeMCPDriver.get_instance()
        if driver.is_connected():
            return driver
    except Exception:
        pass
    return None


# ─── 3단계: Playwright 폴백 (자체 Chromium, 외부 서버 불필요) ───

_browser_session = None  # crawl 전용 BrowserSession 싱글턴 캐시


def _get_browser_session():
    """browser-action 패키지의 Playwright BrowserSession을 가져온다.

    browser-action 핸들러가 이미 로드한 정본 싱글턴(sys.modules["browser_session"])이
    있으면 그것을 재사용 — 같은 브라우저·로그인 세션 공유(사람이 headful로 로그인해 둔
    창 포함). 없으면 crawl 전용 사본을 1회 로드해 캐싱. 어느 쪽이든 `_run_async`
    (system_tools 루프)에서 일관되게 구동되어 루프 충돌이 없다.
    """
    global _browser_session
    mod = sys.modules.get("browser_session")
    if mod is not None and hasattr(mod, "BrowserSession"):
        mod_file = str(getattr(mod, "__file__", "") or "")
        if mod_file.endswith(os.path.join("browser-action", "browser_session.py")):
            return mod.BrowserSession.get_instance()
    if _browser_session is not None:
        return _browser_session
    try:
        bs_path = os.path.join(
            os.path.dirname(__file__), "..", "browser-action", "browser_session.py"
        )
        spec = importlib.util.spec_from_file_location("webcrawl_browser_session", bs_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _browser_session = mod.BrowserSession.get_instance()
        return _browser_session
    except Exception:
        return None


async def _crawl_playwright_async(session, url: str, max_length: int) -> dict:
    """Playwright(Chromium)로 JS 렌더링 후 본문 텍스트 추출.

    - 이미 떠 있는 브라우저(로그인 세션·headful 창 포함)가 있으면 새 탭으로 재사용 —
      기존 화면을 죽이거나 방해하지 않는다.
    - 본문이 iframe에 있는 사이트(네이버 카페/블로그)를 위해 모든 프레임의 텍스트 수집.
    - 크롤 후 로그인 상태를 자동 저장(storage_state) — 세션 신선도 유지.
    """
    opened_tab = None
    status = 200  # new_tab 경로는 응답 객체가 없음 — 200 가정, goto 경로는 실상태
    try:
        if session.is_active:
            opened_tab = await session.new_tab(url)
            page = session.raw_page
        else:
            await session.ensure_browser(headless=True)
            page = session.raw_page
            if page is not None:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if resp is not None:
                    status = resp.status
        if page is None:
            return {"success": False, "error": "Playwright 페이지 생성 실패", "url": url, "method": "playwright"}

        # 동적 콘텐츠 대기 (SPA 렌더링) — networkidle 우선, 실패해도 진행
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            await asyncio.sleep(2)

        # 모든 프레임의 텍스트 수집 (메인 프레임 먼저) — iframe 본문 사이트 대응
        texts = []
        for frame in page.frames:
            try:
                t = await frame.inner_text("body")
            except Exception:
                continue
            if t and t.strip():
                texts.append(t)
        text = "\n\n".join(texts)
        title = await page.title()
        final_url = page.url

        # 로그인 상태 자동 저장 (구버전 browser_session 모듈이면 스킵)
        if hasattr(session, "save_storage_state"):
            await session.save_storage_state()

        if not text or len(text) < _MIN_CONTENT_LENGTH:
            result = {"success": False, "error": "Playwright에서도 콘텐츠 부족", "url": url, "method": "playwright"}
            reason = _diagnose(status, final_url, url, text, title)
            if reason:
                result["reason"] = reason
            return result

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        reason = _diagnose(status, final_url, url, text, title)
        text, original_length, truncated = _truncate(text, max_length)
        result = {
            "success": True,
            "url": url,
            "title": title,
            "text": text,
            "length": original_length,
            "truncated": truncated,
            "method": "playwright",
        }
        if reason:
            result["reason"] = reason
        return result
    except Exception as e:
        return {"success": False, "error": f"Playwright 크롤링 실패: {e}", "url": url, "method": "playwright"}
    finally:
        if opened_tab:
            try:
                await session.close_tab(opened_tab)
            except Exception:
                pass


async def _crawl_chrome_async(driver, url: str, max_length: int) -> dict:
    """Chrome MCP를 사용하여 실제 브라우저로 페이지 텍스트를 가져온다."""
    try:
        # 페이지 이동
        await driver.call_tool("navigate", {"url": url, "tabId": driver._tab_id})

        # JS 렌더링 대기 (페이지 로드 완료)
        await asyncio.sleep(2)

        # 텍스트 추출
        result = await driver.call_tool("get_page_text", {"tabId": driver._tab_id})
        text = result.get("text", "") if isinstance(result, dict) else str(result)

        if not text or len(text) < _MIN_CONTENT_LENGTH:
            return {"success": False, "error": "Chrome MCP에서도 콘텐츠를 추출하지 못함", "url": url, "method": "chrome_mcp"}

        # 제목 추출 시도
        title_result = await driver.call_tool("javascript_tool", {
            "action": "javascript_exec",
            "text": "document.title",
            "tabId": driver._tab_id
        })
        title = ""
        if isinstance(title_result, dict):
            title = title_result.get("text", title_result.get("result", ""))

        # 정리 및 자르기
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        reason = _diagnose(200, url, url, text, title)
        text, original_length, truncated = _truncate(text, max_length)

        result = {
            "success": True,
            "url": url,
            "title": title,
            "text": text,
            "length": original_length,
            "truncated": truncated,
            "method": "chrome_mcp"
        }
        if reason:
            result["reason"] = reason
        return result
    except Exception as e:
        return {"success": False, "error": f"Chrome MCP 크롤링 실패: {e}", "url": url, "method": "chrome_mcp"}


def _run_async(coro):
    """기존 system_tools의 async 루프를 재사용하거나, 없으면 새로 실행."""
    try:
        from system_tools import _get_async_loop
        loop = _get_async_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    except ImportError:
        # system_tools를 임포트할 수 없으면 직접 실행
        return asyncio.run(coro)


# ─── Google News 리다이렉트 래퍼 해소 (2026-08-10, ep1008) ───
# [sense:search]{source:"gnews"} 가 주는 링크는 news.google.com/rss/articles/<id> 래퍼다.
# 정적 크롤은 578KB 스텁(본문 없음)을 받고, 헤드리스 브라우저는 구글이 막는다 —
# 그래서 gnews 발 크롤이 부류째 죽어 있었다(04시 동향보고서·신문의 일상 경로).
# 해소법: 스텁 페이지의 c-wiz 서명(data-n-a-ts/sg)으로 batchexecute 를 불러
# 실제 기사 URL 을 얻고, 그 URL 을 정상 사다리로 크롤한다. (googlenewsdecoder 와 동일 기법)

_GNEWS_ARTICLE_RE = re.compile(
    r'https?://news\.google\.com/(?:rss/)?articles/([^?/&#]+)', re.I)


def _resolve_google_news(url: str) -> str | None:
    """news.google.com 기사 래퍼 → 실제 기사 URL. 실패 시 None (원 URL로 계속)."""
    m = _GNEWS_ARTICLE_RE.match(url or '')
    if not m:
        return None
    art_id = m.group(1)
    try:
        stub = requests.get(url, timeout=10, headers={'User-Agent': CHROME_UA})
        ts = re.search(r'data-n-a-ts="([^"]+)"', stub.text)
        sg = re.search(r'data-n-a-sg="([^"]+)"', stub.text)
        if not (ts and sg):
            return None
        payload = (
            '[[["Fbv4je","[\\"garturlreq\\",[[\\"X\\",\\"X\\",[\\"X\\",\\"X\\"],'
            'null,null,1,1,\\"KR:ko\\",null,180,null,null,null,null,null,0,null,'
            'null,[1,8]],\\"X\\",\\"X\\",1,[1,1,1],1,1,null,0,0,null,0],'
            f'\\"{art_id}\\",{ts.group(1)},\\"{sg.group(1)}\\"]",null,"generic"]]]'
        )
        r = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data={"f.req": payload}, timeout=10)
        if r.status_code != 200:
            return None
        # 응답은 JSON-in-JSON 이고 URL 안의 = & 등이 \\u003d 꼴로 이스케이프돼 있다 —
        # 풀지 않으면 정규식이 백슬래시에서 끊겨 `?idxno` 까지만 남는다
        # (2026-08-21 ep1339·1258 등 7일간 gnews 발 크롤 17건 전멸의 실체).
        body = re.sub(r'\\{1,2}u([0-9a-fA-F]{4})',
                      lambda m: chr(int(m.group(1), 16)), r.text)
        # 정밀 패턴 우선, 실패 시 비-구글 URL 스캔 폴백
        m2 = re.search(r'garturlres\\",\\"(https?://[^\\"]+)', body)
        if m2:
            return m2.group(1)
        for line in body.split('\n'):
            hits = re.findall(r'https?://[^\\"\s]+', line)
            real = [h for h in hits
                    if 'news.google' not in h and 'gstatic' not in h
                    and 'google.com' not in h]
            if real:
                return real[0]
    except Exception:
        pass
    return None


# ─── 메인 함수 ───

# 최종 실패 시 모델에게 전달할 사유별 안내 (정확한 보고 + 다음 행동 힌트)
_REASON_HINTS = {
    "login_required": (
        "로그인이 필요한 페이지입니다. browser_navigate를 headless:false로 열어 사람이 한 번 "
        "로그인해 두면 세션이 자동 저장되어(data/browser_cookies/_auto_state.json) 이후 크롤이 "
        "접근할 수 있습니다. 사용자에게 로그인을 요청하거나 로그인 불필요한 다른 소스를 시도하세요."
    ),
    "bot_blocked": (
        "봇 차단으로 본문을 가져오지 못했습니다 (TLS 크롬 위장·실브라우저 렌더링 모두 시도). "
        "같은 정보를 다루는 다른 소스를 시도하세요."
    ),
    "insufficient_content": "본문을 충분히 추출하지 못했습니다 (정적·브라우저 렌더링 모두 시도).",
}


def crawl_website(url: str, max_length: int = 10000) -> dict:
    """
    웹사이트를 크롤링하여 텍스트 내용을 추출한다.
    1단계: curl_cffi 정적 (TLS 크롬 위장, ~1초)
    2단계: 실패·로그인 벽·봇차단·콘텐츠 부족 시 Chrome MCP → Playwright로 자동 에스컬레이션
    3단계: 전부 실패하면 reason(bot_blocked/login_required/...)을 명시해 반환
    """
    if not url:
        return {"success": False, "error": "URL이 필요합니다.", "url": ""}

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # gnews 래퍼면 실제 기사 URL 로 해소 후 정상 사다리 (해소 실패 시 원 URL 로 진행)
    resolved = _resolve_google_news(url)
    if resolved and not _GNEWS_ARTICLE_RE.match(resolved):  # 재귀 루프 가드
        result = crawl_website(resolved, max_length)  # 해소 URL 은 래퍼가 아니라 재귀 1회로 끝
        result["resolved_from"] = url
        return result

    attempts = []

    # 1단계: 정적 크롤링 — 깨끗하면 바로 반환
    static = _crawl_static(url, max_length)
    attempts.append(static)
    if static.get("success") and not static.get("reason"):
        return static

    # 2단계: Chrome MCP가 "이미 연결돼 있으면" 우선 사용 (실제 크롬 로그인 세션·쿠키 활용).
    #        연결돼 있지 않으면 외부 서버(12306)가 필요하므로 건너뛴다 — 자동 연결하지 않음.
    driver = _get_chrome_driver()
    if driver is not None:
        chrome_result = _run_async(_crawl_chrome_async(driver, url, max_length))
        attempts.append(chrome_result)
        if chrome_result.get("success") and not chrome_result.get("reason"):
            return chrome_result

    # 3단계: Playwright — 자동 복원된 로그인 세션 + 전 프레임 수집
    session = _get_browser_session()
    if session is not None:
        try:
            pw_result = _run_async(_crawl_playwright_async(session, url, max_length))
            attempts.append(pw_result)
            if pw_result.get("success") and not pw_result.get("reason"):
                return pw_result
        except Exception:
            pass

    # ── 전 단계가 흠 있음 — 사유 확정 (가장 능력 있는 마지막 단계의 진단이 진실에 가장 가까움) ──
    reason = None
    for a in reversed(attempts):
        if a.get("reason"):
            reason = a["reason"]
            break

    # 로그인/봇차단이 아니면, 그나마 가장 긴 본문을 사유 딸려 반환
    # (짧은 페이지는 정상일 수 있음 — example.com 같은 초소형 정상 페이지를 실패 처리하지 않는다)
    if reason not in ("login_required", "bot_blocked"):
        best = None
        for a in attempts:
            if a.get("success") and a.get("text", "").strip():
                if best is None or a.get("length", 0) > best.get("length", 0):
                    best = a
        if best is not None:
            if reason:
                best["reason"] = reason
                best["note"] = "본문이 짧거나 완전하지 않을 수 있습니다 (JS 렌더링/iframe 폴백이 더 나은 결과를 얻지 못함)."
            return best

    reason = reason or "insufficient_content"
    result = {
        "success": False,
        "url": url,
        "reason": reason,
        "error": _REASON_HINTS.get(reason, "크롤 실패"),
        "methods_tried": [a.get("method") for a in attempts if a.get("method")],
    }
    if static.get("error"):
        result["detail"] = static["error"]
    return result


def use_tool(tool_input: dict) -> dict:
    """도구 인터페이스"""
    url = tool_input.get('url', '')
    max_length = tool_input.get('max_length', 10000)
    return crawl_website(url, max_length)
