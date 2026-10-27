"""Record post-implementation counterexamples, not passing acceptance tests.

Run from anywhere using the repository's .venv Python. No external adapters run;
function registration and public request journals use temporary directories.
"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from ibl_v2_adapters import Adapter, Adapted
from ibl_v2_compile import Compiler, compile_program
from ibl_v2_entry import handle_request
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime


def adapter(result, effects, run):
    return Adapter({'version': 1, 'params': {}, 'result': result,
                    'effects': effects}, run)


def execute(code, registry=None, **kwargs):
    inputs = kwargs.pop('inputs', None)
    return Runtime(compile_program(code, registry, inputs), inputs, **kwargs).run()


def brief(out):
    return {k: out.get(k) for k in ('success', 'executed', 'value', 'source_complete')} | {
        'diagnostic': (out.get('diagnostic') or {}).get('code'),
        'completion_status': (out.get('completion') or {}).get('status')}


def obligation(name, predicate, action, required=True):
    return {'id': name, 'predicate': predicate, 'required': required,
            'sources': [{'action': action, 'targets': {}}]}


def function_requirements(plan, name):
    return next(v['requirements'] for v in plan.function_contracts.values()
                if v['name'] == name)


def audit():
    findings = {}
    calls = []
    reg = {'t:write': adapter('Bool', ['write_external'], lambda rt, a: calls.append(1) or True)}
    contract = '{"$callable":{params:["Number"],result:"Bool",effects:["pure"]}}'
    direct = ('[def:f]($p:' + contract + '){return $p(1)};'
              'return [fn:f]{p:($x)=>[t:write]{}}')
    nested = ('[def:f]($cfg:{p:' + contract + '}){return $cfg.p(1)};'
              'return [fn:f]{cfg:{p:($x)=>[t:write]{}}}')
    rejected = execute(direct, reg)
    assert rejected['executed'] is False and not calls
    accepted = execute(nested, reg)
    assert accepted['success'] is True and calls == [1]
    findings['A1_nested_callable_contract'] = {
        'direct_source': direct, 'nested_source': nested,
        'direct': brief(rejected), 'nested': brief(accepted), 'nested_effect_calls': len(calls)}

    code = '[t:send]{};return [table:each]{items:[1]}{return abs}'
    spec = [obligation('r', 'true', 't:send')]
    calls = []
    reg = {'t:send': adapter('Number', ['write_external'], lambda rt, a: calls.append(1) or 1)}
    ordinary = execute(code, reg)
    assert ordinary['executed'] is True and ordinary['success'] is False and calls == [1]
    calls.clear()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        with (patch('ibl_v2_adapters.load_registry', lambda *a, **k: reg),
              patch('ibl_v2_store.definitions', lambda: {}),
              patch('tool_batch.prepared_plan', lambda *a: None),
              patch('ibl_run_journal.journal_root', lambda *a: root / 'runs')):
            public = handle_request({'edition': 2, 'code': code, 'completion': spec}, directory)
    assert public['executed'] is False and calls == [1]
    assert public['diagnostic']['code'] == 'VALUE_PROTOCOL'
    findings['A2_post_effect_failure_receipt'] = {
        'source': code, 'completion': spec, 'without_completion': brief(ordinary),
        'public_with_completion': brief(public), 'effect_calls': len(calls),
        'public_has_resume': bool(public.get('resume')), 'public_has_task_ref': bool(public.get('task_ref'))}

    reg = {'t:good': adapter('Number', ['read_external'], lambda rt, a: 2),
           't:partial': adapter('Number', ['read_external'], lambda rt, a: Adapted(7, {'incomplete': True}))}
    unsatisfied = execute('return [t:good]{}', reg,
                          completion=[obligation('good', '$value==3', 't:good')])
    from ibl_honesty import completion_evidence
    from conscious_supervisor import _failed
    assert unsatisfied['completion']['status'] == 'unsatisfied'
    assert completion_evidence(unsatisfied) == [] and _failed(unsatisfied) is False

    def down(rt, args):
        raise Fault('SOURCE_DOWN', 'synthetic source failure')

    fallback_reg = reg | {'t:bad': adapter('Number', ['read_external'], down)}
    fallback_spec = [obligation('good', '$value==2', 't:good')]
    wrappers = ['return [t:bad]{} ?? [t:good]{}',
                '[def:f](){return [t:bad]{} ?? [t:good]{}};return [fn:f]{}',
                'return ((($x)=>$x)([t:bad]{} ?? [t:good]{}))']
    fallback_results = [execute(s, fallback_reg, completion=fallback_spec) for s in wrappers]
    assert all(o['completion']['status'] == 'satisfied' and o['source_complete'] is False
               for o in fallback_results)
    # Execute the actual TypeScript helper, replacing only imports and fetch.
    javascript = r'''
const fs = require('fs'), vm = require('vm'), ts = require('./frontend/node_modules/typescript');
const source = fs.readFileSync('frontend/src/lib/instrument.ts', 'utf8');
const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const observations = [];
  for (const response of cases) {
    const box = {exports: {}, require: name => name === './remote-session'
      ? {iblSurface: {}, checkRemoteSession: () => {}} : {BACKEND_ORIGIN: 'http://synthetic.invalid'},
      fetch: async () => ({ok: true, status: 200, json: async () => response})};
    vm.runInNewContext(code, box);
    try {observations.push({accepted: true, value: await box.exports.iblExecuteApp('return 2')});}
    catch (e) {observations.push({accepted: false, message: e.message});}
  }
  process.stdout.write(JSON.stringify(observations));
})().catch(e => {process.stderr.write(String(e)); process.exitCode = 1;});
'''
    ui = subprocess.run(['node', '-e', javascript], cwd=ROOT, check=True, timeout=30,
                        input=json.dumps([unsatisfied, fallback_results[0]]), text=True,
                        capture_output=True)
    ui = json.loads(ui.stdout)
    assert ui[0] == {'accepted': True, 'value': 2} and ui[1]['accepted'] is False
    findings['A3_completion_consumers'] = {
        'unsatisfied': brief(unsatisfied), 'completion_evidence': completion_evidence(unsatisfied),
        'supervisor_failed': _failed(unsatisfied), 'actual_app_helper': ui,
        'fallback_wrapper_controls': [brief(o) for o in fallback_results]}

    code = ('[def:g]($x){return abs($x)};[def:f]($flag,$x){'
            '[if:$flag]{[fn:g]{x:$x}};return [fn:g]{x:$x}}')
    cached = function_requirements(compile_program(code), 'f')
    initialize = Compiler.init_call_analysis

    def without_cache(self):
        initialize(self)
        self.analysis_cache_enabled = False

    with patch.object(Compiler, 'init_call_analysis', without_cache):
        uncached = function_requirements(compile_program(code), 'f')
    assert all(r['conditional'] for r in cached['x'])
    assert any(not r['conditional'] for r in uncached['x'])
    findings['A4_requirement_cache'] = {'source': code, 'cached': cached, 'uncached': uncached}

    code = '[def:impossible]($x){$n=abs($x);return not $x}'
    plan = compile_program(code)
    assert not plan.issues
    import function_store
    from function_library import register, validate_changes
    saved = function_store._root_provider, function_store._validator, function_store._registrar
    with TemporaryDirectory() as directory:
        try:
            function_store.wire(lambda **_: Path(directory) / 'functions', validate_changes, None)
            with (patch('ibl_v2_adapters.load_registry', lambda *a, **k: {}),
                  patch('function_consumers.stored_programs', lambda: [])):
                ref = register('impossible', '#!ibl edition=2\n' + code, edition=2)
                registered = bool(ref.get('revision'))
        finally:
            function_store.wire(*saved)
    assert registered
    findings['A5_inconsistent_requirements'] = {
        'source': code, 'issues': plan.issues, 'registered': registered,
        'requirements': function_requirements(plan, 'impossible')}

    code = 'return $flag ? abs : 1'
    mixed = execute(code, inputs={'flag': False})
    control = execute('return 1')
    assert mixed['executed'] is False and mixed['diagnostic']['code'] == 'VALUE_PROTOCOL'
    assert control['value'] == 1
    findings['A6_mixed_wire_union'] = {
        'source': code, 'inputs': {'flag': False}, 'mixed': brief(mixed), 'number_control': brief(control)}

    code = 'return {good:[t:good]{},other:[t:partial]{}}'
    specs = [obligation('good', '$value.good==2', 't:good'),
             obligation('other', '$value.other==7', 't:partial', required=False)]
    scoped = execute(code, reg, completion=specs)
    independent = execute('return {good:[t:good]{}}', reg, completion=specs[:1])
    statuses = [o['status'] for o in scoped['completion']['obligations']]
    assert statuses == ['undetermined', 'undetermined']
    assert independent['completion']['status'] == 'satisfied'
    findings['A7_independent_completion_scope'] = {
        'source': code, 'completion': specs, 'combined': brief(scoped),
        'obligations': [{k: o[k] for k in ('id', 'required', 'status', 'reason', 'evidence_refs')}
                        for o in scoped['completion']['obligations']],
        'independent_control': brief(independent)}
    return {'audited_commit': '80f22c26ceec546c6cf5b019ef18f8ff27e03367',
            'meaning': 'Counterexamples observed; exit 0 does not mean repair acceptance.',
            'findings': findings}


if __name__ == '__main__':
    # Some imported legacy modules print initialization notices; keep JSON clean.
    with contextlib.redirect_stdout(io.StringIO()):
        results = audit()
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
