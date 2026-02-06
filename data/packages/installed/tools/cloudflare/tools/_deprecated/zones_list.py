"""
Cloudflare Zone(도메인) 목록 조회 도구

계정에 등록된 도메인 목록과 workers.dev 서브도메인을 조회합니다.
"""

import json
import requests


def get_zones(api_token: str, account_id: str) -> dict:
    """Cloudflare에 등록된 도메인(Zone) 목록 조회"""
    try:
        response = requests.get(
            "https://api.cloudflare.com/client/v4/zones",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            },
            params={"account.id": account_id},
            timeout=15
        )
        data = response.json()

        if data.get("success"):
            zones = []
            for zone in data.get("result", []):
                zones.append({
                    "id": zone.get("id"),
                    "name": zone.get("name"),
                    "status": zone.get("status"),
                    "paused": zone.get("paused"),
                    "type": zone.get("type"),
                    "name_servers": zone.get("name_servers", [])
                })
            return {"success": True, "zones": zones, "count": len(zones)}
        else:
            return {
                "success": False,
                "error": "Zone 목록 조회 실패",
                "details": data.get("errors", [])
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_workers_subdomain(api_token: str, account_id: str) -> dict:
    """workers.dev 서브도메인 조회"""
    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/subdomain",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            },
            timeout=15
        )
        data = response.json()

        if data.get("success"):
            result = data.get("result", {})
            subdomain = result.get("subdomain")
            if subdomain:
                return {
                    "success": True,
                    "subdomain": subdomain,
                    "workers_dev_domain": f"{subdomain}.workers.dev"
                }
            else:
                return {
                    "success": False,
                    "error": "workers.dev 서브도메인이 설정되지 않았습니다",
                    "hint": "Cloudflare 대시보드 → Workers & Pages에 한 번 접속하면 자동으로 생성됩니다"
                }
        else:
            return {
                "success": False,
                "error": "workers.dev 서브도메인 조회 실패",
                "details": data.get("errors", [])
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run(tool_input: dict, creds: dict) -> dict:
    """
    Zone/도메인 목록 조회 실행

    action:
    - zones: 등록된 도메인 목록
    - workers_subdomain: workers.dev 서브도메인
    - all: 모든 정보 (기본값)
    """
    api_token = creds.get("api_token")
    account_id = creds.get("account_id")

    if not api_token or not account_id:
        return {
            "success": False,
            "error": "Cloudflare API 인증 정보가 필요합니다"
        }

    action = tool_input.get("action", "all")

    if action == "zones":
        return get_zones(api_token, account_id)

    elif action == "workers_subdomain":
        return get_workers_subdomain(api_token, account_id)

    elif action == "all":
        # 모든 정보 조회
        zones_result = get_zones(api_token, account_id)
        workers_result = get_workers_subdomain(api_token, account_id)

        available_domains = []

        # Zone에서 도메인 추출
        if zones_result.get("success"):
            for zone in zones_result.get("zones", []):
                if zone.get("status") == "active":
                    available_domains.append({
                        "domain": zone.get("name"),
                        "type": "zone",
                        "example_hostname": f"home.{zone.get('name')}"
                    })

        # workers.dev 추가
        if workers_result.get("success"):
            workers_domain = workers_result.get("workers_dev_domain")
            available_domains.append({
                "domain": workers_domain,
                "type": "workers.dev",
                "example_hostname": workers_domain,
                "note": "Workers/Pages 전용, Tunnel에는 자체 도메인 필요"
            })

        return {
            "success": True,
            "zones": zones_result.get("zones", []) if zones_result.get("success") else [],
            "zones_count": zones_result.get("count", 0) if zones_result.get("success") else 0,
            "workers_subdomain": workers_result.get("workers_dev_domain") if workers_result.get("success") else None,
            "available_domains": available_domains,
            "recommendation": available_domains[0] if available_domains else None,
            "hint": "Tunnel 설정에는 'zone' 타입의 도메인을 사용하세요. workers.dev는 Tunnel에 직접 사용할 수 없습니다."
        }

    else:
        return {
            "success": False,
            "error": f"알 수 없는 action: {action}",
            "available_actions": ["zones", "workers_subdomain", "all"]
        }
