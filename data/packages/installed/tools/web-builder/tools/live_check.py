"""
site_live_check: 사이트의 실제 상태 점검
HTTP 응답, Lighthouse 점수 + Core Web Vitals + 개선 기회, 스크린샷 캡처

site_id 또는 url로 사용 가능:
- site_id: 등록된 사이트 (URL 자동 조회, last_checked 업데이트)
- url: 등록되지 않은 사이트도 직접 점검 가능
"""
import json
import subprocess
import time
import shutil
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


OUTPUTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "outputs" / "web-builder"


def load_sites(package_dir: Path) -> list:
    sites_file = package_dir / "sites.json"
    if sites_file.exists():
        return json.loads(sites_file.read_text(encoding="utf-8"))
    return []


def save_sites(sites: list, package_dir: Path):
    sites_file = package_dir / "sites.json"
    sites_file.write_text(
        json.dumps(sites, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def find_site(site_id: str, package_dir: Path) -> dict | None:
    sites = load_sites(package_dir)
    for s in sites:
        if s["id"] == site_id:
            return s
    return None


def update_last_checked(site_id: str, package_dir: Path):
    """마지막 점검 시각 업데이트"""
    sites = load_sites(package_dir)
    for s in sites:
        if s["id"] == site_id:
            s["last_checked"] = datetime.now().isoformat()
            break
    save_sites(sites, package_dir)


def check_status(url: str) -> dict:
    """HTTP 응답 상태 및 응답 시간 측정"""
    try:
        req = Request(url, headers={"User-Agent": "IndieBizOS-WebBuilder/2.0"})
        start = time.time()
        response = urlopen(req, timeout=15)
        elapsed = round((time.time() - start) * 1000)

        return {
            "ok": True,
            "status_code": response.status,
            "response_time_ms": elapsed,
            "content_type": response.headers.get("Content-Type", ""),
            "server": response.headers.get("Server", ""),
        }
    except HTTPError as e:
        return {"ok": False, "status_code": e.code, "error": str(e.reason)}
    except URLError as e:
        return {"ok": False, "status_code": None, "error": str(e.reason)}
    except Exception as e:
        return {"ok": False, "status_code": None, "error": str(e)}


def check_lighthouse(url: str, label: str) -> dict:
    """Lighthouse 점수 + Core Web Vitals + 개선 기회"""
    lighthouse_path = shutil.which("lighthouse") or "/opt/homebrew/bin/lighthouse"

    if not Path(lighthouse_path).exists():
        return {"ok": False, "error": "Lighthouse가 설치되어 있지 않습니다. npm install -g lighthouse"}

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUTS_DIR / f"lighthouse-{label}.json"

    try:
        result = subprocess.run(
            [
                lighthouse_path, url,
                "--output=json",
                f"--output-path={output_file}",
                "--chrome-flags=--headless --no-sandbox",
                "--only-categories=performance,accessibility,best-practices,seo",
                "--quiet",
            ],
            capture_output=True, text=True, timeout=120,
        )

        if not output_file.exists():
            return {"ok": False, "error": f"Lighthouse 실행 실패: {result.stderr[:300]}"}

        report = json.loads(output_file.read_text(encoding="utf-8"))
        categories = report.get("categories", {})

        # 카테고리 점수
        scores = {}
        for key, cat in categories.items():
            score = cat.get("score") or 0
            scores[key] = {
                "score": round(score * 100),
                "title": cat.get("title", key),
                "grade": "good" if score >= 0.9 else "needs-improvement" if score >= 0.5 else "poor",
            }

        # Core Web Vitals
        audits = report.get("audits", {})
        vital_keys = {
            "first-contentful-paint": "FCP",
            "largest-contentful-paint": "LCP",
            "total-blocking-time": "TBT",
            "cumulative-layout-shift": "CLS",
            "speed-index": "Speed Index",
        }
        web_vitals = {}
        for key, name in vital_keys.items():
            if key in audits:
                audit = audits[key]
                score = audit.get("score", 0)
                web_vitals[name] = {
                    "value": audit.get("displayValue", "N/A"),
                    "score": round((score or 0) * 100),
                }

        # 개선 기회 (savings > 100ms)
        opportunities = []
        for key, audit in audits.items():
            if audit.get("details", {}).get("type") == "opportunity":
                savings = audit.get("details", {}).get("overallSavingsMs", 0)
                if savings > 100:
                    opportunities.append({
                        "title": audit.get("title", key),
                        "savings_ms": int(savings),
                        "description": audit.get("description", "")[:200],
                    })
        opportunities.sort(key=lambda x: x["savings_ms"], reverse=True)

        lighthouse_result = {
            "ok": True,
            "scores": scores,
            "report_path": str(output_file),
        }

        if web_vitals:
            lighthouse_result["web_vitals"] = web_vitals
        if opportunities:
            lighthouse_result["opportunities"] = opportunities[:5]

        return lighthouse_result

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Lighthouse 실행 시간 초과 (120초)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_screenshot(url: str, label: str) -> dict:
    """스크린샷 캡처 (Chromium headless 사용)"""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUTS_DIR / f"screenshot-{label}-{timestamp}.png"

    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    chrome_path = None
    for p in chrome_paths:
        if p and Path(p).exists():
            chrome_path = p
            break

    if not chrome_path:
        return {"ok": False, "error": "Chrome/Chromium을 찾을 수 없습니다"}

    try:
        result = subprocess.run(
            [
                chrome_path,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                f"--screenshot={output_file}",
                "--window-size=1280,800",
                url,
            ],
            capture_output=True, text=True, timeout=30,
        )

        if output_file.exists():
            return {
                "ok": True,
                "path": str(output_file),
                "size": f"{output_file.stat().st_size // 1024}KB",
            }
        else:
            return {"ok": False, "error": f"스크린샷 생성 실패: {result.stderr[:200]}"}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "스크린샷 캡처 시간 초과"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run(tool_input: dict, package_dir: Path) -> dict:
    site_id = tool_input.get("site_id")
    url = tool_input.get("url")

    # site_id 또는 url 중 하나 필수
    if not site_id and not url:
        return {"success": False, "error": "site_id 또는 url 중 하나를 지정하세요"}

    # site_id로 URL 조회
    if site_id:
        site = find_site(site_id, package_dir)
        if not site:
            sites = load_sites(package_dir)
            available = [s["id"] for s in sites]
            return {
                "success": False,
                "error": f"사이트를 찾을 수 없습니다: {site_id}",
                "available_sites": available,
            }
        url = site.get("deploy_url", "")
        if not url:
            return {
                "success": False,
                "error": f"'{site_id}'에 배포 URL이 설정되지 않았습니다. site_registry update로 추가하세요.",
            }
        label = site_id
    else:
        # URL 직접 지정 시 label 생성
        label = url.replace("https://", "").replace("http://", "").split("/")[0].replace(".", "_")

    checks = tool_input.get("checks") or ["status", "lighthouse", "screenshot"]
    result = {
        "success": True,
        "url": url,
        "checked_at": datetime.now().isoformat(),
    }
    if site_id:
        result["site_id"] = site_id

    if "status" in checks:
        result["status"] = check_status(url)

    if "lighthouse" in checks:
        result["lighthouse"] = check_lighthouse(url, label)

    if "screenshot" in checks:
        result["screenshot"] = check_screenshot(url, label)

    # 등록된 사이트면 last_checked 업데이트
    if site_id:
        update_last_checked(site_id, package_dir)

    return result
