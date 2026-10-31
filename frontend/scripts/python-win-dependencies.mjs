/** Synchronize the Python that is shipped, independently of the build host's venv. */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

export function syncDependencies(root, pythonDir, { run = execFileSync, platform = process.platform } = {}) {
  if (platform !== 'win32') throw new Error('Windows runtime dependencies must be synchronized and verified on Windows.');
  const python = join(pythonDir, 'python.exe');
  const requirements = ['core', 'tools'].map(name => join(root, 'backend', `requirements-${name}.txt`));
  for (const path of [python, ...requirements]) {
    if (!existsSync(path)) throw new Error(`Required runtime input is missing: ${path}`);
  }
  // A prior receipt is evidence, never a reason to skip checking the actual environment.
  const receipt = join(pythonDir, 'indiebiz-dependencies.json');
  writeFileSync(receipt, JSON.stringify({ status: 'checking' }));
  const options = { stdio: 'inherit', windowsHide: true };
  run(python, ['-m', 'pip', 'install', '--no-input', '--no-warn-script-location',
    ...requirements.flatMap(path => ['-r', path])], options);
  run(python, ['-m', 'pip', 'check'], options);
  const installed = JSON.parse(run(python, ['-m', 'pip', 'list', '--format=json'],
    { encoding: 'utf8', windowsHide: true }));
  const result = { status: 'verified', verified_at: new Date().toISOString(),
    requirements: requirements.map(path => ({ name: path.split(/[\\/]/).at(-1),
      sha256: createHash('sha256').update(readFileSync(path)).digest('hex') })), installed };
  writeFileSync(receipt, JSON.stringify(result, null, 2));
  return result;
}
