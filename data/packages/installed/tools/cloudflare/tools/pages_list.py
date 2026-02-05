"""
Cloudflare Pages 프로젝트 목록 조회
"""

import requests


def run(tool_input: dict, creds: dict) -> dict:
    """
    Cloudflare Pages 프로젝트 목록 조회

    Args:
        tool_input: {project_name (선택)}
        creds: {api_token, account_id}

    Returns:
        프로젝트 목록 또는 특정 프로젝트 정보
    """
    project_name = tool_input.get("project_name")
    account_id = creds["account_id"]
    api_token = creds["api_token"]

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        if project_name:
            # 특정 프로젝트 조회
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{project_name}"
            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()

            if data.get("success"):
                project = data.get("result", {})
                return {
                    "success": True,
                    "project": {
                        "name": project.get("name"),
                        "subdomain": project.get("subdomain"),
                        "domains": project.get("domains", []),
                        "created_on": project.get("created_on"),
                        "production_branch": project.get("production_branch"),
                        "latest_deployment": project.get("latest_deployment", {}).get("url")
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "프로젝트를 찾을 수 없습니다.",
                    "details": data.get("errors", [])
                }
        else:
            # 전체 프로젝트 목록
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects"
            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()

            if data.get("success"):
                projects = data.get("result", [])
                return {
                    "success": True,
                    "count": len(projects),
                    "projects": [
                        {
                            "name": p.get("name"),
                            "subdomain": p.get("subdomain"),
                            "url": f"https://{p.get('subdomain')}.pages.dev" if p.get("subdomain") else None,
                            "created_on": p.get("created_on")
                        }
                        for p in projects
                    ]
                }
            else:
                return {
                    "success": False,
                    "error": "프로젝트 목록 조회 실패",
                    "details": data.get("errors", [])
                }

    except Exception as e:
        return {"success": False, "error": str(e)}
