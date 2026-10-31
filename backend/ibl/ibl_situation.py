"""Read exact runtime evidence edges; vocabulary and business-value names are not interpreted."""
import time
import uuid

from execution_situation import current, emit, optional_observation
from runtime_utils import file_resource_identity
from ibl_v2_completion import selected_events


def _identity(runtime):
    if not hasattr(runtime, '_situation_id'):
        runtime._situation_id = runtime.journal.run_id if runtime.journal else uuid.uuid4().hex
    return runtime._situation_id


def _sources(events):
    from source_observation import device_identity
    device = device_identity()
    found = {}
    for event in events:
        if event.get('incomplete'):
            continue
        for row in event.get('source_snapshot', []):
            if len(row) > 3 and row[3]:
                subject = {'kind': 'file', 'device': device, 'address': file_resource_identity(row[0])}
                found[(subject['address'], row[3])] = {'subject': subject, 'revision': row[3]}
    return list(found.values())


@optional_observation
def observe_event(runtime, eid):
    if not current():
        return
    event = runtime.trace[eid - 1]
    ref = {'ibl_run': _identity(runtime), 'event_id': eid}
    if event['kind'] == 'tool_evidence':
        for source in _sources([event]):
            emit(source['subject'], 'version', {'stable': True, 'scope': 'runtime_read'},
                 source='file_io', subject_revision=source['revision'], source_ref=ref,
                 observed_at=time.time())
    elif event['kind'] == 'assertion':
        dependencies = _sources(selected_events(runtime.trace, event['parents']))
        emit({'kind': 'ibl_assertion', **ref}, 'validation',
             {'passed': event['passed'], 'coverage': 'declared_predicate',
              'predicate_hash': event['predicate_hash'], 'dependencies_known': bool(dependencies)},
             source='ibl_runtime', source_ref=ref, relation=dependencies)


@optional_observation
def observe_result(runtime, binding):
    if not current() or binding is None:
        return
    dependencies = _sources(selected_events(runtime.trace, binding.evidence))
    if dependencies:
        emit({'kind': 'ibl_result', 'run': _identity(runtime)}, 'derived_result',
             {'plan_hash': runtime.plan.fingerprint, 'dependencies_known': True},
             source='ibl_runtime', relation=dependencies,
             source_ref={'ibl_run': _identity(runtime), 'roots': sorted(binding.evidence)})
