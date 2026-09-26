import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const file = readFileSync(new URL('../src/components/Launcher.tsx', import.meta.url), 'utf8');
const source = file.slice(file.indexOf('  const handleOpenSettings ='), file.indexOf('  const handleOpenScheduler ='));

function fixture(failing) {
  const stored = [
    { provider: 'codex', model: 'configured-model' },
    { provider: 'deepseek', model: 'deepseek-flash' },
    { provider: 'deepseek', model: 'deepseek-v4-pro' },
  ];
  const state = { shown: false, changes: 0, alerts: [], saved: [] };
  const context = vm.createContext({
    api: Object.fromEntries(['SystemAI', 'LightweightAI', 'MidtierAI'].flatMap((name, i) => [
      [`get${name}`, async () => {
        if (name === failing) throw new Error('backend restarting');
        return stored[i];
      }],
      [`update${name}`, async value => state.saved.push(value)],
    ])),
    console: { error() {} }, alert: text => state.alerts.push(text),
    setShowSettingsDialog: value => { state.shown = value; },
    ...Object.fromEntries(['System', 'Lightweight', 'Midtier'].map(name => [
      `set${name}AiSettings`, value => {
        state.changes++;
        context[`${name[0].toLowerCase()}${name.slice(1)}AiSettings`] = value;
      },
    ])),
  });
  vm.runInContext(source + '\nglobalThis.handlers = {handleOpenSettings, handleSaveSystemAi};', context);
  return { state, stored, ...context.handlers, recover() { failing = null; } };
}

for (const tier of ['SystemAI', 'LightweightAI', 'MidtierAI']) {
  test(`failed ${tier} read cannot expose defaults for saving`, async () => {
    const f = fixture(tier);
    await f.handleOpenSettings();
    assert.equal(f.state.shown, false);
    assert.equal(f.state.changes, 0);
    assert.equal(f.state.alerts.length, 1);
    assert.deepEqual(f.state.saved, []);
    f.recover();
    await f.handleOpenSettings();
    assert.equal(f.state.shown, true);
    await f.handleSaveSystemAi();
    assert.deepEqual(f.state.saved.map(({ provider, model }) => ({ provider, model })), f.stored);
  });
}

test('successful reads retain all three configured providers and models', async () => {
  const f = fixture(null);
  await f.handleOpenSettings();
  assert.equal(f.state.shown, true);
  assert.equal(f.state.alerts.length, 0);
  await f.handleSaveSystemAi();
  assert.deepEqual(f.state.saved.map(({ provider, model }) => ({ provider, model })), f.stored);
});
