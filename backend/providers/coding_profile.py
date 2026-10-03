"""명시적인 coding 프로필. 일반 IBL·의식 세션의 기본 정책은 바꾸지 않는다."""
import hashlib
import json
import os
from pathlib import Path


def configure(provider, task, processes):
    provider.execution_profile = "coding"
    provider.TOOL_POLICY = ""
    provider.coding_processes = processes
    provider.coding_session_key = "coding:" + hashlib.sha256(json.dumps({
        "task": task["id"], "workspace": task["workspace"], "profile": "coding",
        "permissions": "macos-workspace-only-v1", "provider": provider.__class__.__name__,
        "model": provider.model}, sort_keys=True).encode()).hexdigest()
    provider.coding_environment = {}
    if provider.__class__.__name__ == "CodexProvider":
        provider.coding_environment = isolated_codex_environment(processes.runtime)
    # 모델 교체는 앱의 명시적 인계로 이어간다. CLI 내부 이력 혼합을 피한다.
    provider.disable_session_persistence = True


def isolated_codex_environment(runtime):
    home = Path(runtime) / "codex"
    home.mkdir(parents=True, exist_ok=True)
    auth = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    if not auth.is_file():
        raise RuntimeError("Codex 구독 로그인이 필요합니다")
    link = home / "auth.json"
    if not link.exists():
        link.symlink_to(auth.resolve())
    return {"CODEX_HOME": str(home)}


def codex_command(provider, resume_session_id=None):
    command = [provider._binary_path, "exec", "--json", "--skip-git-repo-check",
               "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
               "-c", "notify=[]", "-c", 'web_search="disabled"',
               "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
               "-c", "sandbox_workspace_write.exclude_slash_tmp=true"]
    # 쓰기 경계는 이 workspace-write 샌드박스 한 겹이다(작업 공간만 쓰기, .git·임시 폴더·네트워크 차단).
    # coding에는 IndieBiz MCP 브리지를 설치하지 않는다. OS 제한 밖 쓰기 우회가 된다.
    for feature in provider.CODEX_DISABLED_FEATURES:
        command += ["-c", f"features.{feature}=false"]
    model, effort = provider._model_and_effort()
    if model:
        command += ["-m", model]
    if effort:
        command += ["-c", "model_reasoning_effort=" + json.dumps(effort)]
    if resume_session_id:
        command += ["resume", resume_session_id]
    return command + ["-"]
