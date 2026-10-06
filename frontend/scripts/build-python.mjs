import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const pythonEnv = () => ({ ...process.env, PYTHONUTF8: '1' });

// Shared by Vite and npm scripts; never require a Windows python3 alias.
export function pythonCommand({ platform = process.platform, env = process.env,
  projectRoot = root, exists = fs.existsSync, probe = spawnSync } = {}) {
  if (env.INDIEBIZ_PYTHON) return [env.INDIEBIZ_PYTHON];
  const venv = path.join(projectRoot, platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python3');
  if (exists(venv)) return [venv];
  const candidates = platform === 'win32' ? [['python'], ['py', '-3'], ['python3']] : [['python3'], ['python']];
  for (const [command, ...args] of candidates) {
    const result = probe(command, [...args, '-c', 'import sys; sys.exit(sys.version_info.major != 3)'],
      { env: { ...env, PYTHONUTF8: '1' }, stdio: 'ignore', timeout: 10000 });
    if (!result.error && result.status === 0) return [command, ...args];
  }
  throw new Error('Python 3 is required. Install Python or set INDIEBIZ_PYTHON to its executable.');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const [command, ...prefix] = pythonCommand();
    const result = spawnSync(command, [...prefix, ...process.argv.slice(2)], { stdio: 'inherit', env: pythonEnv() });
    if (result.error) throw result.error;
    process.exitCode = result.status ?? 1;
  } catch (error) {
    console.error(error.message); process.exitCode = 1;
  }
}
