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
        "permissions": "scoped-command-and-analysis-v2", "provider": provider.__class__.__name__,
        "model": provider.model}, sort_keys=True).encode()).hexdigest()
    provider.coding_environment = {}
    if provider.__class__.__name__ == "CodexProvider":
        provider.coding_environment = isolated_codex_environment(processes.runtime)
    # 모델 교체는 앱의 명시적 인계로 이어간다. CLI 내부 이력 혼합을 피한다.
    provider.disable_session_persistence = True
    import sys
    bridge = getattr(processes, 'analysis_bridge', None)
    if bridge:
        provider.coding_bridge_command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'code_analysis_cli.py'),
                                         '--mcp', '--connection', str(bridge.channel.config)]
        config = Path(processes.runtime) / 'coding-mcp.json'
        config.write_text(json.dumps({'mcpServers': {'indiebizos': {'command': provider.coding_bridge_command[0],
                           'args': provider.coding_bridge_command[1:]}}}))
        provider.coding_mcp_config = str(config)


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
               "--sandbox", "read-only", "-c", 'approval_policy="never"',
               "-c", "notify=[]", "-c", 'web_search="disabled"',
               "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
               "-c", "sandbox_workspace_write.exclude_slash_tmp=true"]
    # Native tools are read-only. All writes use the same OS-confined run_command as API workers.
    bridge = getattr(provider, 'coding_bridge_command', None)
    if bridge:
        command += ['-c', 'mcp_servers.indiebizos.command=' + json.dumps(bridge[0]),
                    '-c', 'mcp_servers.indiebizos.args=' + json.dumps(bridge[1:])]

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


def claude_command(provider, stream, system_prompt_file=None):
    command = [provider._binary_path, '--print', '--output-format', 'stream-json' if stream else 'json',
               '--permission-mode', 'bypassPermissions', '--no-session-persistence', '--setting-sources', '',
               '--strict-mcp-config', '--tools', '', '--allowed-tools',
               'mcp__indiebizos__execute_ibl,mcp__indiebizos__run_command',
               '--mcp-config', provider.coding_mcp_config]
    if stream:
        command += ['--verbose']
    if provider.model:
        command += ['--model', provider.model]
    command += ['--append-system-prompt-file', system_prompt_file] if system_prompt_file else [
        '--append-system-prompt', provider.system_prompt or '']
    return command
