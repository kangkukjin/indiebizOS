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


def run_command(cmd: list, cwd: str = None, timeout: int = 300) -> dict:
    """명령어 실행"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
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


def get_build_stats(project_path: str) -> dict:
    """빌드 결과 통계"""
    out_dir = os.path.join(project_path, ".next")
    stats = {
        "output_dir": out_dir,
        "exists": os.path.exists(out_dir)
    }

    if stats["exists"]:
        # 디렉토리 크기 계산
        total_size = 0
        file_count = 0
        for dirpath, dirnames, filenames in os.walk(out_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
                file_count += 1

        stats["total_size_mb"] = round(total_size / (1024 * 1024), 2)
        stats["file_count"] = file_count

    return stats


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

    results = []

    # 1. 린트 검사 (선택적)
    results.append("1. 코드 검사 중...")
    lint_result = run_command(["npm", "run", "lint"], cwd=project_path, timeout=60)
    if lint_result["success"]:
        results.append("   ✓ 린트 검사 통과")
    else:
        results.append("   ⚠ 린트 경고가 있습니다 (빌드 계속 진행)")

    # 2. 빌드 실행
    results.append("2. 프로덕션 빌드 중...")
    build_cmd = ["npm", "run", "build"]

    if analyze:
        # 번들 분석 환경변수 설정
        env = os.environ.copy()
        env["ANALYZE"] = "true"
        build_result = run_command(build_cmd, cwd=project_path, timeout=300)
    else:
        build_result = run_command(build_cmd, cwd=project_path, timeout=300)

    if not build_result["success"]:
        error_msg = build_result.get("stderr", build_result.get("error", "알 수 없는 오류"))
        return {
            "success": False,
            "error": f"빌드 실패: {error_msg[:1000]}",
            "logs": results
        }

    results.append("   ✓ 빌드 완료")

    # 3. 빌드 통계
    stats = get_build_stats(project_path)
    results.append(f"3. 빌드 결과:")
    results.append(f"   - 출력 디렉토리: .next/")
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
        "output_dir": os.path.join(project_path, ".next"),
        "stats": stats,
        "logs": results,
        "next_steps": [
            "preview_site로 빌드 결과 확인",
            "deploy_vercel로 Vercel에 배포",
            "또는 .next 폴더를 다른 호스팅에 업로드"
        ]
    }


if __name__ == "__main__":
    result = run(
        project_path="/Users/kangkukjin/Desktop/AI/outputs/web-projects/test-project"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
