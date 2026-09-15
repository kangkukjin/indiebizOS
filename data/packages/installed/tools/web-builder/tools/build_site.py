"""
build_site.py
프로덕션 빌드를 생성합니다.
"""

import subprocess
import json
import os

TOOL_NAME = "build_site"
TOOL_DESCRIPTION = "프로덕션 빌드를 생성합니다"
TOOL_PARAMETERS = {
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로",
        "required": True
    },
    "analyze": {
        "type": "boolean",
        "description": "번들 분석 포함 여부",
        "default": False
    }
}


def run_command(cmd: list, cwd: str = None, timeout: int = 300, env=None) -> dict:
    """명령어 실행"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "빌드 시간 초과 (5분)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _artifact_snapshot(project_path):
    """관례 경로는 후보일 뿐이다. 실제 빌드에서 바뀐 파일로 출력 경로를 확인한다."""
    snapshots = {}
    for name in (".next", "dist", "out", "build", ".output"):
        directory = os.path.join(project_path, name)
        if not os.path.isdir(directory):
            continue
        files = []
        for root, dirs, names in os.walk(directory, followlinks=False):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
            for filename in sorted(names):
                path = os.path.join(root, filename)
                if os.path.islink(path):
                    continue
                stat = os.stat(path)
                files.append((os.path.relpath(path, directory), stat.st_size, stat.st_mtime_ns))
        snapshots[name] = sorted(files)
    return snapshots


def get_build_stats(project_path: str, before=None) -> dict:
    """빌드가 갱신한 후보가 하나일 때만 출력 경로를 확정한다."""
    after = _artifact_snapshot(project_path)
    candidates = [name for name, files in after.items()
                  if files and (before is None or files != before.get(name))]
    outputs = [{"output_dir": os.path.join(project_path, name), "exists": True,
                "total_size_mb": round(sum(f[1] for f in after[name]) / (1024 * 1024), 2),
                "file_count": len(after[name])} for name in candidates]
    if len(outputs) == 1:
        return {**outputs[0], "outputs": outputs}
    return {"output_dir": None, "exists": False, "outputs": outputs,
            "message": "빌드 출력 경로가 여러 개입니다." if outputs else
                       "관례 경로에서 갱신된 산출물을 확인하지 못했습니다. 프로젝트 빌드 설정을 확인하세요."}


def run(project_path: str, analyze: bool = False) -> dict:
    """
    프로덕션 빌드 생성

    Args:
        project_path: 프로젝트 경로
        analyze: 번들 분석 포함 여부

    Returns:
        빌드 결과
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"프로젝트를 찾을 수 없습니다: {project_path}"}

    # package.json 확인
    package_json = os.path.join(project_path, "package.json")
    if not os.path.exists(package_json):
        return {"success": False, "error": "package.json을 찾을 수 없습니다"}

    try:
        with open(package_json, encoding="utf-8") as source:
            package = json.load(source)
    except (OSError, ValueError) as exc:
        return {"success": False, "error": f"package.json 읽기 실패: {exc}"}
    scripts = package.get("scripts", {})
    if not scripts.get("build"):
        return {"success": False, "error": "package.json에 build 스크립트가 없습니다."}
    results = []
    if scripts.get("lint"):
        lint_result = run_command(["npm", "run", "lint"], cwd=project_path, timeout=60)
        results.append("린트 검사 통과" if lint_result["success"] else "린트 검사 실패 (빌드 계속 진행)")
    else:
        results.append("lint 스크립트 없음 — 검사 생략")

    before = _artifact_snapshot(project_path)
    results.append("프로덕션 빌드 중...")
    env = {**os.environ, "ANALYZE": "true"} if analyze else None
    build_result = run_command(["npm", "run", "build"], cwd=project_path, timeout=300, env=env)

    if not build_result["success"]:
        error_msg = build_result.get("stderr", build_result.get("error", "알 수 없는 오류"))
        return {
            "success": False,
            "error": f"빌드 실패: {error_msg[:1000]}",
            "logs": results
        }

    results.append("   ✓ 빌드 완료")

    # 3. 빌드 통계
    stats = get_build_stats(project_path, before)
    results.append(f"3. 빌드 결과:")
    results.append(f"   - 출력 디렉토리: {stats['output_dir'] or '미확정'}")
    results.append(f"   - 총 크기: {stats.get('total_size_mb', 'N/A')} MB")
    results.append(f"   - 파일 수: {stats.get('file_count', 'N/A')}개")

    # 빌드 출력에서 주요 정보 추출
    stdout = build_result.get("stdout", "")
    if "Route" in stdout or "Size" in stdout:
        results.append("4. 라우트 정보:")
        for line in stdout.split("\n"):
            if "○" in line or "●" in line or "ƒ" in line or "λ" in line:
                results.append(f"   {line.strip()}")

    return {
        "success": True,
        "project_path": project_path,
        "output_dir": stats["output_dir"],
        "stats": stats,
        "logs": results,
        "next_steps": [
            "프로젝트의 기존 미리보기 절차로 실제 산출물을 확인",
            "등록된 배포처와 프로젝트 배포 설정에 따라 검증한 산출물을 배포"
        ]
    }


if __name__ == "__main__":
    result = run(
        project_path="outputs/web-projects/test-project"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
