"""Result evidence must survive every evaluated exit, not just normal values."""
import boot_paths  # noqa: F401
import pytest
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime, Budget


def execute(source, *, registry=None, **kwargs):
    registry = registry or {"test:read": Adapter(
        {"version": 1, "params": {"value": "Unknown"}, "result": "Unknown",
         "effects": ["read_external"]}, lambda rt, args: args["value"])}
    plan = compile_program(source, registry)
    assert not plan.issues, plan.report()
    return Runtime(plan, **kwargs).run()


@pytest.mark.parametrize("body,reads", [
    ('$rows=[test:read]{value:[]}\n$x=reduce($rows,0,($a,$r)=>$a+$r)', 1),
    ('$rows=[test:read]{value:[1,2]}\n$x=reduce($rows,0,($a,$r)=>0)', 1),
    ('''[def:f](){[repeat:2]{
        [if:$i==0]{[test:read]{value:"inspected"}}[else]{return "found"}
    }}\n$x=[fn:f]{}''', 1),
    ('''$x=[try]{[repeat:2]{
        [if:$i==0]{[test:read]{value:"inspected"}}[else]{1/0}
    }}[catch]{"failed"}''', 1),
    ('$flag=[test:read]{value:true}\n$x=[try]{[if:$flag]{1/0}}[catch]{0}', 1),
    ('$flag=[test:read]{value:1}\n$x=[try]{[case:$flag]{[when:1]{1/0}[else]{0}}}[catch]{0}', 1),
    ('$n=[test:read]{value:0}\n$x=[try]{1/$n}[catch]{0}', 1),
    ('$row=[test:read]{value:{}}\n$x=[try]{$row.missing}[catch]{0}', 1),
    ('$n=[test:read]{value:7}\n$x=[try]{[$n,1/0]}[catch]{0}', 1),
    ('''$x=[try]{[table:each]{items:[1,0],parallel:2}{
        $n=[test:read]{value:$it}\n10/$n
    }}[catch]{$error.partial}''', 2),
    ('''[def:f](){[try]{1/0}[finally]{[test:read]{value:"cleanup"}}}
    $x=[try]{[fn:f]{}}[catch]{0}''', 1),
    ('''$x=[try]{[try]{[test:read]{value:"body"}\n1/0}
    [finally]{[test:read]{value:"cleanup"}\n1/0}}[catch]{0}''', 2),
])
def test_composed_result_keeps_all_evaluated_sources(body, reads):
    result = execute(body + '\nreturn evidence($x)')
    assert result["success"], result
    events = result["value"]["events"]
    assert sum(e["kind"] == "invoke" for e in events) == reads
    ids = {e["id"] for e in events}
    assert all(set(e["parents"]) <= ids for e in events)
    assert all(p < e["id"] for e in events for p in e["parents"])


@pytest.mark.parametrize("workers", [1, 3])
def test_sibling_proofs_are_isolated_and_unselected_effects_do_not_appear(workers):
    result = execute(f'''[table:each]{{items:[1,2,3],parallel:{workers}}}{{
        $x=[test:read]{{value:$it}}
        [if:false]{{[test:read]{{value:"not called"}}}}
        return evidence($x)
    }}''')
    assert result["success"], result
    proofs = result["value"]
    invocation_ids = [{e["id"] for e in p["events"] if e["kind"] == "invoke"} for p in proofs]
    assert all(len(ids) == 1 for ids in invocation_ids)
    assert len(set.union(*invocation_ids)) == 3


def test_recovery_evidence_does_not_pull_unrelated_prior_statement():
    result = execute('''[test:read]{value:"unrelated"}
    $x=[try]{1/0}[catch]{7}
    return evidence($x)''')
    assert result["success"]
    assert not any(e["kind"] == "invoke" for e in result["value"]["events"])


@pytest.mark.parametrize("body", [
    '$flag=[test:read]{value:true}\n[if:$flag]{$x=1}[else]{$x=2}',
    '$flag=[test:read]{value:1}\n[case:$flag]{[when:1]{$x=1}[else]{$x=2}}',
    '$x=0\n$n=[test:read]{value:2}\n[repeat:$n]{$x=$i}',
    '$x=0\n[try]{[test:read]{value:1}\n1/0}[catch]{$x=7}',
    '$x=0\n$keep=true\n[repeat:while $keep]{$x=$x+1\n$keep=[test:read]{value:false}}',
    '''$flag=[test:read]{value:true}
    $x=[if:$flag]{[table:each]{items:[1,2],parallel:2}{return evidence($it)}}[else]{[]}''',
])
def test_control_dependencies_survive_assignment_and_worker_entry(body):
    result = execute(body + '\nreturn evidence($x)')
    assert result["success"], result
    assert sum(e["kind"] == "invoke" for e in result["value"]["events"]) == 1


def test_parallel_callback_observes_enclosing_control_before_it_returns():
    result = execute('''$flag=[test:read]{value:true}
    [if:$flag]{[table:each]{items:[1,2],parallel:2}{
        $x=7
        return evidence($x)
    }}[else]{[]}''')
    assert result["success"], result
    assert all(sum(e["kind"] == "invoke" for e in proof["events"]) == 1 for proof in result["value"])


def test_loop_evidence_edges_grow_linearly_and_remain_acyclic():
    sizes = []
    for count in (50, 100):
        result = execute(f'$sum=0\n[repeat:{count}]{{$sum=$sum+$i}}\nreturn $sum')
        assert result["success"] and result["value"] == count * (count - 1) // 2
        events = result["evidence"]
        assert all(p < e["id"] for e in events for p in e["parents"])
        sizes.append(sum(len(e["parents"]) for e in events))
    assert sizes[1] <= 2 * sizes[0]


def test_unexpected_adapter_exception_retains_invocation():
    def fail(rt, args):
        raise ValueError("fixture failure")
    registry = {"test:bad": Adapter(
        {"version": 1, "params": {}, "result": "Unknown", "effects": ["pure"]}, fail)}
    result = execute('$x=[try]{[test:bad]{}}[catch]{0}\nreturn evidence($x)', registry=registry)
    assert result["success"], result
    events = result["value"]["events"]
    assert any(e["kind"] == "invoke" for e in events)
    assert any(e["kind"] == "failure" and e["code"] == "VALUE" for e in events)


@pytest.mark.parametrize("kind", ["permission", "cancelled", "budget", "protocol"])
def test_noncatchable_failures_keep_original_kind_and_cleanup_evidence(kind):
    def fail(rt, args):
        raise Fault("DENIED", "fixture", kind=kind)
    registry = {
        "test:bad": Adapter({"version": 1, "params": {}, "result": "Unknown", "effects": ["pure"]}, fail),
        "test:clean": Adapter({"version": 1, "params": {}, "result": "Number", "effects": ["pure"]}, lambda rt, args: 1),
    }
    plan = compile_program('[try]{[test:bad]{}}[catch]{7}[finally]{[test:clean]{}}', registry)
    runtime = Runtime(plan, budget=Budget(steps=100))
    result = runtime.run()
    assert not result["success"] and result["diagnostic"]["kind"] == kind
    events = runtime.evidence(result["diagnostic"]["evidence"])["events"]
    assert {e.get("action") for e in events if e["kind"] == "invoke"} == {"test:bad", "test:clean"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
