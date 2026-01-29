"""
site_snapshot: 등록된 사이트의 현재 상태 요약
파일 구조, git 이력, 페이지 목록, 의존성, 배포 설정을 한눈에 제공
"""
import json
import subprocess
from pathlib import Path


def load_sites(package_dir: Path) -> list:
    sites_file = package_dir / "sites.json"
    if sites_file.exists():
        return json.loads(sites_file.read_text(encoding="utf-8"))
    return []


def find_site(site_id: str, package_dir: Path) -> dict | None:
    sites = load_sites(package_dir)
    for s in sites:
        if s["id"] == site_id:
            return s
    return None


def get_file_tree(path: Path, max_depth: int = 3) -> list:
    """주요 파일/폴더만 포함하는 트리 생성"""
    skip_dirs = {
        "node_modules", ".git", ".next", ".vercel", "dist", "build",
        "__pycache__", ".cache", ".turbo", "coverage", ".svelte-kit",
    }
    skip_files = {".DS_Store", "Thumbs.db"}

    items = []

    def walk(current: Path, depth: int, prefix: str = ""):
        if depth > max_depth:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        except PermissionError:
            return

        dirs = [e for e in entries if e.is_dir() and e.name not in skip_dirs]
        files = [e for e in entries if e.is_file() and e.name not in skip_files]

        for d in dirs:
            items.append(f"{prefix}{d.name}/")
            walk(d, depth + 1, prefix + "  ")

        for f in files:
            items.append(f"{prefix}{f.name}")

    walk(path, 0)
    return items


def get_git_log(path: Path, count: int = 5) -> list:
    """최근 git 커밋 내역"""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={count}", "--format=%h|%s|%cr|%an"],
            cwd=str(path),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "when": parts[2],
                    "author": parts[3],
                })
        return commits
    except Exception:
        return []


def get_git_status(path: Path) -> dict:
    """현재 변경 사항 요약"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(path),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"tracked": False}

        lines = [l for l in result.stdout.strip().split("\n") if l]
        modified = [l[3:] for l in lines if l.startswith(" M") or l.startswith("M ")]
        added = [l[3:] for l in lines if l.startswith("A ") or l.startswith("??")]
        deleted = [l[3:] for l in lines if l.startswith(" D") or l.startswith("D ")]

        return {
            "tracked": True,
            "clean": len(lines) == 0,
            "modified": modified,
            "added": added,
            "deleted": deleted,
        }
    except Exception:
        return {"tracked": False}


def get_pages(path: Path) -> list:
    """주요 페이지 파일 목록"""
    page_extensions = {".html", ".tsx", ".jsx", ".vue", ".svelte", ".astro", ".md", ".mdx"}
    skip_dirs = {"node_modules", ".next", ".git", "dist", "build", "__pycache__"}

    pages = []
    for ext in page_extensions:
        for f in path.rglob(f"*{ext}"):
            if any(part in skip_dirs for part in f.parts):
                continue
            rel = str(f.relative_to(path))
            pages.append(rel)

    return sorted(pages)


def get_package_info(path: Path) -> dict | None:
    """package.json 요약"""
    pkg_file = path / "package.json"
    if not pkg_file.exists():
        return None

    try:
        pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
        return {
            "name": pkg.get("name", ""),
            "version": pkg.get("version", ""),
            "scripts": list(pkg.get("scripts", {}).keys()),
            "dependencies": list(pkg.get("dependencies", {}).keys()),
            "devDependencies": list(pkg.get("devDependencies", {}).keys()),
        }
    except Exception:
        return None


def get_vercel_config(path: Path) -> dict | None:
    """vercel.json 요약"""
    vercel_file = path / "vercel.json"
    if not vercel_file.exists():
        return None

    try:
        return json.loads(vercel_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def run(tool_input: dict, package_dir: Path) -> dict:
    site_id = tool_input.get("site_id")
    if not site_id:
        return {"success": False, "error": "site_id는 필수입니다"}

    site = find_site(site_id, package_dir)
    if not site:
        sites = load_sites(package_dir)
        available = [s["id"] for s in sites]
        return {
            "success": False,
            "error": f"사이트를 찾을 수 없습니다: {site_id}",
            "available_sites": available,
        }

    local_path = Path(site["local_path"])
    if not local_path.exists():
        return {"success": False, "error": f"로컬 경로가 존재하지 않습니다: {site['local_path']}"}

    snapshot = {
        "success": True,
        "site": {
            "id": site["id"],
            "name": site["name"],
            "local_path": site["local_path"],
            "deploy_url": site.get("deploy_url", ""),
            "tech_stack": site.get("tech_stack", []),
        },
        "file_tree": get_file_tree(local_path),
        "pages": get_pages(local_path),
        "git": {
            "recent_commits": get_git_log(local_path),
            "status": get_git_status(local_path),
        },
    }

    pkg_info = get_package_info(local_path)
    if pkg_info:
        snapshot["package"] = pkg_info

    vercel_config = get_vercel_config(local_path)
    if vercel_config:
        snapshot["vercel"] = vercel_config

    return snapshot
