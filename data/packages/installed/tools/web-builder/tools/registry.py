"""
site_registry: 홈페이지 등록/조회/삭제/수정
"""
import json
import re
from pathlib import Path
from datetime import datetime


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


def make_id(name: str) -> str:
    """이름에서 URL-safe ID 생성"""
    slug = re.sub(r'[^a-zA-Z0-9가-힣\s-]', '', name)
    slug = re.sub(r'\s+', '-', slug.strip()).lower()
    return slug or "site"


def detect_tech_stack(local_path: str) -> list:
    """로컬 경로에서 기술 스택 자동 감지"""
    path = Path(local_path)
    if not path.exists():
        return []

    stack = []

    checks = {
        "package.json": None,
        "vercel.json": "vercel",
        "next.config.js": "nextjs",
        "next.config.mjs": "nextjs",
        "next.config.ts": "nextjs",
        "nuxt.config.ts": "nuxt",
        "vite.config.ts": "vite",
        "vite.config.js": "vite",
        "tsconfig.json": "typescript",
        "tailwind.config.js": "tailwind",
        "tailwind.config.ts": "tailwind",
        "index.html": "html",
        "gatsby-config.js": "gatsby",
        "astro.config.mjs": "astro",
        "svelte.config.js": "svelte",
        "angular.json": "angular",
        "Dockerfile": "docker",
        "netlify.toml": "netlify",
    }

    for filename, tech in checks.items():
        if (path / filename).exists():
            if tech and tech not in stack:
                stack.append(tech)

    # package.json 분석
    pkg_file = path / "package.json"
    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            dep_checks = {
                "react": "react",
                "next": "nextjs",
                "vue": "vue",
                "svelte": "svelte",
                "@angular/core": "angular",
                "tailwindcss": "tailwind",
                "three": "threejs",
                "framer-motion": "framer-motion",
            }
            for dep, tech in dep_checks.items():
                if dep in deps and tech not in stack:
                    stack.append(tech)
        except Exception:
            pass

    # CSS 파일 존재
    css_files = list(path.glob("*.css")) + list(path.glob("src/**/*.css"))
    if css_files and "css" not in stack:
        stack.append("css")

    return stack


def register_site(tool_input: dict, package_dir: Path) -> dict:
    name = tool_input.get("name")
    local_path = tool_input.get("local_path")

    if not name:
        return {"success": False, "error": "name은 필수입니다"}
    if not local_path:
        return {"success": False, "error": "local_path는 필수입니다"}

    path = Path(local_path)
    if not path.exists():
        return {"success": False, "error": f"경로가 존재하지 않습니다: {local_path}"}

    sites = load_sites(package_dir)

    site_id = make_id(name)
    existing_ids = {s["id"] for s in sites}
    if site_id in existing_ids:
        return {"success": False, "error": f"이미 등록된 사이트 ID: {site_id}"}

    tech_stack = detect_tech_stack(local_path)

    site = {
        "id": site_id,
        "name": name,
        "local_path": local_path,
        "repo_url": tool_input.get("repo_url", ""),
        "deploy_url": tool_input.get("deploy_url", ""),
        "tech_stack": tech_stack,
        "description": tool_input.get("description", ""),
        "registered_at": datetime.now().isoformat(),
        "last_checked": None,
    }

    sites.append(site)
    save_sites(sites, package_dir)

    return {
        "success": True,
        "message": f"'{name}' 사이트가 등록되었습니다",
        "site": site,
    }


def list_sites(package_dir: Path) -> dict:
    sites = load_sites(package_dir)
    if not sites:
        return {"success": True, "sites": [], "message": "등록된 사이트가 없습니다"}

    summary = []
    for s in sites:
        summary.append({
            "id": s["id"],
            "name": s["name"],
            "deploy_url": s.get("deploy_url", ""),
            "tech_stack": s.get("tech_stack", []),
            "last_checked": s.get("last_checked"),
        })

    return {"success": True, "count": len(sites), "sites": summary}


def remove_site(site_id: str, package_dir: Path) -> dict:
    if not site_id:
        return {"success": False, "error": "site_id는 필수입니다"}

    sites = load_sites(package_dir)
    original_count = len(sites)
    sites = [s for s in sites if s["id"] != site_id]

    if len(sites) == original_count:
        return {"success": False, "error": f"사이트를 찾을 수 없습니다: {site_id}"}

    save_sites(sites, package_dir)
    return {"success": True, "message": f"'{site_id}' 사이트가 제거되었습니다"}


def update_site(tool_input: dict, package_dir: Path) -> dict:
    site_id = tool_input.get("site_id")
    if not site_id:
        return {"success": False, "error": "site_id는 필수입니다"}

    sites = load_sites(package_dir)
    target = None
    for s in sites:
        if s["id"] == site_id:
            target = s
            break

    if not target:
        return {"success": False, "error": f"사이트를 찾을 수 없습니다: {site_id}"}

    updatable = ["name", "local_path", "repo_url", "deploy_url", "description"]
    updated = []
    for field in updatable:
        if field in tool_input and tool_input[field] is not None:
            target[field] = tool_input[field]
            updated.append(field)

    if "local_path" in updated:
        target["tech_stack"] = detect_tech_stack(target["local_path"])

    save_sites(sites, package_dir)
    return {
        "success": True,
        "message": f"'{site_id}' 사이트가 업데이트되었습니다",
        "updated_fields": updated,
        "site": target,
    }


def run(tool_input: dict, package_dir: Path) -> dict:
    action = tool_input.get("action")

    if action == "register":
        return register_site(tool_input, package_dir)
    elif action == "list":
        return list_sites(package_dir)
    elif action == "remove":
        return remove_site(tool_input.get("site_id"), package_dir)
    elif action == "update":
        return update_site(tool_input, package_dir)
    else:
        return {
            "success": False,
            "error": f"알 수 없는 action: {action}",
            "available_actions": ["register", "list", "remove", "update"]
        }
