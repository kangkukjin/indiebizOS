"""
browser_storage.py - 쿠키/인증 상태 저장 및 복원

로그인 상태 유지를 위한 쿠키, localStorage 저장/복원 기능.

Version: 3.0.0
"""

import json
import os
import stat
import time
from datetime import datetime
from urllib.parse import urlparse

from browser_session import BrowserSession, ensure_active, get_cookies_dir


async def browser_cookies_save(params: dict, project_path: str = ".") -> dict:
    """현재 브라우저의 쿠키와 localStorage를 파일로 저장"""
    err = ensure_active()
    if err:
        return err

    name = params.get("name", "")
    session = BrowserSession.get_instance()
    page = session.raw_page

    try:
        # 저장 이름 결정
        if not name:
            current_url = page.url
            parsed = urlparse(current_url)
            name = parsed.netloc.replace("www.", "") if parsed.netloc else "default"

        # 쿠키 추출
        cookies = await page.context.cookies()

        # 만료된 쿠키 필터링
        now = time.time()
        valid_cookies = []
        for cookie in cookies:
            expires = cookie.get("expires", -1)
            if expires == -1 or expires > now:
                valid_cookies.append(cookie)

        # localStorage 추출
        local_storage = {}
        try:
            local_storage = await page.evaluate("""() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }""")
        except Exception:
            pass

        # 저장 데이터 구성
        save_data = {
            "name": name,
            "url": page.url,
            "saved_at": datetime.now().isoformat(),
            "cookies": valid_cookies,
            "local_storage": local_storage,
        }

        # 파일 저장
        cookies_dir = get_cookies_dir()
        safe_name = "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)
        filepath = cookies_dir / f"{safe_name}.json"

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        # 파일 권한 설정 (소유자만 읽기/쓰기)
        try:
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

        return {
            "success": True,
            "name": name,
            "file_path": str(filepath),
            "cookies_count": len(valid_cookies),
            "local_storage_keys": len(local_storage),
            "message": f"'{name}' 상태 저장 완료. browser_cookies_load(name='{name}')로 복원 가능합니다."
        }
    except Exception as e:
        return {"success": False, "error": f"쿠키 저장 실패: {str(e)}"}


async def browser_cookies_load(params: dict, project_path: str = ".") -> dict:
    """저장된 쿠키와 localStorage를 브라우저에 복원"""
    err = ensure_active()
    if err:
        return err

    name = params.get("name", "")
    if not name:
        # 저장된 파일 목록 반환
        cookies_dir = get_cookies_dir()
        files = []
        if cookies_dir.exists():
            for f in sorted(cookies_dir.glob("*.json")):
                try:
                    with open(f, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    files.append({
                        "name": data.get("name", f.stem),
                        "url": data.get("url", ""),
                        "saved_at": data.get("saved_at", ""),
                        "cookies_count": len(data.get("cookies", [])),
                    })
                except Exception:
                    files.append({"name": f.stem, "error": "파일 읽기 실패"})

        if files:
            return {
                "success": False,
                "error": "name이 필요합니다. 아래 목록에서 선택하세요.",
                "saved_states": files
            }
        return {"success": False, "error": "저장된 쿠키 상태가 없습니다."}

    session = BrowserSession.get_instance()
    page = session.raw_page

    try:
        # 파일 읽기
        cookies_dir = get_cookies_dir()
        safe_name = "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)
        filepath = cookies_dir / f"{safe_name}.json"

        if not filepath.exists():
            return {
                "success": False,
                "error": f"'{name}' 상태 파일을 찾을 수 없습니다.",
                "file_path": str(filepath)
            }

        with open(filepath, 'r', encoding='utf-8') as f:
            save_data = json.load(f)

        cookies = save_data.get("cookies", [])
        local_storage = save_data.get("local_storage", {})
        saved_url = save_data.get("url", "")

        # 쿠키 복원
        if cookies:
            await page.context.add_cookies(cookies)

        # localStorage 복원 (같은 도메인에서만 작동)
        if local_storage and saved_url:
            current_url = page.url
            saved_domain = urlparse(saved_url).netloc
            current_domain = urlparse(current_url).netloc

            if saved_domain == current_domain:
                for key, value in local_storage.items():
                    try:
                        await page.evaluate(
                            "(args) => localStorage.setItem(args.key, args.value)",
                            {"key": key, "value": value}
                        )
                    except Exception:
                        pass
            else:
                # 도메인이 다르면 먼저 해당 URL로 이동
                try:
                    await page.goto(saved_url, wait_until="load", timeout=30000)
                    for key, value in local_storage.items():
                        try:
                            await page.evaluate(
                                "(args) => localStorage.setItem(args.key, args.value)",
                                {"key": key, "value": value}
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

        # 페이지 리로드
        try:
            await page.reload(wait_until="load", timeout=30000)
        except Exception:
            pass

        session.clear_refs()

        return {
            "success": True,
            "name": name,
            "cookies_loaded": len(cookies),
            "local_storage_loaded": len(local_storage),
            "url": page.url,
            "message": f"'{name}' 상태 복원 완료. 로그인 상태가 유지됩니다.",
            "snapshot_hint": "페이지 구조를 파악하려면 browser_snapshot을 호출하세요."
        }
    except Exception as e:
        return {"success": False, "error": f"쿠키 복원 실패: {str(e)}"}
