"""수리 사본의 읽기 전용 의존성과 쓰기 가능한 검사 캐시·런타임."""
import os
import shutil
import subprocess
from pathlib import Path


def prepare_dependencies(repo, workspace):
    """패키지 바이트는 빌리되 node_modules 자체와 캐시는 사본이 소유한다."""
    source = Path(repo).resolve() / "frontend/node_modules"
    root = Path(workspace).resolve()
    target = root / "frontend/node_modules"
    if not source.is_dir() or source == target:
        return
    if not target.parent.resolve().is_relative_to(root):
        raise ValueError("수리 의존성의 부모 경로가 사본 밖을 가리킵니다")
    if target.is_symlink():
        if target.resolve() != source:
            raise ValueError("수리 의존성 링크가 원래 저장소와 다릅니다")
        target.unlink()
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        # 도구별 캐시는 숨김 디렉터리에 쓴다. 실행 링크와 lock만 읽기 공유한다.
        if child.name.startswith(".") and child.name not in {".bin", ".package-lock.json"}:
            continue
        destination = target / child.name
        if not os.path.lexists(destination):
            destination.symlink_to(child, target_is_directory=child.is_dir())
    (target / ".tmp").mkdir(exist_ok=True)


def node_runtime(workspace, env):
    """설치된 후보 중 프로젝트와 직접 의존성의 engines.node를 만족하는 Node를 고른다."""
    from coding_process import sandbox_command
    from runtime_utils import get_runtime_paths
    root = Path(workspace).resolve()
    project = root / "frontend"
    if not (project / "package.json").is_file():
        project = root
    if not (project / "package.json").is_file():
        return None
    candidates = [get_runtime_paths().get("node")]
    candidates += [shutil.which("node", path=entry)
                   for entry in env.get("PATH", os.defpath).split(os.pathsep) if entry]
    seen = set()
    # 사본의 패키지도 수정 가능하므로 탐색 프로브부터 같은 OS 경계 안에서 실행한다.
    # package script·설치 훅은 실행하지 않고 semver와 JSON만 읽는다.
    probe = """
const fs = require('node:fs'), path = require('node:path');
const root = process.argv[1];
const semver = require(path.join(root, 'node_modules/semver'));
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json')));
const manifests = [pkg];
for (const name of Object.keys({...pkg.dependencies, ...pkg.devDependencies})) {
  const file = path.join(root, 'node_modules', name, 'package.json');
  if (fs.existsSync(file)) manifests.push(JSON.parse(fs.readFileSync(file)));
}
process.exit(manifests.every(p => !p.engines?.node || semver.satisfies(process.version, p.engines.node)) ? 0 : 1);
"""
    for candidate in candidates:
        binary = shutil.which(candidate, path=env.get("PATH")) if candidate else None
        if not binary or binary in seen:
            continue
        seen.add(binary)
        try:
            runtime = env.get("TMPDIR") or root
            command = sandbox_command([binary, "-e", probe, str(project)], runtime, runtime)
            result = subprocess.run(command, env=env, cwd=project, capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return binary
    return None
